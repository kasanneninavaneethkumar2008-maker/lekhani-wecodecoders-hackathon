"""Rule sets: the demo rule set and two isolated fictional lab rule sets.

The demo/approved rules live in SQLite (seeded from `seed.py`). The two lab
rule sets below are small, fictional fixtures used only inside the Trust Lab
and the Rule Change Simulator. They are never written to the database and can
never become approved organisational rules.
"""
from .checker import RULE_SET_ID, RULE_SET_VERSION, Rule, load_rules

LAB_RULE_SET_ID = "lekhani-lab-example"
LAB_V1 = "example-guideline-v1"
LAB_V2 = "example-guideline-v2"

# --- The bundled sample draft ("Test a sample") -----------------------------
# A separate, clearly fictional rule set. It is never written to the database
# and is only active while a guest has explicitly loaded the sample. Its
# version is `demo-v1`, distinct from the workspace guideline version, so a
# snapshot taken under one set can never be read as a check of the other.
SAMPLE_RULE_SET_ID = "lekhani-greenleaf-sample"
SAMPLE_RULE_SET_VERSION = "demo-v1"
SAMPLE_RULE_SET_LABEL = "Fictional demo guidelines"
SAMPLE_BRAND = "GreenLeaf"
SAMPLE_LANGUAGE = "English"
# The workspace content type this sample maps to. The sample rules apply only
# to this type, so changing the content type makes them inapplicable rather
# than silently carrying the demo findings over.
SAMPLE_CONTENT_TYPE = "product promotion"
SAMPLE_TITLE = "GreenLeaf — fictional sample draft"
SAMPLE_AUDIENCE = "Prospective customers (fictional)"
SAMPLE_TEXT = (
    "Green Leaf gives users the best planning experience, with guaranteed results."
)
SAMPLE_REVISED_TEXT = (
    "GreenLeaf helps customers organise their daily plans. "
    "Explore plans on our website."
)


def demo_rules(db):
    """The active, versioned demo rule set (the workspace's own rules)."""
    return load_rules(db)


def _lab_rule(rule_id, kind, pattern, replacement, message, clause_text, version):
    return Rule(
        rule_id=rule_id,
        kind=kind,
        pattern=pattern,
        replacement=replacement,
        applies_to="any",
        message=message,
        clause_text=clause_text,
        active=True,
        rule_set_id=LAB_RULE_SET_ID,
        rule_set_version=version,
    )


def _sample_rule(rule_id, kind, pattern, replacement, message, clause_text):
    return Rule(
        rule_id=rule_id,
        kind=kind,
        pattern=pattern,
        replacement=replacement,
        applies_to=SAMPLE_CONTENT_TYPE,
        message=message,
        clause_text=clause_text,
        active=True,
        rule_set_id=SAMPLE_RULE_SET_ID,
        rule_set_version=SAMPLE_RULE_SET_VERSION,
    )


def sample_rules():
    """The five fictional GreenLeaf demo rules ("Fictional demo guidelines").

    They are scoped to the workspace's *product promotion* content type and
    are only used after a guest explicitly loads the sample. They must not be
    confused with the workspace's own guideline library.
    """
    return [
        _sample_rule(
            "GLOSS-01", "glossary", "Green Leaf", "GreenLeaf",
            'Incorrect brand spelling. Write the brand name as “GreenLeaf”, not '
            '“Green Leaf”.',
            "Write the brand name as GreenLeaf, not Green Leaf.",
        ),
        _sample_rule(
            "GLOSS-02", "glossary", "users", "customers",
            'Non-preferred term. Use “customers” instead of “users” in '
            'customer-facing promotional copy.',
            "Use customers instead of users in customer-facing promotional copy.",
        ),
        # The required pattern keeps its terminal full stop, so the exact
        # required sentence (including punctuation) must appear.
        _sample_rule(
            "MSG-01", "required", "Explore plans on our website.", None,
            'Product promotions must include the exact sentence: “Explore plans '
            'on our website.”',
            "Product promotions must include the exact sentence: Explore plans on our website.",
        ),
        _sample_rule(
            "CLAIM-01", "claim", r"\bbest\b", None,
            "Possible claim: “best”. This flags wording for human evidence "
            "review; it does not determine whether the claim is true.",
            "Flag best for human evidence review; do not determine whether the "
            "claim is true.",
        ),
        _sample_rule(
            "CLAIM-02", "claim", r"\bguaranteed\b", None,
            "Possible claim: “guaranteed”. This flags wording for human evidence "
            "review; it does not determine whether the claim is true.",
            "Flag guaranteed for human evidence review; do not determine whether "
            "the claim is true.",
        ),
    ]


