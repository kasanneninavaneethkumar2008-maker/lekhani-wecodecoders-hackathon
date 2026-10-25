# Inkloom AI

A small, text-only web app where a **creator** submits draft text, checks it
against a table of approved messaging rules, revises it, and a **reviewer**
records either **Approved** or **Needs changes**.

Built with Python 3, Flask with server-rendered Jinja templates, and SQLite.

**Public name:** Lekhani (लेखनी) — the product name shown in the app and on the
welcome page. “Inkloom AI” remains the formal project name in this
documentation and the Python package.

> This build keeps the original creator/reviewer workflow and adds a functional
> guest workspace, an explicit fictional sample, UTF-8 TXT/text-PDF draft
> import, portable review packs, printing, and a Trust Lab. It is not deployed,
> security-audited, authenticated, or production-certified, and guest work is
> never stored in the database.
>
> Round 2 scope, test evidence, and known limitations are recorded in
> [`ROUND2_SUBMISSION_NOTES.md`](ROUND2_SUBMISSION_NOTES.md). No original
> proposal document is present in this repository, so that comparison is not
> included.

## What it does

- **Guest preview (temporary).** The app opens to the Lekhani welcome page.
  Type a name, then slide the pen nib to the end of the track (or use
  **Continue without sliding**) to open Home. The name lives only in the
  browser session — no guest name, draft, or decision is ever written to the
  database. Home, About, Contact, Report an issue, the Review workspace, and
  the Trust Lab all require that guest name; **Leave workspace** clears it.
- **Public pages.** Home, About Lekhani, Contact Us, Report an issue, Review
  workspace, and Trust Lab share one header (pen logo, navigation, guest
  avatar/name dropdown, mobile menu, a quiet **Reduce motion** switch) and one
  footer. The enquiry and issue forms are visible previews and are disabled:
  delivery and storage are not connected in this stage.
- **Review workspace (guest, in memory).** A three-column review desk
  (editor, findings, rule evidence) on desktop and Write / Findings /
  Evidence tabs on narrow screens. Choose a content type (social post,
  marketing email, website copy, or other), add audience context, and write
  or paste a draft, then **Run checks**. Each finding cites a stable rule ID
  and its exact clause; the evidence panel shows why it was flagged, the
  rule-set version, the reference-validation result, and (for terminology
  rules) a controlled replacement of one chosen occurrence with preview,
  confirmation, and undo. A **Check preview** renders the exact checked
  snapshot with validated spans highlighted — never through `innerHTML`.
  **View rules** opens a read-only, searchable rules drawer. Start from an empty
  desk with three explicit choices — write/paste, import a file, or **Test a
  sample**; no sample text is ever loaded automatically.
- **Fictional GreenLeaf sample.** Clicking **Test a sample** (or the quiet
  action in the import panel) confirms before replacing existing work, then
  loads `Green Leaf gives users the best planning experience, with guaranteed
  results.` with the separate rule set *Fictional demo guidelines* (`demo-v1`),
  scoped to the **Product promotion** content type. Running the real checker
  produces exactly five findings: `GLOSS-01` brand spelling, `GLOSS-02`
  non-preferred term, `MSG-01` missing required sentence, and the claim prompts
  `CLAIM-01` (`best`) and `CLAIM-02` (`guaranteed`). Replacing the draft with
  `GreenLeaf helps customers organise their daily plans. Explore plans on our
  website.` and checking again produces no findings under those five rules. The
  page never presents that as factual, legal, or complete brand safety, and
  **Use workspace rules** returns to the workspace library with the earlier
  check explicitly outdated.
