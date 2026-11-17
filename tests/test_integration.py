"""Full workflow across all four modules, plus the evaluation harness."""
from modules.audit.metrics import compute_metrics
from modules.evaluation.evaluation import run_evaluation


def test_end_to_end_all_scenarios(sim_container):
    c = sim_container
    for cid, lab in c.labels.items():
        d = c.engagement.create_draft(cid, forced_offer_id=lab.get("forced_offer"), fault=lab.get("inject_fault"))
        assert d.status.value == lab["expected_status"], cid
        if "expected_offer" in lab:
            assert d.offer_id == lab["expected_offer"], cid
        if "expected_stage" in lab:
            assert d.reminder_stage == lab["expected_stage"], cid
    # Case G: hallucinated amount detected, repaired, and never reaches the reviewer
    g = c.drafts.open_draft_for("DEMO-G-HALLUCINATION")
    atts = c.drafts.attempts(g.draft_id)
    assert atts[0]["passed"] == 0 and "WRITING" in atts[0]["failure_categories_json"] and "$79.99" in g.body
    # Approve and send every passing draft
    for d in c.review.queue(["PENDING_REVIEW"]):
        c.review.approve(d.draft_id, "qa")
        assert c.email.send(d.draft_id, "qa")["status"] == "MOCK_SENT"
    m = compute_metrics(c.db)
    assert m["mock_emails_sent"] == 9 and m["blocked"] == 4 and m["drafts_generated"] == 9


def test_evaluation_report(settings):
    r = run_evaluation(settings, "offline_simulator")
    assert r["classification_accuracy"] == 1.0 and r["scenario_pass_rate"] == 1.0
    assert r["validator_catch_rate"] == 1.0 and r["false_positive_rate_on_clean_templates"] == 0.0
    assert all(f["first_attempt_caught"] and f["recovered"] for f in r["fault_injection"])
    assert (settings.reports_dir / "evaluation_report.md").exists()
