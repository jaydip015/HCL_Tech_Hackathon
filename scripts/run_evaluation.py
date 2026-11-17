"""Run the evaluation harness in an isolated database and write reports/evaluation_report.md.

  python scripts/run_evaluation.py                 # offline simulator (no API key needed)
  python scripts/run_evaluation.py --provider auto # use the configured real LLM if available
"""
import _bootstrap  # noqa: F401
import argparse

from config import get_settings
from modules.evaluation.evaluation import run_evaluation

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="offline_simulator", choices=["offline_simulator", "auto", "none"])
    a = ap.parse_args()
    s = get_settings()
    r = run_evaluation(s, a.provider)
    for k in ("classification_accuracy", "scenario_pass_rate", "validator_catch_rate", "validator_precise_rate",
              "false_positive_rate_on_clean_templates", "groundedness_rate", "offer_compliance_rate", "consent_compliance_rate"):
        print(f"{k:42} {r[k]}")
    print("Report:", s.reports_dir / "evaluation_report.md")
