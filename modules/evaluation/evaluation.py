"""Evaluation harness (Person 4).

Runs in an isolated database so it never touches real review data:
  1. Classification accuracy on the labelled demo scenarios.
  2. End-to-end scenario outcomes (status, offer, stage, block reason).
  3. Validator catch rate on deliberately corrupted drafts (planted errors).
  4. Generation: first-pass rate, repair/fallback behaviour under injected LLM faults.
  5. Groundedness, offer compliance, consent compliance over every generated draft.
  6. Simulated reviewer session (approve / edit / reject / send) for review metrics.
Writes reports/evaluation_report.md and reports/evaluation_results.json.
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.schemas.models import DraftStatus, EmailContent, Strategy
from backend.services.bootstrap import load_demo_customers
from backend.services.container import Container, build_container
from config import Settings
from modules.audit.metrics import compute_metrics
from modules.generation.simulators import FAULTS


def _isolated_settings(base: Settings, llm_provider: str) -> Settings:
    tmp = Path(tempfile.mkdtemp(prefix="cea_eval_"))
    return base.model_copy(update={"db_path": tmp / "eval.db", "vector_store_dir": tmp / "vs", "llm_provider": llm_provider,
                                   "tone_judge_enabled": False})


# Each case: (name, customer_id, mutation(content, strategy) -> content, expected failing check)
def _planted_errors(c: Container) -> list[tuple[str, str, Any, str]]:
    def sub(old: str, new: str):
        return lambda ec, st: EmailContent(subject=ec.subject, body=ec.body.replace(old, new), cta=ec.cta)

    def add(text: str):
        return lambda ec, st: EmailContent(subject=ec.subject, body=ec.body + "\n\n" + text, cta=ec.cta)

    sup = c.settings.communication["support"]
    return [
        ("Wrong amount", "DEMO-D-OVERDUE", sub("$134.40", "$143.40"), "AMOUNT_VERIFICATION"),
        ("Wrong due date", "DEMO-D-OVERDUE", sub("28 October 2026", "30 October 2026"), "DATE_VERIFICATION"),
        ("Invented tenure", "DEMO-A-LOYAL", sub("48 months", "60 months"), "UNSUPPORTED_CLAIMS"),
        ("Invented discount percentage", "DEMO-A-LOYAL", sub("10% discount", "25% discount"), "PERCENTAGE_VERIFICATION"),
        ("Offer terms dropped", "DEMO-A-LOYAL", sub("Valid for the next billing cycle only.", ""), "OFFER_TERMS"),
        ("Promo in reminder", "DEMO-D1-OVERDUE-S1", add("Pay now and get a 10% discount."), "NO_PROMO_IN_REMINDER"),
        ("Unapproved promotion", "DEMO-K-CONSISTENT", lambda ec, st: ec, "UNAPPROVED_PROMOTION"),  # offer removed below
        ("Banned threat", "DEMO-D-OVERDUE", add("This is your final warning before legal action."), "PROHIBITED_PHRASES"),
        ("Internal label disclosed", "DEMO-B-DECLINING", add("You are in our DECLINING segment."), "INTERNAL_DISCLOSURE"),
        ("Card number leaked", "DEMO-D-OVERDUE", add("Card on file: 4111 1111 1111 1111."), "PII_LEAKAGE"),
        ("Unknown link", "DEMO-D-OVERDUE", add("Pay at http://pay-now-example.biz/x"), "PII_LEAKAGE"),
        ("Dispute link missing", "DEMO-D-OVERDUE", sub(sup["dispute_url"], "our website"), "SUPPORT_CONTACT"),
        ("Unresolved placeholder", "DEMO-C-DORMANT", add("Your plan: {plan_name}."), "PLACEHOLDERS_RESOLVED"),
        ("Body too short", "DEMO-A-LOYAL", lambda ec, st: {"subject": ec.subject, "body": "Thanks for being with us. Bye!", "cta": ""}, "SCHEMA"),
    ]


def run_evaluation(settings: Settings, llm_provider: str = "offline_simulator", write_reports: bool = True) -> dict[str, Any]:
    es = _isolated_settings(settings, llm_provider)
    c = build_container(es)
    labels = load_demo_customers(c)
    results: dict[str, Any] = {"generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z", "llm_provider": c.llm_status,
                               "as_of_date": es.as_of_date.isoformat(), "policy_version": es.policy_version}

    # 1 + 2. classification and scenario outcomes
    scen, correct = [], 0
    for cid, lab in labels.items():
        draft = c.engagement.create_draft(cid, forced_offer_id=lab.get("forced_offer"), fault=lab.get("inject_fault"))
        seg = draft.segment
        predicted = seg.get("primary_segment") if seg.get("status") == "CLASSIFIED" else None
        cls_ok = predicted == lab["expected_segment"]
        correct += cls_ok
        checks = {"segment": cls_ok, "status": draft.status.value == lab["expected_status"]}
        if "expected_offer" in lab:
            checks["offer"] = draft.offer_id == lab["expected_offer"]
        if "expected_stage" in lab:
            checks["stage"] = draft.reminder_stage == lab["expected_stage"]
        if "expected_block" in lab:
            codes = [b.get("code") for b in draft.block_reasons]
            reasons = " ".join(str(b.get("detail")) for b in draft.block_reasons)
            checks["block"] = lab["expected_block"] in codes or lab["expected_block"] in reasons
        scen.append({"scenario": lab["scenario"], "customer_id": cid, "expected_segment": lab["expected_segment"],
                     "predicted_segment": predicted, "expected_status": lab["expected_status"], "status": draft.status.value,
                     "offer": draft.offer_id, "stage": draft.reminder_stage, "mode": draft.generation_mode,
                     "attempts": draft.attempt_count, "block_reasons": [b.get("code") for b in draft.block_reasons],
                     "checks": checks, "passed": all(checks.values()), "draft_id": draft.draft_id})
    results["classification_accuracy"] = round(correct / len(labels), 3)
    results["scenarios"] = scen
    results["scenario_pass_rate"] = round(sum(s["passed"] for s in scen) / len(scen), 3)

    # 3. validator catch rate on planted errors
    planted = []
    for name, cid, mutate, expected in _planted_errors(c):
        profile, seg, strategy, history = c.engagement.decide(cid)
        clean = c.templates.render(strategy)
        base_ok = c.validator.validate(clean, strategy, profile, seg, history).passed
        st2 = strategy
        if name == "Unapproved promotion":  # same text, but strategy has no approved offer attached
            st2 = Strategy(**{**strategy.model_dump(), "offer": None})
        bad = mutate(clean, st2)
        rep = c.validator.validate(bad, st2, profile, seg, history)
        failed = [f.check for f in rep.blocking_failures]
        planted.append({"case": name, "customer_id": cid, "expected_check": expected, "clean_template_passed": base_ok,
                        "caught": not rep.passed, "caught_by_expected_check": expected in failed, "failed_checks": failed,
                        "retry_recommended": rep.retry_recommended})
    results["validator_cases"] = planted
    results["validator_catch_rate"] = round(sum(p["caught"] for p in planted) / len(planted), 3)
    results["validator_precise_rate"] = round(sum(p["caught_by_expected_check"] for p in planted) / len(planted), 3)
    results["false_positive_rate_on_clean_templates"] = round(sum(not p["clean_template_passed"] for p in planted) / len(planted), 3)

    # 4. injected LLM faults -> repair / format retry / fallback
    fault_runs = []
    fault_targets = {"wrong_amount": "DEMO-D1-OVERDUE-S1", "banned_phrase": "DEMO-D-OVERDUE",
                     "promo_in_reminder": "DEMO-D3-OVERDUE-S3", "invalid_json": "DEMO-B-DECLINING",
                     "missing_dispute": "DEMO-D-OVERDUE", "invented_offer": "DEMO-K-CONSISTENT"}
    for fault, cid in fault_targets.items():
        d = c.engagement.create_draft(cid, fault=fault, supersede=True)
        atts = c.drafts.attempts(d.draft_id)
        fault_runs.append({"fault": fault, "description": FAULTS[fault], "customer_id": cid, "final_status": d.status.value,
                           "final_mode": d.generation_mode, "attempts": [(a["mode"], bool(a["passed"])) for a in atts],
                           "first_attempt_caught": bool(atts) and not atts[0]["passed"],
                           "recovered": d.status == DraftStatus.PENDING_REVIEW})
    results["fault_injection"] = fault_runs

    # 5. groundedness / offer / consent compliance over all drafts that reached review
    drafts = [d for d in c.drafts.list(limit=1000) if d.body]
    grounded = offer_ok = consent_ok = 0
    for d in drafts:
        profile, seg = c.engagement.classify(d.customer_id, persist=False)
        st = Strategy(**d.strategy)
        rep = c.validator.validate({"subject": d.subject, "body": d.body, "cta": d.cta}, st, profile, seg, [])
        by = {f.check: f for f in rep.findings}
        grounded += all(by[k].status == "PASS" for k in ("AMOUNT_VERIFICATION", "PERCENTAGE_VERIFICATION",
                                                          "DATE_VERIFICATION", "UNSUPPORTED_CLAIMS") if k in by)
        offer_ok += all(f.status == "PASS" for k, f in by.items() if k.startswith("OFFER") or "PROMO" in k)
        consent_ok += by["CONSENT"].status == "PASS" if "CONSENT" in by else 1
    n = max(len(drafts), 1)
    results["groundedness_rate"] = round(grounded / n, 3)
    results["offer_compliance_rate"] = round(offer_ok / n, 3)
    results["consent_compliance_rate"] = round(consent_ok / n, 3)
    results["drafts_checked"] = len(drafts)
    results["blocking_results"] = [s for s in scen if s["status"] == "BLOCKED"]

    # 6. simulated reviewer session
    review_log = []
    pend = c.review.queue([DraftStatus.PENDING_REVIEW.value])
    for i, d in enumerate(pend[:6]):
        try:
            if i % 3 == 0:
                c.review.approve(d.draft_id, "eval-reviewer")
                c.email.send(d.draft_id, "eval-reviewer")
                review_log.append((d.customer_id, "approve+send", "MOCK_SENT"))
            elif i % 3 == 1:
                nd, rep = c.review.edit(d.draft_id, "eval-reviewer", d.subject, d.body.replace("Dear", "Hello"))
                review_log.append((d.customer_id, "edit", nd.status.value))
            else:
                c.review.reject(d.draft_id, "eval-reviewer", "Evaluation: tone not personal enough")
                review_log.append((d.customer_id, "reject", "REJECTED"))
        except Exception as exc:  # recorded, not hidden
            review_log.append((d.customer_id, "error", str(exc)[:120]))
    results["review_session"] = review_log
    results["metrics"] = compute_metrics(c.db, es.price_input_per_mtok, es.price_output_per_mtok)

    if write_reports:
        settings.reports_dir.mkdir(parents=True, exist_ok=True)
        (settings.reports_dir / "evaluation_results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        (settings.reports_dir / "evaluation_report.md").write_text(to_markdown(results), encoding="utf-8")
    return results


def to_markdown(r: dict[str, Any]) -> str:
    pct = lambda v: "n/a" if v is None else f"{v * 100:.1f}%"  # noqa: E731
    m = r["metrics"]
    lines = [
        "# Evaluation report - Customer Loyalty and Engagement Assistant", "",
        f"- Generated: {r['generated_at']}  |  as-of date: {r['as_of_date']}",
        f"- Generator: {r['llm_provider']}",
        f"- Policy version: `{r['policy_version']}`",
        "- Data: labelled synthetic demonstration customers (not real customers).", "",
        "## Summary", "",
        "| Metric | Result |", "|---|---|",
        f"| Classification accuracy (labelled scenarios) | {pct(r['classification_accuracy'])} |",
        f"| End-to-end scenario pass rate | {pct(r['scenario_pass_rate'])} |",
        f"| Validator catch rate (planted errors) | {pct(r['validator_catch_rate'])} |",
        f"| Caught by the expected check | {pct(r['validator_precise_rate'])} |",
        f"| False positives on clean approved templates | {pct(r['false_positive_rate_on_clean_templates'])} |",
        f"| First-pass validation rate (incl. injected faults) | {pct(m['first_pass_validation_rate'])} |",
        f"| Groundedness (amounts, %, dates, numbers) | {pct(r['groundedness_rate'])} of {r['drafts_checked']} drafts |",
        f"| Offer compliance | {pct(r['offer_compliance_rate'])} |",
        f"| Consent compliance | {pct(r['consent_compliance_rate'])} |",
        f"| Reviewer edit rate / rejection rate | {pct(m['reviewer_edit_rate'])} / {pct(m['reviewer_rejection_rate'])} |",
        f"| Mock emails sent | {m['mock_emails_sent']} |", "",
        "## Scenario results", "",
        "| Scenario | Expected segment | Predicted | Status | Offer | Stage | Mode | Block reasons | Pass |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in r["scenarios"]:
        lines.append(f"| {s['scenario']} | {s['expected_segment'] or 'manual review'} | {s['predicted_segment'] or 'manual review'} | "
                     f"{s['status']} | {s['offer'] or '-'} | {s['stage'] or '-'} | {s['mode']} | "
                     f"{', '.join(dict.fromkeys(s['block_reasons'])) or '-'} | {'PASS' if s['passed'] else 'FAIL'} |")
    lines += ["", "## Validator catch rate (planted errors)", "",
              "| Planted error | Expected check | Caught | Failed checks | Retry recommended |", "|---|---|---|---|---|"]
    for p in r["validator_cases"]:
        lines.append(f"| {p['case']} | {p['expected_check']} | {'YES' if p['caught'] else 'NO'} | "
                     f"{', '.join(p['failed_checks'])} | {p['retry_recommended']} |")
    lines += ["", "## Injected LLM faults (repair and fallback)", "",
              "| Fault | Customer | Attempts (mode, passed) | Final status | Final mode |", "|---|---|---|---|---|"]
    for f in r["fault_injection"]:
        lines.append(f"| {f['description']} | {f['customer_id']} | {f['attempts']} | {f['final_status']} | {f['final_mode']} |")
    lines += ["", "## Refusal / blocking results", ""]
    for b in r["blocking_results"]:
        lines.append(f"- **{b['scenario']}** ({b['customer_id']}): BLOCKED - {', '.join(dict.fromkeys(b['block_reasons']))}; the LLM was not called.")
    lines += ["", "## Simulated reviewer session", ""]
    lines += [f"- {cid}: {action} -> {outcome}" for cid, action, outcome in r["review_session"]]
    lines += ["", "## Operational metrics", "", "```json", json.dumps({k: m[k] for k in (
        "drafts_total", "drafts_by_status", "retry_rate", "fallback_template_usage", "validation_failures_by_check",
        "block_reasons", "tokens", "estimated_cost_usd", "avg_generation_latency_ms")}, indent=2), "```", "",
        "## Known limitations", "",
        "- Offline runs use the clearly-labelled offline simulator instead of a real LLM; with an API key the same harness exercises Claude.",
        "- Demonstration customers are synthetic and hand-labelled; accuracy on them shows rule correctness, not real-world performance.",
        "- Tone is checked with heuristics; the optional LLM judge is advisory and disabled in offline evaluation.",
        "- TF-IDF retrieval is used when Sentence Transformers is unavailable; semantic recall is lower.", ""]
    return "\n".join(lines)
