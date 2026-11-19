"""Schema of the PRIVATE research file. Code only — the data never goes into the repository unencrypted.
Rows reference cards by card_key (stable across rebuilds of the public part), never by row id."""
PRIVATE_DDL = """
CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE pending_cards(card_key TEXT PRIMARY KEY CHECK(card_key LIKE 'pkm|unk|pending:%'), name TEXT, note TEXT NOT NULL);
CREATE TABLE card_alias(alias_key TEXT PRIMARY KEY, card_key TEXT NOT NULL, note TEXT);
CREATE TABLE source_docs(doc TEXT PRIMARY KEY, sha256 TEXT NOT NULL, lines INTEGER NOT NULL, frozen INTEGER NOT NULL, imported_at TEXT NOT NULL);
CREATE TABLE research_record(record_id TEXT PRIMARY KEY, card_key TEXT NOT NULL, decision TEXT NOT NULL, check_at TEXT NOT NULL,
  data_day TEXT, rule_version TEXT NOT NULL, evidence_level TEXT, recheck_after TEXT, early_trigger TEXT,
  market_at_check INTEGER, low_at_check INTEGER, supersedes TEXT REFERENCES research_record(record_id),
  doc TEXT NOT NULL REFERENCES source_docs(doc), doc_line INTEGER NOT NULL, original_line TEXT NOT NULL,
  original_sha256 TEXT NOT NULL UNIQUE, v2_json TEXT NOT NULL, UNIQUE(doc, doc_line));
CREATE TABLE evidence(card_key TEXT PRIMARY KEY, identity TEXT NOT NULL, near_mint_checked_at TEXT, sales_evidence TEXT NOT NULL,
  sales_evidence_at TEXT, manual_check_at TEXT, from_record TEXT);
CREATE TABLE screen_run(run_id TEXT PRIMARY KEY, rule_version TEXT NOT NULL, data_day TEXT, ran_at TEXT NOT NULL, note TEXT NOT NULL);
CREATE TABLE screen_result(run_id TEXT NOT NULL REFERENCES screen_run(run_id), card_key TEXT NOT NULL, state TEXT NOT NULL, detail TEXT,
  PRIMARY KEY(run_id, card_key)) WITHOUT ROWID;
CREATE TABLE research_status(card_key TEXT PRIMARY KEY, evidence_grade TEXT NOT NULL, last_screen_run TEXT, last_screen_state TEXT,
  last_record TEXT, last_decision TEXT, recheck_after TEXT, missing TEXT NOT NULL);
"""
PRIVATE_TABLES = ('meta', 'pending_cards', 'card_alias', 'source_docs', 'research_record', 'evidence', 'screen_run', 'screen_result', 'research_status')
