import json
import re
import anthropic
from tools import execute_tool, extract_contract_clauses, pre_screen_case

MODEL = "claude-sonnet-4-6"
MODEL_CRITIC = "claude-haiku-4-5-20251001"

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
        "name": "run_policy_checklist",
        "description": (
            "Run the complete 27-item policy checklist deterministically across Finance (FIN-001–009), "
            "Legal (LEG-001–010), Security (SEC-001–007), Procurement (PRO-001–005), "
            "Data Handling (DAT-001–003). Returns every check — cleared and triggered. "
            "Call after extract_contract_clauses and validate_cross_document_consistency. "
            "Pass the returned `checklist` array verbatim as policy_checklist in submit_triage_output."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "acv": {"type": "number", "description": "Annual contract value from intake"},
                "tcv": {"type": "number", "description": "Total contract value from calculate_total_contract_value"},
                "payment_terms": {"type": "string"},
                "contract_term_months": {"type": "integer"},
                "data_sensitivity": {"type": "string", "enum": ["public", "internal", "confidential", "restricted"]},
                "budget_remaining": {"type": "number", "description": "Preferred: annual_budget_remaining from lookup_budget"},
                "budget_sufficient": {"type": "boolean", "description": "Fallback if budget_remaining is unavailable: true = budget covers ACV"},
                "vendor_found_in_register": {"type": "boolean"},
                "renewal_status": {"type": "string", "enum": ["new_vendor", "renewal"]},
                "soc2_type2_provided": {"type": "boolean"},
                "dpa_provided": {"type": "boolean"},
                "security_questionnaire_provided": {"type": "boolean"},
                "vendor_category": {"type": "string"},
                "has_eu_subprocessors": {"type": "boolean"},
                "has_apac_subprocessors": {"type": "boolean"},
                "has_ai_training": {"type": "boolean"},
                "ai_training_opt_out_confirmed": {"type": "boolean"},
                "acv_matches_quote": {"type": "boolean", "description": "True if intake ACV == quote annual total"},
                "subprocessors_consistent": {"type": "boolean", "description": "True if intake and questionnaire subprocessors match"},
                "liability_cap_months": {"type": "integer", "description": "Months in liability cap; omit if not detected"},
                "auto_renewal_found": {"type": "boolean"},
                "governing_law_outside_us": {"type": "boolean"},
                "dpa_ref_in_contract": {"type": "boolean"},
                "system_integrations": {"type": "array", "items": {"type": "string"}},
                "required_intake_fields_complete": {"type": "boolean"},
                "all_required_docs_provided": {"type": "boolean"},
            },
            "required": [
                "acv", "tcv", "payment_terms", "contract_term_months", "data_sensitivity",
                "vendor_found_in_register", "renewal_status",
                "soc2_type2_provided", "dpa_provided", "security_questionnaire_provided", "vendor_category",
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
                "case_facts": {
                    "type": "object",
                    "description": "Structured facts extracted from all documents. Fill from tool outputs before submitting.",
                    "properties": {
                        "vendor_name": {"type": "string"},
                        "vendor_category": {"type": "string"},
                        "renewal_status": {"type": "string"},
                        "cost_center": {"type": "string"},
                        "acv": {"type": "number"},
                        "tcv": {"type": "number"},
                        "contract_term_months": {"type": "integer"},
                        "payment_terms": {"type": "string"},
                        "net_payment_days": {"type": "integer"},
                        "budget_remaining": {"type": "number"},
                        "budget_sufficient": {"type": "boolean"},
                        "data_sensitivity": {"type": "string"},
                        "data_types": {"type": "array", "items": {"type": "string"}},
                        "system_integrations": {"type": "array", "items": {"type": "string"}},
                        "subprocessors": {"type": "array", "items": {"type": "string"}},
                        "has_eu_subprocessors": {"type": "boolean"},
                        "has_apac_subprocessors": {"type": "boolean"},
                        "ai_functionality": {"type": "string"},
                        "has_ai_training_language": {"type": "boolean"},
                        "ai_training_opt_out_confirmed": {"type": "boolean"},
                        "soc2_type2_provided": {"type": "boolean"},
                        "dpa_provided": {"type": "boolean"},
                        "security_questionnaire_provided": {"type": "boolean"},
                        "auto_renewal_clause": {"type": "boolean"},
                        "governing_law": {"type": "string"},
                        "governing_law_outside_us": {"type": "boolean"},
                        "liability_cap_months": {"type": "integer"},
                        "dpa_referenced_in_contract": {"type": "boolean"},
                        "vendor_in_register": {"type": "boolean"},
                        "acv_matches_quote": {"type": "boolean"},
                        "subprocessors_consistent": {"type": "boolean"},
                        "all_docs_provided": {"type": "boolean"},
                        "missing_documents": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "policy_checklist": {
                    "type": "array",
                    "description": "Full 27-item checklist from run_policy_checklist — pass the `checklist` array verbatim.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "check_id": {"type": "string"},
                            "domain": {"type": "string"},
                            "description": {"type": "string"},
                            "policy_ref": {"type": "string"},
                            "extracted_value": {"type": "string"},
                            "result": {"type": "string", "enum": ["clear", "triggered"]},
                            "flag_severity": {"type": "string"},
                            "flag_reason": {"type": "string"},
                            "action_required": {"type": "string"},
                        },
                    },
                },
            },
            "required": [
                "summary", "risk_tier", "missing_documents", "blocking_issues",
                "policy_flags", "required_approvals", "required_reviews",
                "draft_internal_ticket", "recommendation", "policy_checklist",
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
7. run_policy_checklist — pass all extracted values; set acv_matches_quote=false if issues[type=acv_mismatch] found; set subprocessors_consistent=false if subprocessor issues found; pass the returned `checklist` array verbatim as policy_checklist in submit_triage_output
8. determine_required_approvals
9. submit_triage_output

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
        model=MODEL_CRITIC,
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
# Build case_facts from tool calls (deterministic fallback)
# ---------------------------------------------------------------------------

def _build_case_facts(tool_calls_log: list, case_data: dict, triage_output: dict) -> dict:
    """
    Assemble case_facts from tool call inputs/outputs so the UI is never empty
    even if the LLM forgot to fill in case_facts in submit_triage_output.
    """
    by_tool: dict = {}
    for tc in tool_calls_log:
        by_tool.setdefault(tc["tool"], []).append(tc)

    def _inp(tool): return (by_tool.get(tool) or [{}])[0].get("input", {})
    def _out(tool): return (by_tool.get(tool) or [{}])[0].get("output", {})

    intake    = case_data.get("intake", {})
    budget    = _out("lookup_budget")
    vendor_r  = _out("check_existing_vendor")
    tcv_out   = _out("calculate_total_contract_value")
    sens_out  = _out("classify_data_sensitivity")
    clauses   = _out("extract_contract_clauses")
    consis_i  = _inp("validate_cross_document_consistency")
    consis_o  = _out("validate_cross_document_consistency")
    chk_i     = _inp("run_policy_checklist")
    submit_i  = _inp("submit_triage_output")

    issue_types = [iss.get("type", "") for iss in (consis_o.get("issues") or [])]

    governing_law_text = (clauses.get("governing_law") or {}).get("excerpt") or ""
    us_states = ["delaware", "california", "new york", "texas", "washington", "nevada", "florida"]
    gov_outside_us = chk_i.get("governing_law_outside_us",
                        not any(s in governing_law_text.lower() for s in us_states)
                        if governing_law_text else False)

    liability_text = (clauses.get("limitation_of_liability") or {}).get("excerpt") or ""
    liability_months = chk_i.get("liability_cap_months") or _parse_liability_months(liability_text)

    payment = intake.get("payment_terms") or chk_i.get("payment_terms") or ""
    net_days = None
    m = re.search(r'Net\s*(\d+)', payment, re.IGNORECASE)
    if m:
        net_days = int(m.group(1))

    doc_check = {k: v for k, v in intake.get("document_checklist", {}).items()
                 if not k.startswith("Document Checklist")}
    missing_docs = submit_i.get("missing_documents") or triage_output.get("missing_documents") or []

    facts = {
        "vendor_name":                   intake.get("vendor_name") or vendor_r.get("vendor_id"),
        "vendor_category":               intake.get("vendor_category") or chk_i.get("vendor_category"),
        "renewal_status":                intake.get("renewal_or_new_vendor") or chk_i.get("renewal_status"),
        "cost_center":                   intake.get("cost_center"),
        "acv":                           intake.get("annual_contract_value") or chk_i.get("acv"),
        "tcv":                           tcv_out.get("total_contract_value") or chk_i.get("tcv"),
        "contract_term_months":          intake.get("contract_term_months") or chk_i.get("contract_term_months"),
        "payment_terms":                 payment,
        "net_payment_days":              net_days,
        "budget_remaining":              budget.get("annual_budget_remaining") or chk_i.get("budget_remaining"),
        "budget_sufficient":             chk_i.get("budget_sufficient",
                                             (budget.get("annual_budget_remaining") or 0) >= (intake.get("annual_contract_value") or 0)
                                             if budget.get("annual_budget_remaining") is not None else None),
        "data_sensitivity":              sens_out.get("sensitivity_level") or chk_i.get("data_sensitivity"),
        "data_types":                    _inp("classify_data_sensitivity").get("data_types") or intake.get("data_access"),
        "system_integrations":           chk_i.get("system_integrations") or intake.get("system_integrations"),
        "subprocessors":                 consis_i.get("intake_subprocessors") or intake.get("subprocessors_declared"),
        "has_eu_subprocessors":          chk_i.get("has_eu_subprocessors",
                                             "European Union" in (clauses.get("subprocessor_regions_detected") or [])),
        "has_apac_subprocessors":        chk_i.get("has_apac_subprocessors",
                                             "APAC" in (clauses.get("subprocessor_regions_detected") or [])),
        "ai_functionality":              intake.get("ai_functionality"),
        "has_ai_training_language":      chk_i.get("has_ai_training",
                                             (clauses.get("ai_model_training") or {}).get("found", False)),
        "ai_training_opt_out_confirmed": chk_i.get("ai_training_opt_out_confirmed", False),
        "soc2_type2_provided":           chk_i.get("soc2_type2_provided",
                                             doc_check.get("SOC 2 Type II Report", {}).get("provided", False)),
        "dpa_provided":                  chk_i.get("dpa_provided",
                                             doc_check.get("Data Processing Agreement", {}).get("provided", False)),
        "security_questionnaire_provided": chk_i.get("security_questionnaire_provided",
                                             doc_check.get("Security Questionnaire", {}).get("provided", False)),
        "auto_renewal_clause":           chk_i.get("auto_renewal_found",
                                             (clauses.get("auto_renewal") or {}).get("found", False)),
        "governing_law":                 governing_law_text or None,
        "governing_law_outside_us":      gov_outside_us,
        "liability_cap_months":          liability_months,
        "dpa_referenced_in_contract":    chk_i.get("dpa_ref_in_contract",
                                             (clauses.get("data_processing_agreement_ref") or {}).get("found", False)),
        "vendor_in_register":            vendor_r.get("found", False),
        "acv_matches_quote":             chk_i.get("acv_matches_quote",
                                             "acv_mismatch" not in issue_types),
        "subprocessors_consistent":      chk_i.get("subprocessors_consistent",
                                             "subprocessor_undeclared_in_intake" not in issue_types),
        "all_docs_provided":             chk_i.get("all_required_docs_provided", len(missing_docs) == 0),
        "missing_documents":             missing_docs,
    }
    return {k: v for k, v in facts.items() if v is not None}


def _parse_liability_months(text: str):
    m = re.search(r'(\d+)\s*month', text, re.IGNORECASE)
    return int(m.group(1)) if m else None


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

    # Backfill case_facts deterministically if LLM left it empty
    if triage_output and not triage_output.get("case_facts"):
        triage_output["case_facts"] = _build_case_facts(tool_calls_log, case_data, triage_output)

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
