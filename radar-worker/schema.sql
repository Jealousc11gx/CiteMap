CREATE TABLE IF NOT EXISTS profiles (
  project_id TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  arxiv_id TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  abstract TEXT NOT NULL DEFAULT '',
  authors TEXT NOT NULL DEFAULT '[]',
  categories TEXT NOT NULL DEFAULT '[]',
  affiliations TEXT NOT NULL DEFAULT '[]',
  corresponding_authors TEXT NOT NULL DEFAULT '[]',
  published_date TEXT,
  arxiv_url TEXT NOT NULL DEFAULT '',
  pdf_url TEXT,
  score REAL NOT NULL DEFAULT 0,
  reason TEXT NOT NULL DEFAULT '',
  tldr TEXT NOT NULL DEFAULT '',
  ai_summary TEXT NOT NULL DEFAULT '',
  title_zh TEXT NOT NULL DEFAULT '',
  abstract_zh TEXT NOT NULL DEFAULT '',
  core_contribution TEXT NOT NULL DEFAULT '',
  method TEXT NOT NULL DEFAULT '',
  result TEXT NOT NULL DEFAULT '',
  limitations TEXT NOT NULL DEFAULT '',
  user_state TEXT NOT NULL DEFAULT 'unread',
  emailed_at TEXT,
  click_token TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(project_id, arxiv_id)
);

CREATE TABLE IF NOT EXISTS events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  arxiv_id TEXT NOT NULL,
  type TEXT NOT NULL,
  state TEXT,
  payload TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_items_project ON items(project_id);
CREATE INDEX IF NOT EXISTS idx_events_project_event ON events(project_id, event_id);
