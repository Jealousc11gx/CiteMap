"""CiteMap - 数据模型与存储层。"""

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Optional

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "papers.db"
DEFAULT_PROJECT_ID = "project_default"
DEFAULT_PROJECT_NAME = "未分类"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            id TEXT PRIMARY KEY,
            title TEXT,
            abstract TEXT,
            tldr TEXT,
            core_contribution TEXT,
            primary_domain TEXT,
            subfields TEXT,
            venue TEXT,
            venue_year INTEGER,
            venue_evidence TEXT,
            venue_checked_at TEXT,
            arxiv_comment TEXT,
            journal_ref TEXT,
            published_date TEXT,
            updated_date TEXT,
            categories TEXT,
            pdf_path TEXT,
            md_path TEXT,
            note_edited_at TEXT,
            source TEXT DEFAULT 'local',
            arxiv_url TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            enhanced_at TEXT
        )
    """)

    # 兼容已存在的旧库：动态添加 md_path 列
    try:
        cur.execute("ALTER TABLE papers ADD COLUMN md_path TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE papers ADD COLUMN note_edited_at TEXT")
    except sqlite3.OperationalError:
        pass
    for column, column_type in (
        ("tldr", "TEXT"),
        ("primary_domain", "TEXT"),
        ("subfields", "TEXT"),
        ("venue", "TEXT"),
        ("venue_year", "INTEGER"),
        ("venue_evidence", "TEXT"),
        ("venue_checked_at", "TEXT"),
        ("arxiv_comment", "TEXT"),
        ("journal_ref", "TEXT"),
    ):
        try:
            cur.execute(f"ALTER TABLE papers ADD COLUMN {column} {column_type}")
        except sqlite3.OperationalError:
            pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS authors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            normalized_name TEXT,
            affiliation TEXT,
            UNIQUE(name, affiliation)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS institutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            normalized_name TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS paper_authors (
            paper_id TEXT,
            author_id INTEGER,
            author_order INTEGER,
            PRIMARY KEY (paper_id, author_id),
            FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
            FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS paper_institutions (
            paper_id TEXT,
            institution_id INTEGER,
            PRIMARY KEY (paper_id, institution_id),
            FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
            FOREIGN KEY (institution_id) REFERENCES institutions(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            lead_institution_id INTEGER,
            description TEXT,
            FOREIGN KEY (lead_institution_id) REFERENCES institutions(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS team_members (
            team_id INTEGER,
            author_id INTEGER,
            role TEXT DEFAULT 'member',
            PRIMARY KEY (team_id, author_id),
            FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
            FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS paper_teams (
            paper_id TEXT,
            team_id INTEGER,
            PRIMARY KEY (paper_id, team_id),
            FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
            FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_papers_source ON papers(source)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_papers_published ON papers(published_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_paper_authors_paper ON paper_authors(paper_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_paper_authors_author ON paper_authors(author_id)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE,
            type TEXT NOT NULL,
            UNIQUE(name, type)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS paper_tags (
            paper_id TEXT NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (paper_id, tag_id),
            FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_paper_tags_paper ON paper_tags(paper_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tags_type ON tags(type)")

    # 项目与论文是多对多关系，同一篇论文可服务多个研究项目。
    cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            description TEXT DEFAULT '',
            is_system INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS project_papers (
            project_id TEXT NOT NULL,
            paper_id TEXT NOT NULL,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (project_id, paper_id),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_project_papers_project ON project_papers(project_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_project_papers_paper ON project_papers(paper_id)")
    cur.execute(
        "INSERT OR IGNORE INTO projects (id, name, is_system) VALUES (?, ?, 1)",
        (DEFAULT_PROJECT_ID, DEFAULT_PROJECT_NAME),
    )

    # 论文雷达：候选元数据与项目匹配分开保存，候选不会污染正式 papers 表。
    cur.execute("""
        CREATE TABLE IF NOT EXISTS radar_configs (
            project_id TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            categories TEXT NOT NULL DEFAULT '[]',
            include_keywords TEXT NOT NULL DEFAULT '[]',
            exclude_keywords TEXT NOT NULL DEFAULT '[]',
            profile_override TEXT NOT NULL DEFAULT '',
            anchor_paper_ids TEXT NOT NULL DEFAULT '[]',
            top_k INTEGER NOT NULL DEFAULT 10,
            min_score REAL NOT NULL DEFAULT 0.0,
            include_cross_list INTEGER NOT NULL DEFAULT 1,
            send_empty INTEGER NOT NULL DEFAULT 0,
            fetch_limit INTEGER NOT NULL DEFAULT 100,
            debug INTEGER NOT NULL DEFAULT 0,
            compute_mode TEXT NOT NULL DEFAULT 'cloud',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)
    # 兼容已存在的雷达数据库。
    for column, definition in (
        ("include_cross_list", "INTEGER NOT NULL DEFAULT 1"),
        ("send_empty", "INTEGER NOT NULL DEFAULT 0"),
        ("fetch_limit", "INTEGER NOT NULL DEFAULT 100"),
        ("debug", "INTEGER NOT NULL DEFAULT 0"),
        ("compute_mode", "TEXT NOT NULL DEFAULT 'cloud'"),
    ):
        try:
            cur.execute(f"ALTER TABLE radar_configs ADD COLUMN {column} {definition}")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
    cur.execute("""
        CREATE TABLE IF NOT EXISTS radar_runs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            run_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            candidate_count INTEGER NOT NULL DEFAULT 0,
            matched_count INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            started_at TEXT DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            UNIQUE(project_id, run_date)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_radar_runs_project ON radar_runs(project_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_radar_runs_date ON radar_runs(run_date)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS radar_candidates (
            id TEXT PRIMARY KEY,
            arxiv_id TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL DEFAULT '',
            abstract TEXT NOT NULL DEFAULT '',
            authors TEXT NOT NULL DEFAULT '[]',
            categories TEXT NOT NULL DEFAULT '[]',
            affiliations TEXT NOT NULL DEFAULT '[]',
            corresponding_authors TEXT NOT NULL DEFAULT '[]',
            published_date TEXT,
            updated_date TEXT,
            arxiv_url TEXT NOT NULL DEFAULT '',
            pdf_url TEXT,
            tldr TEXT,
            ai_summary TEXT,
            title_zh TEXT,
            abstract_zh TEXT,
            core_contribution TEXT,
            method TEXT,
            result TEXT,
            limitations TEXT,
            first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for column in ("tldr", "ai_summary", "title_zh", "abstract_zh", "core_contribution", "method", "result", "limitations", "affiliations", "corresponding_authors"):
        try:
            default = " NOT NULL DEFAULT '[]'" if column in {"affiliations", "corresponding_authors"} else ""
            cur.execute(f"ALTER TABLE radar_candidates ADD COLUMN {column} TEXT{default}")
        except sqlite3.OperationalError:
            pass
    cur.execute("CREATE INDEX IF NOT EXISTS idx_radar_candidates_published ON radar_candidates(published_date)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS radar_matches (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            run_id TEXT,
            score REAL NOT NULL DEFAULT 0.0,
            reason TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL DEFAULT 'unread'
                CHECK (state IN ('unread', 'read', 'saved', 'dismissed')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (candidate_id) REFERENCES radar_candidates(id) ON DELETE CASCADE,
            FOREIGN KEY (run_id) REFERENCES radar_runs(id) ON DELETE SET NULL,
            UNIQUE(project_id, candidate_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_radar_matches_project ON radar_matches(project_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_radar_matches_state ON radar_matches(state)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS radar_sync_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS radar_pending_operations (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            match_id TEXT NOT NULL,
            operation TEXT NOT NULL
                CHECK (operation IN ('read', 'save', 'dismiss')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            retry_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (match_id) REFERENCES radar_matches(id) ON DELETE CASCADE,
            UNIQUE(match_id, operation)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_radar_pending_project ON radar_pending_operations(project_id)")

    # 聊天会话与消息历史
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY,
            title TEXT,
            project_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)
    try:
        cur.execute("ALTER TABLE chat_sessions ADD COLUMN project_id TEXT")
    except sqlite3.OperationalError:
        pass
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            papers TEXT,
            tool_calls TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        )
    """)
    # 兼容已存在的旧库：动态添加 tool_calls 列
    try:
        cur.execute("ALTER TABLE chat_messages ADD COLUMN tool_calls TEXT")
    except sqlite3.OperationalError:
        pass
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON chat_messages(created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_project ON chat_sessions(project_id)")

    # 一次性兼容旧库，同时保证没有项目归属的论文、会话可继续访问。
    cur.execute("""
        INSERT OR IGNORE INTO project_papers (project_id, paper_id)
        SELECT ?, p.id
        FROM papers p
        WHERE NOT EXISTS (
            SELECT 1 FROM project_papers pp WHERE pp.paper_id = p.id
        )
    """, (DEFAULT_PROJECT_ID,))
    cur.execute(
        "UPDATE chat_sessions SET project_id = ? WHERE project_id IS NULL",
        (DEFAULT_PROJECT_ID,),
    )

    conn.commit()
    conn.close()


def upsert_paper(conn: sqlite3.Connection, paper: dict) -> None:
    payload = {
        "arxiv_comment": None,
        "journal_ref": None,
        **paper,
    }
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO papers (
            id, title, abstract, published_date, updated_date, categories,
            pdf_path, source, arxiv_url, arxiv_comment, journal_ref
        )
        VALUES (
            :id, :title, :abstract, :published_date, :updated_date, :categories,
            :pdf_path, :source, :arxiv_url, :arxiv_comment, :journal_ref
        )
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            abstract=excluded.abstract,
            updated_date=excluded.updated_date,
            categories=excluded.categories,
            pdf_path=COALESCE(excluded.pdf_path, papers.pdf_path),
            source=excluded.source,
            arxiv_url=excluded.arxiv_url,
            arxiv_comment=COALESCE(excluded.arxiv_comment, papers.arxiv_comment),
            journal_ref=COALESCE(excluded.journal_ref, papers.journal_ref)
    """, payload)


def get_paper(conn: sqlite3.Connection, paper_id: str) -> Optional[dict]:
    cur = conn.cursor()
    cur.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def get_paper_tags(conn: sqlite3.Connection, paper_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT t.name, t.type
        FROM paper_tags pt
        JOIN tags t ON t.id = pt.tag_id
        WHERE pt.paper_id = ?
        ORDER BY t.type, t.name COLLATE NOCASE
        """,
        (paper_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def hydrate_paper(conn: sqlite3.Connection, paper: dict) -> dict:
    """补充 JSON 字段与论文关系，供 API、工具统一返回。"""
    result = dict(paper)
    raw_subfields = result.get("subfields")
    try:
        result["subfields"] = json.loads(raw_subfields) if raw_subfields else []
    except (TypeError, json.JSONDecodeError):
        result["subfields"] = []
    result["tags"] = get_paper_tags(conn, result["id"])
    result["authors"] = [
        row["name"]
        for row in conn.execute(
            """
            SELECT a.name
            FROM paper_authors pa
            JOIN authors a ON a.id = pa.author_id
            WHERE pa.paper_id = ?
            ORDER BY pa.author_order
            """,
            (result["id"],),
        ).fetchall()
    ]
    result["teams"] = [
        row["name"]
        for row in conn.execute(
            """
            SELECT t.name
            FROM paper_teams pt
            JOIN teams t ON t.id = pt.team_id
            WHERE pt.paper_id = ?
            ORDER BY t.name COLLATE NOCASE
            """,
            (result["id"],),
        ).fetchall()
    ]
    return result


def list_papers(
    db_path: Optional[Path] = None,
    source: Optional[str] = None,
    project_id: Optional[str] = None,
) -> pd.DataFrame:
    conn = get_connection(db_path)
    sql = "SELECT DISTINCT p.* FROM papers p"
    conditions = []
    params: list[str] = []
    if project_id:
        sql += " JOIN project_papers pp ON pp.paper_id = p.id"
        conditions.append("pp.project_id = ?")
        params.append(project_id)
    if source:
        conditions.append("p.source = ?")
        params.append(source)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY p.published_date DESC"
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    # Ensure JSON-safe output by replacing NaN/NaT with None
    df = df.where(pd.notnull(df), None)
    return df


# ──────────────────────────────
# 聊天会话与消息
# ──────────────────────────────

def create_chat_session(
    conn: sqlite3.Connection,
    session_id: str,
    title: str = "",
    project_id: str = DEFAULT_PROJECT_ID,
) -> None:
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO chat_sessions (id, title, project_id) VALUES (?, ?, ?)",
        (session_id, title, project_id),
    )
    cur.execute(
        "UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (session_id,),
    )
    conn.commit()


def update_chat_session_title(conn: sqlite3.Connection, session_id: str, title: str) -> None:
    cur = conn.cursor()
    cur.execute(
        "UPDATE chat_sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (title, session_id),
    )
    conn.commit()


def get_chat_session(conn: sqlite3.Connection, session_id: str) -> Optional[dict]:
    cur = conn.cursor()
    cur.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def list_chat_sessions(
    conn: sqlite3.Connection,
    limit: int = 50,
    project_id: Optional[str] = None,
) -> list[dict]:
    cur = conn.cursor()
    if project_id:
        cur.execute(
            "SELECT * FROM chat_sessions WHERE project_id = ? ORDER BY updated_at DESC LIMIT ?",
            (project_id, limit),
        )
    else:
        cur.execute(
            "SELECT * FROM chat_sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
    return [dict(row) for row in cur.fetchall()]


# ──────────────────────────────
# 项目与论文归属
# ──────────────────────────────

def get_project(conn: sqlite3.Connection, project_id: str) -> Optional[dict]:
    row = conn.execute(
        """
        SELECT p.*, COUNT(pp.paper_id) AS paper_count
        FROM projects p
        LEFT JOIN project_papers pp ON pp.project_id = p.id
        WHERE p.id = ?
        GROUP BY p.id
        """,
        (project_id,),
    ).fetchone()
    return dict(row) if row else None


def list_projects(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("""
        SELECT p.*, COUNT(pp.paper_id) AS paper_count
        FROM projects p
        LEFT JOIN project_papers pp ON pp.project_id = p.id
        GROUP BY p.id
        ORDER BY p.is_system ASC, p.updated_at DESC, p.name COLLATE NOCASE ASC
    """).fetchall()
    return [dict(row) for row in rows]


def create_project(conn: sqlite3.Connection, name: str, description: str = "") -> dict:
    project_id = f"project_{uuid.uuid4().hex}"
    conn.execute(
        "INSERT INTO projects (id, name, description) VALUES (?, ?, ?)",
        (project_id, name.strip(), description.strip()),
    )
    conn.commit()
    return get_project(conn, project_id) or {}


def update_project(
    conn: sqlite3.Connection,
    project_id: str,
    name: str,
    description: Optional[str] = None,
) -> Optional[dict]:
    project = get_project(conn, project_id)
    if not project:
        return None
    if project["is_system"]:
        raise ValueError("未分类项目不能重命名")
    if description is None:
        conn.execute(
            "UPDATE projects SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (name.strip(), project_id),
        )
    else:
        conn.execute(
            "UPDATE projects SET name = ?, description = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (name.strip(), description.strip(), project_id),
        )
    conn.commit()
    return get_project(conn, project_id)


def list_available_papers(conn: sqlite3.Connection, project_id: str) -> list[dict]:
    """列出尚未加入目标项目的论文，并附带现有项目归属。"""
    rows = conn.execute("""
        SELECT p.*, source_project.id AS source_project_id, source_project.name AS source_project_name
        FROM papers p
        LEFT JOIN project_papers source_pp ON source_pp.paper_id = p.id
        LEFT JOIN projects source_project ON source_project.id = source_pp.project_id
        WHERE NOT EXISTS (
            SELECT 1
            FROM project_papers target_pp
            WHERE target_pp.paper_id = p.id AND target_pp.project_id = ?
        )
        ORDER BY p.published_date DESC, p.title COLLATE NOCASE ASC
    """, (project_id,)).fetchall()

    papers: dict[str, dict] = {}
    for row in rows:
        data = dict(row)
        source_project_id = data.pop("source_project_id", None)
        source_project_name = data.pop("source_project_name", None)
        paper = papers.setdefault(data["id"], {**data, "projects": []})
        if source_project_id:
            paper["projects"].append({"id": source_project_id, "name": source_project_name})
    return [hydrate_paper(conn, paper) for paper in papers.values()]


def add_paper_to_project(conn: sqlite3.Connection, project_id: str, paper_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO project_papers (project_id, paper_id) VALUES (?, ?)",
        (project_id, paper_id),
    )
    conn.execute(
        "UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (project_id,),
    )
    if project_id != DEFAULT_PROJECT_ID:
        conn.execute(
            "DELETE FROM project_papers WHERE project_id = ? AND paper_id = ?",
            (DEFAULT_PROJECT_ID, paper_id),
        )
    conn.commit()


def remove_paper_from_project(conn: sqlite3.Connection, project_id: str, paper_id: str) -> None:
    conn.execute(
        "DELETE FROM project_papers WHERE project_id = ? AND paper_id = ?",
        (project_id, paper_id),
    )
    remaining = conn.execute(
        "SELECT 1 FROM project_papers WHERE paper_id = ? LIMIT 1",
        (paper_id,),
    ).fetchone()
    if not remaining:
        conn.execute(
            "INSERT OR IGNORE INTO project_papers (project_id, paper_id) VALUES (?, ?)",
            (DEFAULT_PROJECT_ID, paper_id),
        )
    conn.commit()


def delete_project(conn: sqlite3.Connection, project_id: str) -> bool:
    project = get_project(conn, project_id)
    if not project:
        return False
    if project["is_system"]:
        raise ValueError("系统项目不能删除")

    paper_ids = [
        row["paper_id"]
        for row in conn.execute(
            "SELECT paper_id FROM project_papers WHERE project_id = ?",
            (project_id,),
        ).fetchall()
    ]
    # 旧库通过 ALTER TABLE 获得 project_id，没有列级 FK，需要显式清理。
    conn.execute("""
        DELETE FROM chat_messages
        WHERE session_id IN (SELECT id FROM chat_sessions WHERE project_id = ?)
    """, (project_id,))
    conn.execute("DELETE FROM chat_sessions WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM radar_pending_operations WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM radar_matches WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM radar_runs WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM radar_configs WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    for paper_id in paper_ids:
        remaining = conn.execute(
            "SELECT 1 FROM project_papers WHERE paper_id = ? LIMIT 1",
            (paper_id,),
        ).fetchone()
        if not remaining:
            conn.execute(
                "INSERT OR IGNORE INTO project_papers (project_id, paper_id) VALUES (?, ?)",
                (DEFAULT_PROJECT_ID, paper_id),
            )
    conn.commit()
    return True


def delete_chat_session(conn: sqlite3.Connection, session_id: str) -> None:
    cur = conn.cursor()
    cur.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
    cur.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    conn.commit()


def add_chat_message(
    conn: sqlite3.Connection,
    message_id: str,
    session_id: str,
    role: str,
    content: str,
    papers: Optional[str] = None,
    tool_calls: Optional[str] = None,
) -> None:
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO chat_messages (id, session_id, role, content, papers, tool_calls) VALUES (?, ?, ?, ?, ?, ?)",
        (message_id, session_id, role, content, papers, tool_calls),
    )
    cur.execute(
        "UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (session_id,),
    )
    conn.commit()


def get_chat_messages(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    )
    return [dict(row) for row in cur.fetchall()]
