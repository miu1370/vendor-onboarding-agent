import os
import json
import html as _html
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import streamlit as st
from parsers import load_case, load_policies
from agent import run_vendor_agent

RESULTS_FILE = Path(__file__).parent / "analysis_results.json"
DOCS_PATH = Path(__file__).parent.parent / "docs"
_UPLOAD_DIR = Path(__file__).parent / "uploads"
_NEW_VENDORS_FILE = Path(__file__).parent / "new_vendors.json"
_UPLOAD_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_PATH = str(Path(__file__).parent.parent)
AUDIT_LOG = Path(__file__).parent / "audit_log.json"

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")

_KEY_SOURCE = "none"
_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
if _API_KEY:
    _KEY_SOURCE = "env"
else:
    try:
        _API_KEY = st.secrets.get("ANTHROPIC_API_KEY", "").strip()
        if _API_KEY:
            _KEY_SOURCE = "secrets"
    except Exception:
        pass

_API_KEY_VALID = bool(_API_KEY) and _API_KEY.startswith("sk-ant-")

st.set_page_config(
    page_title="Vendor Onboarding Agent",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Static metadata
# ---------------------------------------------------------------------------
CASE_META = {
    "case_001": {
        "label": "Case 001 · Northstar Analytics",
        "vendor": "Northstar Analytics",
        "category": "SaaS / AI Analytics",
        "acv": 85_000,
    },
    "case_002": {
        "label": "Case 002 · Workspace Depot",
        "vendor": "Workspace Depot",
        "category": "Office Supplies",
        "acv": 12_000,
    },
    "case_003": {
        "label": "Case 003 · TalentPulse AI",
        "vendor": "TalentPulse AI",
        "category": "HR / AI",
        "acv": 120_000,
    },
}

CASE_ORDER = list(CASE_META.keys())

RISK_COLOR = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
REC_LABELS = {
    "ready_for_approval": "✅ Ready for Approval",
    "pending_information": "⏳ Pending Information",
    "escalate_to_human": "🔺 Escalate to Human",
    "blocked": "🚫 Blocked",
}

CATEGORIES = ["Finance", "Legal", "Security", "Procurement", "Data Handling", "Vendor Risk"]

CATEGORY_TOOL_MAP = {
    "Finance": ["lookup_budget", "calculate_total_contract_value", "determine_required_approvals"],
    "Legal": ["extract_contract_clauses"],
    "Security": ["classify_data_sensitivity"],
    "Procurement": ["check_existing_vendor", "validate_cross_document_consistency"],
    "Data Handling": ["classify_data_sensitivity"],
    "Vendor Risk": [],
}

CATEGORY_POLICY_MAP = {
    "Finance": ["Finance", "finance_approval_matrix"],
    "Legal": ["Legal", "legal_review_policy"],
    "Security": ["Security", "security_review_policy"],
    "Procurement": ["Procurement", "procurement_policy", "vendor_risk_policy"],
    "Data Handling": ["Data Handling", "data_handling_policy"],
    "Vendor Risk": ["vendor_risk_policy", "Legal", "Security", "Data Handling"],
}

DOMAIN_CHECKLIST_IDS = {
    "Finance":      ["FIN-001", "FIN-002", "FIN-003", "FIN-004",
                     "FIN-006", "FIN-007", "FIN-008", "FIN-009"],
    "Legal":        ["FIN-005", "LEG-001", "LEG-002", "LEG-003", "LEG-004",
                     "LEG-005", "LEG-006", "LEG-007", "LEG-008", "LEG-009", "LEG-010",
                     "LEG-011", "LEG-012"],
    "Security":     ["SEC-001", "SEC-002", "SEC-003", "SEC-004", "SEC-005", "SEC-006", "SEC-007"],
    "Procurement":  ["PRO-001", "PRO-002", "PRO-003", "PRO-004", "PRO-005"],
    "Data Handling": ["DAT-001", "DAT-002", "DAT-003"],
    "Vendor Risk":  ["PRO-002", "LEG-004", "LEG-005", "LEG-006", "LEG-009", "SEC-001", "DAT-003"],
}

DOMAIN_FACTS_FIELDS = {
    "Finance": [
        ("ACV", "acv"),
        ("TCV", "tcv"),
        ("Contract Term", "contract_term_months"),
        ("Payment Terms", "payment_terms"),
        ("Net Payment Days", "net_payment_days"),
        ("Budget Remaining", "budget_remaining"),
        ("Budget Sufficient", "budget_sufficient"),
        ("Cost Center", "cost_center"),
    ],
    "Legal": [
        ("Auto-Renewal Clause", "auto_renewal_clause"),
        ("Governing Law", "governing_law"),
        ("Governing Law Outside US", "governing_law_outside_us"),
        ("Liability Cap", "liability_cap_months"),
        ("DPA Provided", "dpa_provided"),
        ("DPA Referenced in Contract", "dpa_referenced_in_contract"),
        ("EU Subprocessors", "has_eu_subprocessors"),
        ("APAC Subprocessors", "has_apac_subprocessors"),
        ("AI Training Language", "has_ai_training_language"),
    ],
    "Security": [
        ("Data Sensitivity", "data_sensitivity"),
        ("Data Types", "data_types"),
        ("System Integrations", "system_integrations"),
        ("SOC 2 Type II Provided", "soc2_type2_provided"),
        ("Security Questionnaire Provided", "security_questionnaire_provided"),
        ("AI Training Opt-Out Confirmed", "ai_training_opt_out_confirmed"),
    ],
    "Procurement": [
        ("Vendor", "vendor_name"),
        ("Vendor Category", "vendor_category"),
        ("Renewal Status", "renewal_status"),
        ("Vendor in Register", "vendor_in_register"),
        ("ACV Matches Quote", "acv_matches_quote"),
        ("Subprocessors Consistent", "subprocessors_consistent"),
        ("All Docs Provided", "all_docs_provided"),
        ("Missing Documents", "missing_documents"),
    ],
    "Data Handling": [
        ("Data Sensitivity", "data_sensitivity"),
        ("Data Types", "data_types"),
        ("Subprocessors", "subprocessors"),
        ("EU Subprocessors", "has_eu_subprocessors"),
        ("APAC Subprocessors", "has_apac_subprocessors"),
        ("AI Functionality", "ai_functionality"),
        ("AI Training Language Found", "has_ai_training_language"),
        ("AI Training Opt-Out Confirmed", "ai_training_opt_out_confirmed"),
    ],
    "Vendor Risk": [
        ("Vendor", "vendor_name"),
        ("Vendor Category", "vendor_category"),
        ("Data Sensitivity", "data_sensitivity"),
        ("Vendor in Register", "vendor_in_register"),
        ("EU Subprocessors", "has_eu_subprocessors"),
        ("APAC Subprocessors", "has_apac_subprocessors"),
        ("AI Training Language Found", "has_ai_training_language"),
        ("Governing Law Outside US", "governing_law_outside_us"),
        ("SOC 2 Type II Provided", "soc2_type2_provided"),
    ],
}

# ---------------------------------------------------------------------------
# Policy rule definitions — used in detail page checklist and Policy & Rules module
# ---------------------------------------------------------------------------
POLICY_RULES = {
    # ── Finance ──────────────────────────────────────────────────────────────
    "FIN-001": {
        "rule": "ACV — Procurement Manager Threshold",
        "detail": (
            "- `acv ≤ $25K` → Business Owner only\n"
            "- `acv > $25K` → + Procurement Manager  ← **this rule**\n"
            "- `acv > $50K` → + VP Finance\n"
            "- `acv > $100K` → + CFO\n"
            "- `acv > $250K` → + Executive Sponsor"
        ),
        "trigger": "acv > $25,000",
        "action": "Add Procurement Manager to approval chain",
        "severity": "Warning",
        "policy_ref": "Finance Approval Matrix",
    },
    "FIN-002": {
        "rule": "ACV — VP Finance Threshold",
        "detail": (
            "- `acv ≤ $50K` → VP Finance not required on ACV alone\n"
            "- `acv > $50K` → + VP Finance  ← **this rule**"
        ),
        "trigger": "acv > $50,000",
        "action": "Add VP Finance to approval chain",
        "severity": "Warning",
        "policy_ref": "Finance Approval Matrix",
    },
    "FIN-003": {
        "rule": "ACV — CFO Threshold",
        "detail": (
            "- `acv ≤ $100K` → CFO not required on ACV alone\n"
            "- `acv > $100K` → + CFO  ← **this rule**"
        ),
        "trigger": "acv > $100,000",
        "action": "Add CFO to approval chain",
        "severity": "Warning",
        "policy_ref": "Finance Approval Matrix",
    },
    "FIN-004": {
        "rule": "ACV — Executive Sponsor Threshold",
        "detail": (
            "- `acv ≤ $250K` → Executive Sponsor not required on ACV alone\n"
            "- `acv > $250K` → + Executive Sponsor  ← **this rule**"
        ),
        "trigger": "acv > $250,000",
        "action": "Add Executive Sponsor to approval chain",
        "severity": "Warning",
        "policy_ref": "Finance Approval Matrix",
    },
    "FIN-006": {
        "rule": "TCV — Executive Sponsor Threshold",
        "detail": (
            "- `tcv ≤ $250K` → Executive Sponsor not required on TCV alone\n"
            "- `tcv > $250K` → + Executive Sponsor  ← **this rule**\n\n"
            "tcv = acv × (term_months / 12) + one_time_fees"
        ),
        "trigger": "tcv > $250,000",
        "action": "Add Executive Sponsor to approval chain",
        "severity": "Warning",
        "policy_ref": "Finance Approval Matrix",
    },
    "FIN-007": {
        "rule": "Payment Terms — Finance Review Threshold",
        "detail": (
            "- `Net 30` → passes (standard)\n"
            "- `Net 45` → Procurement Manager review\n"
            "- `Net 60` → VP Finance review  ← **this rule triggers**\n"
            "- `> Net 60` → VP Finance + Legal review (blocking) — see LEG-011"
        ),
        "trigger": "payment_terms ≥ Net 60",
        "action": "Add VP Finance to approval chain",
        "severity": "Warning / Blocking",
        "policy_ref": "Finance Approval Matrix",
    },
    "FIN-008": {
        "rule": "Contract Term — Multi-Year Finance Review",
        "detail": (
            "- `term ≤ 24 months` → passes\n"
            "- `term > 24 months` → Finance review required  ← **this rule**\n\n"
            "Multi-year commitments require Finance sign-off on spend trajectory."
        ),
        "trigger": "contract_term_months > 24",
        "action": "Route to Finance for multi-year contract review",
        "severity": "Warning",
        "policy_ref": "Finance Approval Matrix",
    },
    "FIN-009": {
        "rule": "Budget — Remaining vs ACV",
        "detail": (
            "- `budget_remaining ≥ acv` → passes\n"
            "- `budget_remaining < acv` → Finance/FP&A approval required  ← **this rule**\n"
            "- `budget_remaining = unknown` → escalate to Finance  ← **this rule**\n\n"
            "Applies regardless of ACV tier."
        ),
        "trigger": "budget_remaining < acv, or budget status unknown",
        "action": "Escalate to Finance/FP&A for budget reallocation before proceeding",
        "severity": "Blocking",
        "policy_ref": "Finance Approval Matrix",
    },
    # ── Legal ─────────────────────────────────────────────────────────────────
    "FIN-005": {
        "rule": "TCV — Legal Review Threshold",
        "detail": (
            "- `tcv ≤ $100K` → Legal review not required on TCV alone\n"
            "- `tcv > $100K` → Legal review required  ← **this rule**\n\n"
            "tcv = acv × (term_months / 12) + one_time_fees. Independent of ACV tier."
        ),
        "trigger": "tcv > $100,000",
        "action": "Route to Legal for contract review",
        "severity": "Warning",
        "policy_ref": "Finance Approval Matrix",
    },
    "LEG-001": {
        "rule": "ACV — Legal Review Threshold",
        "detail": (
            "- `acv ≤ $50K` → Legal review not required on ACV alone\n"
            "- `acv > $50K` → Legal review required  ← **this rule**"
        ),
        "trigger": "acv > $50,000",
        "action": "Route to Legal",
        "severity": "Warning",
        "policy_ref": "Legal Review Policy",
    },
    "LEG-002": {
        "rule": "Contract Term — Legal Review Threshold",
        "detail": (
            "- `term ≤ 12 months` → Legal review not required on term alone\n"
            "- `term > 12 months` → Legal review required  ← **this rule**"
        ),
        "trigger": "contract_term_months > 12",
        "action": "Route to Legal for review",
        "severity": "Warning",
        "policy_ref": "Legal Review Policy",
    },
    "LEG-003": {
        "rule": "Personal / Confidential Data — DPA Required",
        "detail": (
            "- `sensitivity ∈ {confidential, restricted}` AND `dpa_provided = true` → passes\n"
            "- `sensitivity ∈ {confidential, restricted}` AND `dpa_provided = false` → **BLOCK**  ← **this rule**\n"
            "- `sensitivity ∈ {public, internal}` → not evaluated"
        ),
        "trigger": "sensitivity ∈ {confidential, restricted} AND dpa_provided = false",
        "action": "Request DPA from vendor before proceeding",
        "severity": "Blocking",
        "policy_ref": "Data Handling Policy",
    },
    "LEG-004": {
        "rule": "AI / ML on Company Data — Legal + Executive Approval",
        "detail": (
            "- `has_ai_training = false` → passes\n"
            "- `has_ai_training = true` AND `opt_out_confirmed = true` → passes\n"
            "- `has_ai_training = true` AND `opt_out_confirmed = false` → **BLOCK**  ← **this rule**\n\n"
            "Ambiguous language ('service improvement', 'model enhancement', 'benchmarking') counts as detected."
        ),
        "trigger": "has_ai_training = true AND opt_out_confirmed = false",
        "action": "Escalate to Legal and Executive Sponsor; confirm opt-out or prohibit training use",
        "severity": "Blocking",
        "policy_ref": "Legal Review Policy",
    },
    "LEG-005": {
        "rule": "EU Subprocessors — GDPR Review",
        "detail": (
            "- `has_eu_subprocessors = false` → passes\n"
            "- `has_eu_subprocessors = true` → Legal GDPR/SCC review required  ← **this rule**\n\n"
            "Legal must verify Standard Contractual Clauses or equivalent transfer mechanism."
        ),
        "trigger": "has_eu_subprocessors = true",
        "action": "Route to Legal for EU data transfer review",
        "severity": "Warning",
        "policy_ref": "Legal Review Policy",
    },
    "LEG-006": {
        "rule": "APAC Subprocessors — Cross-Border Transfer Review",
        "detail": (
            "- `has_apac_subprocessors = false` → passes\n"
            "- `has_apac_subprocessors = true` → Legal cross-border review required  ← **this rule**"
        ),
        "trigger": "has_apac_subprocessors = true",
        "action": "Route to Legal for APAC data transfer review",
        "severity": "Warning",
        "policy_ref": "Legal Review Policy",
    },
    "LEG-007": {
        "rule": "Liability Cap — Below 12-Month Standard",
        "detail": (
            "- Liability cap clause not found → not evaluated\n"
            "- `liability_cap_months ≥ 12` → passes\n"
            "- `liability_cap_months < 12` → Legal negotiation required  ← **this rule**\n\n"
            "Standard minimum is 12 months of fees paid."
        ),
        "trigger": "liability_cap_months detected AND liability_cap_months < 12",
        "action": "Request Legal review and negotiate higher liability cap",
        "severity": "Warning",
        "policy_ref": "Legal Review Policy",
    },
    "LEG-008": {
        "rule": "Auto-Renewal Clause — Tracking Required",
        "detail": (
            "- `auto_renewal_found = false` → passes\n"
            "- `auto_renewal_found = true` → log renewal date  ← **this rule** (info only, does not block)\n\n"
            "Set calendar reminder ≥ 60 days before renewal window to avoid unintended lock-in."
        ),
        "trigger": "auto_renewal_found = true",
        "action": "Log renewal date; set calendar reminder 60 days before renewal window",
        "severity": "Info",
        "policy_ref": "Legal Review Policy",
    },
    "LEG-009": {
        "rule": "Governing Law — Outside the US",
        "detail": (
            "- `governing_law ∈ US jurisdictions` → passes\n"
            "- `governing_law ∉ US jurisdictions` → Legal review required  ← **this rule**\n\n"
            "Non-US governing law introduces enforceability and compliance jurisdiction risk."
        ),
        "trigger": "governing_law references jurisdiction outside the United States",
        "action": "Route to Legal to assess jurisdiction risk",
        "severity": "Warning",
        "policy_ref": "Legal Review Policy",
    },
    "LEG-010": {
        "rule": "DPA — Not Referenced in Contract Body",
        "detail": (
            "- `sensitivity ∈ {public, internal}` → not evaluated\n"
            "- `sensitivity ∈ {confidential, restricted}` AND `dpa_ref_in_contract = true` → passes\n"
            "- `sensitivity ∈ {confidential, restricted}` AND `dpa_ref_in_contract = false` → Warning  ← **this rule**\n\n"
            "Separate from LEG-003 (document provided). The DPA must also be incorporated by reference or attached as an exhibit in the contract body."
        ),
        "trigger": "sensitivity ∈ {confidential, restricted} AND dpa_ref_in_contract = false",
        "action": "Ensure DPA is incorporated by reference or attached as an exhibit",
        "severity": "Warning",
        "policy_ref": "Data Handling Policy",
    },
    "LEG-011": {
        "rule": "Payment Terms — Legal Review Threshold",
        "detail": (
            "- `payment_terms ≤ Net 60` → Legal not required on payment terms alone\n"
            "- `payment_terms > Net 60` → VP Finance + Legal review required  ← **this rule**\n\n"
            "Applies in addition to FIN-007 (Finance flag). Legal reviews extended payment risk and enforceability."
        ),
        "trigger": "payment_terms > Net 60",
        "action": "Route to Legal alongside VP Finance for extended payment terms review",
        "severity": "Warning",
        "policy_ref": "Finance Approval Matrix",
    },
    "LEG-012": {
        "rule": "Personal / Confidential Data — Legal Data Protection Review",
        "detail": (
            "- `sensitivity ∈ {public, internal}` → not evaluated\n"
            "- `sensitivity ∈ {confidential, restricted}` → Legal must confirm all of:  ← **this rule**\n"
            "  1. DPA in place and signed\n"
            "  2. Subprocessor list disclosed\n"
            "  3. Breach notification language acceptable\n"
            "  4. Data retention and deletion obligations documented\n\n"
            "Complements LEG-003 (DPA document check) and LEG-010 (DPA contract reference)."
        ),
        "trigger": "sensitivity ∈ {confidential, restricted}",
        "action": "Legal to verify breach notification, data retention/deletion, and subprocessor disclosure",
        "severity": "Warning",
        "policy_ref": "Legal Review Policy",
    },
    # ── Security ──────────────────────────────────────────────────────────────
    "SEC-001": {
        "rule": "SOC 2 Type II — Required for SaaS Vendors",
        "detail": (
            "- `vendor_category ∉ SaaS/software` → not evaluated\n"
            "- `vendor_category ∈ SaaS/software` AND `soc2_provided = true` → passes\n"
            "- `vendor_category ∈ SaaS/software` AND `soc2_provided = false` → **BLOCK**  ← **this rule**"
        ),
        "trigger": "vendor_category = SaaS/software AND soc2_type2_provided = false",
        "action": "Request SOC 2 Type II report from vendor before proceeding",
        "severity": "Blocking",
        "policy_ref": "Security Review Policy",
    },
    "SEC-002": {
        "rule": "Data Sensitivity — Security Review Required",
        "detail": (
            "- `sensitivity = public` → not evaluated\n"
            "- `sensitivity = internal` → not evaluated\n"
            "- `sensitivity = confidential` → Security review (warning)  ← **this rule**\n"
            "- `sensitivity = restricted` → Security review (blocking)  ← **this rule**"
        ),
        "trigger": "sensitivity ∈ {confidential, restricted}",
        "action": "Route to Security for data access review",
        "severity": "Warning / Blocking",
        "policy_ref": "Security Review Policy",
    },
    "SEC-003": {
        "rule": "High-Risk System Integrations",
        "detail": (
            "- No high-risk integrations → passes\n"
            "- Integration with `CRM | HRIS | Finance | Production | ERP | Payroll` detected → Security review  ← **this rule**"
        ),
        "trigger": "integrations ∩ {CRM, HRIS, Finance, Production, ERP, Payroll} ≠ ∅",
        "action": "Security must review integration scope and data flows",
        "severity": "Warning",
        "policy_ref": "Security Review Policy",
    },
    "SEC-004": {
        "rule": "AI Training Opt-Out — Explicit Confirmation Required",
        "detail": (
            "- `has_ai_training = false` → passes\n"
            "- `has_ai_training = true` AND `opt_out_confirmed = true` → passes\n"
            "- `has_ai_training = true` AND `opt_out_confirmed = false` AND `sensitivity = restricted` → **BLOCK**  ← **this rule**\n"
            "- `has_ai_training = true` AND `opt_out_confirmed = false` AND `sensitivity ≠ restricted` → Warning  ← **this rule**"
        ),
        "trigger": "has_ai_training = true AND opt_out_confirmed = false",
        "action": "Confirm opt-out clause with vendor or prohibit training use via contract amendment",
        "severity": "Warning / Blocking",
        "policy_ref": "Data Handling Policy",
    },
    "SEC-005": {
        "rule": "Security Questionnaire — Required Document",
        "detail": (
            "- `security_questionnaire_provided = true` → passes\n"
            "- `security_questionnaire_provided = false` → **BLOCK**  ← **this rule**\n\n"
            "Required for all vendors regardless of risk tier."
        ),
        "trigger": "security_questionnaire_provided = false",
        "action": "Request completed security questionnaire from vendor",
        "severity": "Blocking",
        "policy_ref": "Security Review Policy",
    },
    "SEC-006": {
        "rule": "EU Subprocessors — Security Transfer Controls",
        "detail": (
            "- `has_eu_subprocessors = false` → passes\n"
            "- `has_eu_subprocessors = true` → Security reviews transfer controls  ← **this rule**\n\n"
            "Complements LEG-005 (Legal GDPR review). Security verifies encryption and DPA coverage."
        ),
        "trigger": "has_eu_subprocessors = true",
        "action": "Security team to review EU subprocessor list and transfer mechanisms",
        "severity": "Warning",
        "policy_ref": "Security Review Policy",
    },
    "SEC-007": {
        "rule": "APAC Subprocessors — Security Transfer Controls",
        "detail": (
            "- `has_apac_subprocessors = false` → passes\n"
            "- `has_apac_subprocessors = true` → Security reviews transfer controls  ← **this rule**\n\n"
            "Complements LEG-006 (Legal cross-border review)."
        ),
        "trigger": "has_apac_subprocessors = true",
        "action": "Security team to review APAC subprocessor list and transfer mechanisms",
        "severity": "Warning",
        "policy_ref": "Security Review Policy",
    },
    # ── Procurement ───────────────────────────────────────────────────────────
    "PRO-001": {
        "rule": "Intake Form — Required Fields Complete",
        "detail": (
            "- All fields present → passes\n"
            "- Any required field missing → Warning  ← **this rule**\n\n"
            "Required: vendor name, requesting team, business owner, cost center, business justification, "
            "vendor category, ACV, contract term, start date, new/renewal status."
        ),
        "trigger": "required_intake_fields_complete = false",
        "action": "Request business owner to complete all intake form fields",
        "severity": "Warning",
        "policy_ref": "Procurement Policy",
    },
    "PRO-002": {
        "rule": "Vendor Register — Duplicate / Consistency Check",
        "detail": (
            "- `renewal_status = new_vendor` AND `vendor_in_register = false` → passes\n"
            "- `renewal_status = renewal` AND `vendor_in_register = true` → passes\n"
            "- `renewal_status = new_vendor` AND `vendor_in_register = true` → **BLOCK** (likely duplicate)  ← **this rule**\n"
            "- `renewal_status = renewal` AND `vendor_in_register = false` → Warning (ID unconfirmed)  ← **this rule**"
        ),
        "trigger": "renewal_status conflicts with vendor_in_register",
        "action": "Confirm vendor status with business owner before proceeding",
        "severity": "Blocking / Warning",
        "policy_ref": "Vendor Risk Policy",
    },
    "PRO-003": {
        "rule": "ACV Consistency — Intake vs Quote",
        "detail": (
            "- `intake_acv = quote_annual_total` → passes\n"
            "- `intake_acv ≠ quote_annual_total` → Warning, reconcile before routing  ← **this rule**\n\n"
            "Tolerance: exact match required (discrepancy > $1 triggers)."
        ),
        "trigger": "intake_acv ≠ quote_annual_total",
        "action": "Reconcile ACV discrepancy with business owner before routing",
        "severity": "Warning",
        "policy_ref": "Procurement Policy",
    },
    "PRO-004": {
        "rule": "Subprocessor Consistency — Intake vs Questionnaire",
        "detail": (
            "- `intake_subprocessors = questionnaire_subprocessors` → passes\n"
            "- Lists differ → Warning  ← **this rule**\n\n"
            "Indicates one document may be outdated or incomplete."
        ),
        "trigger": "intake_subprocessors ≠ questionnaire_subprocessors",
        "action": "Business owner to confirm complete and accurate subprocessor list",
        "severity": "Warning",
        "policy_ref": "Procurement Policy",
    },
    "PRO-005": {
        "rule": "Document Checklist — Completeness",
        "detail": (
            "- All required documents provided → passes\n"
            "- Any required document missing → Warning  ← **this rule**\n\n"
            "SaaS required: quote, contract, security questionnaire, SOC 2 Type II, DPA (if personal data).\n"
            "Low-risk required: quote, business owner approval, tax form."
        ),
        "trigger": "all_required_docs_provided = false",
        "action": "Request missing documents from vendor or business owner",
        "severity": "Warning",
        "policy_ref": "Procurement Policy",
    },
    # ── Data Handling ─────────────────────────────────────────────────────────
    "DAT-001": {
        "rule": "AI / Model Training Language — Detected",
        "detail": (
            "- No AI/training language found → passes\n"
            "- AI/training language detected → Warning, Legal + Security review  ← **this rule**\n\n"
            "Flagged terms: 'model training', 'benchmarking', 'service improvement', 'model enhancement', 'product analytics' when personal or confidential data is in scope."
        ),
        "trigger": "has_ai_training = true",
        "action": "Legal and Security to review data-use scope; confirm opt-out",
        "severity": "Warning",
        "policy_ref": "Data Handling Policy",
    },
    "DAT-002": {
        "rule": "Model Training — Without Confirmed Opt-Out",
        "detail": (
            "- `has_ai_training = false` → passes\n"
            "- `has_ai_training = true` AND `opt_out_confirmed = true` → passes\n"
            "- `has_ai_training = true` AND `opt_out_confirmed = false` AND `sensitivity = restricted` → **BLOCK**  ← **this rule**\n"
            "- `has_ai_training = true` AND `opt_out_confirmed = false` AND `sensitivity ≠ restricted` → Warning  ← **this rule**"
        ),
        "trigger": "has_ai_training = true AND opt_out_confirmed = false",
        "action": "Block until vendor confirms opt-out or amends contract to exclude training use",
        "severity": "Warning / Blocking",
        "policy_ref": "Data Handling Policy",
    },
    "DAT-003": {
        "rule": "Cross-Border Transfer — Restricted Data",
        "detail": (
            "- No non-US subprocessors → passes\n"
            "- Non-US subprocessors AND `sensitivity ∉ restricted` → Warning (review only)\n"
            "- Non-US subprocessors AND `sensitivity = restricted` → **BLOCK**  ← **this rule**\n\n"
            "non-US subprocessors = `has_eu_subprocessors = true` OR `has_apac_subprocessors = true`"
        ),
        "trigger": "(has_eu_subprocessors OR has_apac_subprocessors) AND sensitivity = restricted",
        "action": "Legal and Security must review cross-border data transfer controls before proceeding",
        "severity": "Blocking",
        "policy_ref": "Data Handling Policy",
    },
}

_RULE_OWNERS = {
    "FIN-001": "Procurement Manager",
    "FIN-002": "VP Finance",
    "FIN-003": "CFO",
    "FIN-004": "Executive Sponsor",
    "FIN-005": "Legal",
    "FIN-006": "Executive Sponsor",
    "FIN-007": "VP Finance",
    "FIN-008": "Finance / FP&A",
    "FIN-009": "Finance / FP&A",
    "LEG-001": "Legal",
    "LEG-002": "Legal",
    "LEG-003": "Legal",
    "LEG-004": "Legal / Executive Sponsor",
    "LEG-005": "Legal",
    "LEG-006": "Legal",
    "LEG-007": "Legal",
    "LEG-008": "Procurement",
    "LEG-009": "Legal",
    "LEG-010": "Legal",
    "LEG-011": "Legal",
    "LEG-012": "Legal",
    "SEC-001": "Vendor",
    "SEC-002": "Security",
    "SEC-003": "Security",
    "SEC-004": "Vendor / Legal",
    "SEC-005": "Vendor",
    "SEC-006": "Security",
    "SEC-007": "Security",
    "PRO-001": "Business Owner",
    "PRO-002": "Business Owner / Procurement",
    "PRO-003": "Business Owner",
    "PRO-004": "Business Owner",
    "PRO-005": "Vendor",
    "DAT-001": "Legal / Security",
    "DAT-002": "Legal / Security",
    "DAT-003": "Legal / Security",
}
for _cid, _owner in _RULE_OWNERS.items():
    if _cid in POLICY_RULES:
        POLICY_RULES[_cid]["owner"] = _owner

# Policy document files for the Policy & Rules module
POLICY_FILES = {
    "Finance":       DOCS_PATH / "finance_approval_matrix.md",
    "Legal":         DOCS_PATH / "legal_review_policy.md",
    "Security":      DOCS_PATH / "security_review_policy.md",
    "Procurement":   DOCS_PATH / "procurement_policy.md",
    "Data Handling": DOCS_PATH / "data_handling_policy.md",
    "Vendor Risk":   DOCS_PATH / "vendor_risk_policy.md",
    "Communication": DOCS_PATH / "communication_policy.md",
}

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "nav_page": "vendor_analysis",
    "page": "overview",
    "selected_case": None,
    "analyses": {},
    "selected_version": {},
    "decisions": {},
    "category_decisions": {},
    "rule_decisions": {},  # case_id → v_num → check_id → {status, assignee, action, note}
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

if "results_loaded" not in st.session_state:
    if RESULTS_FILE.exists():
        try:
            _saved = json.loads(RESULTS_FILE.read_text())
            st.session_state.analyses = _saved.get("analyses", {})
            st.session_state.decisions = _saved.get("decisions", {})
            st.session_state.category_decisions = _saved.get("category_decisions", {})
            st.session_state.rule_decisions = _saved.get("rule_decisions", {})
        except Exception:
            pass
    st.session_state.results_loaded = True


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------
def _save_results():
    RESULTS_FILE.write_text(json.dumps({
        "analyses": st.session_state.analyses,
        "decisions": st.session_state.decisions,
        "category_decisions": st.session_state.category_decisions,
        "rule_decisions": st.session_state.rule_decisions,
    }, indent=2))


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------
def get_versions(case_id: str) -> list:
    return st.session_state.analyses.get(case_id, [])


def _selected_idx(case_id: str) -> int:
    versions = get_versions(case_id)
    if not versions:
        return -1
    idx = st.session_state.selected_version.get(case_id, len(versions) - 1)
    return max(0, min(idx, len(versions) - 1))


def get_selected_entry(case_id: str) -> dict | None:
    versions = get_versions(case_id)
    if not versions:
        return None
    return versions[_selected_idx(case_id)]


def get_latest_entry(case_id: str) -> dict | None:
    versions = get_versions(case_id)
    return versions[-1] if versions else None


def get_selected_v_num(case_id: str) -> int | None:
    entry = get_selected_entry(case_id)
    return entry["v"] if entry else None


def add_version(case_id: str, result: dict):
    if case_id not in st.session_state.analyses:
        st.session_state.analyses[case_id] = []
    v_num = len(st.session_state.analyses[case_id]) + 1
    st.session_state.analyses[case_id].append({
        "v": v_num,
        "ts": datetime.now().strftime("%b %d, %H:%M"),
        "result": result,
    })
    st.session_state.selected_version[case_id] = len(st.session_state.analyses[case_id]) - 1
    _save_results()



def _record_final_decision(case_id: str, v_num: int, decision: dict):
    st.session_state.decisions.setdefault(case_id, {})[v_num] = decision
    _save_results()


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------
def get_case_status(case_id: str) -> str:
    entry = get_latest_entry(case_id)
    final = st.session_state.decisions.get(case_id, {})
    if not entry:
        return "⬜ Pending"
    v_num = entry["v"]
    if v_num in final:
        outcome = final[v_num].get("overall", "approved")
        return {"blocked": "🔴 Blocked", "escalated": "🟡 Escalated", "approved": "✅ Onboarded"}.get(
            outcome, "✅ Onboarded"
        )
    triage = entry["result"].get("triage_output") or {}
    pre = entry["result"].get("pre_screen") or {}
    blocking = triage.get("blocking_issues") or []
    if blocking or pre.get("screen_result") == "block":
        return "🔴 Blocking Issues"
    if pre.get("screen_result") == "escalate":
        return "🟡 Escalation Required"
    rec = triage.get("recommendation", "")
    if rec == "escalate_to_human":
        return "🟡 Escalation Required"
    if rec == "pending_information":
        return "🟡 Pending Information"
    return "🟢 Ready to Review"


def get_category_status(case_id: str, category: str) -> str:
    v_num = get_selected_v_num(case_id)
    cat_dec = st.session_state.category_decisions.get(case_id, {}).get(v_num, {}).get(category)
    if cat_dec:
        r = cat_dec.get("result", "approved")
        return {"blocked": "🔴 Blocked", "escalated": "🟡 Escalated", "approved": "✅ Approved"}.get(r, "✅ Approved")

    entry = get_selected_entry(case_id)
    if not entry:
        return "—"
    triage = entry["result"].get("triage_output") or {}

    checklist = triage.get("policy_checklist") or []
    if checklist:
        check_ids_set = set(DOMAIN_CHECKLIST_IDS.get(category, []))
        worst = None
        for c in checklist:
            if c["check_id"] in check_ids_set and c["result"] == "triggered":
                sev = c.get("flag_severity", "")
                if sev == "blocking":
                    worst = "blocking"
                    break
                elif sev in ("warning", "info"):
                    worst = "warning"
        if worst == "blocking":
            return "🔴 Pending Block"
        elif worst == "warning":
            return "⚠️ Pending Escalate"
        return "✅ Pending Approve"

    blocking = triage.get("blocking_issues") or []
    flags = triage.get("policy_flags") or []
    keywords = CATEGORY_POLICY_MAP.get(category, [category])

    def matches(text: str) -> bool:
        return any(k.lower() in text.lower() for k in keywords)

    for b in blocking:
        if matches(b):
            return "🔴 Pending Block"
    for f in flags:
        if matches(f.get("policy", "")) or matches(f.get("issue", "")):
            sev = f.get("severity", "info")
            if sev == "blocking":
                return "🔴 Pending Block"
            if sev == "warning":
                return "⚠️ Pending Escalate"
    return "✅ Pending Approve"


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------
def write_audit_log(entry: dict):
    if AUDIT_LOG.exists():
        data = json.loads(AUDIT_LOG.read_text())
    else:
        data = {"entries": []}
    data["entries"].append(entry)
    AUDIT_LOG.write_text(json.dumps(data, indent=2))


def _load_new_vendors() -> list[dict]:
    if _NEW_VENDORS_FILE.exists():
        try:
            return json.loads(_NEW_VENDORS_FILE.read_text())
        except Exception:
            return []
    return []


def _save_new_vendors(vendors: list[dict]):
    _NEW_VENDORS_FILE.write_text(json.dumps(vendors, indent=2, default=str))


def _format_fact_value(key: str, val) -> str:
    if val is None:
        return "—"
    if isinstance(val, bool):
        return "✅ Yes" if val else "❌ No"
    if isinstance(val, list):
        return ", ".join(str(v) for v in val) if val else "—"
    if key in ("acv", "tcv", "budget_remaining") and isinstance(val, (int, float)):
        return f"${val:,.0f}"
    if key == "contract_term_months" and isinstance(val, (int, float)):
        return f"{int(val)} months"
    if key == "net_payment_days" and isinstance(val, (int, float)):
        return f"Net {int(val)}"
    if key == "liability_cap_months" and isinstance(val, (int, float)):
        return f"{int(val)} months"
    return str(val) if str(val) else "—"


def _render_facts_table(
    facts_fields: list, case_facts: dict, excerpts: dict,
    cat: str, selected_case: str, v_num: int,
):
    """Render extracted facts with per-row source trace (🔍) and override (✎) controls."""
    if not case_facts:
        st.caption("No structured facts available. Re-run the analysis to populate.")
        return

    _fact_overrides = st.session_state.setdefault("fact_overrides", {})
    _case_ov = _fact_overrides.setdefault(selected_case, {}).setdefault(str(v_num), {})

    visible = [(l, k) for l, k in facts_fields if case_facts.get(k) is not None]
    if not visible:
        st.caption("No facts extracted for this category.")
        return

    # Header
    st.markdown(
        "<div style='display:flex;padding:5px 8px;background:#1f2937;"
        "border-radius:6px 6px 0 0;border:1px solid #374151;border-bottom:none;margin-top:4px'>"
        "<span style='flex:0 0 40%;color:#6b7280;font-size:0.72rem;font-weight:600;"
        "text-transform:uppercase;letter-spacing:0.05em'>Field</span>"
        "<span style='flex:1;color:#6b7280;font-size:0.72rem;font-weight:600;"
        "text-transform:uppercase;letter-spacing:0.05em'>Value</span>"
        "</div>",
        unsafe_allow_html=True,
    )

    for i, (label, key) in enumerate(visible):
        raw_disp = _format_fact_value(key, case_facts.get(key))
        display_val = _case_ov.get(key, raw_disp)
        is_overridden = key in _case_ov
        has_src = key in excerpts

        _src_key  = f"fsrc_{selected_case}_{v_num}_{cat}_{key}"
        _edit_key = f"fedit_{selected_case}_{v_num}_{cat}_{key}"
        src_open  = st.session_state.get(_src_key, False)
        edit_open = st.session_state.get(_edit_key, False)

        border_b = "" if i == len(visible) - 1 and not src_open and not edit_open else "border-bottom:1px solid #374151;"
        br_bottom = "border-radius:0 0 6px 6px;" if i == len(visible) - 1 else ""

        c1, c2, c3, c4 = st.columns([4, 5, 0.55, 0.55])
        c1.markdown(
            f"<div style='padding:8px 8px;color:#9ca3af;font-size:0.875rem;"
            f"border-left:1px solid #374151;{border_b}{br_bottom}'>{_html.escape(label)}</div>",
            unsafe_allow_html=True,
        )
        edited_tag = ("&nbsp;<span style='font-size:0.7rem;color:#818cf8'>(edited)</span>"
                      if is_overridden else "")
        c2.markdown(
            f"<div style='padding:8px 4px;font-weight:500;font-size:0.875rem;"
            f"color:#f3f4f6;{border_b}'>{_html.escape(display_val)}{edited_tag}</div>",
            unsafe_allow_html=True,
        )
        src_style  = "primary" if src_open  else "secondary"
        edit_style = "primary" if edit_open else "secondary"
        if c3.button("🔍", key=f"fsrc_btn_{selected_case}_{v_num}_{cat}_{key}",
                     help="View source", use_container_width=True, type=src_style):
            st.session_state[_src_key]  = not src_open
            st.session_state[_edit_key] = False
            st.rerun()
        if c4.button("✎", key=f"fedit_btn_{selected_case}_{v_num}_{cat}_{key}",
                     help="Override value", use_container_width=True, type=edit_style):
            st.session_state[_edit_key] = not edit_open
            st.session_state[_src_key]  = False
            st.rerun()

        if src_open:
            if has_src:
                src, excerpt = excerpts[key]
                excerpt_html = _html.escape(excerpt or "").replace("\n", "<br>")
                st.markdown(
                    f"<div style='background:#0f172a;border-left:3px solid #4f46e5;"
                    f"padding:8px 14px;margin-bottom:2px;font-size:0.82rem'>"
                    f"<div style='color:#818cf8;font-size:0.7rem;font-weight:700;"
                    f"text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px'>"
                    f"{_html.escape(src or '')}</div>"
                    f"<div style='color:#d1d5db;line-height:1.6'>{excerpt_html}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    "<div style='background:#1c1917;border-left:3px solid #57534e;"
                    "padding:7px 14px;margin-bottom:2px;font-size:0.82rem;color:#a8a29e'>"
                    "Source not recorded — derived from document parsing or agent reasoning."
                    "</div>",
                    unsafe_allow_html=True,
                )

        if edit_open:
            new_val = st.text_input(
                "Override value", value=display_val,
                key=f"finput_{selected_case}_{v_num}_{cat}_{key}",
                label_visibility="collapsed",
            )
            ec1, ec2, ec3, _ = st.columns([1, 1, 1, 4])
            if ec1.button("💾 Save", key=f"fsave_{selected_case}_{v_num}_{cat}_{key}",
                          type="primary", use_container_width=True):
                _case_ov[key] = new_val
                st.session_state[_edit_key] = False
                st.rerun()
            if ec2.button("↩ Reset", key=f"freset_{selected_case}_{v_num}_{cat}_{key}",
                          use_container_width=True):
                _case_ov.pop(key, None)
                st.session_state[_edit_key] = False
                st.rerun()
            if ec3.button("✕ Cancel", key=f"fcancel_{selected_case}_{v_num}_{cat}_{key}",
                          use_container_width=True):
                st.session_state[_edit_key] = False
                st.rerun()


def _build_excerpts(tool_calls: list) -> dict:
    """Map case_facts field keys to (source_label, excerpt_text) from tool call outputs."""
    exc: dict = {}
    for call in tool_calls:
        tool = call["tool"]
        out = call.get("output") or {}
        inp = call.get("input") or {}
        if isinstance(out, str):
            try:
                out = json.loads(out)
            except Exception:
                out = {}

        if tool == "extract_contract_clauses":
            def _ex(clause_key, fact_keys):
                clause = out.get(clause_key) or {}
                if clause.get("found") and clause.get("excerpt"):
                    for k in fact_keys:
                        exc[k] = ("Contract", clause["excerpt"])
            _ex("auto_renewal", ["auto_renewal_clause"])
            _ex("governing_law", ["governing_law", "governing_law_outside_us"])
            _ex("limitation_of_liability", ["liability_cap_months"])
            _ex("data_processing_agreement_ref", ["dpa_referenced_in_contract"])
            _ex("subprocessor_clause", ["subprocessors", "has_eu_subprocessors", "has_apac_subprocessors"])
            ai_clause = out.get("ai_model_training") or {}
            if ai_clause.get("found") and ai_clause.get("excerpt"):
                for k in ["has_ai_training_language", "ai_training_opt_out_confirmed"]:
                    exc[k] = ("Contract", ai_clause["excerpt"])

        elif tool == "lookup_budget":
            if out.get("found"):
                info = (
                    f"Cost center: {out.get('cost_center')}  ·  "
                    f"Department: {out.get('department')}  ·  "
                    f"Budget owner: {out.get('budget_owner')}  ·  "
                    f"Annual budget remaining: ${out.get('annual_budget_remaining', 0):,.0f}"
                )
                for k in ["budget_remaining", "budget_sufficient", "cost_center"]:
                    exc[k] = ("Budget System", info)

        elif tool == "check_existing_vendor":
            vname = inp.get("vendor_name", "")
            if vname:
                exc["vendor_name"] = ("Intake Form", f"Vendor name as submitted: {vname}")
            found = out.get("found", False)
            info = f"Vendor register lookup: {'Match found' if found else 'No match found'}."
            if found:
                info += f" Status: {out.get('status', '—')}. ID: {out.get('vendor_id', '—')}."
            elif out.get("similar_vendors"):
                names = ", ".join(v["vendor_name"] for v in out["similar_vendors"])
                info += f" Similar vendors: {names}."
            else:
                info += " No similar vendors found."
            exc["vendor_in_register"] = ("Vendor Register", info)

        elif tool == "calculate_total_contract_value":
            acv_v = out.get("annual_contract_value", 0)
            term_v = out.get("contract_term_months", 0)
            fees_v = out.get("one_time_fees", 0)
            tcv_v = out.get("total_contract_value", 0)
            calc = f"ACV ${acv_v:,.0f} × {term_v} months ÷ 12 + one-time fees ${fees_v:,.0f} = TCV ${tcv_v:,.0f}"
            exc["tcv"] = ("Calculation", calc)
            exc["acv"] = ("Intake Form / Quote", f"Annual Contract Value: ${acv_v:,.0f} | Term: {term_v} months")
            exc["contract_term_months"] = ("Intake Form / Contract", f"Contract term: {term_v} months")

        elif tool == "classify_data_sensitivity":
            types = inp.get("data_types") or []
            restricted = out.get("restricted_fields") or []
            confidential = out.get("confidential_fields") or []
            level = out.get("sensitivity_level", "unknown")
            detail = (
                f"Declared types: {', '.join(types) or 'none'}.  "
                f"Restricted fields: {', '.join(restricted) or 'none'}.  "
                f"Confidential fields: {', '.join(confidential) or 'none'}.  "
                f"→ Classified as: {level}"
            )
            exc["data_sensitivity"] = ("Intake Form + Classification", detail)
            exc["data_types"] = ("Intake Form", f"Declared types: {', '.join(types) or 'none'}")

        elif tool == "validate_cross_document_consistency":
            # Intake-form fields surfaced as inputs to this tool
            renewal = inp.get("intake_renewal_status")
            if renewal:
                exc["renewal_status"] = ("Intake Form",
                    f"Renewal status declared on intake form: {renewal}")
            intake_subs = inp.get("intake_subprocessors") or []
            if intake_subs:
                exc["subprocessors"] = ("Intake Form / Security Questionnaire",
                    f"Intake form declared: {', '.join(intake_subs)}")
            issues = out.get("issues") or []
            has_acv_issue = any("acv" in i.get("type", "") for i in issues)
            has_sp_issue = any("subprocessor" in i.get("type", "") for i in issues)
            for issue in issues:
                t = issue.get("type", "")
                desc = issue.get("description", "")
                if "acv" in t:
                    exc["acv_matches_quote"] = ("Cross-Document Check", desc)
                elif "subprocessor" in t:
                    exc["subprocessors_consistent"] = ("Cross-Document Check", desc)
            if not has_acv_issue:
                exc["acv_matches_quote"] = ("Cross-Document Check",
                    "ACV values are consistent between intake form and vendor quote.")
            if not has_sp_issue:
                exc["subprocessors_consistent"] = ("Cross-Document Check",
                    "Subprocessor lists are consistent between intake form and security questionnaire.")

        elif tool == "run_policy_checklist":
            # Basic intake fields passed as inputs
            vcat = inp.get("vendor_category")
            if vcat:
                exc["vendor_category"] = ("Intake Form",
                    f"Vendor category as declared on intake form: {vcat}")
            pt = inp.get("payment_terms")
            if pt:
                exc["payment_terms"] = ("Intake Form / Contract",
                    f"Payment terms: {pt}")
                exc["net_payment_days"] = ("Intake Form / Contract",
                    f"Payment terms: {pt}")
            for field, label in [
                ("soc2_type2_provided",           "SOC 2 Type II report"),
                ("dpa_provided",                  "Data Processing Agreement"),
                ("security_questionnaire_provided","Security questionnaire"),
            ]:
                if field in inp:
                    status = "provided" if inp[field] else "not provided"
                    exc[field] = ("Intake Form / Document Checklist",
                        f"{label}: {status} (as declared on intake form)")
            if "has_ai_training" in inp:
                exc["ai_functionality"] = ("Intake Form",
                    f"AI/ML functionality declared: {inp['has_ai_training']}")
            if "has_eu_subprocessors" in inp:
                exc["has_eu_subprocessors"] = ("Intake Form / Security Questionnaire",
                    f"EU subprocessors present: {inp['has_eu_subprocessors']}")
            if "has_apac_subprocessors" in inp:
                exc["has_apac_subprocessors"] = ("Intake Form / Security Questionnaire",
                    f"APAC subprocessors present: {inp['has_apac_subprocessors']}")

        elif tool == "submit_triage_output":
            missing = inp.get("missing_documents") or []
            if missing:
                exc["missing_documents"] = ("Agent Analysis",
                    f"Documents identified as missing: {', '.join(missing)}")
                exc["all_docs_provided"] = ("Agent Analysis",
                    f"Missing documents found: {', '.join(missing)} — not all docs provided.")
            else:
                exc["all_docs_provided"] = ("Agent Analysis",
                    "All required documents were present in the submission.")
            exc["required_intake_fields_complete"] = ("Agent Analysis",
                "Completeness of intake form fields assessed during triage.")

    return exc


def _csv_bytes(rows: list[list]) -> bytes:
    import csv, io
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue().encode("utf-8-sig")  # utf-8-sig for Excel compatibility


# Canonical fact field order (fixed across every export)
_CANONICAL_FACTS: list[tuple[str, str]] = [
    ("vendor_name",                    "Vendor Name"),
    ("vendor_category",                "Vendor Category"),
    ("renewal_status",                 "Renewal Status"),
    ("vendor_in_register",             "Vendor in Register"),
    ("acv",                            "ACV"),
    ("tcv",                            "TCV"),
    ("contract_term_months",           "Contract Term (months)"),
    ("payment_terms",                  "Payment Terms"),
    ("net_payment_days",               "Net Payment Days"),
    ("cost_center",                    "Cost Center"),
    ("budget_remaining",               "Budget Remaining"),
    ("budget_sufficient",              "Budget Sufficient"),
    ("acv_matches_quote",              "ACV Matches Quote"),
    ("data_types",                     "Data Types"),
    ("data_sensitivity",               "Data Sensitivity"),
    ("system_integrations",            "System Integrations"),
    ("subprocessors",                  "Subprocessors"),
    ("has_eu_subprocessors",           "EU Subprocessors"),
    ("has_apac_subprocessors",         "APAC Subprocessors"),
    ("subprocessors_consistent",       "Subprocessors Consistent"),
    ("soc2_type2_provided",            "SOC 2 Type II Provided"),
    ("dpa_provided",                   "DPA Provided"),
    ("security_questionnaire_provided","Security Questionnaire Provided"),
    ("dpa_referenced_in_contract",     "DPA Referenced in Contract"),
    ("ai_functionality",               "AI Functionality"),
    ("has_ai_training_language",       "AI Training Language in Contract"),
    ("ai_training_opt_out_confirmed",  "AI Training Opt-Out Confirmed"),
    ("auto_renewal_clause",            "Auto-Renewal Clause"),
    ("liability_cap_months",           "Liability Cap (months)"),
    ("governing_law",                  "Governing Law"),
    ("governing_law_outside_us",       "Governing Law Outside US"),
    ("all_docs_provided",              "All Docs Provided"),
    ("missing_documents",              "Missing Documents"),
    ("required_intake_fields_complete","Required Intake Fields Complete"),
]

# Canonical rule ID order (all 34, sorted)
_CANONICAL_RULE_IDS: list[str] = sorted(POLICY_RULES.keys())


def _full_export_csv(triage, meta, v_num, case_facts, excerpts,
                     checklist_by_id, rd_ver_all) -> bytes:
    """Single fixed-format CSV: metadata → extracted facts → all 34 rules."""
    rows: list[list] = []

    # ── Section 1: Metadata ──────────────────────────────────────────────────
    rows.append(["## ANALYSIS METADATA"])
    rows.append(["Field", "Value"])
    rows += [
        ["Case ID",           meta.get("case_id", "")],
        ["Vendor",            meta.get("vendor", "")],
        ["Category",          meta.get("category", "")],
        ["ACV",               f"${meta.get('acv', 0):,}"],
        ["Version",           f"v{v_num}"],
        ["Export Date",       datetime.now().strftime("%Y-%m-%d %H:%M")],
        ["Risk Tier",         triage.get("risk_tier", "")],
        ["AI Recommendation", triage.get("recommendation", "")],
        ["Blocking Issues",   "; ".join(triage.get("blocking_issues") or [])],
        ["Missing Documents", "; ".join(triage.get("missing_documents") or [])],
        ["Required Approvals","  ".join(triage.get("required_approvals") or [])],
        ["Required Reviews",  "; ".join(triage.get("required_reviews") or [])],
        ["Contract Flags",    "; ".join(str(f) for f in (triage.get("contract_legal_flags") or []))],
        ["Summary",           triage.get("summary", "")],
    ]
    rows.append([])  # blank separator

    # ── Section 2: Extracted Facts (canonical fixed order) ───────────────────
    rows.append(["## EXTRACTED FACTS"])
    rows.append(["Field Key", "Field Label", "Value", "Source", "Excerpt"])
    for key, label in _CANONICAL_FACTS:
        val = case_facts.get(key)
        disp = _format_fact_value(key, val) if val is not None else ""
        src, excerpt = excerpts.get(key, ("", ""))
        rows.append([key, label, disp, src, excerpt])
    rows.append([])

    # ── Section 3: Policy Rules (all 34, fixed order) ────────────────────────
    rows.append(["## POLICY RULES"])
    rows.append([
        "Check ID", "Rule Name", "Domain", "Result", "Severity",
        "Flag Reason", "Action Required", "Owner",
        "Reviewer Status", "Reviewer Assignee", "Reviewer Note",
    ])
    for cid in _CANONICAL_RULE_IDS:
        pr = POLICY_RULES.get(cid, {})
        check = checklist_by_id.get(cid, {})
        rd = rd_ver_all.get(cid, {})
        is_triggered = check.get("result") == "triggered"
        rows.append([
            cid,
            pr.get("rule", check.get("description", "")),
            pr.get("domain", ""),
            check.get("result", "not_run"),
            check.get("flag_severity", "") if is_triggered else "",
            check.get("flag_reason", ""),
            check.get("action_required", ""),
            pr.get("owner", ""),
            rd.get("status", ""),
            rd.get("assignee", ""),
            rd.get("note", ""),
        ])

    return _csv_bytes(rows)


def _brief_reason(check: dict, case_facts: dict | None = None) -> str:
    """One-line natural-language reason for a rule card (pass or fail)."""
    cid = check.get("check_id", "")
    val = check.get("extracted_value", "")
    is_triggered = check["result"] == "triggered"

    # ── Triggered: enrich PRO-005 with actual missing doc names ──────────────
    if is_triggered:
        if cid == "PRO-005" and case_facts:
            missing = case_facts.get("missing_documents") or []
            if missing:
                return "Missing: " + ", ".join(missing)
        return check.get("flag_reason") or "Check triggered."

    # ── Clear: per-check-id explanations ─────────────────────────────────────
    fin_thresholds = {
        "FIN-001": ("$25K", "Procurement Manager"),
        "FIN-002": ("$50K", "VP Finance"),
        "FIN-003": ("$100K", "CFO"),
        "FIN-004": ("$250K", "Executive Sponsor"),
    }
    if cid in fin_thresholds:
        limit, role = fin_thresholds[cid]
        return f"{val} — below {limit} threshold, {role} not required ✓"
    if cid == "FIN-005":
        return f"TCV {val} — below $100K, Legal review not triggered on TCV basis ✓"
    if cid == "FIN-006":
        return f"TCV {val} — below $250K, Executive Sponsor not triggered on TCV basis ✓"
    if cid == "FIN-007":
        return f"{val} — standard terms, no extended-payment review required ✓"
    if cid == "FIN-008":
        return f"{val} — within 24-month limit, no multi-year Finance review required ✓"
    if cid == "FIN-009":
        remaining = (case_facts or {}).get("budget_remaining")
        acv = (case_facts or {}).get("acv")
        if remaining is not None and acv is not None:
            return f"Budget remaining ${remaining:,.0f} covers ACV ${acv:,.0f} ✓"
        return val + " — budget sufficient ✓" if val else "Budget sufficient ✓"

    pass_labels = {
        "Provided": "Document provided ✓",
        "Complete": "All required fields complete ✓",
        "Consistent": "Values match across documents ✓",
        "Not detected": "Not detected in any document ✓",
        "Not found": "Not found — check not applicable ✓",
        "N/A": "Not applicable ✓",
        "Found": "Found and recorded ✓",
    }
    if val in pass_labels:
        return pass_labels[val]
    if val.startswith("Sufficient: True"):
        return "Budget sufficient to cover ACV ✓"
    if val and val != "—":
        return f"{val} ✓"
    return "Passes ✓"


def _draft_email(vendor_name: str, assignee: str, items: list[dict], case_summary: str) -> dict:
    """Returns {"to": str, "subject": str, "body": str} or {"error": str}."""
    try:
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=_API_KEY)
        item_lines = []
        for it in items:
            line = f"  • [{it['check_id']}] {it['rule']}"
            if it.get("flag_reason"):
                line += f"\n      Why flagged: {it['flag_reason']}"
            if it.get("detail"):
                line += f"\n      Policy context: {it['detail']}"
            line += f"\n      Required action: {it['action']}"
            if it.get("note"):
                line += f"\n      Reviewer note: {it['note']}"
            if it.get("policy_ref"):
                line += f"\n      Policy ref: {it['policy_ref']}"
            item_lines.append(line)
        action_block = "\n\n".join(item_lines)
        prompt = (
            f"You are an internal procurement coordinator drafting an email to a colleague.\n\n"
            f"Vendor being onboarded: {vendor_name}\n"
            f"Recipient role: {assignee}\n"
            f"Triage context: {case_summary[:400]}\n\n"
            f"Items requiring their attention:\n{action_block}\n\n"
            f"Return ONLY in this exact format (no preamble, no extra lines before 'To:'):\n"
            f"To: [recipient role or name]\n"
            f"Subject: [descriptive subject line]\n"
            f"---\n"
            f"[email body starting with salutation]\n\n"
            f"Rules for the body:\n"
            f"- For each flagged item, explain WHY it was flagged and exactly what action is needed.\n"
            f"- Tell the recipient to contact christin@accelerant.com with any questions.\n"
            f"- Ask for response within 3 business days.\n"
            f"- Professional and direct tone. Do NOT include any draft label inside the email."
        )
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=768,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        lines = raw.splitlines()
        to_val, subj_val, body_lines = assignee, "", []
        sep_idx = None
        for i, ln in enumerate(lines):
            if ln.startswith("To:"):
                to_val = ln[3:].strip()
            elif ln.startswith("Subject:"):
                subj_val = ln[8:].strip()
            elif ln.strip() == "---":
                sep_idx = i
                break
        if sep_idx is not None:
            body_lines = lines[sep_idx + 1:]
        else:
            body_lines = [ln for ln in lines if not ln.startswith(("To:", "Subject:"))]
        return {"to": to_val, "subject": subj_val, "body": "\n".join(body_lines).strip()}
    except Exception as exc:
        return {"error": str(exc)}


