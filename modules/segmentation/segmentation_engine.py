"""Transparent, rule-based segmentation (policy engine, Person 2).

Rules come from policies/segmentation.yaml. Every rule evaluation is kept as evidence, all
matching segments are returned, and the primary segment follows the configured priority.
Missing or contradictory data never produces a guessed segment: it goes to MANUAL_REVIEW.
The churn label from the dataset is shown as supplementary information only.
"""
from __future__ import annotations

import operator
from typing import Any

from backend.schemas.models import CustomerProfile, RuleEvidence, SegmentResult
from config import Settings

_OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le, "==": operator.eq, "!=": operator.ne}


class SegmentationEngine:
    def __init__(self, settings: Settings, rules: dict[str, Any] | None = None):
        self.settings = settings
        self.rules = rules or settings.segmentation
        self.version = self.rules.get("version", "unknown")

    def _value(self, profile: CustomerProfile | dict[str, Any], field: str) -> Any:
        if isinstance(profile, dict):
            return profile.get(field)
        return getattr(profile, field, None)

    def evaluate_condition(self, profile: CustomerProfile | dict[str, Any], segment: str,
                           cond: dict[str, Any], policy_ref: str | None) -> RuleEvidence:
        field, op = cond["field"], cond["op"]
        actual = self._value(profile, field)
        if "ref_field" in cond:
            ref = self._value(profile, cond["ref_field"])
            threshold = None if ref is None else round(ref * float(cond.get("factor", 1.0)), 4)
            threshold_desc = f"{cond.get('factor', 1.0)} x {cond['ref_field']} ({threshold})"
        else:
            threshold = cond["value"]
            threshold_desc = threshold
        if actual is None or threshold is None:
            return RuleEvidence(segment=segment, reason_code=cond["reason_code"], field=field, operator=op,
                                threshold=threshold_desc, actual=actual, passed=False, policy_ref=policy_ref)
        passed = bool(_OPS[op](actual, threshold))
        margin = float(cond.get("near_margin", self.rules.get("confidence", {}).get("near_threshold_margin", 0.1)))
        near = threshold != 0 and abs(float(actual) - float(threshold)) <= abs(float(threshold)) * margin
        return RuleEvidence(segment=segment, reason_code=cond["reason_code"], field=field, operator=op,
                            threshold=threshold_desc, actual=actual, passed=passed, near_threshold=near,
                            policy_ref=policy_ref)

    def classify(self, profile: CustomerProfile) -> SegmentResult:
        result = SegmentResult(customer_id=profile.customer_id, status="MANUAL_REVIEW",
                               churn_status_info=profile.churn_status, policy_version=self.version)
        # 1. Data gate: never classify on missing or contradictory evidence
        blocking = [i for i in profile.data_issues if i.severity == "BLOCK"]
        if blocking:
            result.manual_review_reasons = [f"DATA_ISSUE:{i.code} - {i.detail}" for i in blocking]
            return result
        missing = [f for f in self.rules.get("required_fields", []) if self._value(profile, f) is None]
        if missing:
            result.manual_review_reasons = [f"MISSING_EVIDENCE:{f}" for f in missing]
            return result

        # 2. Evaluate every rule, keep all evidence
        matched: list[str] = []
        near_hits = 0
        for seg_name, seg in self.rules["segments"].items():
            evid = [self.evaluate_condition(profile, seg_name, c, seg.get("policy_ref")) for c in seg.get("all", [])]
            result.evidence.extend(evid)
            if evid and all(e.passed for e in evid):
                matched.append(seg_name)
                result.reason_codes.extend(e.reason_code for e in evid)
                near_hits += sum(1 for e in evid if e.near_threshold)

        if not matched:
            result.manual_review_reasons = ["NO_RULE_MATCHED - no segment rule applies; route to manual review."]
            return result

        priority = self.rules.get("priority", [])
        matched.sort(key=lambda s: priority.index(s) if s in priority else len(priority))
        conf_cfg = self.rules.get("confidence", {})
        confidence = float(conf_cfg.get("base", 1.0)) - near_hits * float(conf_cfg.get("near_threshold_penalty", 0.15))
        if profile.data_issues:  # WARN-level issues (e.g. unverified consent)
            confidence -= 0.05
        result.confidence = round(max(0.0, min(1.0, confidence)), 2)
        result.segments = matched
        result.primary_segment = matched[0]
        result.secondary_segments = matched[1:]
        if result.confidence < float(conf_cfg.get("min_confidence_for_auto", 0.6)):
            result.manual_review_reasons = [f"LOW_CONFIDENCE ({result.confidence}) - values close to thresholds."]
            return result
        result.status = "CLASSIFIED"
        return result

    def describe_rules(self) -> list[dict[str, Any]]:
        out = []
        for name, seg in self.rules["segments"].items():
            conds = []
            for c in seg.get("all", []):
                rhs = f"{c.get('factor', 1)} x {c['ref_field']}" if "ref_field" in c else c["value"]
                conds.append(f"{c['field']} {c['op']} {rhs}")
            out.append({"segment": name, "priority": self.rules["priority"].index(name) + 1,
                        "rule": " AND ".join(conds), "description": seg.get("description", ""),
                        "policy_ref": seg.get("policy_ref", "")})
        return sorted(out, key=lambda r: r["priority"])
