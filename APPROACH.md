# Approach — Conversational SHL Assessment Recommender

## Architecture

`GET /health` and `POST /chat` are served by FastAPI. The service is stateless: every
`/chat` call re-derives everything (accumulated constraints, turn count, whether a
shortlist is warranted) from the full `messages` array — nothing is cached across
requests except the catalog and its embeddings, which are built once at process
startup (not lazily on the first request, since a cold embedding build takes
~50s — well over the 30s per-call budget).

Retrieval and generation are deliberately separated: the LLM never writes a URL.
It only selects indices from a numbered list of candidates that retrieval pulled
from the real, scraped catalog. This is the single load-bearing design decision
for the "no hallucinated URLs" hard requirement — every recommendation is
constructed by the orchestrator from a `CatalogEntry` object, never from LLM
free text.

## Catalog

SHL's own assignment PDF links directly to a JSON export of the catalog
(`shl_product_catalog.json`, 377 entries) rather than requiring a scrape of the
rendered listing page. `app/scraper/scrape_catalog.py` fetches and transforms it:
`test_type` letter codes (A/B/C/D/E/K/P/S) are derived from the catalog's own
`keys` category tags via SHL's public legend, duration strings are parsed to
minutes, and entries are deduped by canonical URL. All 377 entries are already
Individual Test Solutions (no Job Solution bundles present in the export), so no
additional filtering was needed — verified by checking for zero
`job-solution`-style URLs in the data.

## Retrieval

Embeddings (`sentence-transformers/all-MiniLM-L6-v2`) are built once over each
entry's name, description, category tags, and job levels. At query time, the
**full accumulated conversation** (all user turns concatenated) is embedded and
compared via cosine similarity — not a hand-extracted keyword string. A
keyword-based fallback (token overlap) exists so the service stays bootable if
the embedding stack isn't installed.

Retrieval over-fetches (top-30) and hands the candidates to the LLM, which either
selects 1–10 of them or returns an empty selection with a clarifying question.
The LLM is never allowed to select outside the given indices, so ranking quality
is bounded by retrieval recall, but hallucination is bounded at zero by construction.

## Agent design

A cheap, deterministic heuristic (`app/agent/constraints.py`) only handles the
truly degenerate case — a message with no role/skill/level/duration/remote
signal at all — and clarifies without an LLM call. Every other decision (is this
specific enough to recommend, or still ambiguous enough to ask a follow-up?) is
delegated to a single LLM call per turn that returns either a clarifying question
or a ranked shortlist, alongside the retrieved candidates. This single call also
serves refinement: since the client only ever resends plain `{role, content}`
text (never a structured recommendations array), "refine" isn't a separate code
path — every turn re-runs the same retrieve → decide pipeline over the full
history, so new constraints naturally extend rather than reset the shortlist.

Compare queries are detected by matching catalog product names/codes mentioned
in the latest message (core name, embedded product codes like "OPQ32r"/"AWS", or
initials for names without one, e.g. "GSA"). A matched pair routes to a
comparison prompt grounded strictly in those two catalog records' fields — never
the model's prior knowledge. Scope refusal (legal advice, general hiring
questions, prompt injection) is a keyword-based pre-filter that runs before any
LLM call, so it can't be talked around by injected instructions.

## Evaluation

- **Automated tests (12, all passing):** schema compliance on every response
  type, empty/malformed history, catalog-only URL grounding, off-topic and
  prompt-injection refusal, refinement not resetting the shortlist, comparison
  answers grounded in named catalog products, 8-turn cap enforcement, and a
  regression test for the SQL/Java false-positive described below.
- **10 provided sample-conversation traces**, parsed from SHL's markdown format
  into turns with expected final-shortlist URLs. A regression runner
  (`scripts/run_traces.py`) replays the real user utterances turn-by-turn against
  the live server and computes Recall@10 on each trace's *final* recommendation
  set. **Result: mean Recall@10 = 0.26**, using Groq's `llama-3.3-70b-versatile`.
