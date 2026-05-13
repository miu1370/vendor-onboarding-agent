# Vendor Onboarding Agent

A human-in-the-loop AI platform that automates vendor procurement review. The agent parses intake documents, runs 34 policy checks across 5 compliance domains, scores risk, and surfaces structured findings for human reviewers — who accept, modify, or override each check before submitting a final onboarding decision.

See [ARCHITECTURE.md](../ARCHITECTURE.md) for the design rationale and productionization path.

---

## Quick Start

```bash
cd vendor_agent
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
streamlit run app.py
```

The app opens at `http://localhost:8501`. Click **▶ Analyze** on any case to run the agent. Results are saved automatically to `analysis_results.json` — subsequent visits load from this file so the agent does not re-run unless you request a new version.

To add a new vendor, click **➕ New Vendor** on the pipeline page and upload documents.

---

## Project Structure

```
Candidate_package/
├── cases/
│   ├── case_001/    # Northstar Analytics — SaaS/AI, $85K ACV, HIGH risk
│   ├── case_002/    # Workspace Depot — Office Supplies, $12K ACV, LOW risk
│   └── case_003/    # TalentPulse AI — HR/AI, $120K ACV, HIGH risk
│       Each case: {id}_intake.xlsx, _quote.csv, _contract.pdf,
│                  _security_questionnaire.md, _vendor_email.txt
│
├── docs/            # 7 internal policy documents (read by agent at runtime)
│
├── tools/
│   ├── budget_lookup.csv       # Mock cost-center budget data
│   └── vendor_register.csv     # Mock existing vendor registry
│
├── ARCHITECTURE.md  # Design decisions + productionization path
│
└── vendor_agent/
    ├── app.py                  # Streamlit UI
    ├── agent.py                # Claude tool-calling loop + Generator-Critic
    ├── parsers.py              # Document parsers (xlsx, csv, pdf, md, txt)
    ├── tools.py                # 9 tool functions + dispatcher
    ├── analysis_results.json   # Persisted analysis versions + reviewer decisions
    ├── audit_log.json          # Immutable record of all submitted decisions
    ├── new_vendors.json        # Newly uploaded vendors pending analysis
    ├── uploads/                # Uploaded vendor documents
    └── requirements.txt
```

---

## Deploying to Streamlit Cloud

1. Push the repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) and connect the repo
3. Set **Main file path** to `vendor_agent/app.py`
4. Add the API key under **Advanced settings → Secrets**:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
5. Deploy — Streamlit Cloud redeploys automatically on every push to `main`

---

## Policy Checklist — 34 Rules Across 5 Domains

| Domain | IDs | Key checks |
|--------|-----|------------|
| **Finance** | FIN-001 → FIN-009 | ACV/TCV approval thresholds, payment terms, budget sufficiency, contract duration |
| **Legal** | LEG-001 → LEG-007 | Governing law, liability cap, auto-renewal, DPA, AI training opt-out |
| **Security** | SEC-001 → SEC-006 | SOC 2 Type II, security questionnaire, data residency, EU subprocessors |
| **Data Handling** | DAT-001 → DAT-003 | Restricted data, PII handling, cross-border transfer |
| **Procurement** | PRO-001 → PRO-009 | Vendor register, duplicate check, required docs, approval routing |

Each rule produces: `result` (triggered / pass), `flag_severity` (blocking / warning / info), `flag_reason`, and `action_required`.
