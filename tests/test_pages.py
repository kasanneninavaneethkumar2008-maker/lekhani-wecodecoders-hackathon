"""Lekhani site pages: Home, About, Contact, Report an issue, workspace shell.

Guests enter with a name only; every page is session-gated, shows the guest
identity, and never claims working email delivery, accounts, or checks.
"""
import re


def enter_guest(client, name="Asha Rao"):
    return client.post("/guest/login", data={"name": name}, follow_redirects=True)


# --- guest entry and gating ---------------------------------------------------


def test_guest_entry_opens_the_home_page(client):
    response = enter_guest(client, "Asha Rao")
    assert response.status_code == 200
    assert b"Welcome, Asha Rao" in response.data
    assert b"Thoughtful words." in response.data
    assert b"Guest workspace" in response.data


def test_login_redirects_to_home(client):
    response = client.post("/guest/login", data={"name": "Asha"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/home")


def test_all_site_pages_require_a_guest_name(client):
    for path in ("/home", "/about", "/contact", "/report-issue", "/workspace"):
        response = client.get(path)
        assert response.status_code == 302, path
        assert response.headers["Location"].endswith("/"), path


def test_guest_name_renders_as_text_not_html(client):
    enter_guest(client, "<script>alert(1)</script>")
    page = client.get("/home").data
    assert b"<script>alert(1)</script>" not in page
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_leave_workspace_clears_the_guest_and_returns_to_entry(client):
    enter_guest(client)
    with client.session_transaction() as sess:
        assert sess["guest_name"] == "Asha Rao"
    response = client.get("/guest/logout", follow_redirects=True)
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert "guest_name" not in sess
    assert client.get("/home").status_code == 302


# --- shared header and footer -------------------------------------------------


def test_shared_header_shows_navigation_and_guest_identity(client):
    enter_guest(client, "Asha Rao")
    page = client.get("/home").data
    for href in (b'href="/home"', b'href="/about"', b'href="/contact"',
                 b'href="/report-issue"', b'href="/guest/logout"'):
        assert href in page
    assert b'class="guest-avatar" aria-hidden="true">A<' in page
    assert b"Guest workspace" in page
    assert b"Leave workspace" in page


def test_active_navigation_is_marked_on_each_page(client):
    enter_guest(client)
    expected = {
        "/home": b"/home",
        "/about": b"/about",
        "/contact": b"/contact",
        "/report-issue": b"/report-issue",
    }
    for path, href in expected.items():
        page = client.get(path).data.decode()
        link = re.search(r'<a href="' + re.escape(href.decode()) + r'"[^>]*>', page)
        assert link is not None
        assert 'aria-current="page"' in link.group(0), path


def test_shared_footer_and_notices_on_every_page(client):
    enter_guest(client)
    for path in ("/home", "/about", "/contact", "/report-issue", "/workspace"):
        page = client.get(path).data
        assert b"Rooted in language. Guided by evidence." in page, path
        assert b"Guest demo. Do not enter confidential information." in page, path
        assert b"Checks support human review. They do not certify legal compliance." in page, path
        assert b'href="/about"' in page and b'href="/contact"' in page, path
        assert b'href="/report-issue"' in page, path


# --- Home ---------------------------------------------------------------------


def test_home_ctas_open_the_workspace(client):
    enter_guest(client)
    page = client.get("/home").data
    assert page.count(b'href="/workspace"') >= 2  # hero + next-step panel
    assert b"Start a review" in page
    assert b"Open workspace" in page

    workspace = client.get("/workspace")
    assert workspace.status_code == 200
    assert b"Check a draft against the active rules." in workspace.data
    assert b"Run checks" in workspace.data
    assert b"Guest work is temporary." in workspace.data
    assert b'href="/trust-lab"' in workspace.data


def test_see_how_it_works_links_to_the_about_section(client):
    enter_guest(client)
    assert b'href="/about#how-lekhani-works"' in client.get("/home").data
    about = client.get("/about").data
    assert b'id="how-lekhani-works"' in about
    assert b"Publication happens outside Lekhani." in about


def test_home_value_statements_and_supporting_cards(client):
    enter_guest(client)
    page = client.get("/home").data
    for text in (b"Rule-backed findings", b"Understand the guideline behind each finding.",
                 b"Clear reasons", b"See what needs attention and why.",
                 b"Human decisions", b"Keep approval with a person.",
                 b"Your next step", b"Begin with your content",
                 b"About the project", b"Contact the team", b"Report an issue"):
        assert text in page


# --- About --------------------------------------------------------------------


def test_about_content_flowchart_and_team(client):
    enter_guest(client)
    page = client.get("/about").data
    for text in (
        b"The thinking behind Lekhani.",
        b"A review workspace that connects content findings to approved",
        b"brand rules\xe2\x80\x94and keeps decisions human.",
        b"Why we built it",
        b"What makes it different",
        b"Why Lekhani?",
        b"Rooted in language. Guided by evidence.",
        b"How Lekhani works",
        b"Human review \xe2\x86\x92 Needs changes \xe2\x86\x92 Revise",
        b"Publication happens outside Lekhani.",
        b"Privacy, protection, and honest limits.",
        b"Human control",
        b"Rule validation",
        b"Demo privacy",
        b"Current limits",
        b"Built by Team Lekhani",
        b"Ready to begin?",
    ):
        assert text in page, text
    # No personal names, initials, portraits, or biographies remain.
    assert b"K. Navaneeth Kumar" not in page
    assert b"K. Venkata Uday" not in page
    assert b"K. Sasi Vardhan Srinivas" not in page
    assert b"team-avatar" not in page
    # Five self-running flowchart nodes, no Play/Pause controls, and a
    # working loop back to Revise.
    assert page.count(b"data-flow-node") == 5
    assert b"data-flow-play" not in page
    assert b"data-flow-pause" not in page
    assert b'id="flow-detail"' in page
    assert b"Needs changes" in page


# --- Contact ------------------------------------------------------------------


def test_contact_page_shows_no_contact_details(client):
    enter_guest(client, "Asha Rao")
    page = client.get("/contact").data
    assert b"Let\xe2\x80\x99s hear from you." in page
    # No email address, phone number, or related controls are shown.
    for absent in (b"Team email", b"Team phone", b"mailto:", b"tel:",
                   b"Open email", b"Call", b"Copy"):
        assert absent not in page, absent
    # The enquiry form and its honest, disconnected notice remain.
    assert b"This form is a preview. Message delivery is not connected yet." in page
    assert b"Send enquiry" in page
    assert b"disabled" in page
    assert b"delivery is not connected yet" in page
    assert b"Please do not include passwords, API keys, or confidential drafts." in page
    # The name field is prefilled with the guest name and stays editable.
    assert b'id="contact-name" name="name" required' in page
    assert b'value="Asha Rao"' in page
    # The report link is still offered.
    assert b'href="/report-issue"' in page


def test_contact_topics_and_privacy_reminder(client):
    enter_guest(client)
    page = client.get("/contact").data
    for text in (b"General question.", b"Feedback.", b"Collaboration.", b"Other."):
        assert text in page
    assert b"Please do not include passwords, API keys, or confidential drafts." in page
    assert b'href="/report-issue"' in page


# --- Report an issue ----------------------------------------------------------


def test_report_page_form_options_and_guidance(client):
    enter_guest(client)
    page = client.get("/report-issue").data
    for text in (
        b"Help us improve Lekhani.",
        b"Tell us what happened and what you expected instead.",
        b"Page or navigation problem.",
        b"Incorrect rule finding.",
        b"Missed rule issue.",
        b"Accessibility problem.",
        b"Guest-entry problem.",
        b"Privacy or security concern.",
        b"Guest entry.",
        b"Review workspace.",
        b"Before submitting",
        b"Describe the problem clearly.",
        b"Do not include passwords or API keys.",
        b"Need general help?",
        b"This form is a preview. Issue submission is not connected yet.",
        b"Submit issue",
    ):
        assert text in page, text
    assert b'href="/contact"' in page
    assert b"disabled" in page
    assert b'type="file"' not in page  # no uploads in this build
    # The success state is prepared for a future backend but never rendered.
    assert b"Issue received." not in page
    assert b"Reference:" not in page


def test_report_privacy_warning_is_present_but_hidden_by_default(client):
    enter_guest(client)
    page = client.get("/report-issue").data
    assert b'id="privacy-warning"' in page
    assert b"Do not include passwords, tokens," in page
    assert b"detailed exploit information here" in page
    assert b'id="privacy-warning" hidden' in page