def go_overview():
    st.session_state.page = "overview"
    st.session_state.nav_page = "vendor_analysis"


def go_detail(case_id: str, version_idx: int | None = None):
    st.session_state.page = "detail"
    st.session_state.nav_page = "vendor_analysis"
    st.session_state.selected_case = case_id
    if version_idx is not None:
        st.session_state.selected_version[case_id] = version_idx
    else:
        versions = get_versions(case_id)
        if versions:
            st.session_state.selected_version[case_id] = len(versions) - 1


# ---------------------------------------------------------------------------
# Sidebar — navigation + settings
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🏢 Vendor Onboarding")
    st.caption("AI-assisted procurement triage")
    st.divider()

    # Navigation menu
    nav_items = [
        ("vendor_analysis", "📋  Vendor Analysis"),
        ("policy_rules",    "📄  Policy & Rules"),
    ]
    for nav_key, nav_label in nav_items:
        is_active = st.session_state.nav_page == nav_key
        if st.button(
            nav_label,
            key=f"nav_{nav_key}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            if nav_key == "vendor_analysis":
                st.session_state.page = "overview"
            st.session_state.nav_page = nav_key
            st.rerun()

    st.divider()

    if _API_KEY_VALID:
        st.success(f"API key active ({_KEY_SOURCE})")
    else:
        st.error("No valid API key.\nAdd `ANTHROPIC_API_KEY` to `.env`.")

    can_run = _API_KEY_VALID

    st.divider()
    st.caption(
        "**Agent may:** summarize, flag issues, draft messages, recommend routing.\n\n"
        "**Agent may NOT:** approve vendors, commit spend, send external comms."
    )


# ---------------------------------------------------------------------------
# Run analysis helper
# ---------------------------------------------------------------------------
def run_analysis(case_id: str):
    meta = CASE_META[case_id]
    with st.spinner(f"Running agent on {meta['vendor']}…"):
        try:
            case_data = load_case(case_id, BASE_PATH)
            policies = load_policies(BASE_PATH)
            result = run_vendor_agent(case_data, policies, _API_KEY)
            add_version(case_id, result)
            go_detail(case_id)
            st.rerun()
        except Exception as exc:
            st.error(f"Analysis failed: {exc}")
            st.exception(exc)


# ===========================================================================
# PAGE ROUTING
# ===========================================================================

# ── Policy & Rules ──────────────────────────────────────────────────────────
if st.session_state.nav_page == "policy_rules":

    st.markdown("## Policy & Rules")
    st.caption(
        "Review the complete policy documents and the checklist of rules the agent applies to every case."
    )

    policy_tab, rule_tab = st.tabs(["📄 Policy Documents", "✅ Rule Checklist"])

    # ── Policy Documents ─────────────────────────────────────────────────────
    with policy_tab:
        st.caption(
            "Original policy documents used to configure the agent's triage logic. "
            "Review these to confirm the policies are appropriate for your organization."
        )
        doc_domains = list(POLICY_FILES.keys())
        doc_tabs = st.tabs(doc_domains)
        for dtab, domain in zip(doc_tabs, doc_domains):
            with dtab:
                pfile = POLICY_FILES[domain]
                if pfile.exists():
                    st.markdown(pfile.read_text())
                else:
                    st.warning(f"Policy file not found: `{pfile}`")

    # ── Rule Checklist ───────────────────────────────────────────────────────
    with rule_tab:
        st.caption(
            "Each rule is applied deterministically to the extracted case facts. "
            "The AI extracts — these rules check. Review them to confirm the logic is correct."
        )

        # Severity badge rendering
        def _sev_badge(sev: str) -> str:
            if "Blocking" in sev and "Warning" in sev:
                return "🔴 Blocking · ⚠️ Warning"
            if "Blocking" in sev:
                return "🔴 Blocking"
            if "Warning" in sev:
                return "⚠️ Warning"
            return "ℹ️ Info"

        rule_domains = ["Finance", "Legal", "Security", "Procurement", "Data Handling", "Vendor Risk"]
        rtabs = st.tabs(rule_domains)

        for rtab, domain in zip(rtabs, rule_domains):
            with rtab:
                check_ids = DOMAIN_CHECKLIST_IDS.get(domain, [])
                n_blocking = sum(
                    1 for cid in check_ids
                    if "Blocking" in POLICY_RULES.get(cid, {}).get("severity", "")
                )
                n_warn = sum(
                    1 for cid in check_ids
                    if POLICY_RULES.get(cid, {}).get("severity", "") in ("Warning", "Warning / Blocking", "Info")
                    and "Blocking" not in POLICY_RULES.get(cid, {}).get("severity", "")
                )
                st.caption(
                    f"{len(check_ids)} rules · {n_blocking} blocking · {n_warn} warning/info"
                )

                for cid in check_ids:
                    pr = POLICY_RULES.get(cid)
                    if not pr:
                        continue
                    badge = _sev_badge(pr["severity"])

                    with st.container(border=True):
                        top_left, top_right = st.columns([5, 2])
                        with top_left:
                            st.markdown(
                                f"<span style='font-family:monospace;background:#4f46e5;color:#fff;"
                                f"padding:2px 7px;border-radius:4px;font-size:0.8rem;font-weight:600'>{cid}</span>"
                                f"&nbsp;&nbsp;**{pr['rule']}**",
                                unsafe_allow_html=True,
                            )
                        with top_right:
                            st.markdown(
                                f"<div style='text-align:right'>{badge}</div>",
                                unsafe_allow_html=True,
                            )

                        st.markdown(pr["detail"])
                        st.markdown(
                            f"<span style='color:#6b7280;font-size:0.83rem'>"
                            f"🔍 **Triggers when:** {pr['trigger']}</span><br>"
                            f"<span style='color:#6b7280;font-size:0.83rem'>"
                            f"→ **Action:** {pr['action']}</span><br>"
                            f"<span style='color:#9ca3af;font-size:0.78rem'>"
                            f"Policy ref: {pr['policy_ref']}</span>",
                            unsafe_allow_html=True,
                        )

# ── Vendor Analysis ──────────────────────────────────────────────────────────
else:

    # ── OVERVIEW ────────────────────────────────────────────────────────────
    if st.session_state.page == "overview":

        _new_vendors = _load_new_vendors()
        _show_upload = st.session_state.get("show_upload_form", False)

        ov_title, ov_btn = st.columns([5, 1])
        ov_title.markdown("## Vendor Onboarding Pipeline")
        if ov_btn.button(
            "✕ Cancel" if _show_upload else "➕ New Vendor",
            key="toggle_upload_form",
            use_container_width=True,
            type="secondary",
        ):
            st.session_state["show_upload_form"] = not _show_upload
            st.rerun()

        if _show_upload:
            with st.container(border=True):
                st.markdown("#### Upload New Vendor")
                st.caption("Upload the vendor's documents — vendor details will be extracted automatically.")
                _vfiles = st.file_uploader(
                    "Vendor documents",
                    accept_multiple_files=True,
                    type=["pdf", "docx", "xlsx", "csv", "txt", "md"],
                    label_visibility="collapsed",
                )
                sub_col, _ = st.columns([2, 6])
                if sub_col.button("Submit", type="primary", use_container_width=True,
                                  disabled=not _vfiles):
                    _vid = f"upload_{len(_new_vendors) + 1:03d}"
                    _vendor_dir = _UPLOAD_DIR / _vid
                    _vendor_dir.mkdir(exist_ok=True)
                    _saved_files = []
                    for _f in (_vfiles or []):
                        _fpath = _vendor_dir / _f.name
                        _fpath.write_bytes(_f.read())
                        _saved_files.append(_f.name)
                    _new_vendors.append({
                        "id": _vid,
                        "vendor": _vid,
                        "category": "—",
                        "acv": 0,
                        "files": _saved_files,
                        "status": "submitted",
                        "created_at": datetime.now().isoformat(),
                    })
                    _save_new_vendors(_new_vendors)
                    st.session_state["show_upload_form"] = False
                    st.success(f"{len(_saved_files)} file(s) uploaded — pending analysis.")
                    st.rerun()

        def _final_outcome(case_id: str) -> str | None:
            """Return the final decision overall ('approved'/'blocked'/'escalated') or None."""
            for e in get_versions(case_id):
                dec = st.session_state.decisions.get(case_id, {}).get(e["v"])
                if dec:
                    return dec.get("overall")
            return None

        n_all = len(CASE_ORDER) + len(_new_vendors)
        n_pending_review = sum(
            1 for c in CASE_ORDER
            if get_versions(c) and _final_outcome(c) is None
        ) + sum(1 for nv in _new_vendors if nv.get("status") == "submitted")
        n_pending_update = sum(
            1 for c in CASE_ORDER if _final_outcome(c) == "escalated"
        )
        n_completed = sum(
            1 for c in CASE_ORDER if _final_outcome(c) in ("approved", "blocked")
        )

        s1, s2, s3, s4 = st.columns(4)
        s1.metric("All Vendors", n_all)
        s2.metric("Pending Review", n_pending_review)
        s3.metric("Pending Update", n_pending_update)
        s4.metric("Completed", n_completed)

        st.divider()

        h1, h2, h3, h4, h5, h6 = st.columns([2.5, 2, 1.2, 1.2, 1.5, 2])
        for col, label in zip([h1, h2, h3, h4, h5, h6],
                              ["Vendor", "Category", "ACV", "Risk", "Status", "Actions"]):
            col.markdown(
                f"<span style='color:#6b7280;font-size:0.78rem;font-weight:600;"
                f"text-transform:uppercase;letter-spacing:0.05em'>{label}</span>",
                unsafe_allow_html=True,
            )

        for case_id, meta in CASE_META.items():
            entry = get_latest_entry(case_id)
            triage = (entry["result"].get("triage_output") or {}) if entry else {}
            risk_raw = triage.get("risk_tier", "").upper() if entry else ""
            status = get_case_status(case_id)
            versions = get_versions(case_id)
            version_badge = f"v{len(versions)}" if versions else ""

            with st.container(border=True):
                c1, c2, c3, c4, c5, c6 = st.columns([2.5, 2, 1.2, 1.2, 1.5, 2])
                with c1:
                    badge_html = (
                        f"<span style='background:#e0e7ff;color:#4338ca;font-size:0.7rem;"
                        f"font-weight:600;padding:1px 6px;border-radius:4px;margin-left:6px'>"
                        f"{version_badge}</span>"
                    ) if version_badge else ""
                    st.markdown(f"**{meta['vendor']}**{badge_html}", unsafe_allow_html=True)
                    st.caption(meta["label"].split(" · ")[0])
                with c2:
                    st.write(meta["category"])
                with c3:
                    st.write(f"${meta['acv']:,}")
                with c4:
                    st.write(f"{RISK_COLOR.get(risk_raw, '⚪')} {risk_raw}" if risk_raw else "—")
                with c5:
                    st.write(status)
                with c6:
                    if versions:
                        if st.button("View →", key=f"view_{case_id}", use_container_width=True):
                            go_detail(case_id)
                            st.rerun()
                    else:
                        if st.button("▶ Analyze", key=f"run_{case_id}",
                                     disabled=not can_run, use_container_width=True):
                            run_analysis(case_id)

        # Newly uploaded vendors (not yet analyzed)
        for _nv in _new_vendors:
            with st.container(border=True):
                nc1, nc2, nc3, nc4, nc5, nc6 = st.columns([2.5, 2, 1.2, 1.2, 1.5, 2])
                with nc1:
                    new_badge = ("<span style='background:#d1fae5;color:#065f46;font-size:0.7rem;"
                                 "font-weight:600;padding:1px 6px;border-radius:4px;margin-left:6px'>"
                                 "NEW</span>")
                    st.markdown(f"**{_nv['vendor']}**{new_badge}", unsafe_allow_html=True)
                    st.caption(_nv["id"])
                with nc2:
                    st.write(_nv["category"])
                with nc3:
                    st.write(f"${_nv['acv']:,}")
                with nc4:
                    st.write("—")
                with nc5:
                    st.markdown(
                        "<span style='color:#6b7280;font-size:0.88rem'>📋 Submitted</span>",
                        unsafe_allow_html=True,
                    )
                with nc6:
                    nd1, nd2 = st.columns(2)
                    if nd1.button("🗑 Remove", key=f"del_nv_{_nv['id']}", use_container_width=True):
                        _new_vendors = [v for v in _new_vendors if v["id"] != _nv["id"]]
                        _save_new_vendors(_new_vendors)
                        st.rerun()
                    if nd2.button("Details", key=f"det_nv_{_nv['id']}", use_container_width=True):
                        st.session_state[f"nv_expand_{_nv['id']}"] = not st.session_state.get(
                            f"nv_expand_{_nv['id']}", False)
                        st.rerun()
                if st.session_state.get(f"nv_expand_{_nv['id']}"):
                    _cols = st.columns(3)
                    _cols[0].caption(f"Contact: {_nv.get('contact') or '—'}")
                    _cols[1].caption(f"Submitted: {_nv.get('created_at', '')[:10]}")
                    _cols[2].caption(f"Files: {', '.join(_nv['files']) if _nv['files'] else 'None'}")
                    if _nv.get("notes"):
                        st.caption(f"Notes: {_nv['notes']}")

        with st.expander("ℹ️ How it works", expanded=False):
            def _chip(text, bg="#1e293b", fg="#94a3b8"):
                return (f"<span style='background:{bg};color:{fg};font-size:0.72rem;"
                        f"padding:2px 8px;border-radius:4px;margin:2px 3px 2px 0;"
                        f"display:inline-block;white-space:nowrap'>{text}</span>")

            _steps = [
                (
                    "01", "Upload Documents", "📂",
                    "Vendor documents are parsed automatically — no manual data entry.",
                    [("Intake form", "#1e3a5f", "#93c5fd"),
                     ("Vendor quote", "#1e3a5f", "#93c5fd"),
                     ("Contract (PDF)", "#1e3a5f", "#93c5fd"),
                     ("Security questionnaire", "#1e3a5f", "#93c5fd"),
                     ("Vendor email", "#1e3a5f", "#93c5fd")],
                ),
                (
                    "02", "AI-Powered Analysis", "🤖",
                    "The agent runs 7 specialized tools to extract and cross-validate key information.",
                    [("Budget check", "#1a2e1a", "#86efac"),
                     ("Vendor registry lookup", "#1a2e1a", "#86efac"),
                     ("TCV calculation", "#1a2e1a", "#86efac"),
                     ("Contract clause extraction", "#1a2e1a", "#86efac"),
                     ("Data sensitivity classification", "#1a2e1a", "#86efac"),
                     ("Cross-document validation", "#1a2e1a", "#86efac")],
                ),
                (
                    "03", "Policy Checks", "📋",
                    "34 automated checks across 5 compliance domains — every vendor, every time.",
                    [("Finance", "#2d1b4e", "#c4b5fd"),
                     ("Legal", "#2d1b4e", "#c4b5fd"),
                     ("Security", "#2d1b4e", "#c4b5fd"),
                     ("Data Handling", "#2d1b4e", "#c4b5fd"),
                     ("Procurement", "#2d1b4e", "#c4b5fd")],
                ),
                (
                    "04", "Risk Scoring & Flags", "🎯",
                    "Outputs a risk tier, lists any blocking issues and missing documents, and recommends an approval route.",
                    [("Risk tier (LOW / HIGH)", "#2d2006", "#fde68a"),
                     ("Blocking issues", "#2d2006", "#fde68a"),
                     ("Missing documents", "#2d2006", "#fde68a"),
                     ("Approval routing", "#2d2006", "#fde68a")],
                ),
                (
                    "05", "Human Review & Decision", "✅",
                    "Reviewers step through each check, accept or override findings, draft follow-up emails, and submit the final onboarding decision.",
                    [("Accept / modify each check", "#0f2d1a", "#6ee7b7"),
                     ("Draft follow-up emails", "#0f2d1a", "#6ee7b7"),
                     ("Complete onboarding", "#0f2d1a", "#6ee7b7")],
                ),
            ]

            cols = st.columns(5)
            for col, (num, title, icon, desc, chips) in zip(cols, _steps):
                chips_html = "".join(_chip(t, bg, fg) for t, bg, fg in chips)
                col.markdown(
                    f"<div style='background:#111827;border:1px solid #1f2937;"
                    f"border-radius:8px;padding:14px 12px;height:100%;'>"
                    f"<div style='font-size:0.7rem;color:#4f46e5;font-weight:700;"
                    f"letter-spacing:0.08em;margin-bottom:6px'>STEP {num}</div>"
                    f"<div style='font-size:1rem;font-weight:700;color:#f3f4f6;"
                    f"margin-bottom:6px'>{icon} {title}</div>"
                    f"<div style='font-size:0.8rem;color:#9ca3af;line-height:1.5;"
                    f"margin-bottom:10px'>{desc}</div>"
                    f"<div style='line-height:2'>{chips_html}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    # ── DETAIL ──────────────────────────────────────────────────────────────
    elif st.session_state.page == "detail":

        selected_case = st.session_state.selected_case
        if not selected_case:
            go_overview()
            st.rerun()

        meta = CASE_META[selected_case]
        versions = get_versions(selected_case)

        if st.button("← Back to Pipeline"):
            go_overview()
            st.rerun()

        st.markdown(f"## {meta['label']}")

        if not versions:
            st.info("No analysis yet. Click **▶ Analyze** on the pipeline page.")
            st.stop()

        def _fmt_ts(ts: str) -> str:
            for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
                        "%H:%M %b %d", "%H:%M %b %d %Y"):
                try:
                    return datetime.strptime(ts, fmt).strftime("%b %d, %H:%M")
                except ValueError:
                    pass
            return ts[:16]

        version_labels = [
            f"v{e['v']}  ·  {_fmt_ts(e['ts'])}" + ("  (latest)" if i == len(versions) - 1 else "")
            for i, e in enumerate(versions)
        ]
        current_idx = _selected_idx(selected_case)
        _nv_key = f"show_new_ver_{selected_case}"

        ver_sel_col, ver_btn_col = st.columns([3, 1])
        with ver_sel_col:
            chosen_label = st.selectbox(
                "Version",
                version_labels,
                index=current_idx,
                label_visibility="collapsed",
            )
            new_idx = version_labels.index(chosen_label)
            if new_idx != current_idx:
                st.session_state.selected_version[selected_case] = new_idx
                st.rerun()
        with ver_btn_col:
            _nv_open = st.session_state.get(_nv_key, False)
            if st.button(
                "✕ Cancel" if _nv_open else "＋ New Version",
                key=f"toggle_new_ver_{selected_case}",
                use_container_width=True,
            ):
                st.session_state[_nv_key] = not _nv_open
                st.rerun()

        if st.session_state.get(_nv_key):
            with st.container(border=True):
                st.markdown("#### Upload documents for new version")
                st.caption(
                    "Upload replacement files for any document type. "
                    "Files are saved and the agent will use them when re-analysed."
                )
                _CASE_DIR = Path(BASE_PATH) / "cases" / selected_case
                _doc_types = {
                    "Intake form": (f"{selected_case}_intake.xlsx", ["xlsx"]),
                    "Vendor quote": (f"{selected_case}_quote.csv", ["csv"]),
                    "Contract": (f"{selected_case}_contract.pdf", ["pdf"]),
                    "Security questionnaire": (f"{selected_case}_security_questionnaire.md", ["md", "txt"]),
                    "Vendor email": (f"{selected_case}_vendor_email.txt", ["txt", "md"]),
                }
                _uploaded: dict[str, object] = {}
                for _label, (_fname, _exts) in _doc_types.items():
                    _existing = "✓ exists" if (_CASE_DIR / _fname).exists() else "missing"
                    _uf = st.file_uploader(
                        f"{_label} ({_existing})",
                        type=_exts,
                        key=f"nv_upload_{selected_case}_{_label}",
                    )
                    if _uf:
                        _uploaded[_fname] = _uf

                nv_c1, nv_c2, _ = st.columns([1, 1, 4])
                _do_analyze = nv_c1.button(
                    "▶ Save & Analyse",
                    type="primary",
                    use_container_width=True,
                    key=f"nv_run_{selected_case}",
                    disabled=not can_run,
                )
                if nv_c2.button("✕ Cancel", key=f"nv_cancel_{selected_case}", use_container_width=True):
                    st.session_state[_nv_key] = False
                    st.rerun()

                if _do_analyze:
                    for _fname, _uf in _uploaded.items():
                        (_CASE_DIR / _fname).write_bytes(_uf.read())
                    if _uploaded:
                        st.success(f"Saved {len(_uploaded)} file(s). Running analysis…")
                    st.session_state[_nv_key] = False
                    run_analysis(selected_case)

        entry = get_selected_entry(selected_case)
        result = entry["result"]
        v_num = entry["v"]

        triage = result.get("triage_output") or {}
        pre_screen = result.get("pre_screen") or {}
        reflection = result.get("reflection")
        tool_calls = result.get("tool_calls", [])

        risk_raw = triage.get("risk_tier", "?").upper()
        rec_raw = triage.get("recommendation", "?")
        blocking = triage.get("blocking_issues") or []

        prev_entry = versions[_selected_idx(selected_case) - 1] if _selected_idx(selected_case) > 0 else None
        prev_triage = (prev_entry["result"].get("triage_output") or {}) if prev_entry else None

        def _delta(curr_val, prev_val):
            if prev_val is None:
                return None
            diff = curr_val - prev_val
            if diff == 0:
                return None
            return f"+{diff}" if diff > 0 else str(diff)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Risk Level", f"{RISK_COLOR.get(risk_raw, '⚪')} {risk_raw}")
        m2.metric(
            "Blocking Issues", len(blocking),
            delta=_delta(len(blocking), len(prev_triage.get("blocking_issues") or []) if prev_triage else None),
            delta_color="inverse",
        )
        m3.metric(
            "Missing Docs", len(triage.get("missing_documents") or []),
            delta=_delta(len(triage.get("missing_documents") or []),
                         len(prev_triage.get("missing_documents") or []) if prev_triage else None),
            delta_color="inverse",
        )
        m4.metric("ACV", f"${meta['acv']:,}")

        _ai_rec_col, _dl_col = st.columns([5, 1])
        _ai_rec_col.markdown(f"**AI Recommendation:** {REC_LABELS.get(rec_raw, rec_raw)}")
        # Unified export — built lazily so it's always up-to-date with reviewer decisions
        _dl_col.download_button(
            "⬇ Export CSV",
            data=_full_export_csv(
                triage, {**meta, "case_id": selected_case}, v_num,
                triage.get("case_facts") or {},
                _build_excerpts(result.get("tool_calls", [])),
                {c["check_id"]: c for c in (triage.get("policy_checklist") or [])},
                st.session_state.rule_decisions.get(selected_case, {}).get(str(v_num), {}),
            ),
            file_name=f"{selected_case}_v{v_num}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
            key=f"exp_full_{selected_case}_{v_num}",
            help="Download full analysis report (metadata + extracted facts + all 34 rules)",
        )

        if blocking:
            st.error(f"⛔ {len(blocking)} Blocking Issue(s) — resolve before proceeding")

        if prev_entry:
            prev_risk = (prev_entry["result"].get("triage_output") or {}).get("risk_tier", "").upper()
            prev_rec = (prev_entry["result"].get("triage_output") or {}).get("recommendation", "")
            changes = []
            if prev_risk and prev_risk != risk_raw:
                changes.append(f"Risk: {prev_risk} → {risk_raw}")
            if prev_rec and prev_rec != rec_raw:
                changes.append(f"Recommendation: {REC_LABELS.get(prev_rec, prev_rec)} → {REC_LABELS.get(rec_raw, rec_raw)}")
            b_prev = len((prev_entry["result"].get("triage_output") or {}).get("blocking_issues") or [])
            b_curr = len(blocking)
            if b_curr != b_prev:
                changes.append(f"Blocking issues: {b_prev} → {b_curr}")
            if changes:
                st.info(f"**Changes from v{prev_entry['v']}:** " + "  ·  ".join(changes))
            else:
                st.info(f"No significant changes from v{prev_entry['v']}.")

        st.divider()

        case_facts = triage.get("case_facts") or {}
        policy_checklist = triage.get("policy_checklist") or []
        checklist_by_id = {c["check_id"]: c for c in policy_checklist}
        excerpts = _build_excerpts(tool_calls)

        def _tab_sort_key(cat):
            """Stable sort: most blocking triggered first, then most warnings, then CATEGORIES order."""
            check_ids = DOMAIN_CHECKLIST_IDS.get(cat, [])
            n_block = sum(
                1 for c in check_ids
                if checklist_by_id.get(c, {}).get("result") == "triggered"
                and checklist_by_id.get(c, {}).get("flag_severity") == "blocking"
            )
            n_warn = sum(
                1 for c in check_ids
                if checklist_by_id.get(c, {}).get("result") == "triggered"
                and checklist_by_id.get(c, {}).get("flag_severity") == "warning"
            )
            return (-n_block, -n_warn, CATEGORIES.index(cat) if cat in CATEGORIES else 99)

        def _status_emoji(cat):
            check_ids = DOMAIN_CHECKLIST_IDS.get(cat, [])
            has_blocking = any(
                checklist_by_id.get(c, {}).get("result") == "triggered"
                and checklist_by_id.get(c, {}).get("flag_severity") == "blocking"
                for c in check_ids
            )
            has_warning = any(
                checklist_by_id.get(c, {}).get("result") == "triggered"
                and checklist_by_id.get(c, {}).get("flag_severity") == "warning"
                for c in check_ids
            )
            if has_blocking:
                return "🔴"
            if has_warning:
                return "⚠️"
            if checklist_by_id:
                return "✅"
            return ""

        sorted_cats = sorted(CATEGORIES, key=_tab_sort_key)
        tab_labels = [f"{cat}  {_status_emoji(cat)}" for cat in sorted_cats]
        tabs = st.tabs(tab_labels)

        for tab, cat in zip(tabs, sorted_cats):
            with tab:
                cat_status = get_category_status(selected_case, cat)

                # ── Extracted Facts ───────────────────────────────────────
                facts_fields = DOMAIN_FACTS_FIELDS.get(cat, [])
                if facts_fields:
                    with st.expander("📋 Extracted Facts", expanded=True):
                        _render_facts_table(
                            facts_fields, case_facts, excerpts,
                            cat, selected_case, v_num,
                        )

                # ── Rule Checklist (individual cards) ─────────────────────
                check_ids = DOMAIN_CHECKLIST_IDS.get(cat, [])
                if check_ids and checklist_by_id:
                    # Sort: blocking triggered → warning triggered → info → clear
                    def _rule_sort(cid):
                        c = checklist_by_id.get(cid)
                        if not c or c["result"] != "triggered":
                            return 4
                        return {"blocking": 0, "warning": 1, "info": 2}.get(c.get("flag_severity", ""), 3)

                    sorted_ids = sorted(check_ids, key=_rule_sort)
                    n_triggered = sum(
                        1 for cid in check_ids
                        if checklist_by_id.get(cid, {}).get("result") == "triggered"
                    )
                    n_blocking = sum(
                        1 for cid in check_ids
                        if checklist_by_id.get(cid, {}).get("flag_severity") == "blocking"
                        and checklist_by_id.get(cid, {}).get("result") == "triggered"
                    )
                    n_warn = sum(
                        1 for cid in check_ids
                        if checklist_by_id.get(cid, {}).get("flag_severity") == "warning"
                        and checklist_by_id.get(cid, {}).get("result") == "triggered"
                    )
                    st.caption(
                        f"{len(check_ids)} checks · {n_triggered} triggered "
                        f"({n_blocking} blocking, {n_warn} warnings)"
                    )

                    for cid in sorted_ids:
                        c = checklist_by_id.get(cid)
                        pr = POLICY_RULES.get(cid, {})
                        if not c:
                            continue
                        is_triggered = c["result"] == "triggered"
                        sev = c.get("flag_severity", "") if is_triggered else ""
                        reason = _brief_reason(c, case_facts)
                        action = c.get("action_required", "") if is_triggered else ""
                        if is_triggered and cid == "PRO-005" and case_facts:
                            missing = case_facts.get("missing_documents") or []
                            if missing:
                                action = "Request from vendor: " + ", ".join(missing)
                        rule_name = pr.get("rule", c["description"])
                        owner = pr.get("owner", "")

                        if is_triggered:
                            if sev == "blocking":
                                icon = "🔴"
                                badge_bg, badge_fg, badge_text = "#fee2e2", "#dc2626", "BLOCKING"
                            elif sev == "warning":
                                icon = "⚠️"
                                badge_bg, badge_fg, badge_text = "#fef9c3", "#a16207", "WARNING"
                            else:
                                icon = "ℹ️"
                                badge_bg, badge_fg, badge_text = "#dbeafe", "#1d4ed8", "INFO"
                        else:
                            icon = "✅"
                            badge_bg, badge_fg, badge_text = "#dcfce7", "#15803d", "PASS"

                        rd_case = st.session_state.rule_decisions.setdefault(selected_case, {})
                        rd_ver = rd_case.setdefault(str(v_num), {})
                        rd = rd_ver.get(cid)
                        # include cat so rules shared across tabs (e.g. PRO-002 in Procurement + Vendor Risk) get unique keys
                        _k = f"{selected_case}_{v_num}_{cat}_{cid}"
                        edit_key = f"rule_edit_{_k}"
                        if edit_key not in st.session_state:
                            st.session_state[edit_key] = False

                        with st.container(border=True):
                            h_left, h_right = st.columns([6, 1])
                            with h_left:
                                st.markdown(
                                    f"<span style='font-family:monospace;background:#4f46e5;color:#fff;"
                                    f"padding:1px 6px;border-radius:3px;font-size:0.78rem;font-weight:600'>"
                                    f"{cid}</span>&nbsp; {icon} **{rule_name}**",
                                    unsafe_allow_html=True,
                                )
                            with h_right:
                                st.markdown(
                                    f"<div style='text-align:right;padding-top:4px'>"
                                    f"<span style='background:{badge_bg};color:{badge_fg};"
                                    f"font-size:0.72rem;font-weight:600;padding:2px 8px;"
                                    f"border-radius:4px'>{badge_text}</span></div>",
                                    unsafe_allow_html=True,
                                )

                            if is_triggered:
                                eff_assignee = rd["assignee"] if rd else owner
                                eff_action = rd["action"] if rd else action
                                st.markdown(
                                    f"<div style='display:flex;gap:8px;align-items:center;margin:6px 0 2px 0;'>"
                                    f"<span style='color:#9ca3af;font-size:0.73rem;font-weight:600;"
                                    f"text-transform:uppercase;letter-spacing:0.05em;flex-shrink:0;'>Who</span>"
                                    f"<span style='background:#312e81;color:#c7d2fe;padding:2px 10px;"
                                    f"border-radius:20px;font-size:0.82rem;font-weight:600'>{eff_assignee}</span>"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )
                                st.markdown(
                                    f"<div style='display:flex;gap:8px;align-items:flex-start;margin:2px 0 4px 0;'>"
                                    f"<span style='color:#9ca3af;font-size:0.73rem;font-weight:600;"
                                    f"text-transform:uppercase;letter-spacing:0.05em;flex-shrink:0;padding-top:2px;'>What</span>"
                                    f"<span style='font-size:0.88rem;color:#f3f4f6;'>{eff_action}</span>"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )
                                st.markdown(
                                    f"<span style='font-size:0.82rem;color:#6b7280'>{reason}</span>",
                                    unsafe_allow_html=True,
                                )
                                if pr.get("detail"):
                                    st.markdown(
                                        f"<span style='font-size:0.78rem;color:#4b5563;font-style:italic'>"
                                        f"{pr['detail']}</span>",
                                        unsafe_allow_html=True,
                                    )
                                if rd and rd.get("note"):
                                    st.markdown(
                                        f"<span style='font-size:0.8rem;color:#818cf8;font-style:italic'>"
                                        f"Note: {rd['note']}</span>",
                                        unsafe_allow_html=True,
                                    )

                                if rd and not st.session_state[edit_key]:
                                    _rd_status = rd["status"]
                                    if _rd_status == "accepted":
                                        status_color, status_label = "#15803d", "✓ Accepted"
                                    elif _rd_status == "overridden_pass":
                                        status_color, status_label = "#0369a1", "✓ Overridden: marked as passed"
                                    else:
                                        status_color, status_label = "#818cf8", "✎ Modified"
                                    rc1, rc2, _ = st.columns([3, 1, 4])
                                    rc1.markdown(
                                        f"<span style='font-size:0.82rem;color:{status_color};font-weight:600'>"
                                        f"{status_label}</span>",
                                        unsafe_allow_html=True,
                                    )
                                    if rc2.button("↩", key=f"rule_reset_{_k}", help="Reset decision"):
                                        rd_ver.pop(cid, None)
                                        _save_results()
                                        st.rerun()
                                elif not st.session_state[edit_key]:
                                    ab1, ab2, _ = st.columns([1, 1, 4])
                                    if ab1.button("✓ Accept", key=f"rule_accept_{_k}",
                                                  type="primary", use_container_width=True):
                                        rd_ver[cid] = {"status": "accepted", "assignee": owner,
                                                       "action": action, "note": ""}
                                        _save_results()
                                        st.rerun()
                                    if ab2.button("✎ Modify", key=f"rule_modify_{_k}",
                                                  use_container_width=True):
                                        st.session_state[edit_key] = True
                                        st.rerun()

                                if st.session_state[edit_key]:
                                    mtype_key = f"rule_mtype_{_k}"
                                    if mtype_key not in st.session_state:
                                        st.session_state[mtype_key] = "Adjust assignment / action"
                                    st.radio(
                                        "Modification type",
                                        ["Adjust assignment / action", "Override: mark as passed"],
                                        key=mtype_key,
                                        horizontal=True,
                                    )
                                    mtype = st.session_state[mtype_key]
                                    if mtype == "Adjust assignment / action":
                                        with st.form(key=f"rule_form_{_k}"):
                                            new_assignee = st.text_input(
                                                "Assign to", value=rd["assignee"] if rd else owner)
                                            new_action = st.text_input(
                                                "Action required", value=rd["action"] if rd else action)
                                            new_note = st.text_input(
                                                "Note (optional)", value=rd.get("note", "") if rd else "")
                                            sf1, sf2, _ = st.columns([1, 1, 4])
                                            saved = sf1.form_submit_button("💾 Save", type="primary",
                                                                            use_container_width=True)
                                            cancelled = sf2.form_submit_button("✕ Cancel",
                                                                                use_container_width=True)
                                        if saved:
                                            rd_ver[cid] = {
                                                "status": "modified",
                                                "assignee": new_assignee or owner,
                                                "action": new_action or action,
                                                "note": new_note,
                                            }
                                            st.session_state[edit_key] = False
                                            _save_results()
                                            st.rerun()
                                        if cancelled:
                                            st.session_state[edit_key] = False
                                            st.rerun()
                                    else:  # Override to pass
                                        with st.form(key=f"rule_form_ovrd_{_k}"):
                                            new_note = st.text_input(
                                                "Reason for override (required)",
                                                value=rd.get("note", "") if rd else "",
                                                placeholder="Explain why this check can be waived…")
                                            sf1, sf2, _ = st.columns([1, 1, 4])
                                            saved = sf1.form_submit_button("💾 Save", type="primary",
                                                                            use_container_width=True)
                                            cancelled = sf2.form_submit_button("✕ Cancel",
                                                                                use_container_width=True)
                                        if saved:
                                            rd_ver[cid] = {
                                                "status": "overridden_pass",
                                                "assignee": "",
                                                "action": "Override: mark as passed",
                                                "note": new_note,
                                            }
                                            st.session_state[edit_key] = False
                                            _save_results()
                                            st.rerun()
                                        if cancelled:
                                            st.session_state[edit_key] = False
                                            st.rerun()

                            else:  # Pass rule
                                st.markdown(
                                    f"<span style='font-size:0.88rem;color:#6b7280'>{reason}</span>",
                                    unsafe_allow_html=True,
                                )
                                if rd:
                                    pc1, pc2, _ = st.columns([2, 1, 5])
                                    pc1.markdown(
                                        "<span style='font-size:0.82rem;color:#818cf8;font-weight:600'>"
                                        "⚠ Overridden</span>",
                                        unsafe_allow_html=True,
                                    )
                                    if pc2.button("↩", key=f"rule_reset_pass_{_k}",
                                                  help="Reset override"):
                                        rd_ver.pop(cid, None)
                                        _save_results()
                                        st.rerun()
                                elif not st.session_state[edit_key]:
                                    _, override_col = st.columns([7, 3])
                                    if override_col.button("✎ Override this check",
                                                           key=f"rule_override_pass_{_k}",
                                                           use_container_width=True):
                                        st.session_state[edit_key] = True
                                        st.rerun()

                                if st.session_state[edit_key]:
                                    with st.form(key=f"rule_form_{_k}"):
                                        new_sev = st.radio(
                                            "Flag as",
                                            options=["⚠ Escalation Required", "🔴 Blocking"],
                                            horizontal=True,
                                            key=f"rule_pass_sev_{_k}",
                                        )
                                        new_note = st.text_input(
                                            "Reason for override (required)", value="",
                                            placeholder="Explain why this passing check should be flagged…")
                                        sf1, sf2, _ = st.columns([1, 1, 4])
                                        saved = sf1.form_submit_button("💾 Save", type="primary",
                                                                        use_container_width=True)
                                        cancelled = sf2.form_submit_button("✕ Cancel",
                                                                            use_container_width=True)
                                    if saved:
                                        _sev = "blocking" if new_sev and "Blocking" in new_sev else "warning"
                                        _action_label = "Override: flagged as blocking" if _sev == "blocking" else "Override: flagged for escalation"
                                        rd_ver[cid] = {
                                            "status": "overridden_fail",
                                            "override_severity": _sev,
                                            "assignee": owner,
                                            "action": _action_label,
                                            "note": new_note,
                                        }
                                        st.session_state[edit_key] = False
                                        _save_results()
                                        st.rerun()
                                    if cancelled:
                                        st.session_state[edit_key] = False
                                        st.rerun()

                elif check_ids and not checklist_by_id:
                    # Legacy fallback — no checklist data, show old policy flags
                    all_flags = triage.get("policy_flags") or []
                    keywords = CATEGORY_POLICY_MAP.get(cat, [cat])
                    cat_flags = [
                        f for f in all_flags
                        if any(
                            k.lower() in f.get("policy", "").lower()
                            or k.lower() in f.get("issue", "").lower()
                            for k in keywords
                        )
                    ]
                    cat_blocking_issues = [
                        b for b in blocking if any(k.lower() in b.lower() for k in keywords)
                    ]
                    for b in cat_blocking_issues:
                        st.error(f"🔴 {b}")
                    for flag in cat_flags:
                        sev = flag.get("severity", "info")
                        icon = {"blocking": "🔴", "warning": "⚠️", "info": "ℹ️"}.get(sev, "ℹ️")
                        st.warning(f"{icon} [{flag.get('policy','')}] {flag.get('issue','')}")
                    if not cat_blocking_issues and not cat_flags:
                        st.success("No issues detected for this category.")

        # ── Action Summary ────────────────────────────────────────────────
        st.divider()
        st.markdown(
            f"### Action Summary "
            f"<span style='color:#9ca3af;font-size:0.85rem'>— v{v_num}</span>",
            unsafe_allow_html=True,
        )

        all_triggered_ids = [
            cid for cat in CATEGORIES
            for cid in DOMAIN_CHECKLIST_IDS.get(cat, [])
            if checklist_by_id.get(cid, {}).get("result") == "triggered"
        ]
        # deduplicate while preserving order (Vendor Risk shares IDs with other domains)
        seen_t: set = set()
        unique_triggered = [c for c in all_triggered_ids if not (c in seen_t or seen_t.add(c))]

        rd_ver_all = st.session_state.rule_decisions.get(selected_case, {}).get(str(v_num), {})
        n_triggered_total = len(unique_triggered)
        n_decided_total = sum(1 for c in unique_triggered if c in rd_ver_all)
        final_for_v = st.session_state.decisions.get(selected_case, {}).get(v_num)

        if final_for_v:
            outcome = final_for_v.get("overall", "approved")
            _outcome_display = {
                "blocked": ("🔴 Blocked", "Vendor blocked — onboarding halted."),
                "escalated": ("🟡 Escalated", "Vendor escalated for senior review."),
                "approved": ("✅ Onboarded", "Vendor successfully onboarded."),
            }.get(outcome, ("✅ Onboarded", "Vendor successfully onboarded."))
            overall_label, outcome_msg = _outcome_display
            st.success(f"**{overall_label}** — {outcome_msg}")
            st.caption(f"Submitted at {final_for_v.get('timestamp', '')}")
            if st.button("↩ Reset Final Decision", key=f"reset_final_{selected_case}_{v_num}"):
                st.session_state.decisions.setdefault(selected_case, {}).pop(v_num, None)
                _save_results()
                st.rerun()
        else:
            if n_triggered_total == 0:
                st.success("No rules triggered — no follow-up actions required.")
            else:
                pending_ids = [c for c in unique_triggered if c not in rd_ver_all]
                if pending_ids:
                    st.info(
                        f"{n_decided_total} / {n_triggered_total} triggered rules reviewed. "
                        f"Pending: {', '.join(pending_ids)}"
                    )
                    st.progress(n_decided_total / n_triggered_total)
                else:
                    st.caption(f"All {n_triggered_total} triggered rules reviewed.")

            # Group accepted/modified decisions by owner
            # overridden_pass = reviewer waived a triggered rule → no follow-up needed
            # overridden_fail = reviewer flagged a passing rule → include in summary
            owner_actions: dict[str, list] = {}
            for cid in unique_triggered:
                rd = rd_ver_all.get(cid)
                if rd and rd["status"] != "overridden_pass":
                    assignee = rd["assignee"]
                    pr_r = POLICY_RULES.get(cid, {})
                    chk = checklist_by_id.get(cid, {})
                    owner_actions.setdefault(assignee, []).append({
                        "check_id": cid,
                        "rule": pr_r.get("rule", cid),
                        "action": rd["action"],
                        "note": rd.get("note", ""),
                        "status": rd["status"],
                        "flag_reason": chk.get("flag_reason", ""),
                        "detail": pr_r.get("detail", ""),
                        "policy_ref": pr_r.get("policy_ref", ""),
                    })
            # Include pass rules that were manually flagged by reviewer
            all_pass_ids = [
                cid for cat in CATEGORIES
                for cid in DOMAIN_CHECKLIST_IDS.get(cat, [])
                if checklist_by_id.get(cid, {}).get("result") != "triggered"
            ]
            seen_p: set = set()
            for cid in all_pass_ids:
                if cid in seen_p:
                    continue
                seen_p.add(cid)
                rd = rd_ver_all.get(cid)
                if rd and rd["status"] == "overridden_fail":
                    assignee = rd["assignee"]
                    pr_r = POLICY_RULES.get(cid, {})
                    owner_actions.setdefault(assignee, []).append({
                        "check_id": cid,
                        "rule": pr_r.get("rule", cid),
                        "action": rd["action"],
                        "note": rd.get("note", ""),
                        "status": rd["status"],
                        "flag_reason": "",
                        "detail": pr_r.get("detail", ""),
                        "policy_ref": pr_r.get("policy_ref", ""),
                    })

            for assignee, items in owner_actions.items():
                with st.container(border=True):
                    st.markdown(
                        f"**📬 {assignee}** "
                        f"<span style='color:#9ca3af;font-size:0.82rem'>"
                        f"— {len(items)} action{'s' if len(items) > 1 else ''}</span>",
                        unsafe_allow_html=True,
                    )
                    def _item_html(item):
                        if item["status"] == "overridden_fail":
                            _sev = item.get("override_severity", "warning")
                            _sev_color = "#ef4444" if _sev == "blocking" else "#d97706"
                            _sev_label = "override: blocking" if _sev == "blocking" else "override: escalation"
                            _of_tag = f"<span style='font-size:0.73rem;color:{_sev_color}'>({_sev_label})</span>"
                        else:
                            _of_tag = None
                        _status_tags = {
                            "modified": "<span style='font-size:0.73rem;color:#6366f1'>(modified)</span>",
                            "overridden_fail": _of_tag,
                        }
                        mod_tag = ("&nbsp;" + _status_tags[item["status"]]) if item["status"] in _status_tags else ""
                        note_tag = (f"<br><span style='font-size:0.78rem;color:#6b7280;"
                                    f"font-style:italic'>Note: {item['note']}</span>"
                                    ) if item.get("note") else ""
                        return (
                            f"<div style='border-left:3px solid #4f46e5;padding:4px 10px;margin:4px 0;'>"
                            f"<span style='font-family:monospace;font-size:0.75rem;color:#818cf8'>"
                            f"{item['check_id']}</span>{mod_tag}"
                            f"<br><span style='font-size:0.87rem;color:#f3f4f6'>"
                            f"{item['action']}</span>{note_tag}</div>"
                        )
                    st.markdown("".join(_item_html(i) for i in items), unsafe_allow_html=True)

                    _ekey = f"email_{selected_case}_{v_num}_{assignee}"
                    _eedit = f"email_edit_{_ekey}"
                    _esent = f"email_sent_{_ekey}"
                    if _ekey in st.session_state:
                        draft = st.session_state[_ekey]
                        if draft.get("error"):
                            st.error(f"Error drafting email: {draft['error']}")
                            if st.button("↩ Retry", key=f"email_retry_{_ekey}"):
                                del st.session_state[_ekey]
                                st.rerun()
                        else:
                            st.markdown(
                                "<div style='background:#451a03;border-left:3px solid #d97706;"
                                "padding:6px 12px;border-radius:4px;margin:6px 0;"
                                "font-size:0.8rem;color:#fbbf24'>"
                                "⚠ DRAFT — Requires approval before sending</div>",
                                unsafe_allow_html=True,
                            )
                            if st.session_state.get(_eedit):
                                # Edit mode
                                new_to = st.text_input("To", value=draft["to"],
                                                        key=f"email_to_{_ekey}")
                                new_subj = st.text_input("Subject", value=draft["subject"],
                                                          key=f"email_subj_{_ekey}")
                                new_body = st.text_area("Body", value=draft["body"],
                                                         height=220, key=f"email_body_{_ekey}")
                                ec1, ec2, _ = st.columns([1, 1, 4])
                                if ec1.button("💾 Save", key=f"email_save_{_ekey}", type="primary",
                                              use_container_width=True):
                                    st.session_state[_ekey] = {
                                        "to": new_to, "subject": new_subj, "body": new_body}
                                    st.session_state[_eedit] = False
                                    st.rerun()
                                if ec2.button("✕ Cancel", key=f"email_cancel_{_ekey}",
                                              use_container_width=True):
                                    st.session_state[_eedit] = False
                                    st.rerun()
                            else:
                                # Read-only view
                                st.markdown(
                                    f"<div style='margin:6px 0'>"
                                    f"<span style='font-size:0.75rem;color:#9ca3af;text-transform:uppercase;"
                                    f"letter-spacing:0.05em'>To</span><br>"
                                    f"<span style='font-size:0.9rem'>{_html.escape(draft['to'])}</span>"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )
                                st.markdown(
                                    f"<div style='margin:6px 0'>"
                                    f"<span style='font-size:0.75rem;color:#9ca3af;text-transform:uppercase;"
                                    f"letter-spacing:0.05em'>Subject</span><br>"
                                    f"<span style='font-size:0.9rem;font-weight:600'>"
                                    f"{_html.escape(draft['subject'])}</span>"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )
                                st.markdown(
                                    "<span style='font-size:0.75rem;color:#9ca3af;"
                                    "text-transform:uppercase;letter-spacing:0.05em'>Body</span>",
                                    unsafe_allow_html=True,
                                )
                                st.markdown(
                                    f"<div style='background:#1f2937;border-radius:6px;"
                                    f"padding:12px 16px;font-size:0.88rem;line-height:1.6;"
                                    f"white-space:pre-wrap;color:#e5e7eb'>"
                                    f"{_html.escape(draft['body'])}</div>",
                                    unsafe_allow_html=True,
                                )
                                ev1, ev2, ev3, _ = st.columns([1, 1, 1, 3])
                                if ev1.button("✎ Edit", key=f"email_edit_btn_{_ekey}",
                                              use_container_width=True):
                                    st.session_state[_eedit] = True
                                    st.rerun()
                                if ev2.button("✉ Send", key=f"email_send_{_ekey}",
                                              type="primary", use_container_width=True):
                                    st.session_state[_esent] = True
                                    st.rerun()
                                if ev3.button("↩ Regenerate", key=f"email_regen_{_ekey}",
                                              use_container_width=True):
                                    del st.session_state[_ekey]
                                    st.session_state.pop(_esent, None)
                                    st.rerun()
                                if st.session_state.get(_esent):
                                    st.success(
                                        "Marked as sent. Ensure this email has been approved "
                                        "before external delivery — contact christin@accelerant.com "
                                        "if unsure."
                                    )
                    else:
                        if st.button(f"✉ Draft email to {assignee}",
                                     key=f"email_draft_{_ekey}"):
                            vendor_name = (triage.get("case_facts") or {}).get(
                                "vendor_name") or selected_case
                            summary = triage.get("summary", "")
                            with st.spinner("Drafting email…"):
                                st.session_state[_ekey] = _draft_email(
                                    vendor_name, assignee, items, summary
                                )
                            st.rerun()

            # Final Submit
            if not final_for_v and owner_actions:
                st.divider()
                has_blocking = any(
                    checklist_by_id.get(c, {}).get("flag_severity") == "blocking"
                    for c in unique_triggered
                )
                has_warning = any(
                    checklist_by_id.get(c, {}).get("flag_severity") == "warning"
                    for c in unique_triggered
                )
                if has_blocking:
                    overall = "blocked"
                    overall_label = "🔴 Blocked"
                    btn_label = "🔴 Block Vendor & Close Review"
                elif has_warning:
                    overall = "escalated"
                    overall_label = "🟡 Escalated"
                    btn_label = "🟡 Escalate for Senior Review"
                else:
                    overall = "approved"
                    overall_label = "✅ Clear to Onboard"
                    btn_label = "✅ Complete Vendor Onboarding"

                st.markdown(f"**Proposed outcome: {overall_label}**")
                if st.button(btn_label, type="primary",
                             key=f"submit_{selected_case}_{v_num}"):
                    now = datetime.now()
                    write_audit_log({
                        "case_id": selected_case,
                        "vendor": meta["vendor"],
                        "version": v_num,
                        "overall": overall,
                        "rule_decisions": rd_ver_all,
                        "timestamp": now.isoformat(),
                        "ai_recommendation": rec_raw,
                        "risk_tier": risk_raw,
                    })
                    _record_final_decision(selected_case, v_num, {
                        "overall": overall,
                        "timestamp": now.strftime("%H:%M %b %d"),
                    })
                    go_overview()
                    st.rerun()
