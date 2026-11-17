"""SQLite persistence layer (stdlib sqlite3).

The build spec suggested SQLAlchemy; plain sqlite3 is used so the prototype runs with no
extra dependency. All writes go through `transaction()` so a failure rolls back cleanly.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    customer_name TEXT,
    email_address TEXT,
    tenure_months INTEGER,
    contract_type TEXT,
    payment_method TEXT,
    paperless_billing TEXT,
    monthly_charges REAL,
    total_charges REAL,
    num_services INTEGER,
    customer_satisfaction REAL,
    num_complaints REAL,
    customer_service_calls INTEGER,
    late_payments INTEGER,
    avg_monthly_gb REAL,
    days_since_last_interaction INTEGER,
    churn_status INTEGER,
    usage_last_3m REAL,
    usage_prev_3m REAL,
    last_active_date TEXT,
    bill_due_date TEXT,
    amount_due REAL,
    payment_status TEXT,
    on_time_payment_ratio REAL,
    marketing_consent INTEGER,
    last_contacted_date TEXT,
    customer_support_contact TEXT,
    contact_frequency TEXT,
    data_source TEXT,
    synthetic_seed INTEGER,
    ingested_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_customers_source ON customers(data_source);

CREATE TABLE IF NOT EXISTS offers (
    offer_id TEXT PRIMARY KEY,
    offer_json TEXT NOT NULL,
    catalog_version TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS policies (
    doc_id TEXT PRIMARY KEY,
    doc_name TEXT,
    version TEXT,
    sha256 TEXT,
    path TEXT,
    chunk_count INTEGER,
    ingested_at TEXT
);

CREATE TABLE IF NOT EXISTS customer_segments (
    customer_id TEXT PRIMARY KEY,
    status TEXT,
    primary_segment TEXT,
    segments_json TEXT,
    reason_codes_json TEXT,
    confidence REAL,
    policy_version TEXT,
    classified_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_segments_primary ON customer_segments(primary_segment);

CREATE TABLE IF NOT EXISTS strategies (
    strategy_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT,
    draft_id TEXT,
    strategy_json TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS drafts (
    draft_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    status TEXT NOT NULL,
    subject TEXT,
    body TEXT,
    cta TEXT,
    objective TEXT,
    tone TEXT,
    template_id TEXT,
    offer_id TEXT,
    reminder_stage INTEGER,
    facts_used_json TEXT,
    strategy_json TEXT,
    segment_json TEXT,
    block_reasons_json TEXT,
    prompt_version TEXT,
    model_name TEXT,
    policy_version TEXT,
    generation_mode TEXT,
    attempt_count INTEGER DEFAULT 0,
    content_hash TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);
CREATE INDEX IF NOT EXISTS idx_drafts_customer ON drafts(customer_id);

CREATE TABLE IF NOT EXISTS validation_reports (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id TEXT,
    source TEXT,
    passed INTEGER,
    retry_recommended INTEGER,
    failure_categories_json TEXT,
    findings_json TEXT,
    tone_scores_json TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_val_draft ON validation_reports(draft_id);

CREATE TABLE IF NOT EXISTS review_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id TEXT,
    reviewer TEXT,
    action TEXT,
    reason TEXT,
    feedback TEXT,
    diff_json TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS contact_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT,
    draft_id TEXT UNIQUE,
    channel TEXT,
    template_id TEXT,
    objective TEXT,
    is_marketing INTEGER,
    content_hash TEXT,
    sent_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_contact_customer ON contact_history(customer_id);

CREATE TABLE IF NOT EXISTS mock_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id TEXT UNIQUE,
    message_id TEXT,
    customer_id TEXT,
    to_address_masked TEXT,
    status TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS generation_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id TEXT,
    attempt_no INTEGER,
    mode TEXT,
    model_name TEXT,
    prompt_version TEXT,
    latency_ms INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    passed INTEGER,
    failure_categories_json TEXT,
    error TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_attempts_draft ON generation_attempts(draft_id);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id TEXT,
    customer_id TEXT,
    event TEXT,
    actor TEXT,
    payload_json TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_draft ON audit_logs(draft_id);
"""


def _default(o: Any) -> Any:
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if hasattr(o, "model_dump"):
        return o.model_dump(mode="json")
    if isinstance(o, set):
        return sorted(o)
    return str(o)


def to_json(obj: Any) -> str:
    return json.dumps(obj, default=_default, ensure_ascii=False)


def from_json(text: str | None, default: Any = None) -> Any:
    if text in (None, ""):
        return default
    return json.loads(text)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0).isoformat() + "Z"


class Database:
    """Thin wrapper: one short-lived connection per operation, safe across threads."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = self._connect()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def init_schema(self) -> None:
        with self.transaction() as conn:
            conn.executescript(SCHEMA)

    def query(self, sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
        with self.transaction() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def query_one(self, sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: tuple | dict = ()) -> int:
        with self.transaction() as conn:
            cur = conn.execute(sql, params)
            return cur.lastrowid or cur.rowcount

    def executemany(self, sql: str, rows: list[tuple] | list[dict]) -> None:
        with self.transaction() as conn:
            conn.executemany(sql, rows)

    def scalar(self, sql: str, params: tuple | dict = ()) -> Any:
        row = self.query_one(sql, params)
        return next(iter(row.values())) if row else None
