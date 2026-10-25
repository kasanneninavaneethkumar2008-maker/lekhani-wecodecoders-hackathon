"""Deterministic checks, rule coverage, and citation validation.

The checker never judges truth or legality. `claim` issues are prompts that
ask a human to review wording; they are not verdicts.

Every issue produced by the pipeline carries:
  * `rule_id`  -- the stable ID of an approved rule, and
  * `quote`    -- the exact text of that rule's approved clause.

`validate_citations` re-checks both against the rule table and silently
discards any issue whose ID is missing from the table or whose quote differs
from the stored clause text.
"""
import re
from dataclasses import dataclass

RULE_KINDS = ("glossary", "required", "forbidden", "claim")
RULE_SET_ID = "lekhani-fictional-demo"
RULE_SET_VERSION = "demo-rules-v1"
MAX_DRAFT_LENGTH = 100_000


@dataclass(frozen=True)
class Rule:
    rule_id: str
    kind: str
    pattern: str
    replacement: str | None
    applies_to: str
    message: str
    clause_text: str
    active: bool = True
    rule_set_id: str = RULE_SET_ID
    rule_set_version: str = RULE_SET_VERSION


@dataclass(frozen=True)
class Issue:
    """A single finding, ready to display only after citation validation."""

    rule_id: str
    kind: str
    message: str
    quote: str  # exact stored clause text for rule_id
    excerpt: str | None  # the matched draft text (None when nothing matched)
    is_prompt: bool  # True for 'claim' issues: human review requested
    start_offset: int | None = None
    end_offset: int | None = None
    rule_set_id: str | None = None
    rule_set_version: str | None = None
    title: str = ""  # short, human-readable label for a findings card
    # Every validated match for this rule, as (start, end) offsets into the
    # original draft text. Empty for required-phrase findings, which have no
    # offending span. The first pair equals start_offset/end_offset.
    occurrences: tuple[tuple[int, int], ...] = ()

    @property
    def is_claim(self) -> bool:
        return self.kind == "claim"

    @property
    def category(self) -> str:
        """The rule category that produced this finding."""
        return self.kind


@dataclass(frozen=True)
class ValidationResult:
    kept: tuple[Issue, ...]
    discarded: tuple[Issue, ...]
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class CheckRun:
    issues: tuple[Issue, ...]
    rejected: tuple[Issue, ...]
    rejection_reasons: tuple[str, ...]
    coverage: dict
    rule_set_id: str
    rule_set_version: str
    complete: bool
    warnings: tuple[str, ...] = ()


def literal_pattern(pattern: str) -> str:
    """Regex source for a literal rule phrase.

    Bundled glossary and messaging rules are matched as literal text:
      * case-insensitive,
      * whole-word bounded, so "no risk" never matches inside "piano risky",
      * with any run of whitespace between words, so a phrase still matches
        across a line break or double space.

    Matching runs against the *original* text (no normalised copy), so the
    offsets on an issue always point at the reader's exact draft.
    """
    words = [part for part in re.split(r"\s+", pattern.strip()) if part]
    if not words:
        return r"(?!)"
    source = r"\s+".join(re.escape(word) for word in words)
    # Only add a word boundary where the phrase actually starts/ends with a
    # word character, so a required sentence that ends in a full stop can be
    # matched (and required) exactly, including that punctuation.
    first, last = words[0][0], words[-1][-1]
    if first.isalnum() or first == "_":
        source = r"\b" + source
    if last.isalnum() or last == "_":
        source += r"\b"
    return source


def _pattern_source(rule: Rule) -> str:
    """Regex source for matching a rule against draft text."""
    if rule.kind == "claim":
        # Claim patterns are stored as regex sources.
        return rule.pattern
    # Glossary terms and required/forbidden phrases are literal text.
    return literal_pattern(rule.pattern)


def rule_applies(rule: Rule, content_type: str) -> bool:
    """Whether a rule is scoped to this content type.

    ``applies_to`` is a comma-separated list of content types (or "any").
    The workspace and the older creator form use different names for the
    same ideas (for example "website copy" and "product page"), so a rule
    may list both while staying explicitly scoped.
    """
    scopes = [part.strip().casefold() for part in rule.applies_to.split(",")]
    if "any" in scopes or "" in scopes:
        return True
    return content_type.casefold() in scopes


