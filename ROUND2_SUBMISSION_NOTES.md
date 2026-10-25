# Lekhani (लेखनी) — Round 2 submission notes

Round 2 deadline: **25 October 2026, 10:00 AM IST**.

This document records only verified work. The local application was not deployed,
submitted to the organisers, emailed, or connected to Google or a cloud database.
An updated audit PDF has been generated locally, but has **not** been submitted.
No original proposal document is present in this repository, so a direct
proposal-to-build comparison is **not** available.

---

## 1. Completed features

### Guest entry and site
- Welcome page with the Lekhani wordmark and लेखनी script, name field, slide-to-
  enter control, **Continue without sliding**, and Enter-key submission.
- Names are trimmed and rejected when whitespace-only, limited to 60
  characters, Unicode-safe, and always rendered as escaped text. A guest name
  is a display name and grants no authenticated reviewer/admin access.
- Slide works with pointer and touch; duplicate submission is guarded.
- Home, About, Contact, Report an issue, Review workspace, and Trust Lab.
- About shows only “Built by Team Lekhani”; Contact shows no email or phone and
  clearly states delivery is not connected; both forms remain honest disabled
  previews with no fake success state.
- Leave workspace clears the guest identity; direct workspace access without a
  guest returns to the welcome page. A useful 404 page renders for unknown
  routes.
- White/off-white/ink/indigo/lavender palette, logo, reduced-motion switch, and
  existing About flowchart and page navigation preserved.

### Review workspace
- Three-column desktop desk (editor / findings / rule evidence) and mobile
  Write / Findings / Evidence tabs, with no horizontal overflow at 390 px.
- Empty start state with three explicit input methods: write/paste, import
  file, and **Test a sample**. No sample text is loaded automatically.
- Editable draft title, content type, intended audience, plain-text editor, and
  live word/character counts. Audience is labelled as context metadata.
- One shared deterministic checker and citation validator for manual, imported,
  and sample text:
  - terminology rules with optional exact replacement,
  - required and forbidden messaging,
  - possible promotional-claim prompts.
- Every displayed finding cites a rule ID, the exact stored clause, the
  rule-set ID/version, the affected text where a span exists, and an
  explanation. Unknown IDs, altered quotations, and wrong versions are
  rejected; rejected candidates are shown separately and never become an
  all-clear.
- Snapshot-bound statuses: Not checked, Checking, Checked, Changes since check,
  Check incomplete, Check failed. A normal re-check carries an earlier guest
  review forward and marks it outdated instead of silently dropping it.
- Coverage panel reports applicable terminology/messaging/claim rule counts,
  rule-set version, and rejected-candidate count, separate from finding counts.
  If no rules apply, the page says so and does not show a clean result.
- Single-occurrence terminology replacement with preview, confirmation, stale-
  text refusal, and undo; it never rewrites the whole draft.
- Guest review demonstration with the required identity-not-verified label,
  review note, **Needs changes**, **Mark approved — demo**, and a required
  current completed check. It records name, outcome, note, time, snapshot
  fingerprint, and rule set; editing invalidates it. It is not stored,
  published, or treated as an approval.
- Review-pack JSON export includes format version, draft, metadata, rule set,
  rule snapshots, check snapshot, current/historical status, findings, optional
  guest-review record, an explicit unverified-guest status, and a SHA-256
  content fingerprint (not a signature).
- Review-pack import validates structure/types/size/duplicates, recognises both
  the workspace rule set and the bundled sample, reruns checks with local rules,
  never trusts imported findings/approval labels as current, and preserves the
  current draft on failure. Print summary reuses the same verified result.

### Fictional GreenLeaf sample
- Separate rule set: **Fictional demo guidelines**, id
  `lekhani-greenleaf-sample`, version `demo-v1`, brand GreenLeaf, language
  English, content type **Product promotion**.
- Loading it requires explicit action and confirmation if work exists; it
  activates only its five rules and leaves the workspace rule library untouched.
- Original text: `Green Leaf gives users the best planning experience, with
  guaranteed results.` → exactly five findings:
  `GLOSS-01` brand spelling, `GLOSS-02` non-preferred term, `MSG-01` required
  sentence missing, `CLAIM-01` possible claim “best”, `CLAIM-02` possible claim
  “guaranteed”.
- Revised text: `GreenLeaf helps customers organise their daily plans. Explore
  plans on our website.` → no findings under those five rules, shown with the
  factual/legal limitation notice.
