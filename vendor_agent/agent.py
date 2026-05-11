import json
import anthropic
from tools import execute_tool, extract_contract_clauses

MODEL = "claude-sonnet-4-6"

TOOLS = [
    {
        "name": "lookup_budget",
        "description": "Look up the available budget for a cost center from the internal finance system.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cost_center": {"type": "string", "description": "Cost center code, e.g. REVOPS-042"},
            },
            "required": ["cost_center"],
        },
    },
    {
        "name": "check_existing_vendor",
        "description": "Check the vendor register for an exact or fuzzy match. Returns match info or similar names that could be duplicates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "vendor_name": {"type": "string"},
            },
            "required": ["vendor_name"],
        },
    },
    {
        "name": "calculate_total_contract_value",
        "description": "Calculate total contract value (ACV × term_months / 12 + one-time fees) and return a breakdown.",
        "input_schema": {
            "type": "object",
            "properties": {
                "annual_contract_value": {"type": "number"},
                "contract_term_months": {"type": "integer"},
                "one_time_fees": {"type": "number", "description": "Sum of all one-time fees from the quote. Default 0."},
            },
            "required": ["annual_contract_value", "contract_term_months"],
        },
    },
    {
        "name": "classify_data_sensitivity",
        "description": "Classify the sensitivity level of data types the vendor will access (public / internal / confidential / restricted).",
        "input_schema": {
            "type": "object",
            "properties": {
                "data_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Full list of data types the vendor will access or process",
                },
            },
            "required": ["data_types"],
        },
    },
    {
        "name": "extract_contract_clauses",
        "description": (
            "Run pattern-based extraction on the contract to identify key legal clauses: "
            "auto-renewal, limitation of liability, governing law, AI/model-training language, "
            "data retention, termination rights, DPA reference, and subprocessor regions. "
            "Call this before determine_required_approvals. No input parameters required."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "validate_cross_document_consistency",
        "description": (
            "Compare key fields across the intake form, quote, vendor register, and security questionnaire. "
            "Detects: ACV mismatches, new_vendor vs register conflicts, subprocessor discrepancies. "
            "Call this after check_existing_vendor and calculate_total_contract_value."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "intake_acv": {"type": "number", "description": "ACV from the intake form"},
                "intake_renewal_status": {
                    "type": "string",
                    "enum": ["new_vendor", "renewal"],
                    "description": "renewal_or_new_vendor field from intake",
                },
                "intake_subprocessors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Subprocessors listed in the intake form",
                },
                "quote_annual_total": {
                    "type": "number",
                    "description": "Sum of all annual_amount fields from the quote CSV",
                },
                "vendor_found_in_register": {
                    "type": "boolean",
                    "description": "True if check_existing_vendor returned found=true or flag_for_review=true with similar vendors",
                },
                "vendor_register_status": {
                    "type": "string",
                    "description": "Status field from vendor register (active / inactive / empty string)",
                },
                "questionnaire_subprocessors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Subprocessors listed in the security questionnaire",
                },
            },
            "required": [
                "intake_acv",
                "intake_renewal_status",
                "intake_subprocessors",
                "quote_annual_total",
                "vendor_found_in_register",
            ],
        },
    },
    {
        "name": "determine_required_approvals",
        "description": "Determine which approvals and reviews are required based on vendor details and internal policies.",
        "input_schema": {
            "type": "object",
            "properties": {
                "annual_contract_value": {"type": "number"},
                "total_contract_value": {"type": "number"},
                "contract_term_months": {"type": "integer"},
                "risk_tier": {"type": "string", "enum": ["low", "medium", "high"]},
                "data_sensitivity": {
                    "type": "string",
                    "enum": ["public", "internal", "confidential", "restricted"],
                },
                "payment_terms": {"type": "string"},
                "has_eu_subprocessors": {"type": "boolean"},
                "has_apac_subprocessors": {"type": "boolean"},
                "has_ai_training": {"type": "boolean"},
                "budget_sufficient": {"type": "boolean"},
            },
            "required": [
                "annual_contract_value",
                "total_contract_value",
                "contract_term_months",
                "risk_tier",
                "data_sensitivity",
                "payment_terms",
            ],
        },
    },
    {
        "name": "submit_triage_output",
        "description": (
            "Submit the final structured triage output for human review. "
            "Call this only after using all other relevant tools."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "2-4 sentence summary of the vendor request and key issues",
                },
                "risk_tier": {"type": "string", "enum": ["low", "medium", "high"]},
                "missing_documents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Documents required by policy that are absent",
                },
                "blocking_issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Issues that prevent the request from being marked ready for approval",
                },
                "consistency_issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Cross-document inconsistencies found by validate_cross_document_consistency",
                },
                "contract_legal_flags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Legal flags surfaced by extract_contract_clauses",
                },
                "policy_flags": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "policy": {"type": "string"},
                            "issue": {"type": "string"},
                            "severity": {"type": "string", "enum": ["info", "warning", "blocking"]},
                        },
                        "required": ["policy", "issue", "severity"],
                    },
                },
                "required_approvals": {"type": "array", "items": {"type": "string"}},
                "required_reviews": {"type": "array", "items": {"type": "string"}},
                "draft_vendor_followup": {
                    "type": "string",
                    "description": "DRAFT email to vendor requesting missing items. Omit if nothing needed from vendor.",
                },
                "draft_internal_ticket": {
                    "type": "string",
                    "description": "DRAFT internal procurement ticket summarising the request and next steps",
                },
                "recommendation": {
                    "type": "string",
                    "enum": ["ready_for_approval", "pending_information", "escalate_to_human", "blocked"],
                },
            },
            "required": [
                "summary",
                "risk_tier",
                "missing_documents",
                "blocking_issues",
                "policy_flags",
                "required_approvals",
                "required_reviews",
                "draft_internal_ticket",
                "recommendation",
            ],
        },
    },
]