def _scope_applies(rule: Rule, content_type: str) -> bool:
    return rule_applies(rule, content_type)


def find_matches(text: str, rule: Rule) -> list[re.Match]:
    """Every match for a rule in the original text, in document order."""
    try:
        regex = re.compile(_pattern_source(rule), re.IGNORECASE)
    except re.error:
        # A malformed stored pattern yields no matches rather than crashing.
        return []
    return list(regex.finditer(text))


def _matches(text: str, rule: Rule) -> list[re.Match]:
    return find_matches(text, rule)


def _excerpt(text: str, match: re.Match, width: int = 40) -> str:
    start = max(0, match.start() - width)
    end = min(len(text), match.end() + width)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


def check_text(text: str, content_type: str, rules) -> list[Issue]:
    """Run all deterministic checks and return citation-validated issues.

    Issues are produced from the rule table and then validated against it;
    anything whose ID is missing or whose quote does not match the stored
    clause exactly is discarded before returning.
    """
    issues = run_checks(text, content_type, rules)
    return validate_citations(issues, rules).kept


def check_review(text: str, content_type: str, rules) -> CheckRun:
    """Run the single shared pipeline and return findings plus honest coverage."""
    text = text or ""
    active_rules = [r for r in rules if r.active and r.kind in RULE_KINDS]
    applicable = [r for r in active_rules if _scope_applies(r, content_type)]
    coverage = {
        "terminology": [r.rule_id for r in applicable if r.kind == "glossary"],
        "messaging": [r.rule_id for r in applicable if r.kind in ("required", "forbidden")],
        "claim_patterns": [r.rule_id for r in applicable if r.kind == "claim"],
    }
    # The active rule set is identified by every loaded rule, not only the
    # rules that apply to this content type. Otherwise a check with no
    # applicable rules would falsely cite the default rule-set version.
    versions = {(r.rule_set_id, r.rule_set_version) for r in active_rules}
    if not versions:
        versions = {(RULE_SET_ID, RULE_SET_VERSION)}
    # A mixed rule set is incomplete: never cite it as a coherent version.
    if len(versions) != 1:
        return CheckRun((), (), (), coverage, "mixed", "unknown", False,
                        ("The active rules contain more than one rule-set version.",))
    rule_set_id, rule_set_version = next(iter(versions))
    warnings = []
    if len(text) > MAX_DRAFT_LENGTH:
        return CheckRun((), (), (), coverage, rule_set_id, rule_set_version,
                        False, (f"Drafts are limited to {MAX_DRAFT_LENGTH:,} characters.",))
    for rule in applicable:
        if rule.kind == "claim":
            try:
                re.compile(rule.pattern, re.IGNORECASE)
            except re.error:
                warnings.append(f"Rule {rule.rule_id} has an invalid claim pattern.")
    if warnings:
        return CheckRun((), (), (), coverage, rule_set_id, rule_set_version,
                        False, tuple(warnings))
    candidates = run_checks(text, content_type, applicable)
    validation = validate_citations(candidates, applicable,
                                    rule_set_id=rule_set_id,
                                    rule_set_version=rule_set_version)
    complete = not validation.discarded
    if validation.discarded:
        warnings.append("One or more candidate findings failed citation validation.")
    return CheckRun(validation.kept, validation.discarded,
                    validation.rejection_reasons, coverage,
                    rule_set_id, rule_set_version, complete, tuple(warnings))


