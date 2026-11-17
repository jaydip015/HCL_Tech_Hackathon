"""Customer persistence, search and pagination (Person 1)."""
from __future__ import annotations

from typing import Any

from backend.database.db import Database, from_json, now_iso, to_json

CUSTOMER_COLUMNS = [
    "customer_id", "customer_name", "email_address", "tenure_months", "contract_type", "payment_method",
    "paperless_billing", "monthly_charges", "total_charges", "num_services", "customer_satisfaction",
    "num_complaints", "customer_service_calls", "late_payments", "avg_monthly_gb",
    "days_since_last_interaction", "churn_status", "usage_last_3m", "usage_prev_3m", "last_active_date",
    "bill_due_date", "amount_due", "payment_status", "on_time_payment_ratio", "marketing_consent",
    "last_contacted_date", "customer_support_contact", "contact_frequency", "data_source", "synthetic_seed",
    "ingested_at",
]

_SORTABLE = {"customer_id", "tenure_months", "monthly_charges", "amount_due", "days_since_last_interaction"}


class CustomerRepository:
    def __init__(self, db: Database):
        self.db = db

    # ---------------------------------------------------------------- writes
    def upsert_many(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        cols = ", ".join(CUSTOMER_COLUMNS)
        params = ", ".join(f":{c}" for c in CUSTOMER_COLUMNS)
        rows = []
        for r in records:
            row = {c: r.get(c) for c in CUSTOMER_COLUMNS}
            row["ingested_at"] = row.get("ingested_at") or now_iso()
            if isinstance(row.get("marketing_consent"), bool):
                row["marketing_consent"] = int(row["marketing_consent"])
            rows.append(row)
        self.db.executemany(f"INSERT OR REPLACE INTO customers ({cols}) VALUES ({params})", rows)
        return len(rows)

    def update_fields(self, customer_id: str, **fields: Any) -> None:
        allowed = {k: v for k, v in fields.items() if k in CUSTOMER_COLUMNS and k != "customer_id"}
        if not allowed:
            return
        sets = ", ".join(f"{k} = :{k}" for k in allowed)
        self.db.execute(f"UPDATE customers SET {sets} WHERE customer_id = :cid", {**allowed, "cid": customer_id})

    def save_segment(self, result: dict[str, Any]) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO customer_segments
               (customer_id, status, primary_segment, segments_json, reason_codes_json, confidence, policy_version, classified_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (result["customer_id"], result["status"], result.get("primary_segment"), to_json(result.get("segments", [])),
             to_json(result.get("reason_codes", [])), result.get("confidence", 0.0), result.get("policy_version"), now_iso()),
        )

    def save_segments_bulk(self, results: list[dict[str, Any]]) -> None:
        ts = now_iso()
        self.db.executemany(
            """INSERT OR REPLACE INTO customer_segments
               (customer_id, status, primary_segment, segments_json, reason_codes_json, confidence, policy_version, classified_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            [(r["customer_id"], r["status"], r.get("primary_segment"), to_json(r.get("segments", [])),
              to_json(r.get("reason_codes", [])), r.get("confidence", 0.0), r.get("policy_version"), ts) for r in results],
        )

    # ---------------------------------------------------------------- reads
    def get_row(self, customer_id: str) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM customers WHERE customer_id = ?", (customer_id,))

    def exists(self, customer_id: str) -> bool:
        return self.get_row(customer_id) is not None

    def count(self, segment: str | None = None, source: str | None = None, query: str | None = None) -> int:
        where, params = self._filters(segment, source, query)
        return int(self.db.scalar(f"SELECT COUNT(*) FROM customers c LEFT JOIN customer_segments s USING(customer_id) {where}", params) or 0)

    def search(self, query: str | None = None, segment: str | None = None, source: str | None = None,
               limit: int = 50, offset: int = 0, order_by: str = "customer_id") -> list[dict[str, Any]]:
        where, params = self._filters(segment, source, query)
        order = order_by if order_by in _SORTABLE else "customer_id"
        limit = max(1, min(int(limit), 1000))
        sql = (
            "SELECT c.customer_id, c.customer_name, c.tenure_months, c.contract_type, c.monthly_charges, "
            "c.payment_status, c.amount_due, c.marketing_consent, c.data_source, "
            "s.primary_segment, s.status AS segment_status "
            f"FROM customers c LEFT JOIN customer_segments s USING(customer_id) {where} "
            f"ORDER BY c.{order} LIMIT ? OFFSET ?"
        )
        return self.db.query(sql, (*params, limit, max(0, int(offset))))

    def iter_rows(self, batch_size: int = 20000, source: str | None = None):
        last = ""
        while True:
            if source:
                rows = self.db.query("SELECT * FROM customers WHERE customer_id > ? AND data_source = ? ORDER BY customer_id LIMIT ?",
                                     (last, source, batch_size))
            else:
                rows = self.db.query("SELECT * FROM customers WHERE customer_id > ? ORDER BY customer_id LIMIT ?",
                                     (last, batch_size))
            if not rows:
                return
            yield rows
            last = rows[-1]["customer_id"]

    def get_segment(self, customer_id: str) -> dict[str, Any] | None:
        row = self.db.query_one("SELECT * FROM customer_segments WHERE customer_id = ?", (customer_id,))
        if row:
            row["segments"] = from_json(row.pop("segments_json"), [])
            row["reason_codes"] = from_json(row.pop("reason_codes_json"), [])
        return row

    def segment_distribution(self) -> dict[str, int]:
        rows = self.db.query(
            "SELECT COALESCE(primary_segment, status) AS seg, COUNT(*) AS n FROM customer_segments GROUP BY seg ORDER BY n DESC")
        return {r["seg"] or "UNKNOWN": r["n"] for r in rows}

    def source_counts(self) -> dict[str, int]:
        return {r["data_source"] or "unknown": r["n"] for r in
                self.db.query("SELECT data_source, COUNT(*) AS n FROM customers GROUP BY data_source")}

    @staticmethod
    def _filters(segment: str | None, source: str | None, query: str | None) -> tuple[str, tuple]:
        clauses, params = [], []
        if segment:
            if segment == "UNCLASSIFIED":
                clauses.append("s.customer_id IS NULL")
            elif segment == "MANUAL_REVIEW":
                clauses.append("s.status = 'MANUAL_REVIEW'")
            else:
                clauses.append("s.primary_segment = ?")
                params.append(segment)
        if source:
            clauses.append("c.data_source = ?")
            params.append(source)
        if query:
            clauses.append("(c.customer_id LIKE ? OR c.customer_name LIKE ?)")
            params += [f"%{query}%", f"%{query}%"]
        return ("WHERE " + " AND ".join(clauses)) if clauses else "", tuple(params)