def lab_rules_v1():
    """Fictional guideline v1, used only by the Trust Lab and simulator."""
    return [
        _lab_rule(
            "LAB-GLS-001", "glossary", "disrupt", "change",
            'Lab glossary term "disrupt" should be replaced.',
            'Lab glossary LAB-GLS-001: Write "change" rather than "disrupt".',
            LAB_V1,
        ),
        _lab_rule(
            "LAB-MSG-101", "forbidden", "guaranteed results", None,
            'The lab rule forbids the phrase "guaranteed results".',
            'Lab forbidden message LAB-MSG-101: Never use "guaranteed results".',
            LAB_V1,
        ),
        _lab_rule(
            "LAB-CLM-001", "claim", r"\b(best|top[- ]rated)\b", None,
            "Possible superlative or ranking claim; prompt human review.",
            "Lab claim prompt LAB-CLM-001: Superlatives and rankings need human review.",
            LAB_V1,
        ),
        _lab_rule(
            "LAB-MSG-201", "required", "pricing may change", None,
            "Lab guideline v1 requires the pricing-stability phrase.",
            "Lab required message LAB-MSG-201: Say that pricing may change.",
            LAB_V1,
        ),
    ]


def lab_rules_v2():
    """Fictional guideline v2: one clause reworded, one rule added, one
    forbidden phrase replaced, one required rule removed."""
    return [
        _lab_rule(
            "LAB-GLS-001", "glossary", "disrupt", "change",
            'Lab glossary term "disrupt" should be replaced.',
            'Lab glossary LAB-GLS-001: Prefer "change" over "disrupt" in customer copy.',
            LAB_V2,
        ),
        _lab_rule(
            "LAB-GLS-002", "glossary", "synergy", "collaboration",
            'Lab glossary term "synergy" should be replaced.',
            'Lab glossary LAB-GLS-002: Prefer "collaboration" over "synergy".',
            LAB_V2,
        ),
        _lab_rule(
            "LAB-MSG-101", "forbidden", "risk-free", None,
            'The lab rule forbids the phrase "risk-free".',
            'Lab forbidden message LAB-MSG-101: Never use "risk-free".',
            LAB_V2,
        ),
        _lab_rule(
            "LAB-CLM-001", "claim", r"\b(best|top[- ]rated)\b", None,
            "Possible superlative or ranking claim; prompt human review.",
            "Lab claim prompt LAB-CLM-001: Superlatives and rankings need human review.",
            LAB_V2,
        ),
    ]


__all__ = [
    "RULE_SET_ID",
    "RULE_SET_VERSION",
    "LAB_RULE_SET_ID",
    "LAB_V1",
    "LAB_V2",
    "SAMPLE_RULE_SET_ID",
    "SAMPLE_RULE_SET_VERSION",
    "SAMPLE_RULE_SET_LABEL",
    "SAMPLE_BRAND",
    "SAMPLE_LANGUAGE",
    "SAMPLE_CONTENT_TYPE",
    "SAMPLE_TITLE",
    "SAMPLE_AUDIENCE",
    "SAMPLE_TEXT",
    "SAMPLE_REVISED_TEXT",
    "demo_rules",
    "sample_rules",
    "lab_rules_v1",
    "lab_rules_v2",
]