- **TXT and text-PDF import.** One file at a time: UTF-8 `.txt` or a text-based
  PDF up to 5 MB and 10 pages. The file picker and drag-and-drop share the same
  server validation and extraction path; the extension and browser MIME type
  are not trusted. A PDF must actually carry the PDF signature, an encrypted
  or malformed PDF is refused, and a PDF with no extractable text gets the
  documented “paste manually / OCR is not supported” message. Extraction shows
  an editable preview with **Use this text** and **Cancel**; the current draft
  is never replaced before confirmation, and every failure keeps it intact.
  Imports are capped by the same 100,000-character draft limit as the editor, and
  imported text is draft content, never approved guideline content.

  Statuses are explicit: Not checked, Checking, Checked, Changes since check,
  Check incomplete, and Check failed. A check is bound to a snapshot of the
  draft text, content type, audience, and rule-set version; editing any of
  them marks the results outdated. The **Check coverage** accordion uses the
  real rule and rejected-candidate counts plus an explicit “Not determined by
  this check” list. The **Guest review** accordion records a clearly labelled
  demonstration (guest name, outcome, note, time, content fingerprint,
  rule-set and check references) only for a current completed check; it is
  never an approval, and it becomes outdated when the reviewed snapshot
  changes. Guest work is held in the request/response only: refreshing or
  leaving discards it, while internal navigation and browser unloads warn
  when a non-empty draft would be lost.
- **Portable review pack and print.** **Export review pack** downloads a
  versioned JSON file (title, draft, context, rule ID/version, rule
  snapshots, the check snapshot, current findings, an optional guest-review
  record, an explicit unverified-guest status, coverage limits, and a SHA-256
  fingerprint of the UTF-8 draft text). **Open review pack** validates
  structure, version, types, size, matching configuration, and duplicate rule
  IDs; both the workspace library and the bundled sample (`demo-v1`) are
  recognised locally and re-checked with local rules, unknown sets are imported
  as draft text only. Imported findings and approval labels are never trusted
  as current, and an import problem keeps the current draft instead of
  discarding it. **Print summary** produces a clean print layout with the title,
  draft, findings, cited clauses, rule-set version, coverage limits, and
  guest-review status.
- **Round 3 roadmap.** Home carries three clearly non-functional “Planned ·
  Round 3” cards (accounts/saved workspaces, verified review requests, and
  custom and versioned brand rules/evidence) plus the notice that these features are not
  available in the guest version. The workspace links quietly to the same
  section. No Google, cloud-save, or email control is rendered as if it works.
- **Trust Lab.** A clearly labelled, fictional demonstration. Three isolated
  cases (valid citation, unknown rule ID, altered quotation) run through the
  same shared validator; a separate simulator compares two bundled fictional
  guideline versions and reports changed rules plus new, resolved, unchanged,
  and details-changed findings from real checker output. Lab work never
  touches workspace drafts or approved rules.
- **Demo role choice (not authentication).** The local demo role switch stays
  available at `/continue` for demoing and testing: **Continue as Creator**
  or **Continue as Reviewer**. There is
  no password sign-in. The selected role is stored in the session and
  enforced on the server for every request (the user is re-read from the
  database; a wrong role gets HTTP 403), but anyone at the chooser can pick
  either role — so this is a local demo convenience, **not authentication and
  not a security boundary**. See “Demo role choice” below.
- **Creator workflow.** Submit draft text with its **content type** and
  **intended audience** → run the checks → revise the text → send the draft
  for review. The signed-in creator form is typed or pasted only; draft-file
  import belongs to the guest workspace path.
- **Deterministic checks.** Three kinds of checks, all purely rule-based
  (no external AI provider, no randomness):
  1. **Glossary terminology** — non-approved terms with suggested replacements.
  2. **Required / forbidden messaging** — phrases that must appear
     (scoped by content type) or must never appear.
  3. **Possible promotional claims** — regex patterns that flag wording
     such as superlatives or absolutes.
- **Citations.** Every issue shown to a person cites an approved clause by
  its **stable rule ID** (e.g. `GLS-001`) and quotes the approved clause
  **exactly as stored** in the rule table. Before anything is displayed or
  saved, the citation validator re-checks each issue against the rule table
  and **discards** it if the ID is missing or the quote differs — even by a
  single character.