- **Load test** (`scripts/load_test.py`): an 8-turn conversation correctly forces
  closure (`end_of_conversation: true`, non-empty shortlist) at the cap, and a
  10-turn conversation past the cap doesn't error. Max latency observed across
  both the trace suite and load test: **11.8s**, comfortably under the 30s limit.

## What didn't work, and what I changed

| Problem found | Fix |
|---|---|
| Query text built from regex-extracted keywords (e.g. `"senior leadership leadership senior"`) embedded far worse than natural language, since the model is trained on sentences, not keyword soup. | Embed the full conversation text directly instead of extracted constraints. |
| A hard-coded "≥2 constraint categories" gate for clarify-vs-recommend was both too strict (rejected clearly specific requests like a detailed safety-role description) and too loose (let filler phrases like "for an engineer" through as false signal). | Replaced with a single LLM decision per turn, given the retrieved candidates and full context; kept only a zero-signal deterministic fallback for genuinely empty requests. |
| Compare-detection false-positives: product names like "ADO.NET" or "Data Entry ... - US" generated 2-letter acronyms/codes ("AN", "US") that matched ordinary words in unrelated sentences ("for **an** inbound call center, ... **US** based"), routing normal recommendation requests into the compare path. | Excluded common geo/language codes (US, UK, etc.) from code-token matching and raised the minimum acronym length to 3. |
| Dense retrieval systematically under-ranks SHL's generic flagship instruments — OPQ32r and SHL Verify Interactive G+ — which the gold traces add by convention for most roles. Their descriptions are behaviorally generic, so they don't embed close to domain-specific JD text (observed rank ~80–220 out of 377 for typical queries). Raising top-k and enriching embedding text with category/job-level tags helped modestly but didn't resolve it. | Documented as an open limitation rather than hard-coding specific product names into the retrieval logic, which would be overfitting to the 10 sample traces rather than a generalizable fix. A production version would want a hybrid signal (e.g. a learned re-ranker or popularity prior) on top of pure embedding similarity. |
| Groq's free tier has a 100K-token daily cap, which iterative development exhausted mid-session; free OpenRouter models are an available fallback but have variable, occasionally slow (~25s) shared-tier latency. | Built a provider-agnostic `generate()` with Groq primary and Gemini/OpenRouter fallback (one-line config swap), and lowered the internal LLM timeout to 18s to leave headroom under the 30s cap regardless of provider. For actual deployment, Groq is preferred for its low, consistent latency. |
| Compare-detection false-positive, round two, found during final verification: short catalog product names that are also common skill keywords ("SQL", "Java") caused ordinary recommend requests ("strong SQL and Java skills") to match 2+ "products" and misfire into compare mode with an empty shortlist. | Gated compare mode on explicit comparison language ("difference between", "compare", "versus", etc.) in addition to matching 2+ named products — matches how every compare example in the sample traces is actually phrased, and stops the false trigger without weakening real compare detection. |

## Stack

FastAPI + pydantic (schema enforcement on every response path, including
refusals), `sentence-transformers` for embeddings, Groq (`llama-3.3-70b-versatile`)
as the primary LLM with OpenRouter/Gemini as swappable fallbacks, all free-tier.
No vector database — a 377-row in-memory matrix multiply is fast enough that
FAISS/Chroma would be unjustified overhead at this catalog size.

## AI tool usage

This project was built with **Claude Code** (Anthropic's agentic CLI) as a
pair-programming tool throughout: scaffolding the FastAPI service and schemas,
implementing the retrieval/orchestrator/prompt logic, debugging the issues in
the table above by writing and running diagnostic scripts against the real
catalog and sample traces, and iterating on prompt wording based on observed
failures. All design decisions, trade-offs, and the debugging process described
here reflect actual back-and-forth iteration against real data, not a single
generated pass.
