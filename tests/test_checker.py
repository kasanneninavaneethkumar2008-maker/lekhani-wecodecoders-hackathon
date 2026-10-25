"""Unit tests for the deterministic checker (glossary, messaging, claims)."""
from inkloom.checker import Rule, check_text, run_checks, validate_citations


def make_rule(rule_id="T-001", kind="glossary", **overrides):
    defaults = dict(
        rule_id=rule_id,
        kind=kind,
        pattern="synergy",
        replacement="collaboration",
        applies_to="any",
        message=f"{kind} message for {rule_id}",
        clause_text=f"Approved clause {rule_id}: exact stored text.",
        active=True,
    )
    defaults.update(overrides)
    return Rule(**defaults)


# --- glossary terminology ----------------------------------------------------


def test_glossary_match_is_flagged_with_replacement():
    rule = make_rule(kind="glossary", pattern="disrupt", replacement="change")
    issues = run_checks("We will disrupt the market.", "product page", [rule])
    assert len(issues) == 1
    issue = issues[0]
    assert issue.kind == "glossary"
    assert issue.rule_id == "T-001"
    assert "disrupt" in issue.excerpt
    assert "Suggested replacement: change." in issue.message
    assert issue.quote == rule.clause_text
    assert issue.is_prompt is False


def test_glossary_match_is_case_insensitive_and_word_bounded():
    rule = make_rule(kind="glossary", pattern="disrupt", replacement="change")
    assert len(run_checks("To DISRUPT routines.", "product page", [rule])) == 1
    # "undisrupted" contains the letters but not the whole word.
    assert run_checks("undisrupted habits", "product page", [rule]) == []


def test_glossary_absent_term_yields_no_issue():
    rule = make_rule(kind="glossary", pattern="disrupt", replacement="change")
    assert run_checks("We improve routines.", "product page", [rule]) == []


# --- required messaging ------------------------------------------------------


def test_required_phrase_missing_is_flagged():
    rule = make_rule(
        kind="required",
        pattern="pricing may change",
        applies_to="product page",
        replacement=None,
    )
    issues = run_checks("Great product.", "product page", [rule])
    assert len(issues) == 1
    assert issues[0].kind == "required"
    assert issues[0].excerpt is None
    assert issues[0].quote == rule.clause_text


def test_required_phrase_present_yields_no_issue():
    rule = make_rule(
        kind="required",
        pattern="pricing may change",
        applies_to="product page",
        replacement=None,
    )
    text = "Buy now. Pricing may change before checkout."
    assert run_checks(text, "product page", [rule]) == []


def test_required_rule_only_applies_within_scope():
    rule = make_rule(
        kind="required",
        pattern="pricing may change",
        applies_to="product page",
        replacement=None,
    )
    # Different content type: rule is out of scope, so no issue.
    assert run_checks("Short note.", "email", [rule]) == []


# --- forbidden messaging -----------------------------------------------------


def test_forbidden_phrase_present_is_flagged():
    rule = make_rule(kind="forbidden", pattern="act now", replacement=None)
    issues = run_checks("You should Act Now today.", "social post", [rule])
    assert len(issues) == 1
    assert issues[0].kind == "forbidden"
    assert "act now" in issues[0].excerpt.lower()


def test_forbidden_phrase_absent_yields_no_issue():
    rule = make_rule(kind="forbidden", pattern="act now", replacement=None)
    assert run_checks("Take your time.", "social post", [rule]) == []


# --- possible promotional claims (prompts, not verdicts) ---------------------


def test_claim_match_is_a_prompt_not_a_verdict():
    rule = make_rule(
        kind="claim",
        pattern=r"\b(best|top[- ]rated)\b",
        replacement=None,
        message="Possible superlative claim; prompt a human to review it.",
    )
    issues = run_checks("The best treadmill on the market.", "product page", [rule])
    assert len(issues) == 1
    issue = issues[0]
    assert issue.kind == "claim"
    assert issue.is_prompt is True
    # The issue carries no truth/legal judgment — only a prompt + citation.
    assert issue.quote == rule.clause_text
    assert "best" in issue.excerpt


def test_claim_pattern_is_case_insensitive():
    rule = make_rule(kind="claim", pattern=r"\bguaranteed\b", replacement=None)
    assert len(run_checks("GUARANTEED satisfaction.", "email", [rule])) == 1


# --- combined behaviour ------------------------------------------------------


def test_clean_text_produces_no_issues():
    rules = [
        make_rule(rule_id="A-1", kind="glossary", pattern="disrupt", replacement="change"),
        make_rule(
            rule_id="A-2",
            kind="required",
            pattern="pricing may change",
            applies_to="product page",
            replacement=None,
        ),
        make_rule(rule_id="A-3", kind="forbidden", pattern="act now", replacement=None),
        make_rule(rule_id="A-4", kind="claim", pattern=r"\bbest\b", replacement=None),
    ]
    text = "A calm page. Pricing may change at any time."
    assert check_text(text, "product page", rules) == ()


def test_multiple_rules_report_in_rule_order_deterministically():
    rules = [
        make_rule(rule_id="Z-2", kind="forbidden", pattern="act now", replacement=None),
        make_rule(rule_id="A-1", kind="glossary", pattern="disrupt", replacement="change"),
    ]
    text = "Disrupt the norm and act now."
    first = run_checks(text, "product page", rules)
    second = run_checks(text, "product page", rules)
    assert [i.rule_id for i in first] == ["Z-2", "A-1"]
    assert first == second


def test_inactive_rules_are_ignored():
    rule = make_rule(kind="glossary", pattern="disrupt", replacement="change", active=False)
    assert run_checks("We disrupt things.", "product page", [rule]) == []


def test_malformed_claim_regex_yields_no_crash_and_no_issue():
    rule = make_rule(kind="claim", pattern="(unclosed", replacement=None)
    assert run_checks("some text", "email", [rule]) == []


def test_empty_text_flags_required_but_nothing_else():
    rules = [
        make_rule(
            rule_id="R-1",
            kind="required",
            pattern="free trial",
            applies_to="email",
            replacement=None,
        ),
        make_rule(rule_id="R-2", kind="forbidden", pattern="act now", replacement=None),
    ]
    issues = run_checks("", "email", rules)
    assert [i.rule_id for i in issues] == ["R-1"]
