import csv
import difflib
import json
import re
from pathlib import Path

BASE_PATH = str(Path(__file__).parent.parent)


def _load_csv(filename):
    rows = []
    with open(Path(BASE_PATH) / "tools" / filename, newline="") as f:
        for row in csv.DictReader(f):
            rows.append(dict(row))
    return rows


# ---------------------------------------------------------------------------
# Existing deterministic tools
# ---------------------------------------------------------------------------

def lookup_budget(cost_center: str) -> dict:
    for row in _load_csv("budget_lookup.csv"):
        if row["cost_center"] == cost_center:
            return {
                "found": True,
                "cost_center": cost_center,
                "department": row["department"],
                "annual_budget_remaining": float(row["annual_budget_remaining"]),
                "budget_owner": row["budget_owner"],
            }
    return {"found": False, "cost_center": cost_center, "annual_budget_remaining": None}


def check_existing_vendor(vendor_name: str) -> dict:
    vendors = _load_csv("vendor_register.csv")
    all_names = [v["vendor_name"] for v in vendors]

    for v in vendors:
        if v["vendor_name"].lower() == vendor_name.lower():
            return {
                "found": True,
                "match_type": "exact",
                "vendor_id": v["vendor_id"],
                "status": v["status"],
                "category": v["category"],
                "owner": v["owner"],
                "flag_for_review": True,
            }

    close = difflib.get_close_matches(vendor_name, all_names, n=3, cutoff=0.55)
    similar = []
    for name in close:
        v = next(v for v in vendors if v["vendor_name"] == name)
        similar.append({"vendor_name": v["vendor_name"], "vendor_id": v["vendor_id"], "status": v["status"]})

    return {
        "found": False,
        "similar_vendors": similar,
        "flag_for_review": bool(similar),
    }


def calculate_total_contract_value(
    annual_contract_value: float,
    contract_term_months: int,
    one_time_fees: float = 0,
) -> dict:
    tcv = (annual_contract_value * contract_term_months / 12) + one_time_fees
    return {
        "annual_contract_value": annual_contract_value,
        "contract_term_months": contract_term_months,
        "one_time_fees": one_time_fees,
        "total_contract_value": round(tcv, 2),
    }


def classify_data_sensitivity(data_types: list) -> dict:
    # Customer names + emails = customer personal information → RESTRICTED (per Data Handling Policy)
    RESTRICTED_KEYWORDS = {
        "customer name", "customer email", "customer personal",
        "customer pii", "employee personal", "employee name", "employee email",
        "employee pii", "performance rating", "salary", "compensation",
        "engagement survey", "attrition risk", "authentication credential",
        "production data", "financial account", "employee performance",
        "sensitive employee",
    }
    CONFIDENTIAL_KEYWORDS = {
        "crm opportunity", "sales activity", "customer workflow", "opportunity history",
        "internal financial", "vendor pricing", "product roadmap", "usage analytics",
    }

    restricted, confidential = [], []
    for item in data_types:
        item_lower = item.lower()
        if any(k in item_lower for k in RESTRICTED_KEYWORDS):
            restricted.append(item)
        elif any(k in item_lower for k in CONFIDENTIAL_KEYWORDS):
            confidential.append(item)

    level = "restricted" if restricted else ("confidential" if confidential else "internal")

    return {
        "sensitivity_level": level,
        "restricted_fields": restricted,
        "confidential_fields": confidential,
        "security_review_required": level in ("restricted", "confidential"),
        "legal_review_required": level in ("restricted", "confidential"),
    }