- **Claims are prompts, not verdicts.** Claim issues are labelled "prompt for
  human review" and say so in the text. They never assert that a claim is
  true, false, legal, or illegal.
- **Reviewer workflow.** The reviewer reads a submitted draft (with its latest
  check results for context) and records **Approved** or **Needs changes**,
  with an optional comment. The decision, the reviewer who made it, and the
  time it was made are stored in the `decisions` table, and the draft status
  is updated.
- **Saved data.** Drafts (with authorship and created/updated timestamps),
  check runs (with a snapshot of the checked text), validated issues,
  reviewer decisions (decision, reviewer, timestamp), the approved rule
  table, and user accounts.

## Project layout

```
inkloom/
  __init__.py        App factory, error pages
  auth.py            Demo role chooser ("/continue") + role decorators
  checker.py         Deterministic checks + citation validator
  csrf.py            CSRF protection & Origin validation middleware
  file_import.py     Validated UTF-8 TXT / text-PDF extraction (pypdf)
  creator.py         Creator routes (submit, check, revise, send for review)
  reviewer.py        Reviewer routes (queue, record decision)
  site.py            Public pages (Home, About, Contact, Report an issue),
                     workspace routes, review-pack import/export, print,
                     Trust Lab and simulator routes
  workbench.py       Workspace snapshots, staleness, controlled replacement,
                     guest-review records, preview segments (no storage)
  rulesets.py        Rule-set loading + two isolated fictional lab rule sets
  review_pack.py     Versioned review-pack build/validation (untrusted input)
  simulator.py       Pure rule-change comparison with the shared checker
  integrations.py    Unconnected interfaces for future auth/persistence/
                     delivery services (nothing is wired up)
  db.py              SQLite helpers + `init-db` / `seed` CLI commands
  seed.py            Fictional sample rules (the only seed data)
  schema.sql         Database schema
  templates/         Server-rendered Jinja templates (site_base.html + pages,
                     workspace.html + workspace/ partials, workspace_rules.html,
                     trust_lab.html, print_summary.html)
  static/welcome.css Welcome-page styles
  static/lek.css     Shared styles for the site pages, workspace, lab, print
  static/lek.js      Header menus, motion switch, flowchart, workspace state
  .env.example       Sample configuration (secret key)
tests/
  test_checker.py           Checker unit tests
  test_citation_validator.py  Citation validator tests (incl. against the DB)
  test_csrf.py              CSRF protection and Origin validation tests
  test_workflow.py          Sign-in, roles, persistence over HTTP
  test_pages.py             Guest-page gating, content, honest form states
  test_advanced.py          Versioned validation, workspace, packs, simulator,
                            Trust Lab, print, stale/motion behaviour
  test_workspace.py         Workspace matching, snapshots, replacement,
                            guest review, import safety, new-draft warning
  test_round2.py            GreenLeaf sample, TXT/PDF import, review carry-
                            forward, product-promotion scope, roadmap
run.py                 Dev server entry point
requirements.txt       Dependencies (Flask, pytest)
```

## Setup

Requires Python 3.10+ (developed and tested on Python 3.14).

```bash
python3 -m venv .venv
# Windows:
.venv/Scripts/python -m pip install -r requirements.txt
# macOS / Linux:
.venv/bin/pip install -r requirements.txt
```

## Initialize the database

```bash
# Windows: use .venv/Scripts/python -m flask … instead of `flask`
flask --app inkloom init-db   # creates instance/inkloom.sqlite3 (recreates tables)
flask --app inkloom seed      # loads the fictional sample rules (no users, no drafts)
```

`init-db` recreates the tables, so it wipes any existing local data.

## Run

```bash
flask --app inkloom run        # or: python run.py (from the activated venv)
```

Open <http://127.0.0.1:5000/>. The app opens to the Lekhani welcome page:
type your name, then slide the pen nib to the end of the track (or use
**Continue without sliding**) to open Home. From there the header links to
About, Contact, Report an issue, the workspace, and the Trust Lab; the guest
menu (or the mobile menu) has **Leave workspace**, which returns to guest
entry. A **Reduce motion** switch in the navigation stops non-essential
animation immediately and is remembered in browser storage (a preference
only, never draft content).

