# Lekhani (लेखनी) — Final Verification & Audit Report

**Date:** 25 October 2026

**Audited Directory:** Local project working copy (full path omitted for privacy)

**Host Environment:** Windows 11 (NT 10.0), Python 3.14.7, Node v24.22.1, npm 11.19.1

**Git Branch & Worktree:** Branch `main`; worktree listing completed successfully.

**Test Suite Status:** **163 passed, 0 failed, 0 skipped** (`pytest-9.1.1`)

---

## 1. Executive Summary & Verdict

### **Verdict: Core Workflow Verified Working**
The Lekhani application's complete core user journey, review workspace, and deterministic rule validation engine are fully operational. During this final verification, one genuine syntax defect in `inkloom/workbench.py` (line continuation artifact) and the previously noted absence of CSRF protection were addressed with lightweight, dependency-free defenses and comprehensive tests.

---

## 2. Exact Commands Run & Results

| Check Category | Exact Command Executed | Exit Code | Result Summary |
| :--- | :--- | :--- | :--- |
| **Git Worktree Check** | `git -c safe.directory="C:/Users/kasan/OneDrive/Documents/codeaxis/inkloom ai" worktree list --porcelain -z` | `0` | Confirmed single worktree on branch `refs/heads/main` |
| **Dependency Consistency** | `.\.venv\Scripts\python -m pip check` | `0` | `No broken requirements found.` |
| **Syntax Compilation Check** | `.\.venv\Scripts\python -m py_compile inkloom\*.py tests\*.py` | `0` | All Python source files compiled cleanly to bytecode |
| **Full Automated Test Suite** | `.\.venv\Scripts\python -m pytest -p no:cacheprovider` | `0` | **163 passed in 8.27s** (0 failures, 0 skipped) |
| **CSRF Test Suite** | `.\.venv\Scripts\python -m pytest tests\test_csrf.py -v` | `0` | **8 passed in 0.48s** |

---

## 3. Verified Workflows and Pages

1. **Guest Entry & Welcome (`/`):**
   - Welcomes user with Lekhani brand and लेखनी script.
   - Rejects blank and whitespace-only names; truncates names over 60 characters.
   - Escapes HTML entities safely (`<script>` rendered as `&lt;script&gt;`).
   - Supports slide-to-enter (`role="slider"`) and accessible fallback ("Continue without sliding").
   - Stores display name in signed session cookie; writes zero database rows.
2. **Page Navigation & Access Control:**
   - Session-gated pages (`/home`, `/about`, `/contact`, `/report-issue`, `/workspace`, `/trust-lab`) redirect unauthenticated visitors (HTTP 302) to `/`.
   - "Leave workspace" (`/guest/logout`) clears session cookies and flashes exit confirmation.
3. **Review Workspace (`/workspace`):**
   - Opens completely empty; word/character counts at 0; status is "Not checked".
   - Explicitly loads the fictional GreenLeaf sample only upon user confirmation.
   - Running checks against sample rules (`demo-v1`) produces exactly five deterministic findings (`GLOSS-01`, `GLOSS-02`, `MSG-01`, `CLAIM-01`, `CLAIM-02`).
   - Re-checking revised sample text produces zero findings under active rules.
4. **Stale Results & Controlled Terminology Replacement:**
   - Any edits to draft text, content type, audience, or rule set immediately mark findings "Changes since check".
   - Single-occurrence replacement replaces only the exact matched span and verifies the snapshot fingerprint.
   - Stale replacements are rejected with HTTP 409; invalid offsets are rejected with HTTP 400.
   - "Undo replacement" restores earlier draft text and clears stale status.
5. **Guest Review Demonstration:**
   - Requires an active, completed check; records "Needs changes" or "Mark approved — demo".
   - Clearly displays "Guest demonstration — identity not verified".
   - Invalidation occurs automatically if the reviewed draft text or context is altered.
6. **File Import & Review Packs:**
   - File import validates format by magic bytes (detects `%PDF-` signature and UTF-8 text without NUL bytes).
   - Enforces 5 MB upload size, 10 PDF pages, and 100,000 character draft limit. Shows editable preview.
   - Review-pack export produces versioned JSON with SHA-256 draft integrity fingerprint and guest disclosures.
   - Review-pack import validates schema, re-runs checks using local rules, and refuses untrusted approval claims.
   - Print summary (`/workspace/print`) generates clean print layout with guest disclosures and stale check indicators.
7. **Trust Lab & Simulator (`/trust-lab`):**
   - Evaluates three reference validation cases (valid citation, unknown rule ID, altered quotation).
   - Simulator compares `v1` vs. `v2` guidelines on sample text using pure functions.
8. **Public Content & Notices:**
   - About page credits "Built by Team Lekhani"; no personal names or biographies present.
   - Contact and Report an Issue forms are honest disabled previews; do not claim message delivery.
   - Round 3 roadmap on Home clearly designates planned features as unavailable in the current version.
   - Custom 404 page handles non-existent routes with clear recovery navigation.

---

## 4. Bugs Found, Root Causes, and Fixes Applied