def determine_required_approvals(
    annual_contract_value: float,
    total_contract_value: float,
    contract_term_months: int,
    risk_tier: str,
    data_sensitivity: str,
    payment_terms: str,
    has_eu_subprocessors: bool = False,
    has_apac_subprocessors: bool = False,
    has_ai_training: bool = False,
    budget_sufficient: bool = True,
) -> dict:
    approvals = {"Business Owner"}
    reviews = set()
    flags = []

    if annual_contract_value > 250_000:
        approvals |= {"Procurement Manager", "CFO", "Executive Sponsor"}
    elif annual_contract_value > 100_000:
        approvals |= {"Procurement Manager", "VP Finance", "CFO"}
    elif annual_contract_value > 50_000:
        approvals |= {"Procurement Manager", "VP Finance"}
    elif annual_contract_value > 25_000:
        approvals.add("Procurement Manager")

    if not budget_sufficient:
        reviews.add("Finance / FP&A")
        flags.append("Budget insufficient — Finance review required regardless of ACV threshold")

    if contract_term_months > 24:
        reviews.add("Finance (multi-year contract)")
        flags.append(f"Contract term {contract_term_months} months exceeds 24-month threshold")

    m = re.search(r"net\s*(\d+)", payment_terms.lower())
    net_days = int(m.group(1)) if m else 30
    if net_days > 60:
        reviews |= {"VP Finance", "Legal (payment terms > Net 60)"}
        flags.append(f"Payment terms {payment_terms} exceed Net 60 — VP Finance + Legal required")
    elif net_days == 60:
        reviews.add("VP Finance")
        flags.append("Payment terms Net 60 — VP Finance review required")
    elif net_days == 45:
        approvals.add("Procurement Manager")

    legal_triggers = []
    if annual_contract_value > 50_000:
        legal_triggers.append("ACV > $50,000")
    if total_contract_value > 100_000:
        legal_triggers.append("TCV > $100,000")
    if contract_term_months > 12:
        legal_triggers.append("Contract term > 12 months")
    if data_sensitivity in ("restricted", "confidential"):
        legal_triggers.append("Personal or confidential data processing")
    if has_eu_subprocessors or has_apac_subprocessors:
        legal_triggers.append("Subprocessors outside the United States")
    if has_ai_training:
        legal_triggers.append("Vendor uses data for AI model training / product improvement")

    if legal_triggers:
        reviews.add("Legal")
        flags.append("Legal review required: " + "; ".join(legal_triggers))

    if data_sensitivity in ("restricted", "confidential") or risk_tier in ("medium", "high"):
        reviews.add("Security")
        flags.append("Security review required based on data sensitivity / risk tier")

    exec_triggers = []
    if has_ai_training:
        exec_triggers.append("Vendor uses company/employee data for AI model training")
    if risk_tier == "high" and data_sensitivity == "restricted":
        exec_triggers.append("High-risk vendor processing restricted data")
    if total_contract_value > 250_000:
        exec_triggers.append("Total contract value > $250,000")

    if exec_triggers:
        approvals.add("Executive Sponsor")
        flags.append("Executive approval required: " + "; ".join(exec_triggers))

    return {
        "required_approvals": sorted(approvals),
        "required_reviews": sorted(reviews),
        "flags": flags,
    }


# ---------------------------------------------------------------------------
# NEW: Contract clause extractor (deterministic pattern matching)
# ---------------------------------------------------------------------------

