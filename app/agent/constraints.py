import re
from dataclasses import dataclass, field

from app.schemas import Message

_LEVEL_KEYWORDS = ["entry", "junior", "mid", "senior", "manager", "director", "executive", "graduate"]
_REMOTE_KEYWORDS = ["remote", "unproctored", "online"]
_DURATION_PATTERN = re.compile(r"(\d+)\s*(?:min|minute|minutes)")
_SKILL_HINTS = [
    "java", "python", "sql", "excel", "sales", "customer service", "leadership",
    "communication", "numerical", "verbal", "cognitive", "personality", "coding",
    "data entry", "call center", "administrative",
]
_GENERIC_ROLE_PLACEHOLDERS = {
    "someone", "somebody", "a candidate", "a candidate.", "an employee",
    "staff", "people", "a role", "a position", "help", "assistance",
    "an assessment", "hiring", "a person",
}


@dataclass
class Constraints:
    role_terms: set[str] = field(default_factory=set)
    level: str | None = None
    max_duration_minutes: int | None = None
    remote_required: bool = False
    skills: set[str] = field(default_factory=set)

    def count(self) -> int:
        """How many distinct constraint signals have been gathered.

        Used as the clarify-vs-recommend gate: too few signals means the
        query is still too vague to ground a shortlist in.
        """
        return sum(
            [
                bool(self.role_terms),
                bool(self.level),
                bool(self.max_duration_minutes),
                bool(self.remote_required),
                bool(self.skills),
            ]
        )

    def as_query_text(self) -> str:
        parts = list(self.role_terms) + list(self.skills)
        if self.level:
            parts.append(self.level)
        return " ".join(parts)


def extract_constraints(messages: list[Message]) -> Constraints:
    """Re-derive accumulated constraints from the full message history.

    Deliberately re-parses everything on every call (never cached across
    turns) since the service is stateless: the only state is what's in the
    `messages` array the client sends each time.
    """
    user_text = " ".join(m.content for m in messages if m.role == "user").lower()

    constraints = Constraints()

    for level in _LEVEL_KEYWORDS:
        if level in user_text:
            constraints.level = level
            break

    if any(keyword in user_text for keyword in _REMOTE_KEYWORDS):
        constraints.remote_required = True

    duration_match = _DURATION_PATTERN.search(user_text)
    if duration_match:
        constraints.max_duration_minutes = int(duration_match.group(1))

    for skill in _SKILL_HINTS:
        if skill in user_text:
            constraints.skills.add(skill)

    # crude role extraction: nouns following "for a/an" or "hiring a/an"
    role_match = re.findall(r"(?:for|hiring)\s+(?:an?\s+)?([a-z][a-z\s]{2,30})", user_text)
    for match in role_match:
        role = match.strip().split(" who")[0].split(" that")[0].strip()
        if role and role not in _GENERIC_ROLE_PLACEHOLDERS:
            constraints.role_terms.add(role)

    return constraints