The Contact page deliberately shows no email address or phone number: the
enquiry form is a disabled preview, with the report-issue link still offered.
The review pack downloads from the app server (checks also run there); the
page says so rather than claiming the draft never leaves the browser.

## Demo role choice — not authentication

The **/continue role switch is for the local demo only.**

- They are **not authentication**: there is no password, no sign-in, and no
  way to tell users apart beyond “this browser session picked this role”.
- They are **not a security boundary**: anyone who can open the page can
  pick either role. The server still enforces the *selected* role on every
  request (wrong role → HTTP 403), which keeps the two workflows cleanly
  separated while demoing — it does **not** keep anyone out.
- Do not expose this app to a network, and do not rely on it to protect any
  data you would not hand to a stranger on the same machine.

If `INKLOOM_SECRET_KEY` is unset, a development-only default signs the demo
session cookie.

## Temporary data and processing

What actually happens to a guest's content:

- **Checks run on this app server**, not in the browser. The draft is submitted
  in a form POST, matched against the active rule set, and the rendered result
  is returned. The request is not written to the database and is not logged by
  the application.
- **Uploaded files are read on the server** for validation/extraction (Werkzeug
  may spool a large upload to a temporary file while the request is handled).
  The application does not save the file, its name, or its text to the
  database; only the editable preview is carried in the page until the guest
  confirms it.
- **The guest name and selected demo role live in the signed session cookie.**
  Draft text, findings, check snapshots, and guest-review records are carried in
  the page's forms and URL-free request state only. They are not placed in the
  URL, localStorage, IndexedDB, or a cookie.
- **Refreshing the workspace discards guest work.** A browser unload or an
  internal navigation away from a non-empty draft asks for confirmation. The
  review pack download is the deliberate way to keep a copy.
- **Leaving the workspace** clears the guest name from the session and returns
  to the welcome page. The database is untouched.

## Tests

```bash
# Windows: .venv/Scripts/python -m pytest
pytest
```

The suite covers:

- **Checker:** glossary / required / forbidden / claim detection, case and
  word-boundary behaviour, content-type scoping, determinism, inactive and
  malformed rules, clean text.
- **Citation validator:** valid citations kept; issues discarded when the
  rule ID is missing from the rule table or the quote differs from the
  stored clause (including whitespace-only and wrong-rule quotes); mixed
  batches; validation against the live database rule table.
- **Workflow / access:** pages without a selected role redirect to the
  welcome page; the landing page shows the Lekhani welcome copy and guest
  entry with no sign-in or coming-soon placeholders; no `/login` route or
  password field remains; 403 for the wrong role in both directions; role
  switching; 404 for other creators' drafts; the full submit → check → revise
  → review cycle; decision/reviewer/timestamp persistence; and rejection of
  decisions on non-submitted drafts.
- **Site pages:** guest entry opens Home; every site page redirects to entry
  without a name; the guest name renders as escaped text; navigation, active
  state, and footer are shared; Home CTAs open the workspace; the About
  flowchart is self-running (no Play/Pause) and the anonymous
  “Built by Team Lekhani” credit replaces personal names; the Contact page
  shows no email/phone details; the preview forms are visibly disabled; and
  no fake success state or issue reference is shown.
- **Advanced features:** valid lab citations accepted; unknown rule IDs,
  altered quotations, and wrong rule-set versions rejected; invalid
  candidates never produce an all-clear; workspace findings, quotes,
  coverage, and the zero-findings message; review-pack export fields and
  fingerprint; import round-trip; unsupported/oversized/malformed packs;
  duplicate IDs; imported markup escaped; unknown imported rules not
  activated; matching and changed fingerprints distinguished; print summary;
  Trust Lab outcomes through the real validator; simulator differences; and
  static checks that editing marks results outdated, flowchart selections are
  pinned, and reduced-motion styles/disabling are present.