def _build_system_prompt(policies: dict) -> str:
    policy_text = "\n\n---\n\n".join(
        f"## {name.replace('_', ' ').title()}\n\n{content}"
        for name, content in policies.items()
    )
    return f"""You are a vendor procurement triage agent. Your job is to review vendor onboarding packages and produce a structured recommendation for the human procurement owner.

Call tools in this order:
1. lookup_budget — check cost-center budget
2. check_existing_vendor — detect duplicates in vendor register
3. calculate_total_contract_value — use ACV, term, and one-time fees from the quote
4. classify_data_sensitivity — pass the full list of data types from intake and questionnaire
5. extract_contract_clauses — no parameters; analyses the loaded contract automatically
6. validate_cross_document_consistency — pass values you learned from steps 1–5
7. determine_required_approvals — pass all relevant parameters including ai_training and subprocessor flags
8. submit_triage_output — only after all other tools have been called

Rules:
- You MUST NOT approve any vendor, commit spend, accept contract terms, or send external communications.
- All drafted communications are for human review only — label them DRAFT.
- If a vendor is marked new_vendor but already exists in the register → flag as consistency issue.
- Check whether budget remaining ≥ ACV; set budget_sufficient=false if not.
- Ambiguous AI-training language ("service improvement", "improve the services", "model enhancement", "benchmarking") counts as has_ai_training=true and must be flagged.
- Classify customer names + emails as restricted data (customer personal information), not just confidential.
- Missing SOC 2 Type II for medium/high-risk vendors is a blocking issue.
- Missing DPA when personal data is processed is a blocking issue.
- AI training without a confirmed opt-out mechanism is a blocking issue for restricted data vendors.

INTERNAL POLICIES:
{policy_text}"""


def _build_case_prompt(case: dict) -> str:
    intake = case["intake"]
    acv = intake.get("annual_contract_value") or 0
    term = intake.get("contract_term_months") or 0

    quote_lines = []
    total_one_time = 0.0
    for item in case["quote"]:
        ann = float(item.get("annual_amount") or 0)
        ot = float(item.get("one_time_amount") or 0)
        total_one_time += ot
        quote_lines.append(
            f"  • {item['line_item']}: ${ann:,.0f}/yr  +  ${ot:,.0f} one-time  [{item.get('billing_type','')}]"
        )

    doc_status = "\n".join(
        f"  {'✓' if v.get('provided') else '✗'} {k}: {v.get('artifact','')}"
        for k, v in intake.get("document_checklist", {}).items()
        if k not in ("Document Checklist - 001", "Document Checklist - 002", "Document Checklist - 003")
    )

    return f"""Please triage the following vendor onboarding case.

=== INTAKE FORM ===
Vendor: {intake.get('vendor_name')}
Requesting Team: {intake.get('requesting_team')}
Business Owner: {intake.get('business_owner')} <{intake.get('business_owner_email')}>
Cost Center: {intake.get('cost_center')}
Vendor Category: {intake.get('vendor_category')}
New or Renewal: {intake.get('renewal_or_new_vendor')}
Use Case: {intake.get('use_case')}
Annual Contract Value (intake): ${acv:,}
Contract Term: {term} months
Payment Terms: {intake.get('payment_terms')}
Requested Start: {intake.get('requested_start_date')}
Data Access: {', '.join(intake.get('data_access') or []) or 'None declared'}
System Integrations: {', '.join(intake.get('system_integrations') or []) or 'None'}
Subprocessors: {', '.join(intake.get('subprocessors_declared') or []) or 'None declared'}
AI Functionality: {intake.get('ai_functionality') or 'None'}

=== DOCUMENT CHECKLIST (intake assertions — cross-check with actual files) ===
{doc_status}

=== QUOTE ===
{chr(10).join(quote_lines)}
  Total one-time fees: ${total_one_time:,.0f}

=== VENDOR EMAIL ===
{case['vendor_email']}

=== SECURITY QUESTIONNAIRE ===
{case['security_questionnaire']}

=== CONTRACT EXCERPT ===
{case['contract'][:5000]}

Begin your analysis now. Follow the tool call order in your instructions."""


def run_vendor_agent(case_data: dict, policies: dict, api_key: str) -> dict:
    client = anthropic.Anthropic(api_key=api_key)

    messages = [{"role": "user", "content": _build_case_prompt(case_data)}]
    system = _build_system_prompt(policies)

    triage_output = None
    tool_calls_log = []

    for _ in range(25):
        response = client.messages.create(
            model=MODEL,
            max_tokens=8096,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            break
        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            if block.name == "submit_triage_output":
                triage_output = block.input
                result_str = json.dumps({"status": "received"})
            elif block.name == "extract_contract_clauses":
                # Inject contract text from case data — not from LLM input
                result = extract_contract_clauses(case_data["contract"])
                result_str = json.dumps(result)
            else:
                result_str = execute_tool(block.name, block.input)

            tool_calls_log.append(
                {
                    "tool": block.name,
                    "input": block.input,
                    "output": json.loads(result_str),
                }
            )

            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": result_str}
            )

        messages.append({"role": "user", "content": tool_results})

        if triage_output:
            break

    return {
        "triage_output": triage_output,
        "tool_calls": tool_calls_log,
        "message_count": len(messages),
    }
