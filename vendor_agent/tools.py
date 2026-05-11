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
# Tool dispatcher (for tools that take LLM-supplied inputs)
# ---------------------------------------------------------------------------

TOOL_REGISTRY = {
    "lookup_budget": lookup_budget,
    "check_existing_vendor": check_existing_vendor,
    "calculate_total_contract_value": calculate_total_contract_value,
    "classify_data_sensitivity": classify_data_sensitivity,
    "determine_required_approvals": determine_required_approvals,
    "validate_cross_document_consistency": validate_cross_document_consistency,
}


def execute_tool(tool_name: str, tool_input: dict) -> str:
    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    result = fn(**tool_input)
    return json.dumps(result)
