# Architecture Note — Vendor Onboarding Agent

## Pipeline

```
Input documents (xlsx · csv · pdf · md · txt)
        │
        ▼ parsers.py
        │
        ▼ PRE-SCREEN          deterministic hard checks before any LLM call
        │
        ▼ GENERATOR           claude-sonnet-4-6, tool-calling loop (≤15 turns)
        │   lookup_budget · check_existing_vendor · calculate_total_contract_value
        │   classify_data_sensitivity · extract_contract_clauses
        │   validate_cross_document_consistency · run_policy_checklist (34 rules)
        │   determine_required_approvals · submit_triage_output
        │
        ▼ CRITIC              independent reflection pass (medium/high risk only)
        │   surfaces missed flags · verifies communication compliance
        │
        ▼ STREAMLIT UI        per-domain human review
        │   Finance · Legal · Security · Procurement · Data Handling · Vendor Risk
        │   each rule: Accept | Modify (override requires justification)
        │   progress tracked per triggered rule; reviewer submits final decision
        │   when ready
        │
        ▼ PERSISTENCE
            analysis_results.json   analysis versions + reviewer decisions
            audit_log.json          immutable record of every decision and override
```

---

## Key Decisions

**Pre-screen before LLM.** Checks with unambiguous answers — missing documents, ACV thresholds, required fields — run as deterministic code before the LLM loop. Same input, same result, every time. The LLM handles what requires judgment: contract language, cross-document conflicts, ambiguous data classifications.

**34 deterministic rules, not LLM policy judgment.** `run_policy_checklist()` is a pure function. Separating value extraction (LLM) from rule evaluation (code) makes findings auditable, consistent, and easy to update — changing a threshold means editing one rule, not re-prompting.

**Per-domain HITL, not a single end gate.** Reviewers evaluate findings domain by domain so they can identify exactly where the agent is wrong and adjust accordingly. A single gate at the end obscures which domain produced an incorrect finding and makes prompt iteration harder.

**Communication compliance in the Critic.** The communication policy governs the agent's own output, not the vendor's submission. The Critic — which already reviews the Generator's output independently — checks that drafts are labeled, contain no autonomous approval language, and disclose nothing sensitive to the vendor.

---

## Prototype vs Productionization

The prototype is scoped to validate the core evaluation loop and establish the foundation for trust. Productionization builds on that foundation in two phases.

**Prototype (current)**
- Upload vendor cases and parse five document formats
- Run 34 policy checks across five domains; every check listed whether triggered or clear
- Flag findings with severity, policy reference, and suggested action
- Per-domain HITL: reviewer accepts or overrides each finding with justification
- Export analysis to CSV for offline comparison against golden set — this closes the evaluation loop: export → identify gaps → adjust prompt or rule → re-run

**Phase 1 — Version control for agent and policy**
The CSV evaluation loop works but has no memory. When a prompt or policy rule changes, there is no record of what changed, when, and what effect it had. Phase 1 adds separate version control for agent prompts and policy rules — every analysis is tagged with the exact configuration that produced it. This makes regressions diagnosable: a change in output can be attributed to a prompt update or a policy update, not both. It also enables per-version evaluation against the golden set, so teams can compare quality rate and override rate across versions before deciding whether to deploy a change.

**Phase 2 — Communication integration**
Once evaluation is stable, reduce friction in the communication workflow. Slack approval actions so reviewers do not need to return to the platform. Gmail / Outlook integration so vendor follow-up drafts can be sent directly after human confirmation, with the send event written to the audit log. No message leaves the system without explicit human action.
