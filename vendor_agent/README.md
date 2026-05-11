# Vendor Onboarding Agent

An AI agent prototype that reviews mock vendor onboarding packages and produces structured procurement recommendations for a human owner.

## Setup

```bash
cd vendor_agent
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
streamlit run app.py
```

The app opens at `http://localhost:8501`. Select a case, click **▶ Run Agent Analysis**, and review the output across the six tabs.

## Project structure

```
Candidate_package/
├── cases/           # 3 synthetic vendor onboarding cases (xlsx, csv, pdf, md, txt)
├── docs/            # 7 internal policy documents
├── tools/           # Mock deterministic data (budget_lookup.csv, vendor_register.csv)
└── vendor_agent/
    ├── app.py       # Streamlit UI + human approval gate
    ├── agent.py     # Claude API agent with tool-calling loop
    ├── parsers.py   # Document parsers (xlsx, csv, pdf, md, txt)
    ├── tools.py     # 5 deterministic tool functions + dispatcher
    └── requirements.txt
```

## Architecture note

The agent follows the process flow provided in `tools/Agent process flow.png`:

```
Input documents
    │
    ▼
parsers.py          ← parse xlsx / csv / pdf / md / txt
    │
    ▼
Claude (claude-sonnet-4-6) with tool_use
    ├── lookup_budget()                 → check cost-center budget vs ACV
    ├── check_existing_vendor()         → detect duplicate vendor entries
    ├── calculate_total_contract_value()→ ACV × term / 12 + one-time fees
    ├── classify_data_sensitivity()     → restricted / confidential / internal
    ├── determine_required_approvals()  → finance matrix + legal + security triggers
    └── submit_triage_output()          → structured JSON recommendation
    │
    ▼
Streamlit UI
    ├── Summary & policy flags
    ├── Approval routing
    ├── Missing documents
    ├── DRAFT communications (vendor follow-up + internal ticket)
    ├── Tool call log (transparent reasoning)
    └── Human Approval Gate  ← decision recorded here; nothing proceeds without it
```

All external communications are drafted only — they require explicit human approval before sending. The agent cannot approve vendors, commit spend, or modify contract terms.

## How to productionize

| Area | Current prototype | Production approach |
|------|-------------------|---------------------|
| **Auth** | API key in env var | OAuth / SSO; per-user API key vault |
| **Data ingestion** | Local file paths | S3 / GCS intake bucket; webhook trigger |
| **State** | Streamlit session state | Database (Postgres) + task queue (Celery/SQS) |
| **Audit log** | In-memory tool call log | Append-only audit table; every agent action recorded |
| **Human gate** | Streamlit radio buttons | Approval workflow (Slack bot, email action links, or procurement system integration) |
| **Policy updates** | Edit markdown files | Versioned policy store; agent re-evaluated on policy change |
| **LLM** | claude-sonnet-4-6 | Prompt-cache policy docs (5-min TTL); route high-risk cases to claude-opus-4-7 |
| **Observability** | None | LLM tracing (LangSmith / Helicone); latency + token dashboards |
| **Testing** | Manual case review | Golden-set eval harness: run all 3 cases on every deploy, assert expected risk tiers and approval lists |