def extract_contract_clauses(contract_text: str) -> dict:
    """
    Pattern-match key legal clauses from contract text.
    Returns structured findings for the LLM to interpret against policy.
    """
    text_l = contract_text.lower()

    def find(patterns, window=350):
        for p in patterns:
            idx = text_l.find(p)
            if idx != -1:
                start = max(0, idx - 80)
                end = min(len(contract_text), idx + window)
                return {"found": True, "excerpt": contract_text[start:end].strip()}
        return {"found": False, "excerpt": None}

    auto_renewal = find(["auto-renew", "automatically renew", "automatic renewal", "auto renew", "evergreen"])
    liability = find(["limitation of liability", "limit of liability", "aggregate liability", "liability cap", "in no event"])
    gov_law = find(["governing law", "choice of law", "governed by"])
    data_retention_clause = find(["data retention", "retention period", "data deletion", "purge", "delete within"])
    termination = find(["termination", "either party may terminate", "notice of termination"])
    dpa_ref = find(["data processing agreement", "data processing addendum", "dpa", "data processor"])
    subprocessor_clause = find(["subprocessor", "sub-processor", "third-party processor"])

    # Detect AI / data-use language specifically
    ai_patterns = [
        "improve, and enhance the services and related models",
        "improve service performance",
        "model enhancement",
        "benchmarking",
        "service improvement",
        "product improvement",
        "product analytics",
        "account-level recommendation",
    ]
    ai_clause = find(ai_patterns, window=500)

    # --- Flag analysis ---
    ai_flags = []
    if ai_clause["found"]:
        excerpt_l = (ai_clause["excerpt"] or "").lower()
        # Unambiguous model training
        if any(t in excerpt_l for t in ["related models", "model enhancement", "benchmarking"]):
            ai_flags.append(
                "Contract explicitly permits vendor to use customer/employee data to improve AI models or benchmarks — "
                "requires Legal + Security + Executive approval; opt-out must be confirmed before signing"
            )
        # Ambiguous service improvement
        elif any(t in excerpt_l for t in ["service improvement", "improve service", "improve the services", "product improvement"]):
            ai_flags.append(
                "Ambiguous data-use language detected ('service improvement' / 'improve the services') — "
                "Legal and Security must confirm this does not permit model training on company data"
            )

    non_standard_clauses = []

    # Governing law outside US
    if gov_law["found"] and gov_law["excerpt"]:
        non_us = ["england", "wales", "ireland", "canada", "australia", "germany", "france", "singapore", "cayman"]
        for j in non_us:
            if j in gov_law["excerpt"].lower():
                non_standard_clauses.append(f"Governing law may be outside the United States ({j}) — Legal review required")
                break

    # Liability cap < 12 months
    if liability["found"] and liability["excerpt"]:
        m = re.search(r"(\d+)\s*month", liability["excerpt"].lower())
        if m and int(m.group(1)) < 12:
            non_standard_clauses.append(
                f"Liability cap appears below 12 months of fees ({m.group(1)} months) — Legal review required"
            )

    # Subprocessor regions
    subprocessor_regions = []
    if "european union" in text_l or "clearbit" in text_l or "(eu)" in text_l:
        subprocessor_regions.append("European Union")
    if "apac" in text_l or "asia" in text_l or "annotationworks" in text_l:
        subprocessor_regions.append("APAC")
    if "modelops" in text_l:
        subprocessor_regions.append("EU (ModelOps Labs)")

    return {
        "auto_renewal": auto_renewal,
        "limitation_of_liability": liability,
        "governing_law": gov_law,
        "ai_model_training": {
            "found": ai_clause["found"],
            "excerpt": ai_clause["excerpt"],
            "flags": ai_flags,
        },
        "data_retention_clause": data_retention_clause,
        "termination_rights": termination,
        "data_processing_agreement_ref": dpa_ref,
        "subprocessor_clause": subprocessor_clause,
        "subprocessor_regions_detected": subprocessor_regions,
        "non_standard_clauses": non_standard_clauses,
        "all_legal_flags": non_standard_clauses + ai_flags,
    }


# ---------------------------------------------------------------------------
# NEW: Cross-document consistency validator
# ---------------------------------------------------------------------------

