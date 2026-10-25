"""Fictional sample data: the approved sample rules (and nothing else).

No users and no drafts are seeded. The demo role choice creates its demo
account on first use, and every draft in the database is one that a person
actually created in the app — there is no pre-loaded sample content.

The rules are fictional and exist only for demonstration and testing.
Seeding is idempotent (keyed by rule_id).
"""

# Stable rule IDs. Issues may only cite these IDs and must quote `clause_text` exactly.
SAMPLE_RULES = [
    # --- Glossary terminology -------------------------------------------------
    dict(
        rule_id="GLS-001",
        kind="glossary",
        pattern="disrupt",
        replacement="change",
        applies_to="any",
        message='Glossary term "disrupt" is not approved for customer-facing copy.',
        clause_text='Glossary entry GLS-001: Write "change" rather than "disrupt" in customer-facing copy.',
    ),
    dict(
        rule_id="GLS-002",
        kind="glossary",
        pattern="synergy",
        replacement="collaboration",
        applies_to="any",
        message='Glossary term "synergy" is not approved for customer-facing copy.',
        clause_text='Glossary entry GLS-002: Write "collaboration" rather than "synergy" in customer-facing copy.',
    ),
    dict(
        rule_id="GLS-003",
        kind="glossary",
        pattern="revolutionize",
        replacement="improve",
        applies_to="any",
        message='Glossary term "revolutionize" is not approved for customer-facing copy.',
        clause_text='Glossary entry GLS-003: Write "improve" rather than "revolutionize" in customer-facing copy.',
    ),
    # --- Required messaging ---------------------------------------------------
    dict(
        rule_id="MSG-001",
        kind="required",
        pattern="pricing may change",
        replacement=None,
        applies_to="website copy,product page",
        message="Website copy must include the pricing-stability sentence.",
        clause_text="Required message MSG-001: Website copy and product pages must state that pricing may change before purchase.",
    ),
    dict(
        rule_id="MSG-002",
        kind="required",
        pattern="you can cancel",
        replacement=None,
        applies_to="website copy,product page",
        message="Website copy must mention that the reader can cancel.",
        clause_text="Required message MSG-002: Website copy and product pages must tell the reader they can cancel at any time.",
    ),
    dict(
        rule_id="MSG-003",
        kind="required",
        pattern="free trial",
        replacement=None,
        applies_to="marketing email,email",
        message="Marketing emails about the trial must name the free trial explicitly.",
        clause_text='Required message MSG-003: Marketing emails offering a trial must use the exact phrase "free trial".',
    ),
    # --- Forbidden messaging --------------------------------------------------
    dict(
        rule_id="MSG-101",
        kind="forbidden",
        pattern="guaranteed results",
        replacement=None,
        applies_to="any",
        message='The phrase "guaranteed results" is forbidden in all messaging.',
        clause_text='Forbidden message MSG-101: The phrase "guaranteed results" must never appear in any draft.',
    ),
    dict(
        rule_id="MSG-102",
        kind="forbidden",
        pattern="no risk",
        replacement=None,
        applies_to="any",
        message='The phrase "no risk" is forbidden in all messaging.',
        clause_text='Forbidden message MSG-102: The phrase "no risk" must never appear in any draft.',
    ),
    dict(
        rule_id="MSG-103",
        kind="forbidden",
        pattern="act now",
        replacement=None,
        applies_to="any",
        message='The urgency phrase "act now" is forbidden in all messaging.',
        clause_text='Forbidden message MSG-103: The urgency phrase "act now" must never appear in any draft.',
    ),
    # --- Possible promotional claims (prompts for human review only) ----------
    dict(
        rule_id="CLM-001",
        kind="claim",
        pattern=r"\b(best|top[- ]rated|number one|#1|world[- ]class)\b",
        replacement=None,
        applies_to="any",
        message="Possible superlative or ranking claim; prompt a human to review it.",
        clause_text="Claim prompt CLM-001: Superlatives and rankings must be checked by a human before use.",
    ),
    dict(
        rule_id="CLM-002",
        kind="claim",
        pattern=r"\b(guaranteed|always works|never fails|instant results)\b",
        replacement=None,
        applies_to="any",
        message="Possible absolute-performance claim; prompt a human to review it.",
        clause_text="Claim prompt CLM-002: Absolute performance claims must be checked by a human before use.",
    ),
    dict(
        rule_id="CLM-003",
        kind="claim",
        pattern=r"\b(clinically proven|doctor[- ]approved|medically proven)\b",
        replacement=None,
        applies_to="any",
        message="Possible health-authority claim; prompt a human to review it.",
        clause_text="Claim prompt CLM-003: Claims that imply medical or professional endorsement must be checked by a human before use.",
    ),
]


def seed_rules(db):
    """Insert (or replace) the fictional sample rules."""
    for rule in SAMPLE_RULES:
        db.execute(
            """INSERT OR REPLACE INTO rules
               (rule_id, kind, pattern, replacement, applies_to, message, clause_text, active)
               VALUES (:rule_id, :kind, :pattern, :replacement, :applies_to,
                       :message, :clause_text, 1)""",
            rule,
        )
    db.commit()


def seed_all(db):
    """Seed everything the app ships with: the sample rules. No users, no drafts."""
    seed_rules(db)