- Exact clauses:
  - `GLOSS-01`: “Write the brand name as GreenLeaf, not Green Leaf.”
  - `GLOSS-02`: “Use customers instead of users in customer-facing promotional copy.”
  - `MSG-01`: “Product promotions must include the exact sentence: Explore plans on our website.”
  - `CLAIM-01`: “Flag best for human evidence review; do not determine whether the claim is true.”
  - `CLAIM-02`: “Flag guaranteed for human evidence review; do not determine whether the claim is true.”

### File import
- File picker and drag-and-drop share one validation/extraction path.
- One UTF-8 `.txt` or text-based PDF; 5 MB; 10 PDF pages; 100,000 extracted
  characters. PDF is detected by its bytes, not by extension/MIME.
- Editable preview with **Use this text** and **Cancel**; no replacement before
  confirmation; failures preserve current work.
- Specific handling for unsupported type, multiple files, empty file, oversized
  file, non-UTF-8/binary text, password-protected PDF, malformed PDF, PDF with
  no usable text, and over-limit extracted text. Scanned PDFs direct the guest
  to paste manually; OCR is not implemented.

### Round 3 roadmap
- Home: **Coming in Round 3**, three cards with **Planned · Round 3** badges,
  and the notice “These features are planned, not available in the current guest
  version.” No fake progress percentages or working-looking Google/save/email
  controls.
- Workspace: quiet link to `Home#round-3`.

---

## 2. Actual architecture and data flow

- **Stack:** Python 3, Flask, Jinja server-rendered templates, SQLite, plain
  CSS/JavaScript. No frontend framework, bundler, CDN, analytics, or external AI
  service. `pypdf` is used only for PDF text extraction.
- **Entry:** `POST /guest/login` stores the display name in Flask's signed session
  cookie. It is not a database user.
- **Workspace check:** browser form POST → Flask route → `checker.check_review`
  over the active rule list → `validate_citations` → Jinja render. The client
  never restores findings from a supplied snapshot; it only carries snapshot
  metadata to prove staleness.
- **Rules:** the workspace's fictional library is seeded into SQLite. The
  GreenLeaf sample is a code fixture in `rulesets.py` and is never written to
  the database. Both use the same `Rule`/`Issue` checker types.
- **File import:** `POST /workspace/import-file` → `file_import.validate_and_extract`
  → editable preview → `Use this text` → ordinary draft text. No uploaded file
  is saved by the app.
- **Review packs:** export is built from the active rules and current verified
  check; import is treated as untrusted data and re-checked locally.
- **Temporary state:** draft, findings, check snapshots, and guest-review records
  exist only in rendered form fields / request state. Refresh discards them;
  export is the save action. The database receives no guest name, draft, check,
  finding, or review.

---

## 3. Changes from Round 1

- Added the isolated GreenLeaf sample fixture, `demo-v1`, the explicit
  **Product promotion** content type, and a rule-set mode that cannot silently
  blend sample rules with the workspace library.
- Added UTF-8 TXT and text-PDF import with picker + drag/drop, content sniffing,
  preview/confirm, and explicit failure handling.
- Added the Round 3 roadmap and workspace link.
- Fixed three real defects found while wiring the Round 2 flow:
  1. `check_review` labelled a run with zero applicable rules as the default
     rule set; it now reports the loaded set and never implies a clean check.
  2. Pressing **Run checks** again dropped an earlier guest review; it is now
     carried forward and shown as outdated.
  3. The existing New-draft confirmation buttons sat outside the workspace form
     and were inert; confirmation buttons now target the form explicitly.
- Export now derives the rule-set identity from the exported rules (rather than
  hardcoding the workspace set), sorts rule snapshots deterministically,
  recognises the sample set on import, and includes an unverified-guest status.
- Reduced the post-export submit guard from 2 s to 0.6 s so a guest can continue
  immediately after the download.
- Workspace copy changed from “approved rules” to “active rules”, because the
  fictional demo rules are not an approved organisational policy.
- Added 35 targeted tests (Round 1 baseline: 128 passed; now 163).
- Added lightweight CSRF protection and Origin validation middleware (`csrf.py`),
  protecting all state-changing endpoints with synchronizer tokens and same-origin checks.

---

## 4. Test evidence

| Check | Command | Result |
| --- | --- | --- |
| Full test suite | `.venv/Scripts/python -m pytest -q` | **163 passed** |
| Dependency consistency | `.venv/Scripts/python -m pip check` | `No broken requirements found.` |
| Browser journey | `node _audit_round2.mjs` (Chrome 155 headless via CDP, app on `127.0.0.1:5031` with a temporary seeded SQLite file) | **46 passed, 0 failed** |
| Visual screenshots | not requested; none taken | — |