Latest run: **163 passed**. A separate headless-Chrome audit of the complete
guest journey (`_audit_round2.mjs`, 46 checks) passed with 0 failures against a
locally seeded copy of the app; it is a development tool, not part of pytest.
It needs the app on `127.0.0.1:5031` and Chrome's DevTools endpoint on port
`9444`, and it writes temporary files under `instance/audit-*`.

## Accessibility

The welcome page, site pages, workspace, Trust Lab, and print summary are
styled (indigo on white, visible focus rings, keyboard-operable menus and
native radio controls, and a self-running, keyboard-operable flowchart).
Reduced-motion visitors get a static flowchart with no continuous movement;
the site switch mirrors that. Forms are labelled, use native controls, and
include a skip link. **This is not a claim of accessibility conformance** —
no standard (e.g. WCAG) has been audited or certified.

## Assumptions (choices where the proposal was unclear)

1. **Two roles only:** `creator` and `reviewer`. There is no admin and no
   sign-in of any kind; the landing-page choice maps to a demo account that
   is created on first use (existing rows are never modified).
2. **Draft lifecycle:** `draft → submitted → approved | changes_requested`.
   Editing locks while a draft is submitted; a "Needs changes" decision
   returns it to the creator, who can revise and send it again. Approved
   drafts are final for this version.3. **Workspace content types** are a fixed list: social post, marketing email,
   website copy, product promotion, other. Required messaging may be scoped to
   one or more of them; glossary/forbidden/claim rules apply everywhere.
   `product promotion` exists so the fictional GreenLeaf sample maps explicitly
   onto the existing content-type model; the sample's five rules apply only to
   it. Scopes are comma-separated and also include the older creator form's
   names (for example `website copy,product page`), so the existing
   creator/reviewer workflow keeps its rule coverage.
4. **Each check run snapshots the text** it checked, so history stays
   intelligible after edits; the latest run is shown by default.
5. **Only validated issues are stored** — discarded (unciteable) issues are
   dropped before storage rather than shown with a warning.
6. **Claims checks** use word lists stored as regexes in the rule table;
   they are deterministic and intentionally over-broad, since they only
   prompt a human to look.
7. **A reviewer may record only one decision per submission state**; later
   decisions append to history rather than overwrite.
8. **Sample rules are fictional**, for demonstration only. No users or
   drafts are seeded: every draft in the database is one actually created
   in the app.
9. **Sessions** are standard Flask signed-cookie sessions; only the demo
   user id is stored, and the role is re-read from the database on every
   request, so a request cannot smuggle in a role it was not assigned. That
   is consistency within the demo, not a security boundary — the chooser
   itself hands either role to anyone (see “Demo role choice” above).

## Deployment readiness

This is a Flask application with server-rendered templates; it is **not** a
static frontend and must run behind a WSGI server.

| Item | Verified detail |
| --- | --- |
| Runtime | Python 3.10+ (developed on Python 3.14). Requires a running application server. |
| Install | `python -m pip install -r requirements.txt` (Flask, gunicorn, pypdf; pytest for tests) |
| Database | SQLite file at `instance/inkloom.sqlite3` (or the path passed as `DATABASE` in a test config). Create and seed it once per environment: `flask --app inkloom init-db` then `flask --app inkloom seed`. `init-db` recreates tables, so it wipes local data. |
| Local run | `flask --app inkloom run` or `python run.py`; `run.py` honours `PORT` and binds `0.0.0.0`. |
| Production start | `gunicorn run:app` (Linux/Render-style hosts). Verified only that gunicorn is installed; it cannot execute on this Windows host. |
| Environment variables | `INKLOOM_SECRET_KEY` (required for a stable session key; a development default is used if unset) and `PORT` (read by `run.py`). No database URL or API keys exist. Values are never committed; `.env.example` lists names only. |
| Static assets | Served by Flask at `/static/...` (`lek.css`, `lek.js`, `welcome.css`). No frontend build step, CDN, external font, or image host. |
| Route fallback | Flask's own 404 handler renders `errors/404.html`. Do **not** rewrite unknown paths to a frontend index; `/`, `/home`, `/about`, `/contact`, `/report-issue`, `/workspace`, `/trust-lab`, and the demo `/continue` routes must reach Flask. |
| Uploads | 5 MB / 10-page limits are enforced by the app; ensure the host's request body limit is at least that large. |
| Deployment blockers | No account, host, domain, or deployment credentials are configured here. Nothing was deployed or submitted. The seeded SQLite file must exist before the first request that loads rules. |

