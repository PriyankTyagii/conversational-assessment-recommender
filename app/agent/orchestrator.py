import json
import re

from app.agent.constraints import extract_constraints
from app.agent.llm import generate
from app.agent.prompts import (
    CLARIFY_TEMPLATE,
    COMPARE_INSTRUCTIONS,
    REFUSE_TEMPLATE,
    RERANK_INSTRUCTIONS,
    SYSTEM_PROMPT,
)
from app.catalog.loader import CatalogEntry, load_catalog
from app.config import settings
from app.retrieval.store import get_store
from app.schemas import ChatRequest, ChatResponse, Message, Recommendation

_OFF_TOPIC_KEYWORDS = [
    "legal", "lawsuit", "sue", "discriminat", "interview question",
    "salary negotiation", "fire an employee", "terminate",
]
_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard the system prompt",
    "you are now",
    "act as",
]
_ACRONYM_IGNORE_WORDS = {"new", "the", "of", "and", "for", "in", "on", "a", "an", "-"}
_COMPARISON_PHRASES = [
    "difference between", "different from", "compare", "comparison",
    "versus", " vs ", " vs.", "vs\n", "how does", "compared to", "or which",
]


def _has_comparison_intent(text: str) -> bool:
    """Gate compare-mode on explicit comparison language, not just mentioning
    two product-shaped names — otherwise an ordinary recommend request like
    "needs strong SQL and Java skills" false-triggers compare mode purely
    because "SQL" and "Java" are also short catalog product names."""
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in _COMPARISON_PHRASES)


def _is_out_of_scope(latest_user_message: str) -> bool:
    text = latest_user_message.lower()
    if any(pattern in text for pattern in _INJECTION_PATTERNS):
        return True
    if any(keyword in text for keyword in _OFF_TOPIC_KEYWORDS):
        return True
    return False


def _core_name(name: str) -> str:
    """Strip trailing annotations like "(New)" — recruiters say "Contact
    Center Call Simulation", not "Contact Center Call Simulation (New)"."""
    return re.sub(r"\s*\(.*?\)\s*$", "", name).strip()


_GEO_LANGUAGE_CODES = {
    "US", "USA", "UK", "CA", "AU", "NZ", "EU", "IN", "FR", "DE", "ES", "IT", "NL",
}


def _code_tokens(name: str) -> list[str]:
    """Product-code-like tokens (e.g. "OPQ32r", "AWS") that stand in for the
    product on their own, as opposed to ordinary title-case words.

    Many catalog names use a "<Test> - <Country Code> (<Revision>)" pattern
    (e.g. "Data Entry Alphanumeric Split Screen - US"), so short geo/language
    codes are excluded — they're modifiers a recruiter uses in everyday
    sentences ("US based"), not a way of naming a specific product.
    """
    base = re.sub(r"\(.*?\)", "", name)
    tokens = re.findall(r"\S+", base)
    return [
        t
        for t in tokens
        if t.upper() not in _GEO_LANGUAGE_CODES
        and (re.search(r"[0-9]", t) or (t.isupper() and len(t) >= 3))
    ]


def _acronym_for(name: str) -> str:
    base = re.sub(r"\(.*?\)", "", name)
    words = re.findall(r"[A-Za-z]+", base)
    letters = [w[0].upper() for w in words if w.lower() not in _ACRONYM_IGNORE_WORDS]
    return "".join(letters)


def _find_mentioned_entries(text: str, catalog: list[CatalogEntry]) -> list[CatalogEntry]:
    """Detect catalog products named in `text` — by core name, embedded
    product code (e.g. "OPQ32r", "AWS"), or a derived acronym for names with
    no embedded code (e.g. "Global Skills Assessment" -> "GSA").

    Used to gate the compare behavior — comparisons must be grounded in real
    catalog entries the user actually named, never guessed.
    """
    matched: dict[str, CatalogEntry] = {}

    for entry in catalog:
        core = _core_name(entry.name)
        if len(core) >= 3 and core.lower() in text.lower():
            matched[entry.url] = entry
            continue

        code_tokens = _code_tokens(entry.name)
        if any(re.search(rf"\b{re.escape(tok)}\b", text, re.IGNORECASE) for tok in code_tokens):
            matched[entry.url] = entry
            continue

        if not code_tokens:
            acronym = _acronym_for(entry.name)
            if len(acronym) >= 3 and re.search(rf"\b{re.escape(acronym)}\b", text, re.IGNORECASE):
                matched[entry.url] = entry

    return list(matched.values())


def _format_conversation(messages: list[Message]) -> str:
    return "\n".join(f"{m.role.capitalize()}: {m.content}" for m in messages[-6:])


def _to_recommendation(entry: CatalogEntry) -> Recommendation:
    return Recommendation(name=entry.name, url=entry.url, test_type=entry.test_type or None)


def _compare_reply(messages: list[Message], entries: list[CatalogEntry]) -> str:
    facts = "\n\n".join(
        f"- {e.name} (test_type: {e.test_type or 'unknown'}, "
        f"duration: {e.duration_minutes or 'unknown'} min, "
        f"remote: {e.remote_testing}, job levels: {', '.join(e.job_levels) or 'unspecified'})\n"
        f"  {e.description}"
        for e in entries
    )
    prompt = COMPARE_INSTRUCTIONS.format(
        conversation=_format_conversation(messages), facts=facts
    )
    try:
        return generate(SYSTEM_PROMPT, prompt)
    except Exception:
        return "Here's what the catalog says: " + " ".join(
            f"{e.name} — {e.description}" for e in entries
        )