def validate_cross_document_consistency(
    intake_acv: float,
    intake_renewal_status: str,
    intake_subprocessors: list,
    quote_annual_total: float,
    vendor_found_in_register: bool,
    vendor_register_status: str = "",
    questionnaire_subprocessors: list = None,
) -> dict:
    """
    Compare structured fields across intake, quote, vendor register, and questionnaire.
    Returns a list of inconsistencies for the agent to surface.
    """
    issues = []

    # ACV vs quote annual total
    if abs(intake_acv - quote_annual_total) > 1:
        issues.append({
            "type": "acv_mismatch",
            "severity": "warning",
            "description": (
                f"Intake ACV (${intake_acv:,.0f}) does not match quote annual total "
                f"(${quote_annual_total:,.0f}). Confirm correct figure before routing."
            ),
        })

    # New vendor flag vs vendor register
    if intake_renewal_status == "new_vendor" and vendor_found_in_register:
        issues.append({
            "type": "new_vendor_conflict",
            "severity": "blocking",
            "description": (
                f"Intake is marked 'new_vendor' but a matching record already exists in the vendor "
                f"register (status: {vendor_register_status or 'unknown'}). "
                "Confirm whether this is a duplicate request or a new legal entity before proceeding."
            ),
        })

    if intake_renewal_status == "renewal" and not vendor_found_in_register:
        issues.append({
            "type": "renewal_not_in_register",
            "severity": "warning",
            "description": (
                "Intake is marked 'renewal' but no matching vendor was found in the register. "
                "Confirm vendor ID before proceeding."
            ),
        })

    # Subprocessor consistency (intake vs questionnaire)
    if questionnaire_subprocessors and intake_subprocessors:
        def normalize(lst):
            return {s.lower().strip().split(" (")[0] for s in lst if s}

        intake_set = normalize(intake_subprocessors)
        q_set = normalize(questionnaire_subprocessors)

        only_in_q = q_set - intake_set
        only_in_intake = intake_set - q_set

        if only_in_q:
            issues.append({
                "type": "subprocessor_undeclared_in_intake",
                "severity": "warning",
                "description": (
                    f"Subprocessor(s) in security questionnaire not declared in intake: "
                    f"{', '.join(sorted(only_in_q))}. Intake should be updated."
                ),
            })
        if only_in_intake:
            issues.append({
                "type": "subprocessor_undeclared_in_questionnaire",
                "severity": "info",
                "description": (
                    f"Subprocessor(s) in intake not listed in security questionnaire: "
                    f"{', '.join(sorted(only_in_intake))}. Confirm completeness of questionnaire."
                ),
            })

    return {
        "issues_found": len(issues),
        "is_consistent": len(issues) == 0,
        "issues": issues,
    }


# ---------------------------------------------------------------------------
# NEW: Pre-screen (deterministic short-circuit before LLM)
# ---------------------------------------------------------------------------

def pre_screen_case(intake: dict, doc_checklist: dict) -> dict:
    """
    Short-circuit logic: check Block conditions first, then Escalate.
    Called before the LLM to provide deterministic context.
    """
    block_reasons: list[str] = []
    escalate_reasons: list[str] = []

    vendor_category = (intake.get("vendor_category") or "").lower()
    acv = float(intake.get("annual_contract_value") or 0)
    data_access = intake.get("data_access") or []
    payment_terms = (intake.get("payment_terms") or "")
    contract_term = int(intake.get("contract_term_months") or 0)
    ai_func = (intake.get("ai_functionality") or "").lower()
    is_saas = "saas" in vendor_category or "software" in vendor_category

    # ── BLOCK conditions (checked first; any hit = immediate block) ────────
    if is_saas and acv > 25_000:
        if not doc_checklist.get("soc2_type2", {}).get("provided"):
            block_reasons.append(
                "SOC 2 Type II not provided — required for SaaS vendors with ACV > $25,000"
            )

    if data_access:
        if not doc_checklist.get("data_processing_agreement", {}).get("provided"):
            block_reasons.append(
                "Data Processing Agreement not provided despite declared data access"
            )

    if is_saas and not doc_checklist.get("security_questionnaire", {}).get("provided"):
        block_reasons.append("Security questionnaire missing for SaaS vendor")

    # ── ESCALATE conditions (only checked if no Block) ─────────────────────
    if acv > 50_000:
        escalate_reasons.append(
            f"ACV ${acv:,.0f} exceeds $50,000 — requires Procurement Manager + VP Finance"
        )

    m = re.search(r"net\s*(\d+)", payment_terms.lower())
    net_days = int(m.group(1)) if m else 30
    if net_days >= 60:
        escalate_reasons.append(
            f"Payment terms {payment_terms} require VP Finance review (≥ Net 60)"
        )

    pii_kw = {"personal", "employee name", "employee email", "salary", "performance",
               "engagement", "attrition", "customer name", "customer email"}
    for item in data_access:
        if any(k in item.lower() for k in pii_kw):
            escalate_reasons.append(f"PII data processing declared: '{item}'")
            break

    if any(t in ai_func for t in ("train", "model", "improve", "enhancement", "benchmarking")):
        escalate_reasons.append(
            "AI functionality with potential data-training use — requires Legal + Executive review"
        )

    if contract_term > 12:
        escalate_reasons.append(
            f"Contract term {contract_term} months requires Legal review"
        )

    screen_result = "block" if block_reasons else ("escalate" if escalate_reasons else "proceed")
    return {
        "screen_result": screen_result,
        "block_reasons": block_reasons,
        "escalate_reasons": escalate_reasons,
    }