### 1. Syntax Error in `inkloom/workbench.py`
- **Observed Failure:** Compiling `inkloom/workbench.py` or loading it without pre-existing `.pyc` cache raised `SyntaxError: unexpected character after line continuation character` at line 391.
- **Root Cause:** A literal backslash `\` followed by `n` had been appended to the end of `inkloom/workbench.py`.
- **Fix Applied:** Removed trailing `\n` literal from line 391.
- **Rerun Result:** `python -m py_compile inkloom/workbench.py` exited with code 0.

### 2. Missing CSRF Protection on State-Changing POST Routes
- **Observed Failure:** Forms and endpoints accepted state-changing POST requests without validating origin or session tokens.
- **Root Cause:** Application lacked CSRF middleware and token generation helpers.
- **Fix Applied:**
  1. Implemented `inkloom/csrf.py` with Origin/Referer verification and session-bound synchronizer tokens (`session["_csrf_token"]`).
  2. Registered `init_csrf(app)` in `inkloom/__init__.py`.
  3. Added `<meta name="csrf-token" content="{{ csrf_token() }}">` to `inkloom/templates/base.html`.
  4. Injected `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` into all form templates (`index.html`, `workspace.html`, `_carried_fields.html`, `trust_lab.html`, `guest/role.html`, `contact.html`, `report_issue.html`, `creator/draft_form.html`, `creator/draft_detail.html`, `reviewer/review_detail.html`).
  5. Updated AJAX fetch in `inkloom/static/lek.js` to send `X-CSRF-Token` header and `csrf_token` body.
  6. Added 8 comprehensive unit and integration tests in `tests/test_csrf.py`.
- **Rerun Result:** All 8 CSRF tests passed; full test suite passed (163 tests).

### 3. Stale Documentation in README.md and ROUND2_SUBMISSION_NOTES.md
- **Observed Inaccuracy:** Documents claimed "No CSRF tokens" and listed outdated test counts (155).
- **Fix Applied:** Updated `README.md` and `ROUND2_SUBMISSION_NOTES.md` to document the implemented CSRF protection, updated test suite totals (163 passed), and added `csrf.py` / `test_csrf.py` to project manifests.

---

## 5. Scope & Evidence Status Classification

| Scope Item | Status Label | Verification Detail |
| :--- | :--- | :--- |
| **Deterministic Rule Checker** | **IMPLEMENTED** | Verified via 163 unit/integration tests and in-memory execution. |
| **Citation Validator** | **IMPLEMENTED** | Discards altered quotations, unknown rule IDs, and mismatched versions. |
| **Guest Workspace & Session Gating** | **IMPLEMENTED** | Verified end-to-end; session-only signed cookie; zero database writes. |
| **TXT / Text-PDF Import** | **IMPLEMENTED** | Byte sniffing, length checks, editable preview, and failure guards verified. |
| **Review-Pack JSON Export / Import** | **IMPLEMENTED** | SHA-256 fingerprinting, schema validation, and local re-checking verified. |
| **CSRF & Origin Protection** | **IMPLEMENTED** | Synchronizer tokens and Origin/Referer verification implemented and tested. |
| **Login Video Asset / Playback** | **NOT IMPLEMENTED** | Welcome page uses CSS glow effects and SVG artwork; no `<video>` element exists. |
| **Google Sign-In / OAuth** | **NOT IMPLEMENTED** | Deferred to Round 3; honest "Coming soon" notice displayed. |
| **Persistent User Accounts / Drafts** | **NOT IMPLEMENTED** | Deferred to Round 3; guest work is intentionally ephemeral. |
| **Contact / Issue Backend Delivery** | **NOT IMPLEMENTED** | Deferred to Round 3; preview forms are visibly disabled. |
| **OCR for Scanned PDFs** | **NOT IMPLEMENTED** | Scanned PDFs display an explicit message directing the user to paste manually. |
| **Public Deployment URL** | **NOT PROVIDED** | Application is not deployed to cloud hosting; repository is local. |
| **Original Evaluation Benchmark Metrics** | **NOT MEASURED** | 8/10 planted violations, clean draft error rates, and human review timing targets had no test fixtures or human timing data in the repository. |

---

## 6. Blocked Checks

1. **Gunicorn Server Execution:** **BLOCKED** on this host because Gunicorn requires POSIX `fcntl` and process forking, which are unsupported on Windows. Production deployment must target a Linux container or host.
2. **Headless Chrome CDP Browser Script (`_audit_round2.mjs`):** **BLOCKED** from execution during read-only audit because the script writes fixture files to `instance/audit-files` and downloads to `instance/audit-downloads`.

---

## 7. Remaining Limitations & Round 3 Commitments

1. **Host-Level Body Size Limit:** Flask enforces limits per field and streams up to 5 MB + 1 byte for uploads; production reverse proxies (Nginx/Caddy) should set `client_max_body_size 10M`.
2. **Unsaved Work on Hard Refresh:** Draft text lives in the browser DOM and request state; hard page refresh (`Ctrl+F5`) returns to an empty workspace. (Review-pack export is the designated save mechanism).
3. **Round 3 Roadmap Commitments:**
   - Google Sign-In and persistent workspace accounts.
   - Verified reviewer assignments and authenticated decision recording.
   - Temporary user-authored rule sets for draft checks, plus versioned
     organizational brand guidelines with evidence expiration.