def run_checks(text: str, content_type: str, rules) -> list[Issue]:
    """Produce candidate issues (before citation validation).

    Deterministic: the same text, content type, and rules always produce the
    same issues in the same order.
    """
    issues: list[Issue] = []
    if not text:
        text = ""
    for rule in rules:
        if not rule.active or rule.kind not in RULE_KINDS:
            continue
        if not _scope_applies(rule, content_type):
            continue

        if rule.kind == "required":
            if not _matches(text, rule):
                issues.append(
                    Issue(
                        rule_id=rule.rule_id,
                        kind=rule.kind,
                        message=rule.message,
                        quote=rule.clause_text,
                        excerpt=None,
                        is_prompt=False,
                        rule_set_id=rule.rule_set_id,
                        rule_set_version=rule.rule_set_version,
                        title=f'Required phrase not found: “{rule.pattern}”',
                    )
                )
            continue

        matches = _matches(text, rule)
        if not matches:
            continue

        message = rule.message
        if rule.kind == "glossary" and rule.replacement:
            message = f"{rule.message} Suggested replacement: {rule.replacement}."

        matched_text = text[matches[0].start():matches[0].end()]
        if rule.kind == "glossary":
            title = f'Term to revise: “{matched_text}”'
            if rule.replacement:
                title += f' → “{rule.replacement}”'
        elif rule.kind == "forbidden":
            title = f'Forbidden phrase: “{matched_text}”'
        else:
            title = f'Possible claim: “{matched_text}”'

        issues.append(
            Issue(
                rule_id=rule.rule_id,
                kind=rule.kind,
                message=message,
                quote=rule.clause_text,
                excerpt=_excerpt(text, matches[0]),
                is_prompt=(rule.kind == "claim"),
                start_offset=matches[0].start(),
                end_offset=matches[0].end(),
                rule_set_id=rule.rule_set_id,
                rule_set_version=rule.rule_set_version,
                title=title,
                occurrences=tuple((m.start(), m.end()) for m in matches),
            )
        )
    return issues


def validate_citations(issues, rules, rule_set_id=None,
                       rule_set_version=None) -> ValidationResult:
    """Validate each issue's citation against the rule table.

    An issue is kept only if its rule_id exists in `rules` AND its quote is
    character-for-character identical to that rule's stored clause text.
    Everything else is discarded.
    """
    by_id = {rule.rule_id: rule for rule in rules}
    kept: list[Issue] = []
    discarded: list[Issue] = []
    reasons: list[str] = []
    for issue in issues:
        rule = by_id.get(issue.rule_id)
        if rule is None:
            discarded.append(issue)
            reasons.append("Unknown rule identifier.")
        elif issue.quote != rule.clause_text:
            discarded.append(issue)
            reasons.append("Quoted clause does not exactly match the stored rule.")
        elif (issue.rule_set_id is not None and issue.rule_set_id != rule.rule_set_id
              or issue.rule_set_version is not None
              and issue.rule_set_version != rule.rule_set_version
              or rule_set_id is not None and rule_set_id != rule.rule_set_id
              or rule_set_version is not None
              and rule_set_version != rule.rule_set_version):
            discarded.append(issue)
            reasons.append("Rule-set identifier or version does not match.")
        else:
            kept.append(issue)
    return ValidationResult(kept=tuple(kept), discarded=tuple(discarded),
                            rejection_reasons=tuple(reasons))


def load_rules(db) -> list[Rule]:
    """Load the active rule table as versioned `Rule` objects, by rule_id."""
    from .rulesets import RULE_SET_ID, RULE_SET_VERSION

    rows = db.execute(
        """SELECT rule_id, kind, pattern, replacement, applies_to,
                  message, clause_text, active
           FROM rules WHERE active = 1 ORDER BY rule_id"""
    ).fetchall()
    return [
        Rule(
            rule_id=row["rule_id"],
            kind=row["kind"],
            pattern=row["pattern"],
            replacement=row["replacement"],
            applies_to=row["applies_to"],
            message=row["message"],
            clause_text=row["clause_text"],
            active=bool(row["active"]),
            rule_set_id=RULE_SET_ID,
            rule_set_version=RULE_SET_VERSION,
        )
        for row in rows
    ]


def validate_issue_against_db(issue: Issue, db) -> bool:
    """Validate a single issue directly against the database rule table."""
    row = db.execute(
        "SELECT rule_id, clause_text FROM rules WHERE rule_id = ?",
        (issue.rule_id,),
    ).fetchone()
    return row is not None and issue.quote == row["clause_text"]
