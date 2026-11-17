"""Customer-specific policy question answering (Person 2).

Pipeline: verified decision evidence for ONE customer (profile, segment, strategy) +
RAG-retrieved policy excerpts -> answer with sources. The deterministic decision is the
authority; RAG only explains it. With no LLM configured, a deterministic answer is composed
from the same evidence. If no relevant policy evidence is retrieved, the fixed message
"Insufficient policy evidence to answer this question." is returned.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from backend.schemas.models import PolicyAnswer, PolicySource
from modules.generation.llm_client import LLMError, LLMProvider, extract_json
from modules.generation.prompt_manager import PromptManager
from modules.rag.retriever import PolicyRetriever

INSUFFICIENT = "Insufficient policy evidence to answer this question."

INTENTS = {
    "classification": ["classified", "classify", "classification", "segment", "why is this customer", "why was this customer"],
    "offer": ["eligible", "eligibility", "offer", "reward", "discount", "engagement offer", "win-back"],
    "blocked": ["blocked", "block", "suppressed", "why can't", "why cannot", "not sent", "consent"],
    "tone": ["tone", "wording", "how should we write", "style"],
    "reminder": ["reminder", "overdue", "payment", "stage", "bill"],
    "policy": ["which policy", "what policy", "policy supports", "supports this decision"],
}


def detect_intents(question: str) -> list[str]:
    q = question.lower()
    return [name for name, words in INTENTS.items() if any(w in q for w in words)]


class PolicyQAService:
    def __init__(self, retriever: PolicyRetriever, evidence_fn: Callable[[str], dict[str, Any]],
                 provider: LLMProvider, prompts: PromptManager):
        self.retriever = retriever
        self.evidence_fn = evidence_fn
        self.provider = provider
        self.prompts = prompts

    def _query(self, question: str, ev: dict[str, Any]) -> str:
        seg = ev["segment"]
        strat = ev["strategy"]
        extra = [seg.get("primary_segment") or "", " ".join(seg.get("reason_codes", []))]
        extra += [b["code"].replace("_", " ").lower() for b in strat.get("block_reasons", [])]
        if strat.get("objective"):
            extra.append(strat["objective"].lower())
        return f"{question} {' '.join(e for e in extra if e)}"

    def answer(self, customer_id: str, question: str, top_k: int = 4) -> PolicyAnswer:
        question = (question or "").strip()
        if not question:
            raise ValueError("Question must not be empty")
        ev = self.evidence_fn(customer_id)  # raises if the customer does not exist
        intents = detect_intents(question)
        sources: list[PolicySource] = []
        if intents:  # only search the knowledge base for questions about this domain
            query = self._query(question, ev)
            sources = self.retriever.retrieve(query, top_k=top_k)
            ref_docs = self._referenced_docs(ev, classification_first="classification" in intents)
            if ref_docs and sources:  # the policies (and sections) cited by the decision itself come first
                pinned = []
                for doc_id, section in ref_docs[:3]:
                    cands = self.retriever.retrieve(query, top_k=8, doc_ids=[doc_id], min_score=0.0)
                    exact = [s for s in cands if section and s.section.split(" ")[0].rstrip(".") == section]
                    pinned += (exact or cands)[:1]
                seen = {(s.doc_id, s.section) for s in pinned}
                sources = pinned + [s for s in sources if (s.doc_id, s.section) not in seen]
                sources = sources[:top_k + 1]
        if not sources:
            return PolicyAnswer(customer_id=customer_id, question=question, answer=INSUFFICIENT,
                                insufficient_evidence=True, decision_evidence=ev)
        if self.provider.available:
            ans = self._llm_answer(customer_id, question, ev, sources)
            if ans is not None:
                return ans
        return PolicyAnswer(customer_id=customer_id, question=question, sources=sources, decision_evidence=ev,
                            answer=self._deterministic(customer_id, intents, ev, sources), mode="deterministic")

    @staticmethod
    def _decision_refs(ev: dict[str, Any], classification_first: bool = False) -> list[str]:
        st = ev["strategy"]
        block = [b.get("policy_ref") for b in st.get("block_reasons", [])]
        seg = [e.get("policy_ref") for e in ev["segment"].get("evidence", [])
               if e.get("passed") and e.get("segment") == ev["segment"].get("primary_segment")]
        strat = list(st.get("policy_refs", []))
        refs = (seg + block + strat) if classification_first else (block + strat + seg)
        return [r for r in dict.fromkeys(refs) if r]

    def _referenced_docs(self, ev: dict[str, Any], classification_first: bool = False) -> list[tuple[str, str]]:
        """[(doc_id, section_number)] in decision order, e.g. ('POL-CONSENT', '3')."""
        by_title = {d.title: d.doc_id for d in self.retriever.docs}
        ordered: list[tuple[str, str]] = []
        for ref in self._decision_refs(ev, classification_first):
            for title, doc_id in by_title.items():
                if ref.startswith(title) and doc_id not in [o[0] for o in ordered]:
                    sec = ref.split("§", 1)[1].split()[0].strip() if "§" in ref else ""
                    ordered.append((doc_id, sec))
        return ordered

    # ------------------------------------------------------------------ LLM path
    def _llm_answer(self, customer_id: str, question: str, ev: dict[str, Any], sources: list[PolicySource]) -> PolicyAnswer | None:
        excerpts = "\n\n".join(f"[{s.doc_id} | {s.section} | v{s.version}]\n{s.excerpt}" for s in sources)
        p = self.prompts.render("policy_qa", customer_id=customer_id, question=question,
                                evidence_json=json.dumps(ev, indent=1, default=str)[:6000], excerpts=excerpts)
        try:
            resp = self.provider.complete(p.system, p.user, temperature=0.0, max_tokens=600)
            data = extract_json(resp.text)
        except (LLMError, ValueError):
            return None
        insufficient = bool(data.get("insufficient_evidence"))
        cited = {(c.get("doc_id"), c.get("section")) for c in data.get("citations", []) if isinstance(c, dict)}
        used = [s for s in sources if (s.doc_id, s.section) in cited] or sources
        return PolicyAnswer(customer_id=customer_id, question=question,
                            answer=INSUFFICIENT if insufficient else str(data.get("answer", "")).strip() or INSUFFICIENT,
                            insufficient_evidence=insufficient, sources=[] if insufficient else used,
                            decision_evidence=ev, mode="llm", model_name=resp.model)

    # ------------------------------------------------------------------ deterministic path
    def _deterministic(self, cid: str, intents: list[str], ev: dict[str, Any], sources: list[PolicySource]) -> str:
        seg, st, prof = ev["segment"], ev["strategy"], ev["profile"]
        lines: list[str] = []
        if "classification" in intents or not intents:
            if seg["status"] == "CLASSIFIED":
                passed = [e for e in seg["evidence"] if e["passed"] and e["segment"] in seg["segments"]]
                rules = "; ".join(f"{e['field']} {e['operator']} {e['threshold']} (actual {e['actual']})" for e in passed)
                sec = f" Secondary segments: {', '.join(seg['secondary_segments'])}." if seg["secondary_segments"] else ""
                lines.append(f"{cid} is classified as {seg['primary_segment']} (confidence {seg['confidence']}). "
                             f"Rules met: {rules}. Reason codes: {', '.join(seg['reason_codes'])}.{sec} "
                             f"The primary segment follows the priority OVERDUE > DORMANT > DECLINING > LOYAL > CONSISTENT.")
            else:
                lines.append(f"{cid} has not been classified and is routed to manual review: "
                             f"{'; '.join(seg['manual_review_reasons'])}.")
        if "offer" in intents:
            if st.get("offer"):
                o = st["offer"]
                lines.append(f"Selected offer: {o['offer_id']} ({o['name']}, {o['value']}); terms: {o['terms']} "
                             f"Valid until {o['expiry_date']}.")
            decisions = st.get("offer_decisions", [])
            if decisions:
                lines.append("Offer eligibility: " + " | ".join(
                    f"{d['offer_id']}: {'eligible' if d['eligible'] else 'not eligible - ' + '; '.join(d['reasons'])}"
                    for d in decisions))
            elif st.get("objective") == "REMIND":
                lines.append("No offer can be attached: customers with an overdue bill never receive promotional offers.")
            elif st.get("blocked"):
                lines.append("No offer was evaluated because the communication is blocked (see reasons below).")
        if "blocked" in intents or (st.get("blocked") and "classification" not in intents):
            if st.get("blocked"):
                lines.append("Communication is blocked: " + "; ".join(
                    f"{b['code']} - {b['detail']}" + (f" ({b['policy_ref']})" if b.get("policy_ref") else "")
                    for b in st["block_reasons"]))
            elif "blocked" in intents:
                lines.append("No block applies to this customer: consent, frequency and data checks passed.")
        if "tone" in intents and st.get("tone"):
            lines.append(f"Use a {st['tone'].lower()} tone for objective {st['objective']} (template {st['template_id']}).")
        if "reminder" in intents:
            if st.get("objective") == "REMIND":
                lines.append(f"The customer's bill is {prof['days_overdue']} days overdue (amount {prof['amount_due']:.2f}, "
                             f"due {prof['bill_due_date']}), so a stage {st['reminder_stage']} reminder applies. "
                             "The reminder must include the amount, due date, support phone and dispute link, and no offers.")
            else:
                lines.append(f"No payment reminder applies: payment status {prof['payment_status']}, "
                             f"{prof['days_overdue']} days overdue.")
        refs = self._decision_refs(ev, "classification" in intents)
        if refs:
            lines.append("Policy references for this decision: " + "; ".join(refs) + ".")
        top = sources[0]
        lines.append(f"Supporting policy text ({top.doc_name}, {top.section}): \"{top.excerpt[:280].strip()}\"")
        return "\n\n".join(lines)
