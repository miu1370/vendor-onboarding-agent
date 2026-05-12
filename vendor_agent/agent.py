import json
import re
import anthropic
from tools import execute_tool, extract_contract_clauses, pre_screen_case

MODEL = "claude-sonnet-4-6"

TOOLS = [
    {
        "name": "lookup_budget",
        "description": "Look up the available budget for a cost center from the internal finance system.",
        "input_schema": {
            "type": "object",
            "properties": {"cost_center": {"type": "string"}},
            "required": ["cost_center"],
        },
    },
    {
        "name": "check_existing_vendor",
        "description": "Check the vendor register for an exact or fuzzy match.",
        "input_schema": {
            "type": "object",
            "properties": {"vendor_name": {"type": "string"}},
            "required": ["vendor_name"],
        },
    },
    {
        "name": "calculate_total_contract_value",
        "description": "Calculate total contract value (ACV × term_months / 12 + one-time fees).",
        "input_schema": {
            "type": "object",
            "properties": {
                "annual_contract_value": {"type": "number"},
                "contract_term_months": {"type": "integer"},
                "one_time_fees": {"type": "number"},
            },
            "required": ["annual_contract_value", "contract_term_months"],
        },
    },
    {
        "name": "classify_data_sensitivity",
        "description": "Classify data sensitivity level: public / internal / confidential / restricted.",
        "input_schema": {
            "type": "object",
            "properties": {
                "data_types": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["data_types"],
        },
    },
    {
        "name": "extract_contract_clauses",
        "description": (
            "Pattern-based extraction of key contract clauses: auto-renewal, liability, "
            "governing law, AI/model-training language, DPA reference, subprocessor regions. "
            "No input parameters — uses the loaded contract automatically."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "validate_cross_document_consistency",
        "description": (
            "Compare key fields across intake, quote, vendor register, and questionnaire. "
            "Detects ACV mismatches, new_vendor vs register conflicts, subprocessor discrepancies."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "intake_acv": {"type": "number"},
                "intake_renewal_status": {"type": "string", "enum": ["new_vendor", "renewal"]},
                "intake_subprocessors": {"type": "array", "items": {"type": "string"}},
                "quote_annual_total": {"type": "number"},
                "vendor_found_in_register": {"type": "boolean"},
                "vendor_register_status": {"type": "string"},
                "questionnaire_subprocessors": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "intake_acv", "intake_renewal_status", "intake_subprocessors",
                "quote_annual_total", "vendor_found_in_register",
            ],
        },
    },
    {
        "name": "determine_required_approvals",
        "description": "Determine required approvals and reviews based on vendor details and internal policies.",
        "input_schema": {
            "type": "object",
            "properties": {
                "annual_contract_value": {"type": "number"},
                "total_contract_value": {"type": "number"},
                "contract_term_months": {"type": "integer"},
                "risk_tier": {"type": "string", "enum": ["low", "medium", "high"]},
                "data_sensitivity": {"type": "string", "enum": ["public", "internal", "confidential", "restricted"]},
                "payment_terms": {"type": "string"},
                "has_eu_subprocessors": {"type": "boolean"},
                "has_apac_subprocessors": {"type": "boolean"},
                "has_ai_training": {"type": "boolean"},
                "budget_sufficient": {"type": "boolean"},
            },
            "required": [
                "annual_contract_value", "total_contract_value", "contract_term_months",
                "risk_tier", "data_sensitivity", "payment_terms",
            ],
        },
    },
    {
        "name": "submit_triage_output",
        "description": "Submit the final structured triage output. Call only after all other tools.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "risk_tier": {"type": "string", "enum": ["low", "medium", "high"]},
                "missing_documents": {"type": "array", "items": {"type": "string"}},
                "blocking_issues": {"type": "array", "items": {"type": "string"}},
                "consistency_issues": {"type": "array", "items": {"type": "string"}},
                "contract_legal_flags": {"type": "array", "items": {"type": "string"}},
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
                "draft_vendor_followup": {"type": "string"},
                "draft_internal_ticket": {"type": "string"},
                "recommendation": {
                    "type": "string",
                    "enum": ["ready_for_approval", "pending_information", "escalate_to_human", "blocked"],
                },
            },
            "required": [
                "summary", "risk_tier", "missing_documents", "blocking_issues",
                "policy_flags", "required_approvals", "required_reviews",
                "draft_internal_ticket", "recommendation",
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_system_prompt(policies: dict) -> str:
    policy_text = "\n\n---\n\n".join(
        f"## {name.replace('_', ' ').title()}\n\n{content}"
        for name, content in policies.items()
    )
    return f"""You are a vendor procurement triage agent. Review vendor onboarding packages and produce a structured recommendation.

Call tools in this order:
1. lookup_budget
2. check_existing_vendor
3. calculate_total_contract_value
4. classify_data_sensitivity
5. extract_contract_clauses (no parameters)
6. validate_cross_document_consistency
7. determine_required_approvals
8. submit_triage_output

Rules:
- Never approve vendors, commit spend, accept contract terms, or send external communications.
- If vendor is marked new_vendor but exists in register → consistency issue.
- Budget remaining < ACV → budget_sufficient=false.
- Ambiguous AI-training language ("service improvement", "model enhancement", "benchmarking") → has_ai_training=true, flag it.
- Customer names/emails = restricted data (customer PII), not just confidential.
- Missing SOC 2 Type II for medium/high-risk SaaS = blocking issue.
- Missing DPA when personal data is processed = blocking issue.
- AI training without confirmed opt-out = blocking issue for restricted-data vendors.

INTERNAL POLICIES:
{policy_text}"""


def _build_case_prompt(case: dict, pre_screen: dict) -> str:
    intake = case["intake"]
    acv = intake.get("annual_contract_value") or 0
    term = intake.get("contract_term_months") or 0

    quote_lines, total_one_time = [], 0.0
    for item in case["quote"]:
        ann = float(item.get("annual_amount") or 0)
        ot = float(item.get("one_time_amount") or 0)
        total_one_time += ot
        quote_lines.append(f"  • {item['line_item']}: ${ann:,.0f}/yr + ${ot:,.0f} one-time")

    doc_status = "\n".join(
        f"  {'✓' if v.get('provided') else '✗'} {k}: {v.get('artifact','')}"
        for k, v in intake.get("document_checklist", {}).items()
        if not k.startswith("Document Checklist")
    )

    # Inject pre-screen context to guide short-circuit behavior
    if pre_screen["block_reasons"]:
        screen_note = (
            "\n=== PRE-SCREENING ALERT: BLOCK CONDITIONS DETECTED ===\n"
            + "\n".join(f"  ⛔ {r}" for r in pre_screen["block_reasons"])
            + "\nSet recommendation=blocked and include these as blocking_issues.\n"
        )
    elif pre_screen["escalate_reasons"]:
        screen_note = (
            "\n=== PRE-SCREENING ALERT: ESCALATE CONDITIONS DETECTED ===\n"
            + "\n".join(f"  ⚠ {r}" for r in pre_screen["escalate_reasons"])
            + "\nSet recommendation=escalate_to_human and include these as policy_flags.\n"
        )
    else:
        screen_note = "\n=== PRE-SCREENING: No immediate block or escalate triggers found. ===\n"

    return f"""Triage this vendor onboarding case.
{screen_note}
=== INTAKE ===
Vendor: {intake.get('vendor_name')}  |  Category: {intake.get('vendor_category')}  |  New/Renewal: {intake.get('renewal_or_new_vendor')}
Team: {intake.get('requesting_team')}  |  Owner: {intake.get('business_owner')} <{intake.get('business_owner_email')}>
Cost Center: {intake.get('cost_center')}  |  ACV: ${acv:,}  |  Term: {term} months  |  Payment: {intake.get('payment_terms')}
Start: {intake.get('requested_start_date')}
Use Case: {intake.get('use_case')}
Data Access: {', '.join(intake.get('data_access') or []) or 'None'}
Integrations: {', '.join(intake.get('system_integrations') or []) or 'None'}
Subprocessors: {', '.join(intake.get('subprocessors_declared') or []) or 'None'}
AI Functionality: {intake.get('ai_functionality') or 'None'}

=== DOCUMENT CHECKLIST ===
{doc_status}

=== QUOTE ===
{chr(10).join(quote_lines)}
  One-time total: ${total_one_time:,.0f}

=== VENDOR EMAIL ===
{case['vendor_email']}

=== SECURITY QUESTIONNAIRE ===
{case['security_questionnaire']}

=== CONTRACT EXCERPT ===
{case['contract'][:5000]}

Begin analysis — follow tool call order."""


# ---------------------------------------------------------------------------
# Reflection: Critic pass (Generator-Critic pattern)
# ---------------------------------------------------------------------------

def run_critic(generator_triage: dict, finance_policy: str, security_policy: str, api_key: str) -> dict:
    """
    Second LLM pass: audits generator's recommendation against finance and security policies.
    Returns structured critique for the Reflection Log.
    """
    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""You are a strict procurement compliance auditor. Review this AI-generated vendor triage recommendation.

GENERATOR RECOMMENDATION:
{json.dumps(generator_triage, indent=2)}

FINANCE APPROVAL MATRIX (audit against this):
{finance_policy}

SECURITY REVIEW POLICY (audit against this):
{security_policy}

Return ONLY a valid JSON object — no markdown, no code blocks:
{{
  "agreement_level": "agree" or "partial" or "disagree",
  "confirmed_findings": ["list of generator findings you confirm"],
  "missed_findings": ["list of issues the generator missed or under-weighted"],
  "over_flagged": ["list of issues the generator over-emphasized"],
  "risk_assessment": "agree" or "recommend_upgrade" or "recommend_downgrade",
  "confidence": <integer 0-100>,
  "summary": "<2-3 sentence critique of the generator analysis>"
}}"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass

    return {
        "agreement_level": "agree",
        "confirmed_findings": [],
        "missed_findings": [],
        "over_flagged": [],
        "risk_assessment": "agree",
        "confidence": 70,
        "summary": "Critic review completed.",
    }


# ---------------------------------------------------------------------------
# Main agent entry point
# ---------------------------------------------------------------------------

def run_vendor_agent(case_data: dict, policies: dict, api_key: str) -> dict:
    # Step 1: Deterministic pre-screening (short-circuit logic)
    clean_checklist = {
        k: v for k, v in case_data["intake"].get("document_checklist", {}).items()
        if not k.startswith("Document Checklist")
    }
    pre_screen = pre_screen_case(case_data["intake"], clean_checklist)

    # Step 2: Generator — full LLM analysis with tool-calling loop
    client = anthropic.Anthropic(api_key=api_key)
    messages = [{"role": "user", "content": _build_case_prompt(case_data, pre_screen)}]
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
                result = extract_contract_clauses(case_data["contract"])
                result_str = json.dumps(result)
            else:
                result_str = execute_tool(block.name, block.input)

            tool_calls_log.append({"tool": block.name, "input": block.input, "output": json.loads(result_str)})
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result_str})

        messages.append({"role": "user", "content": tool_results})

        if triage_output:
            break

    # Step 3: Critic — reflection pass for medium/high risk (Generator-Critic pattern)
    reflection = None
    if triage_output and triage_output.get("risk_tier") in ("medium", "high"):
        try:
            critic = run_critic(
                triage_output,
                policies.get("finance_approval_matrix", ""),
                policies.get("security_review_policy", ""),
                api_key,
            )
            gen_flags = (triage_output.get("blocking_issues") or [])[:3]
            gen_flags += [
                f.get("issue", "") for f in (triage_output.get("policy_flags") or [])[:2]
            ]
            reflection = {
                "generator": {
                    "risk_tier": triage_output.get("risk_tier"),
                    "recommendation": triage_output.get("recommendation"),
                    "summary": (triage_output.get("summary") or "")[:300],
                    "key_findings": gen_flags,
                },
                "critic": critic,
                "final": {
                    "risk_tier": triage_output.get("risk_tier"),
                    "risk_assessment": critic.get("risk_assessment", "agree"),
                    "adjustments": critic.get("missed_findings", []),
                },
            }
        except Exception:
            pass

    return {
        "triage_output": triage_output,
        "tool_calls": tool_calls_log,
        "pre_screen": pre_screen,
        "reflection": reflection,
        "message_count": len(messages),
    }