The 46 browser checks covered: blank-name rejection; Enter submission; pointer
slide; touch slide; Unicode name rendering; empty workspace and three input
methods; no automatic sample; sample load/confirmation/labels; exactly five
findings; sample-only rules; claim prompt evidence; exact-clause selection;
review-pack download and contents; revised-sample clean re-check; guest-review
recording and invalidation; Keep-this-draft; TXT picker preview/use; empty-file
failure preserving work; PDF drag-and-drop preview; cancel import; roadmap;
390 px mobile tabs and overflow; 404; About/Contact/Report/Trust Lab; leave
workspace; direct-access redirect.

**Not run:** a lint/typecheck command (the project defines none), a production
build (none exists for server-rendered Flask), and gunicorn (cannot execute on
this Windows host — see below).

Automated execution time is not human review time. No user interviews, manual
review timings, or human usability findings are claimed.

---

## 5. Known limitations

### Defects
- No unresolved failure is known in the tested guest journey. The following are
  accepted risks rather than hidden passes:
  - No global Flask `MAX_CONTENT_LENGTH`; limits are enforced field-by-field
    and the upload reader stops after 5 MB + 1 byte. (CSRF protection is implemented
    via session tokens and Origin verification).
  - PDF extraction depends on `pypdf`; unusual font encodings can produce an
    imperfect preview, which the guest can edit or cancel.
  - Gunicorn is installed but not runnable on this Windows machine; the
    production server path is unverified locally.

### Intentionally deferred services
- Google sign-in and accounts, persistent drafts, verified reviewer access,
  email notifications, recorded authenticated approvals, cloud database/object
  storage, OCR, analytics, and tracking are not implemented.
- No deployment, public link, hackathon form submission, or real email delivery
  was performed. The audit PDF is a local report artifact only; it is not proof
  of submission to the organisers.

### Unsupported inputs
- Password-protected and scanned/image-only PDFs, PDFs over 10 pages, files over
  5 MB, UTF-16/UTF-32 text, binary files, and formats other than `.txt`/`.pdf`.
- More than one file per import.

### Honest scope limits
- The checker matches configured terminology, messaging, and claim-trigger
  patterns. It does not determine truth, legality, visual brand consistency,
  full accessibility, or arbitrary tone.
- A clean result is not compliance. A guest review is a demonstration, not an
  approval. The content fingerprint detects change; it is not a signature.

---

## 6. Three Round 3 commitments

1. **Accounts & saved workspaces** — Google sign-in, persistent drafts,
   user-specific access, and a deliberate import path for temporary guest work.
2. **Verified review requests** — assigned authorised reviewers, email
   notifications, recorded authenticated decisions, and approval invalidation.
3. **Custom & versioned brand rules** — temporary user-authored rules for draft
   checks, organisation-specific approved rules, preserved versions, evidence
   expiry, and outdated-guideline identification.

These are commitments, not delivered features. Nothing in the current UI
pretends they work.

---

## Disclosures

- Persistent draft storage is **deferred**.
- Verified reviewer access is **deferred**.
- Guest review is a **demonstration**.
- File import is an **added Round 2 feature**; it was not part of the original
  guest-only flow.
- Not all original proposal commitments are delivered. The verified feature and
  limitation lists above are the accurate scope.

---

## Deployment steps (not performed)

```bash
# Linux host, Python 3.10+
python -m venv .venv
.venv/bin/pip install -r requirements.txt
export INKLOOM_SECRET_KEY="<long random value>"   # name only; no value committed
.venv/bin/flask --app inkloom init-db
.venv/bin/flask --app inkloom seed
.venv/bin/gunicorn run:app --bind 0.0.0.0:${PORT:-8000}
```

- Requires a running application server; a static host cannot serve Flask
  routes. Flask serves `/static/*` itself.
- The SQLite file must be created and seeded once per environment (or mounted
  persistently). `init-db` recreates tables and wipes local data.
- Do not rewrite unknown paths to a frontend index; let Flask render its 404.
- No deployment credentials or host account are configured in this repository.

---

## Submission checklist

| Item | Status |
| --- | --- |
| Working project link | **Pending** — not deployed; no host/credentials configured |
| Accessible repository link | **Pending** — no remote is configured for this workspace |
| Updated PDF | **Available locally** — generated 25 October 2026; organiser submission pending |
| Completed-feature list | **Available** — section 1 |
| Implementation details | **Available** — section 2 and README |
| Changes from plan | **Available** — section 3; direct proposal comparison unavailable because no proposal file is in the repository |
| Three Round 3 improvements | **Available** — section 6 |
