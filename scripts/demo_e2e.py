"""End-to-end demonstration of scenarios A-H in the terminal (uses the configured database)."""
import _bootstrap  # noqa: F401
import argparse

from backend.services.bootstrap import load_demo_customers
from backend.services.container import build_container
from modules.email.mock_email_service import DeliveryError
from modules.review.review_service import ReviewError


def show(title: str) -> None:
    print("\n" + "=" * 90 + f"\n{title}\n" + "=" * 90)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="approve and mock-send passing drafts")
    a = ap.parse_args()
    c = build_container()
    labels = load_demo_customers(c)
    print("Generator:", c.llm_status)
    for cid, lab in labels.items():
        show(f"{lab['scenario']}  [{cid}]\n{lab['description']}")
        d = c.engagement.create_draft(cid, forced_offer_id=lab.get("forced_offer"), fault=lab.get("inject_fault"),
                                      supersede=True)
        seg = d.segment
        print(f"Segment: {seg.get('primary_segment') or 'MANUAL_REVIEW'}  all={seg.get('segments')}  "
              f"reasons={seg.get('reason_codes') or seg.get('manual_review_reasons')}")
        print(f"Strategy: {d.objective} / {d.tone} / {d.template_id}  stage={d.reminder_stage}  offer={d.offer_id}")
        for n in d.strategy.get("notes", []):
            print("  note:", n)
        print(f"Draft {d.draft_id}: {d.status.value}  mode={d.generation_mode}  attempts={d.attempt_count}")
        for att in c.drafts.attempts(d.draft_id):
            print(f"  attempt {att['attempt_no']}: {att['mode']:16} passed={bool(att['passed'])} failures={att['failure_categories_json']}")
        if d.block_reasons:
            for b in d.block_reasons:
                print(f"  BLOCKED: {b.get('code')} - {b.get('detail')}")
        if d.body:
            print(f"\nSubject: {d.subject}\n{d.body}\n")
        if a.send and d.status.value == "PENDING_REVIEW":
            try:
                c.review.approve(d.draft_id, "demo-reviewer")
                print("Mock delivery:", c.email.send(d.draft_id, "demo-reviewer"))
            except (ReviewError, DeliveryError) as exc:
                print("Not sent:", exc)