## Third-party libraries and assets

- **Flask** (BSD-3-Clause) — web framework and server-rendered templates.
- **gunicorn** (MIT) — production WSGI server entry point.
- **pypdf** (BSD-3-Clause) — text extraction from text-based PDFs; imported lazily
  only on the PDF path.
- **pytest** (MIT) — test runner.
- No external fonts, icon packages, stock images, or analytics scripts are
  loaded. The pen-nib, flowchart, and decorative artwork are inline SVG written
  for this project.

## Limitations and out of scope

- **No persistence for guest work.** Drafts and results live only in the page
  and request/response; there is no database write, IndexedDB, or silent
  localStorage copy. Review-pack export is the deliberate save action.
- **Checks are synchronous and bounded.** A check is a form request handled
  by the app server; the page never reuses a client-supplied result, so an
  out-of-date response cannot be presented as current. Matching covers the
  configured literal phrases and claim regexes only, with case-insensitive,
  whole-word, whitespace-flexible literal matching.
- **Guest review is a demonstration, not an approval.** It has no verified
  identity, no signature, and no persistence beyond the open page; it is
  intentionally unavailable when the check is stale or incomplete.
- **No authentication or verified identity.** The guest name is a display
  name; it grants no reviewer/admin access. There is no Google sign-in yet.
  Guest notes, fingerprints, and print summaries are not approvals, signed
  certificates, or tamper-proof records.
- **Checks are deterministic and limited.** They cover configured terminology,
  messaging, and claim-trigger patterns only. They do not decide truth,
  legality, visual consistency, full accessibility, or arbitrary tone.
- **Draft file import is limited and non-OCR.** One UTF-8 `.txt` or text-based
  PDF at a time, 5 MB, 10 PDF pages, and 100,000 extracted characters. Scanned
  PDFs need OCR, which is not implemented; they get the failure message rather
  than fabricated text. UTF-16/UTF-32 text files are not converted. PDF text
  extraction uses `pypdf`; unusual font encodings may extract poorly, and the
  editable preview is the place to correct that. Imported rules are never
  activated; unknown review-pack rule sets load the draft only.
- **Review-pack import accepts JSON packs only** (draft-file import is the
  separate `.txt`/`.pdf` path), with a conservative 1 MB limit.
- **CSRF protection implemented.** State-changing requests (POST, PUT, DELETE, PATCH)
  are protected via Origin/Referer same-origin verification and session-bound
  synchronizer CSRF tokens (`session["_csrf_token"]`), supplied via hidden form
  inputs and `X-CSRF-Token` headers. Request bodies remain bounded field-by-field;
  the upload reader stops at 5 MB + 1 byte, while a global Flask `MAX_CONTENT_LENGTH`
  is not set.
- **Deployment is not verified.** Gunicorn is listed for a Linux host but
  cannot run on this Windows development machine, so only the Flask
  development server and WSGI app factory were exercised locally. There is no
  cloud database, object storage, or static build step; a static-only host
  cannot serve the Flask routes.
- Any external AI provider or model call
- Whole-piece rewriting or AI-generated text
- Automated approval — a human reviewer records every decision
- Publishing beyond the app's own pages/print output
- Analytics dashboards, notifications, teams/permissions beyond the two roles
- Connected contact/issue delivery, remote storage, and deployment hardening
