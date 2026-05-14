# Architecture Note — Vendor Onboarding Agent

## Pipeline

```
 USER                                        SYSTEM
 ─────────────────────────────────────────────────────────────────────────────

 Upload documents                            parsers.py
 (xlsx · csv · pdf · md · txt)  ──────────▶ structured case data
                                                        │
                                             ┌──────────▼──────────────────┐
                                             │  PRE-SCREEN   [CODE]        │
                                             │                             │
                                             │  missing required docs?     │
                                             │  ACV / TCV thresholds?      │
                                             │  required intake fields?    │
                                             │                             │
                                             │  deterministic · same input │
                                             │  always same result         │
                                             └──────────┬──────────────────┘
                                                        │
                                             ┌──────────▼──────────────────┐
 Click ▶ Analyze                ──────────▶  │  GENERATOR    [LLM]         │
                                             │                             │
                                             │  reads: contracts,          │
                                             │    questionnaires, emails   │
                                             │                             │
                                             │  extracts → case_facts      │
                                             │  drafts  → vendor email     │
                                             └──────────┬──────────────────┘
                                                        │ case_facts
                                             ┌──────────▼──────────────────┐
                                             │  POLICY CHECKLIST  [CODE]   │
                                             │                             │
                                             │  34 rules · pure function   │
                                             │  input:  case_facts         │
                                             │  output: triggered / clear  │
                                             │                             │
                                             │  Finance · Legal · Security │
                                             │  Procurement · Data Handling│
                                             └──────────┬──────────────────┘
                                                        │
                                             ┌──────────▼──────────────────┐
                                             │  CRITIC   [LLM]             │
                                             │  medium / high risk only    │
                                             │                             │
                                             │  independent review of      │
                                             │  generator output           │
                                             │  → surfaces missed flags    │
                                             └──────────┬──────────────────┘
                                                        │
 ◀──────────────── findings + checklist ───────────────┘

 ╔═══════════════════════════════════════════════════════════════════════╗
 ║  REVIEW FINDINGS   [HUMAN]                                           ║
 ║                                                                       ║
 ║  per-domain tabs: Finance · Legal · Security ·                       ║
 ║  Procurement · Data Handling · Vendor Risk                           ║
 ║                                                                       ║
 ║  each triggered rule:                                                ║
 ║    ✓ Accept  |  ✎ Modify (adjust assignee / action)                  ║
 ║              |  ⚠ Override → Escalation or Blocking                  ║
 ║                  override requires written justification             ║
 ╚═══════════════════════════════════════════════════════════════════════╝
                                   │
                          all rules reviewed
                                   │
 ╔═══════════════════════════════════════════════════════════════════════╗
 ║  CONFIRM EMAIL DRAFT   [HUMAN]                                       ║
 ║                                                                       ║
 ║  LLM drafts vendor follow-up based on findings                      ║
 ║  reviewer edits or approves — nothing sends without explicit action  ║
 ╚═══════════════════════════════════════════════════════════════════════╝
                                   │
 ╔═══════════════════════════════════════════════════════════════════════╗
 ║  SUBMIT FINAL DECISION   [HUMAN]                                     ║
 ║                                                                       ║
 ║  ✅ Complete Onboarding  |  🟡 Escalate  |  🔴 Block                 ║
 ╚═══════════════════════════════════════════════════════════════════════╝
                                   │
              ┌────────────────────┴────────────────────┐
              ▼                                         ▼
   analysis_results.json                       audit_log.json
   analysis versions +                         immutable record of every
   reviewer decisions                          decision and override
```

---

## Why LLM extracts, code evaluates

Vendor documents are unstructured — contracts use varied language, questionnaires differ by vendor, intake forms have free-text fields. Extracting structured facts from these requires language understanding, which is what the LLM does well.

But once facts are extracted, policy evaluation is a different problem: *"is ACV > $50K?"* has one correct answer given the number. Delegating that to an LLM introduces unnecessary variance. `run_policy_checklist()` is a pure function — same facts in, same 34 results out, every time. Changing a threshold means editing one line of code, not re-prompting.

This separation also makes findings auditable: each triggered rule traces to an extracted value, and each extracted value traces to a source document.

---

## Why human review is per-domain, not a single gate

A single approve/reject gate at the end obscures where the agent went wrong. Per-domain review lets each reviewer evaluate findings in their area — Finance checks the approval thresholds, Legal checks the contract terms — and record exactly which judgements they accepted or overrode. This is what makes the override log useful: it tells you not just that someone disagreed, but *what* they disagreed with and *why*.

---

## Prototype vs Productionization

**Prototype (current)**
- Upload vendor cases; parse five document formats
- Run 34 policy checks across five domains; every check listed whether triggered or clear
- Flag findings with severity, policy reference, and suggested action
- Per-domain HITL: reviewer accepts or overrides each finding with justification
- Export analysis to CSV for offline comparison against a golden set

**Phase 1 — Version control for agent and policy**
When a prompt or policy rule changes, there is currently no record of what changed or what effect it had. Phase 1 adds separate version control for agent prompts and policy rules — every analysis is tagged with the exact configuration that produced it. This makes regressions diagnosable and enables per-version evaluation against the golden set.

**Phase 2 — Communication integration**
Slack approval actions so reviewers do not need to return to the platform. Gmail / Outlook integration so vendor follow-up drafts can be sent directly after human confirmation, with the send event written to the audit log. No message leaves the system without explicit human action.
