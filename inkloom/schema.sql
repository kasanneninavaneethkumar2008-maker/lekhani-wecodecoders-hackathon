-- Inkloom AI first-version schema.
-- Timestamps are stored as UTC ISO-8601 strings.

DROP TABLE IF EXISTS decisions;
DROP TABLE IF EXISTS issues;
DROP TABLE IF EXISTS checks;
DROP TABLE IF EXISTS drafts;
DROP TABLE IF EXISTS rules;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  email         TEXT NOT NULL UNIQUE,
  display_name  TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role          TEXT NOT NULL CHECK (role IN ('creator', 'reviewer')),
  created_at    TEXT NOT NULL
);

-- Approved rule table. `clause_text` is the approved clause that every
-- displayed issue must quote verbatim; `rule_id` is its stable identifier.
CREATE TABLE rules (
  rule_id    TEXT PRIMARY KEY,
  kind       TEXT NOT NULL CHECK (kind IN ('glossary', 'required', 'forbidden', 'claim')),
  pattern    TEXT NOT NULL,          -- literal term/phrase, or regex source for 'claim'
  replacement TEXT,                  -- glossary preferred wording (nullable)
  applies_to TEXT NOT NULL DEFAULT 'any',  -- 'any' or a content type
  message    TEXT NOT NULL,          -- reviewer-facing explanation
  clause_text TEXT NOT NULL,         -- exact approved clause text (quoted by issues)
  active     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE drafts (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  title        TEXT NOT NULL,
  body         TEXT NOT NULL,
  content_type TEXT NOT NULL,
  audience     TEXT NOT NULL,
  author_id    INTEGER NOT NULL REFERENCES users(id),
  status       TEXT NOT NULL DEFAULT 'draft'
               CHECK (status IN ('draft', 'submitted', 'approved', 'changes_requested')),
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);

-- One row per check run; stores the text snapshot that was checked.
CREATE TABLE checks (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  draft_id      INTEGER NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
  checked_by    INTEGER NOT NULL REFERENCES users(id),
  created_at    TEXT NOT NULL,
  content_type  TEXT NOT NULL,
  body_snapshot TEXT NOT NULL
);

-- Only citation-validated issues are stored. Each row cites a rule by its
-- stable rule_id and quotes the approved clause verbatim.
CREATE TABLE issues (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  check_id     INTEGER NOT NULL REFERENCES checks(id) ON DELETE CASCADE,
  rule_id      TEXT NOT NULL REFERENCES rules(rule_id),
  kind         TEXT NOT NULL,
  message      TEXT NOT NULL,
  clause_quote TEXT NOT NULL,
  excerpt      TEXT,
  is_prompt    INTEGER NOT NULL DEFAULT 0
);

-- Reviewer decisions: decision, reviewer, and time of decision.
CREATE TABLE decisions (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  draft_id    INTEGER NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
  reviewer_id INTEGER NOT NULL REFERENCES users(id),
  decision    TEXT NOT NULL CHECK (decision IN ('approved', 'needs_changes')),
  comment     TEXT,
  created_at  TEXT NOT NULL
);

CREATE INDEX idx_drafts_author ON drafts(author_id);
CREATE INDEX idx_checks_draft ON checks(draft_id);
CREATE INDEX idx_issues_check ON issues(check_id);
CREATE INDEX idx_decisions_draft ON decisions(draft_id);
