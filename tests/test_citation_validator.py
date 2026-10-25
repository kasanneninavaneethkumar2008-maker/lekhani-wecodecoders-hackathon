"""Tests for the citation validator: every shown issue must cite the rule table."""
from inkloom.checker import Issue, check_text, load_rules, run_checks, validate_citations


def issue_for(rule, quote=None):
    return Issue(
        rule_id=rule.rule_id,
        kind=rule.kind,
        message=rule.message,
        quote=rule.clause_text if quote is None else quote,
        excerpt="sample excerpt",
        is_prompt=(rule.kind == "claim"),
    )


def rules_fixture():
    return [
        make_rule("CL-001", "Approved clause CL-001: exact text A."),
        make_rule("CL-002", "Approved clause CL-002: exact text B."),
    ]


def make_rule(rule_id, clause_text):
    from inkloom.checker import Rule

    return Rule(
        rule_id=rule_id,
        kind="forbidden",
        pattern="act now",
        replacement=None,
        applies_to="any",
        message=f"Explanation for {rule_id}",
        clause_text=clause_text,
    )


# --- keeping valid citations -------------------------------------------------


def test_issue_with_matching_id_and_quote_is_kept():
    rules = rules_fixture()
    result = validate_citations([issue_for(rules[0])], rules)
    assert len(result.kept) == 1
    assert result.discarded == ()


def test_empty_input_is_valid():
    result = validate_citations([], rules_fixture())
    assert result.kept == () and result.discarded == ()


# --- discarding invalid citations -------------------------------------------


def test_unknown_rule_id_is_discarded():
    rules = rules_fixture()
    orphan = issue_for(rules[0])
    orphan = Issue(
        rule_id="CL-999",  # missing from the rule table
        kind=orphan.kind,
        message=orphan.message,
        quote=orphan.quote,
        excerpt=orphan.excerpt,
        is_prompt=orphan.is_prompt,
    )
    result = validate_citations([orphan], rules)
    assert result.kept == ()
    assert len(result.discarded) == 1


def test_quote_differing_from_stored_clause_is_discarded():
    rules = rules_fixture()
    tampered = Issue(
        rule_id="CL-001",
        kind="forbidden",
        message="m",
        quote="Approved clause CL-001: exact text A",  # missing period
        excerpt=None,
        is_prompt=False,
    )
    result = validate_citations([tampered], rules)
    assert result.kept == ()
    assert len(result.discarded) == 1


def test_quote_from_another_rule_is_discarded():
    rules = rules_fixture()
    swapped = Issue(
        rule_id="CL-001",
        kind="forbidden",
        message="m",
        quote=rules[1].clause_text,  # valid clause, wrong rule
        excerpt=None,
        is_prompt=False,
    )
    result = validate_citations([swapped], rules)
    assert result.kept == ()


def test_whitespace_only_difference_is_discarded():
    rules = rules_fixture()
    padded = Issue(
        rule_id="CL-001",
        kind="forbidden",
        message="m",
        quote=" " + rules[0].clause_text + " ",
        excerpt=None,
        is_prompt=False,
    )
    result = validate_citations([padded], rules)
    assert result.kept == () and len(result.discarded) == 1


def test_mixed_batch_filters_precisely():
    rules = rules_fixture()
    good = issue_for(rules[0])
    missing_id = Issue(
        rule_id="CL-404",
        kind="claim",
        message="m",
        quote=rules[0].clause_text,
        excerpt=None,
        is_prompt=True,
    )
    bad_quote = Issue(
        rule_id="CL-002",
        kind="glossary",
        message="m",
        quote="not the stored clause",
        excerpt=None,
        is_prompt=False,
    )
    also_good = issue_for(rules[1])
    result = validate_citations([good, missing_id, bad_quote, also_good], rules)
    assert [i.rule_id for i in result.kept] == ["CL-001", "CL-002"]
    assert [i.rule_id for i in result.discarded] == ["CL-404", "CL-002"]


# --- end-to-end through the database ----------------------------------------


def test_check_text_discards_issues_not_in_the_rule_table(db):
    """Simulate a corrupt issue by validating it against the real rule table."""
    from inkloom.checker import Rule
    from inkloom.checker import validate_issue_against_db

    rules = load_rules(db)
    assert rules, "seeded rules expected"

    fabricated = Issue(
        rule_id="NOT-A-RULE",
        kind="forbidden",
        message="m",
        quote="whatever",
        excerpt=None,
        is_prompt=False,
    )
    assert validate_issue_against_db(fabricated, db) is False

    genuine = Issue(
        rule_id=rules[0].rule_id,
        kind=rules[0].kind,
        message=rules[0].message,
        quote=rules[0].clause_text,
        excerpt=None,
        is_prompt=False,
    )
    assert validate_issue_against_db(genuine, db) is True


def test_every_issued_citation_matches_the_rule_table(db):
    """Pipeline output always cites stored rules verbatim."""
    rules = load_rules(db)
    text = (
        "We will disrupt the market with guaranteed results. Act now! "
        "The best offer ever, clinically proven to work."
    )
    issues = check_text(text, "product page", rules)
    by_id = {r.rule_id: r for r in rules}
    assert issues, "expected issues from the messy sample text"
    for issue in issues:
        assert issue.rule_id in by_id
        assert issue.quote == by_id[issue.rule_id].clause_text


def test_run_checks_then_validate_keeps_all_valid_issues(db):
    rules = load_rules(db)
    text = "Act now for the best deal of your life."
    candidates = run_checks(text, "product page", rules)
    result = validate_citations(candidates, rules)
    assert len(result.kept) == len(candidates)
    assert result.discarded == ()