# ---------------------------------------------------------------------------
# Policy checklist runner (deterministic, 27 items)
# ---------------------------------------------------------------------------

def run_policy_checklist(
    acv: float,
    tcv: float,
    payment_terms: str,
    contract_term_months: int,
    data_sensitivity: str,
    vendor_found_in_register: bool,
    renewal_status: str,
    soc2_type2_provided: bool,
    dpa_provided: bool,
    security_questionnaire_provided: bool,
    vendor_category: str,
    # budget: pass either budget_remaining (preferred) or budget_sufficient (boolean fallback)
    budget_remaining: float = None,
    budget_sufficient: bool = None,
    has_eu_subprocessors: bool = False,
    has_apac_subprocessors: bool = False,
    has_ai_training: bool = False,
    ai_training_opt_out_confirmed: bool = False,
    acv_matches_quote: bool = True,
    subprocessors_consistent: bool = True,
    liability_cap_months: int = None,
    auto_renewal_found: bool = False,
    governing_law_outside_us: bool = False,
    dpa_ref_in_contract: bool = False,
    system_integrations: list = None,
    required_intake_fields_complete: bool = True,
    all_required_docs_provided: bool = False,
) -> dict:
    is_saas = "saas" in vendor_category.lower() or "software" in vendor_category.lower()
    net_match = re.search(r"net\s*(\d+)", payment_terms.lower())
    net_days = int(net_match.group(1)) if net_match else 30
    # Resolve budget check: prefer exact remaining amount, fall back to boolean flag
    if budget_remaining is not None:
        budget_exceeded = budget_remaining < acv
        budget_display = f"Remaining ${budget_remaining:,.0f} vs ACV ${acv:,.0f}"
        budget_reason = f"Budget remaining (${budget_remaining:,.0f}) < ACV (${acv:,.0f})"
    elif budget_sufficient is not None:
        budget_exceeded = not budget_sufficient
        budget_display = f"Sufficient: {budget_sufficient}"
        budget_reason = "Budget marked insufficient by finance system"
    else:
        budget_exceeded = False
        budget_display = "Unknown"
        budget_reason = ""
    sensitive = data_sensitivity in ("confidential", "restricted")
    integrations = system_integrations or []
    HIGH_RISK_INT = {"crm", "hris", "hr", "finance", "production", "erp", "payroll"}
    has_high_risk_int = any(any(r in i.lower() for r in HIGH_RISK_INT) for i in integrations)

    def item(check_id, domain, description, policy_ref, extracted_value, triggered,
             severity=None, reason="", action=""):
        return {
            "check_id": check_id,
            "domain": domain,
            "description": description,
            "policy_ref": policy_ref,
            "extracted_value": str(extracted_value),
            "result": "triggered" if triggered else "clear",
            "flag_severity": (severity if triggered and severity else ""),
            "flag_reason": (reason if triggered else ""),
            "action_required": (action if triggered else ""),
        }

    checks = [
        # Finance
        item("FIN-001", "Finance", "ACV vs $25K threshold", "finance_approval_matrix.md",
             f"${acv:,.0f}", acv > 25_000, "warning",
             "ACV exceeds $25K — Procurement Manager required",
             "Add Procurement Manager to approval chain"),
        item("FIN-002", "Finance", "ACV vs $50K threshold", "finance_approval_matrix.md",
             f"${acv:,.0f}", acv > 50_000, "warning",
             "ACV exceeds $50K — VP Finance required",
             "Add VP Finance to approval chain"),
        item("FIN-003", "Finance", "ACV vs $100K threshold", "finance_approval_matrix.md",
             f"${acv:,.0f}", acv > 100_000, "warning",
             "ACV exceeds $100K — CFO required",
             "Add CFO to approval chain"),
        item("FIN-004", "Finance", "ACV vs $250K threshold", "finance_approval_matrix.md",
             f"${acv:,.0f}", acv > 250_000, "warning",
             "ACV exceeds $250K — Executive Sponsor required",
             "Add Executive Sponsor to approval chain"),
        item("FIN-005", "Legal", "TCV vs $100K threshold", "finance_approval_matrix.md",
             f"${tcv:,.0f}", tcv > 100_000, "warning",
             "TCV exceeds $100K — Legal review required",
             "Route to Legal for contract review"),
        item("FIN-006", "Finance", "TCV vs $250K threshold", "finance_approval_matrix.md",
             f"${tcv:,.0f}", tcv > 250_000, "warning",
             "TCV exceeds $250K — Executive Sponsor required",
             "Add Executive Sponsor to approval chain"),
        item("FIN-007", "Finance", "Payment terms (Net 30/45/60/90+)", "finance_approval_matrix.md",
             payment_terms, net_days >= 60,
             "blocking" if net_days > 60 else "warning",
             f"Payment terms {payment_terms} require VP Finance"
             + (" + Legal" if net_days > 60 else "") + " review",
             "Add VP Finance" + (" and Legal" if net_days > 60 else "") + " to approval chain"),
        item("FIN-008", "Finance", "Contract term vs 24-month threshold", "finance_approval_matrix.md",
             f"{contract_term_months} months", contract_term_months > 24, "warning",
             f"Contract term {contract_term_months}m exceeds 24-month threshold",
             "Route to Finance for multi-year contract review"),
        item("FIN-009", "Finance", "Budget remaining vs ACV", "finance_approval_matrix.md",
             budget_display,
             budget_exceeded, "blocking",
             budget_reason,
             "Escalate to Finance/FP&A for budget reallocation before proceeding"),

        # Legal
        item("LEG-001", "Legal", "ACV > $50K → Legal review", "legal_review_policy.md",
             f"${acv:,.0f}", acv > 50_000, "warning",
             "ACV exceeds $50K — Legal review required",
             "Route to Legal"),
        item("LEG-002", "Legal", "Contract term > 12 months → Legal review", "legal_review_policy.md",
             f"{contract_term_months} months", contract_term_months > 12, "warning",
             f"Contract term {contract_term_months}m exceeds 12-month threshold",
             "Route to Legal for review"),
        item("LEG-003", "Legal", "Personal data processing → DPA required", "data_handling_policy.md",
             f"Sensitivity: {data_sensitivity}, DPA provided: {dpa_provided}",
             sensitive and not dpa_provided, "blocking",
             "Personal/confidential data processing declared but DPA not provided",
             "Request DPA from vendor before proceeding"),
        item("LEG-004", "Legal", "AI/ML on company data → Legal + Executive approval",
             "legal_review_policy.md",
             "Yes" if has_ai_training else "No",
             has_ai_training, "blocking",
             "Vendor uses company data for AI/ML — Legal and Executive approval required",
             "Escalate to Legal and Executive Sponsor; confirm opt-out or prohibit training use"),
        item("LEG-005", "Legal", "EU subprocessors present", "legal_review_policy.md",
             "Yes" if has_eu_subprocessors else "No",
             has_eu_subprocessors, "warning",
             "EU subprocessors detected — Legal GDPR/SCCs review required",
             "Route to Legal for EU data transfer review"),
        item("LEG-006", "Legal", "APAC subprocessors present", "legal_review_policy.md",
             "Yes" if has_apac_subprocessors else "No",
             has_apac_subprocessors, "warning",
             "APAC subprocessors detected — Legal cross-border transfer review required",
             "Route to Legal for APAC data transfer review"),
        item("LEG-007", "Legal", "Liability cap < 12 months", "legal_review_policy.md",
             f"{liability_cap_months} months" if liability_cap_months is not None else "Not detected",
             liability_cap_months is not None and liability_cap_months < 12, "warning",
             f"Liability cap is {liability_cap_months} months — below standard 12-month minimum",
             "Request Legal review and negotiate higher liability cap"),
        item("LEG-008", "Legal", "Auto-renewal clause found", "legal_review_policy.md",
             "Found" if auto_renewal_found else "Not found",
             auto_renewal_found, "info",
             "Auto-renewal clause detected — ensure renewal notice period is tracked",
             "Log renewal date; set calendar reminder 60 days before renewal window"),
        item("LEG-009", "Legal", "Governing law outside US", "legal_review_policy.md",
             "Yes" if governing_law_outside_us else "No",
             governing_law_outside_us, "warning",
             "Governing law is outside the United States — Legal review required",
             "Route to Legal to assess jurisdiction risk"),
        item("LEG-010", "Legal", "DPA reference found in contract", "data_handling_policy.md",
             "Found" if dpa_ref_in_contract else "Not found",
             sensitive and not dpa_ref_in_contract, "warning",
             "Personal data processing declared but DPA not referenced in contract text",
             "Ensure DPA is incorporated by reference or attached as exhibit"),
        item("LEG-011", "Legal", "Payment terms > Net 60 → Legal review", "finance_approval_matrix.md",
             payment_terms, net_days > 60, "warning",
             f"Payment terms {payment_terms} exceed Net 60 — Legal review required in addition to VP Finance",
             "Route to Legal alongside VP Finance for extended payment terms review"),
        item("LEG-012", "Legal", "Personal/confidential data — Legal data protection review",
             "legal_review_policy.md",
             f"Sensitivity: {data_sensitivity}",
             sensitive, "warning",
             "Vendor processes personal or confidential data — Legal must confirm data protection terms",
             "Legal to verify: breach notification language, data retention/deletion obligations, subprocessor disclosure"),

        # Security
        item("SEC-001", "Security", "SOC 2 Type II provided", "security_review_policy.md",
             "Provided" if soc2_type2_provided else "Missing",
             is_saas and not soc2_type2_provided, "blocking",
             "SOC 2 Type II required for SaaS vendor but not provided",
             "Request SOC 2 Type II report from vendor before proceeding"),
        item("SEC-002", "Security", "Data sensitivity level", "security_review_policy.md",
             data_sensitivity, sensitive,
             "blocking" if data_sensitivity == "restricted" else "warning",
             f"Data sensitivity is {data_sensitivity} — Security review required",
             "Route to Security for data access review"),
        item("SEC-003", "Security", "High-risk system integrations (CRM/HRIS/Finance/Production)",
             "security_review_policy.md",
             ", ".join(integrations) if integrations else "None",
             has_high_risk_int, "warning",
             "Integration with high-risk system detected",
             "Security must review integration scope and data flows"),
        item("SEC-004", "Security", "AI training opt-out confirmed", "data_handling_policy.md",
             "Confirmed" if ai_training_opt_out_confirmed else "Not confirmed",
             has_ai_training and not ai_training_opt_out_confirmed,
             "blocking" if data_sensitivity == "restricted" else "warning",
             "AI training language present but opt-out not confirmed",
             "Confirm opt-out clause with vendor or prohibit training use"),
        item("SEC-005", "Security", "Security questionnaire completeness", "security_review_policy.md",
             "Provided" if security_questionnaire_provided else "Missing",
             not security_questionnaire_provided, "blocking",
             "Security questionnaire not provided",
             "Request completed security questionnaire from vendor"),
        item("SEC-006", "Security", "EU subprocessors reviewed by Security", "security_review_policy.md",
             "Yes" if has_eu_subprocessors else "N/A",
             has_eu_subprocessors, "warning",
             "EU subprocessors present — Security must review data transfer controls",
             "Security team to review EU subprocessor list and transfer mechanisms"),
        item("SEC-007", "Security", "APAC subprocessors reviewed by Security", "security_review_policy.md",
             "Yes" if has_apac_subprocessors else "N/A",
             has_apac_subprocessors, "warning",
             "APAC subprocessors present — Security must review data transfer controls",
             "Security team to review APAC subprocessor list and transfer mechanisms"),

        # Procurement
        item("PRO-001", "Procurement", "All required intake fields present", "procurement_policy.md",
             "Complete" if required_intake_fields_complete else "Incomplete",
             not required_intake_fields_complete, "warning",
             "Required intake fields are missing — cannot complete triage",
             "Request business owner to complete all intake form fields"),
        item("PRO-002", "Procurement", "New vendor vs vendor register (duplicate check)",
             "vendor_risk_policy.md",
             f"Status: {renewal_status}, In register: {vendor_found_in_register}",
             (renewal_status == "new_vendor" and vendor_found_in_register) or
             (renewal_status == "renewal" and not vendor_found_in_register),
             "blocking" if renewal_status == "new_vendor" and vendor_found_in_register else "warning",
             ("Intake marked 'new_vendor' but vendor already exists in register — possible duplicate"
              if renewal_status == "new_vendor" and vendor_found_in_register
              else "Intake marked 'renewal' but no matching vendor found in register"),
             "Confirm vendor status with business owner before proceeding"),
        item("PRO-003", "Procurement", "ACV consistency (intake vs quote)", "procurement_policy.md",
             "Consistent" if acv_matches_quote else "Mismatch",
             not acv_matches_quote, "warning",
             "ACV in intake does not match quote annual total",
             "Reconcile ACV discrepancy with business owner before routing"),
        item("PRO-004", "Procurement", "Subprocessor consistency (intake vs questionnaire)",
             "procurement_policy.md",
             "Consistent" if subprocessors_consistent else "Mismatch",
             not subprocessors_consistent, "warning",
             "Subprocessor lists differ between intake and security questionnaire",
             "Business owner to confirm complete and accurate subprocessor list"),
        item("PRO-005", "Procurement", "Document checklist completeness", "procurement_policy.md",
             "Complete" if all_required_docs_provided else "Incomplete",
             not all_required_docs_provided, "warning",
             "Not all required documents have been provided",
             "Request missing documents from vendor or business owner"),

        # Data Handling
        item("DAT-001", "Data Handling", "AI training language detected", "data_handling_policy.md",
             "Detected" if has_ai_training else "Not detected",
             has_ai_training, "warning",
             "AI/model-training language found in contract or questionnaire",
             "Legal and Security to review data-use scope; confirm opt-out"),
        item("DAT-002", "Data Handling", "Data used for model training without opt-out",
             "data_handling_policy.md",
             f"AI training: {has_ai_training}, Opt-out confirmed: {ai_training_opt_out_confirmed}",
             has_ai_training and not ai_training_opt_out_confirmed,
             "blocking" if data_sensitivity == "restricted" else "warning",
             "Vendor may use company data for model training and opt-out is not confirmed",
             "Block until vendor confirms opt-out or amends contract to exclude training use"),
        item("DAT-003", "Data Handling", "Subprocessors outside US handling restricted data",
             "data_handling_policy.md",
             f"EU: {has_eu_subprocessors}, APAC: {has_apac_subprocessors}, Sensitivity: {data_sensitivity}",
             (has_eu_subprocessors or has_apac_subprocessors) and data_sensitivity == "restricted",
             "blocking",
             "Subprocessors outside the US are handling restricted data",
             "Legal and Security must review cross-border data transfer controls before proceeding"),
    ]

    triggered = sum(1 for c in checks if c["result"] == "triggered")
    blocking = sum(1 for c in checks if c["flag_severity"] == "blocking")
    warnings = sum(1 for c in checks if c["flag_severity"] == "warning")

    return {
        "total_checks": len(checks),
        "triggered": triggered,
        "blocking": blocking,
        "warnings": warnings,
        "checklist": checks,
    }


# ---------------------------------------------------------------------------
# Tool dispatcher (for tools that take LLM-supplied inputs)
# ---------------------------------------------------------------------------

TOOL_REGISTRY = {
    "lookup_budget": lookup_budget,
    "check_existing_vendor": check_existing_vendor,
    "calculate_total_contract_value": calculate_total_contract_value,
    "classify_data_sensitivity": classify_data_sensitivity,
    "determine_required_approvals": determine_required_approvals,
    "validate_cross_document_consistency": validate_cross_document_consistency,
    "run_policy_checklist": run_policy_checklist,
    "pre_screen_case": pre_screen_case,
}


def execute_tool(tool_name: str, tool_input: dict) -> str:
    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    result = fn(**tool_input)
    return json.dumps(result)