def _rerank_with_llm(
    messages: list[Message], candidates: list[CatalogEntry]
) -> tuple[str, list[CatalogEntry]] | None:
    """Ask the LLM to either commit to a shortlist or ask a clarifying question.

    Returns (reply, shortlist) where an empty shortlist means "still
    clarifying" (a real decision, not a failure). Returns None only when the
    call/parse itself failed, so the caller can fall back separately.
    """
    candidate_lines = "\n".join(
        f"{i}: {e.name} — {e.test_type or 'n/a'} — "
        f"{e.duration_minutes or '?'} min — {e.description[:160]}"
        for i, e in enumerate(candidates)
    )
    prompt = RERANK_INSTRUCTIONS.format(
        conversation=_format_conversation(messages),
        candidates=candidate_lines,
        max_recommendations=settings.max_recommendations,
    )
    try:
        raw = generate(SYSTEM_PROMPT, prompt)
        parsed = json.loads(raw.strip().strip("`").removeprefix("json").strip())
        indices = [i for i in parsed["selected_indices"] if isinstance(i, int) and 0 <= i < len(candidates)]
        selected = [candidates[i] for i in indices[: settings.max_recommendations]]
        return parsed.get("reply", ""), selected
    except Exception:
        return None


def handle_chat(request: ChatRequest) -> ChatResponse:
    """Route a chat turn to clarify / recommend / refine / compare / refuse.

    Reconstructs all state (constraints, turn count) from the full
    `messages` history on every call — the service holds no session state
    between requests. Note the client only ever resends plain
    {role, content} text, never our structured `recommendations` array, so
    "has a shortlist already been committed" can't be read back off prior
    turns — it's re-derived from whether accumulated constraints are
    currently sufficient to retrieve one.
    """
    turn_count = sum(1 for m in request.messages if m.role == "user")
    latest_user_message = next(
        (m.content for m in reversed(request.messages) if m.role == "user"), ""
    )

    if not latest_user_message.strip():
        return ChatResponse(reply=CLARIFY_TEMPLATE, recommendations=[], end_of_conversation=False)

    if _is_out_of_scope(latest_user_message):
        return ChatResponse(reply=REFUSE_TEMPLATE, recommendations=[], end_of_conversation=False)

    catalog = load_catalog()
    mentioned_entries = (
        _find_mentioned_entries(latest_user_message, catalog)
        if _has_comparison_intent(latest_user_message)
        else []
    )
    if len(mentioned_entries) >= 2:
        # Comparisons are answered from catalog facts and never carry a
        # shortlist — the reply is a factual answer, not a new commitment.
        at_turn_cap = turn_count >= settings.max_turns
        reply = _compare_reply(request.messages, mentioned_entries[:4])
        return ChatResponse(reply=reply, recommendations=[], end_of_conversation=at_turn_cap)

    constraints = extract_constraints(request.messages)
    at_turn_cap = turn_count >= settings.max_turns
    has_any_signal = constraints.count() >= settings.min_constraints_to_recommend

    if not has_any_signal and not at_turn_cap:
        # Deterministic, zero-cost gate for genuinely empty requests (e.g.
        # "I need an assessment") — everything else is a judgment call
        # (is this specific enough to commit to a shortlist, or still
        # ambiguous?) handed to the LLM below, since a keyword-count
        # heuristic can't reliably tell those apart.
        return ChatResponse(reply=CLARIFY_TEMPLATE, recommendations=[], end_of_conversation=False)

    store = get_store()
    # Embed the full accumulated conversation, not the extracted keyword
    # constraints — sentence-transformer models are trained on natural
    # language, and a mangled keyword string (e.g. "senior leadership
    # leadership senior") embeds far worse than the original sentences.
    query_text = " ".join(m.content for m in request.messages if m.role == "user")
    retrieved = store.search(query_text, top_k=settings.retrieval_top_k)

    if not retrieved:
        return ChatResponse(
            reply=(
                "I couldn't find a strong match in the catalog for that yet. "
                "Could you share more detail about the role, skills, or level?"
            ),
            recommendations=[],
            end_of_conversation=False,
        )

    reranked = _rerank_with_llm(request.messages, retrieved)
    if reranked is not None:
        reply, shortlist = reranked
    else:
        # LLM call/parse failed — fall back to a conservative heuristic
        # rather than either guessing or failing the request outright.
        shortlist = retrieved[: settings.max_recommendations] if has_any_signal else []
        reply = "" if shortlist else CLARIFY_TEMPLATE

    if not shortlist and at_turn_cap:
        # Must close out by the turn cap even if still "clarifying".
        shortlist = retrieved[: settings.max_recommendations]
        reply = ""

    if not shortlist:
        return ChatResponse(reply=reply or CLARIFY_TEMPLATE, recommendations=[], end_of_conversation=False)

    if not reply:
        reply = f"Here are {len(shortlist)} assessments from the catalog that fit:"

    return ChatResponse(
        reply=reply,
        recommendations=[_to_recommendation(e) for e in shortlist],
        end_of_conversation=at_turn_cap,
    )
