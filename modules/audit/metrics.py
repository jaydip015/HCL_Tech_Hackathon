"""Observability metrics computed from the audit store (Person 4)."""
from __future__ import annotations

from typing import Any

from backend.database.db import Database, from_json


def compute_metrics(db: Database, price_in: float = 3.0, price_out: float = 15.0) -> dict[str, Any]:
    q = db.scalar
    drafts = q("SELECT COUNT(*) FROM drafts") or 0
    generated = q("SELECT COUNT(*) FROM drafts WHERE generation_mode != 'not_generated'") or 0
    status_rows = db.query("SELECT status, COUNT(*) AS n FROM drafts GROUP BY status")
    by_status = {r["status"]: r["n"] for r in status_rows}
    first_pass = q("SELECT COUNT(*) FROM generation_attempts WHERE attempt_no = 1 AND passed = 1") or 0
    first_total = q("SELECT COUNT(*) FROM generation_attempts WHERE attempt_no = 1") or 0
    gen_reports = q("SELECT COUNT(*) FROM validation_reports") or 0
    failed_reports = q("SELECT COUNT(*) FROM validation_reports WHERE passed = 0") or 0
    retried = q("SELECT COUNT(DISTINCT draft_id) FROM generation_attempts WHERE mode IN ('repair','format_retry')") or 0
    fallback = q("SELECT COUNT(DISTINCT draft_id) FROM generation_attempts WHERE mode = 'static_fallback'") or 0
    tokens_in = q("SELECT COALESCE(SUM(input_tokens),0) FROM generation_attempts") or 0
    tokens_out = q("SELECT COALESCE(SUM(output_tokens),0) FROM generation_attempts") or 0
    avg_latency = q("SELECT AVG(latency_ms) FROM generation_attempts WHERE mode NOT LIKE 'static%'")
    offers = {r["offer_id"]: r["n"] for r in db.query(
        "SELECT offer_id, COUNT(*) AS n FROM drafts WHERE offer_id IS NOT NULL GROUP BY offer_id")}
    segs = {r["seg"]: r["n"] for r in db.query(
        "SELECT COALESCE(primary_segment, status) AS seg, COUNT(*) AS n FROM customer_segments GROUP BY seg")}
    fail_checks: dict[str, int] = {}
    for r in db.query("SELECT findings_json FROM validation_reports WHERE passed = 0"):
        for f in from_json(r["findings_json"], []):
            if f.get("status") == "FAIL":
                fail_checks[f["check"]] = fail_checks.get(f["check"], 0) + 1
    block_codes: dict[str, int] = {}
    for r in db.query("SELECT block_reasons_json FROM drafts WHERE status IN ('BLOCKED','CANCELLED')"):
        for b in from_json(r["block_reasons_json"], []):
            block_codes[b.get("code", "?")] = block_codes.get(b.get("code", "?"), 0) + 1
    reviews = {r["action"]: r["n"] for r in db.query("SELECT action, COUNT(*) AS n FROM review_actions GROUP BY action")}
    reviewed = sum(reviews.get(a, 0) for a in ("APPROVE", "REJECT"))
    return {
        "total_customers": q("SELECT COUNT(*) FROM customers") or 0,
        "customers_processed": q("SELECT COUNT(*) FROM customer_segments") or 0,
        "customers_per_segment": segs,
        "offers_selected": offers,
        "drafts_total": drafts,
        "drafts_generated": generated,
        "drafts_by_status": by_status,
        "first_pass_validation_rate": round(first_pass / first_total, 3) if first_total else None,
        "validation_failure_rate": round(failed_reports / gen_reports, 3) if gen_reports else None,
        "retry_rate": round(retried / generated, 3) if generated else None,
        "fallback_template_usage": fallback,
        "approved": by_status.get("APPROVED", 0) + by_status.get("MOCK_SENT", 0),
        "rejected": by_status.get("REJECTED", 0),
        "blocked": by_status.get("BLOCKED", 0),
        "mock_emails_sent": q("SELECT COUNT(*) FROM mock_deliveries") or 0,
        "avg_generation_latency_ms": round(avg_latency, 1) if avg_latency is not None else None,
        "tokens": {"input": tokens_in, "output": tokens_out},
        "estimated_cost_usd": round(tokens_in / 1e6 * price_in + tokens_out / 1e6 * price_out, 4),
        "validation_failures_by_check": dict(sorted(fail_checks.items(), key=lambda kv: -kv[1])),
        "block_reasons": dict(sorted(block_codes.items(), key=lambda kv: -kv[1])),
        "review_actions": reviews,
        "reviewer_edit_rate": round(reviews.get("EDIT", 0) / reviewed, 3) if reviewed else None,
        "reviewer_rejection_rate": round(reviews.get("REJECT", 0) / reviewed, 3) if reviewed else None,
    }
