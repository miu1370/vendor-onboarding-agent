"""
Pre-defined mock triage results for all 3 cases.
Used when ANTHROPIC_API_KEY is unavailable or Mock Mode is enabled.
Mirrors the exact structure returned by run_vendor_agent().
"""

MOCK_RESULTS = {
    "case_001": {
        "pre_screen": {
            "screen_result": "block",
            "block_reasons": [
                "SOC 2 Type II not provided — required for SaaS vendors with ACV > $25,000",
                "Data Processing Agreement not provided despite declared data access",
            ],
            "escalate_reasons": [
                "ACV $85,000 exceeds $50,000 — requires Procurement Manager + VP Finance",
                "Payment terms Net 60 require VP Finance review (≥ Net 60)",
                "PII data processing declared: 'Customer names and emails'",
                "AI functionality with potential data-training use — requires Legal + Executive review",
                "Contract term 24 months requires Legal review",
            ],
        },
        "triage_output": {
            "summary": (
                "Northstar Analytics is a high-risk SaaS AI analytics vendor requesting a 24-month "
                "contract at $85,000 ACV. Two blocking issues prevent proceeding: SOC 2 Type II is missing "
                "(required for SaaS > $25K) and a Data Processing Agreement has not been provided despite "
                "declared access to customer names and emails (restricted PII). Additionally, the intake form "
                "marks this as a new_vendor but Northstar Analytics already exists as active in the vendor "
                "register — this must be resolved before routing. The contract contains ambiguous AI/model "
                "training language and an EU subprocessor (Clearbit) that requires GDPR review."
            ),
            "risk_tier": "high",
            "recommendation": "blocked",
            "missing_documents": [
                "SOC 2 Type II report",
                "Data Processing Agreement (DPA)",
            ],
            "blocking_issues": [
                "SOC 2 Type II not provided — required for SaaS vendors with ACV > $25,000 (Security policy §3.1)",
                "Data Processing Agreement missing — required when vendor accesses personal data (Legal policy §2.4)",
            ],
            "consistency_issues": [
                "Intake marked 'new_vendor' but Northstar Analytics, Inc. already exists as active in "
                "the vendor register (ID: V-0041). Confirm whether this is a duplicate request or a new "
                "legal entity before proceeding.",
            ],
            "contract_legal_flags": [
                "Ambiguous data-use language detected ('improve, and enhance the services and related models') "
                "— Legal and Security must confirm this does not permit model training on company data",
                "EU subprocessor Clearbit detected — GDPR Data Transfer Impact Assessment required",
            ],
            "policy_flags": [
                {
                    "policy": "Finance Approval Matrix",
                    "issue": "ACV $85,000 exceeds $50,000 threshold — VP Finance sign-off required in addition to Procurement Manager",
                    "severity": "warning",
                },
                {
                    "policy": "Finance Approval Matrix",
                    "issue": "Payment terms Net 60 — VP Finance review required per payment policy",
                    "severity": "warning",
                },
                {
                    "policy": "Legal Review Policy",
                    "issue": "Contract term 24 months exceeds 12-month threshold — Legal review mandatory",
                    "severity": "warning",
                },
                {
                    "policy": "Legal Review Policy",
                    "issue": "Ambiguous AI/model-training language in contract — Legal must confirm scope before signing",
                    "severity": "blocking",
                },
                {
                    "policy": "Security Review Policy",
                    "issue": "EU subprocessor (Clearbit) — GDPR transfer mechanism must be confirmed with Legal",
                    "severity": "warning",
                },
                {
                    "policy": "Data Handling Policy",
                    "issue": "Customer names and emails classified as RESTRICTED — heightened controls required",
                    "severity": "warning",
                },
                {
                    "policy": "Procurement Policy",
                    "issue": "Vendor appears to already exist in register as active — potential duplicate onboarding",
                    "severity": "blocking",
                },
            ],
            "required_approvals": [
                "Business Owner",
                "Procurement Manager",
                "VP Finance",
                "Executive Sponsor",
            ],
            "required_reviews": [
                "Finance / FP&A",
                "Legal",
                "Security",
            ],
            "draft_vendor_followup": (
                "Subject: Missing Documents Required — Northstar Analytics Onboarding (Case 001)\n\n"
                "Dear Northstar Analytics Team,\n\n"
                "Thank you for submitting your vendor onboarding package. Before we can proceed with evaluation, "
                "we require the following documents:\n\n"
                "1. SOC 2 Type II Report — Please provide your most recent SOC 2 Type II audit report "
                "(issued within the last 12 months).\n\n"
                "2. Data Processing Agreement (DPA) — As your services involve access to customer personal "
                "data, a signed DPA is required prior to contract execution.\n\n"
                "Additionally, please clarify the data-use language in Section 8.3 of the MSA regarding "
                "'improving and enhancing services and related models' — specifically whether customer or "
                "employee data is used for AI model training, and whether an opt-out mechanism is available.\n\n"
                "Please respond within 5 business days.\n\n"
                "Best regards,\nProcurement Team"
            ),
            "draft_internal_ticket": (
                "PROCUREMENT TRIAGE — Case 001: Northstar Analytics\n"
                "Status: BLOCKED — Missing critical compliance documents\n\n"
                "Action Required:\n"
                "- Request SOC 2 Type II and DPA from vendor (draft email ready)\n"
                "- Resolve new_vendor vs. existing register conflict (V-0041)\n"
                "- Legal to review AI training clause in MSA §8.3\n"
                "- Security to assess EU subprocessor (Clearbit) GDPR compliance\n\n"
                "Do not route for approval until blocking issues resolved."
            ),
        },
        "tool_calls": [
            {"tool": "lookup_budget", "input": {"cost_center": "CC-1042"}, "output": {"found": True, "cost_center": "CC-1042", "department": "Sales", "annual_budget_remaining": 120000.0, "budget_owner": "Sarah Chen"}},
            {"tool": "check_existing_vendor", "input": {"vendor_name": "Northstar Analytics"}, "output": {"found": True, "match_type": "exact", "vendor_id": "V-0041", "status": "active", "category": "SaaS", "owner": "IT", "flag_for_review": True}},
            {"tool": "calculate_total_contract_value", "input": {"annual_contract_value": 85000, "contract_term_months": 24, "one_time_fees": 12000}, "output": {"annual_contract_value": 85000, "contract_term_months": 24, "one_time_fees": 12000, "total_contract_value": 182000.0}},
            {"tool": "classify_data_sensitivity", "input": {"data_types": ["Customer names and emails", "CRM opportunity data", "Sales activity logs"]}, "output": {"sensitivity_level": "restricted", "restricted_fields": ["Customer names and emails"], "confidential_fields": ["CRM opportunity data", "Sales activity logs"], "security_review_required": True, "legal_review_required": True}},
            {"tool": "extract_contract_clauses", "input": {}, "output": {"ai_model_training": {"found": True, "excerpt": "...improve, and enhance the services and related models...", "flags": ["Ambiguous data-use language detected — Legal must confirm scope"]}, "auto_renewal": {"found": True, "excerpt": "...automatically renews for successive one-year terms..."}, "limitation_of_liability": {"found": True, "excerpt": "...aggregate liability shall not exceed fees paid in the prior 6 months..."}, "governing_law": {"found": True, "excerpt": "...governed by the laws of Delaware..."}, "data_processing_agreement_ref": {"found": False, "excerpt": None}, "subprocessor_regions_detected": ["European Union"], "all_legal_flags": ["Ambiguous data-use language — Legal review required"]}},
            {"tool": "validate_cross_document_consistency", "input": {"intake_acv": 85000, "intake_renewal_status": "new_vendor", "intake_subprocessors": ["Clearbit"], "quote_annual_total": 85000, "vendor_found_in_register": True, "vendor_register_status": "active", "questionnaire_subprocessors": ["Clearbit", "ModelOps Labs"]}, "output": {"issues_found": 2, "is_consistent": False, "issues": [{"type": "new_vendor_conflict", "severity": "blocking", "description": "Intake marked 'new_vendor' but Northstar Analytics already exists in register (active)"}, {"type": "subprocessor_undeclared_in_intake", "severity": "warning", "description": "ModelOps Labs in questionnaire but not declared in intake"}]}},
            {"tool": "determine_required_approvals", "input": {"annual_contract_value": 85000, "total_contract_value": 182000, "contract_term_months": 24, "risk_tier": "high", "data_sensitivity": "restricted", "payment_terms": "Net 60", "has_eu_subprocessors": True, "has_ai_training": True, "budget_sufficient": True}, "output": {"required_approvals": ["Business Owner", "Executive Sponsor", "Procurement Manager", "VP Finance"], "required_reviews": ["Finance / FP&A", "Legal", "Security"], "flags": ["Legal review: ACV > $50K; TCV > $100K; term > 12 months; restricted data; EU subprocessors; AI training"]}},
            {"tool": "submit_triage_output", "input": {"summary": "BLOCKED — see triage output", "risk_tier": "high", "recommendation": "blocked", "missing_documents": ["SOC 2 Type II", "DPA"], "blocking_issues": ["SOC 2 missing", "DPA missing"], "policy_flags": [], "required_approvals": ["Business Owner", "Procurement Manager", "VP Finance", "Executive Sponsor"], "required_reviews": ["Legal", "Security", "Finance / FP&A"], "draft_internal_ticket": "...", "consistency_issues": []}, "output": {"status": "received"}},
        ],
        "reflection": {
            "generator": {
                "risk_tier": "high",
                "recommendation": "blocked",
                "summary": "Two blocking issues (missing SOC 2 + DPA) and a duplicate vendor register conflict prevent routing.",
                "key_findings": [
                    "SOC 2 Type II missing — required for SaaS > $25K ACV",
                    "DPA missing despite customer PII access declared",
                    "Vendor already exists in register — possible duplicate",
                ],
            },
            "critic": {
                "agreement_level": "agree",
                "confirmed_findings": [
                    "SOC 2 Type II absence is a clear policy block per Security Review Policy §3.1",
                    "Missing DPA is non-negotiable when restricted PII is processed",
                    "New-vendor vs. register conflict must be resolved before routing",
                ],
                "missed_findings": [
                    "Net 60 payment terms also require explicit VP Finance sign-off — should be elevated to warning",
                ],
                "over_flagged": [],
                "risk_assessment": "agree",
                "confidence": 92,
                "summary": (
                    "The generator correctly identified both blocking issues and the consistency conflict. "
                    "The AI training clause flag is appropriate given the ambiguous language. "
                    "Minor miss: Net 60 payment terms should be flagged more prominently in the Finance category."
                ),
            },
            "final": {
                "risk_tier": "high",
                "risk_assessment": "agree",
                "adjustments": ["Elevate Net 60 payment terms flag to Finance category warning"],
            },
        },
        "message_count": 18,
    },

    "case_002": {
        "pre_screen": {
            "screen_result": "proceed",
            "block_reasons": [],
            "escalate_reasons": [],
        },
        "triage_output": {
            "summary": (
                "Workspace Depot is a low-risk office supplies renewal with an ACV of $12,000 over 12 months. "
                "The vendor is already active in the register, no system integrations or data access are declared, "
                "and the budget ($18,000 remaining) comfortably covers the ACV. Two minor administrative documents "
                "are missing (W-9 and vendor setup form) but these are not blocking — they must be collected "
                "before payment is processed. Business owner approval is sufficient to route this case."
            ),
            "risk_tier": "low",
            "recommendation": "ready_for_approval",
            "missing_documents": [
                "W-9 Tax Form",
                "Vendor Setup Form",
            ],
            "blocking_issues": [],
            "consistency_issues": [],
            "contract_legal_flags": [],
            "policy_flags": [
                {
                    "policy": "Procurement Policy",
                    "issue": "W-9 and Vendor Setup Form missing — required before first payment but not before approval routing",
                    "severity": "warning",
                },
                {
                    "policy": "Finance Approval Matrix",
                    "issue": "ACV $12,000 is within Business Owner approval threshold — no Procurement Manager needed",
                    "severity": "info",
                },
            ],
            "required_approvals": ["Business Owner"],
            "required_reviews": [],
            "draft_vendor_followup": (
                "Subject: Document Request — Workspace Depot Renewal (Case 002)\n\n"
                "Dear Workspace Depot Team,\n\n"
                "Thank you for your renewal submission. To complete processing, please provide:\n\n"
                "1. W-9 Tax Form (current year)\n"
                "2. Completed Vendor Setup Form\n\n"
                "These documents are required before we can process payment. Your renewal can proceed "
                "to approval while we await these forms.\n\n"
                "Best regards,\nProcurement Team"
            ),
            "draft_internal_ticket": (
                "PROCUREMENT TRIAGE — Case 002: Workspace Depot\n"
                "Status: READY FOR APPROVAL\n\n"
                "Notes:\n"
                "- Existing vendor renewal, low risk, no data access\n"
                "- Collect W-9 and Vendor Setup Form before first payment\n"
                "- Route to Business Owner for approval\n"
            ),
        },
        "tool_calls": [
            {"tool": "lookup_budget", "input": {"cost_center": "CC-2010"}, "output": {"found": True, "cost_center": "CC-2010", "department": "Operations", "annual_budget_remaining": 18000.0, "budget_owner": "Mark Torres"}},
            {"tool": "check_existing_vendor", "input": {"vendor_name": "Workspace Depot"}, "output": {"found": True, "match_type": "exact", "vendor_id": "V-0019", "status": "active", "category": "Office Supplies", "owner": "Operations", "flag_for_review": False}},
            {"tool": "calculate_total_contract_value", "input": {"annual_contract_value": 12000, "contract_term_months": 12, "one_time_fees": 0}, "output": {"annual_contract_value": 12000, "contract_term_months": 12, "one_time_fees": 0, "total_contract_value": 12000.0}},
            {"tool": "classify_data_sensitivity", "input": {"data_types": []}, "output": {"sensitivity_level": "internal", "restricted_fields": [], "confidential_fields": [], "security_review_required": False, "legal_review_required": False}},
            {"tool": "extract_contract_clauses", "input": {}, "output": {"ai_model_training": {"found": False, "excerpt": None, "flags": []}, "auto_renewal": {"found": True, "excerpt": "...renews automatically for one-year terms unless cancelled 30 days prior..."}, "limitation_of_liability": {"found": True, "excerpt": "...liability limited to fees paid in prior 12 months..."}, "governing_law": {"found": True, "excerpt": "...governed by the laws of California..."}, "data_processing_agreement_ref": {"found": False, "excerpt": None}, "subprocessor_regions_detected": [], "all_legal_flags": []}},
            {"tool": "validate_cross_document_consistency", "input": {"intake_acv": 12000, "intake_renewal_status": "renewal", "intake_subprocessors": [], "quote_annual_total": 12000, "vendor_found_in_register": True, "vendor_register_status": "active", "questionnaire_subprocessors": []}, "output": {"issues_found": 0, "is_consistent": True, "issues": []}},
            {"tool": "determine_required_approvals", "input": {"annual_contract_value": 12000, "total_contract_value": 12000, "contract_term_months": 12, "risk_tier": "low", "data_sensitivity": "internal", "payment_terms": "Net 30", "has_eu_subprocessors": False, "has_ai_training": False, "budget_sufficient": True}, "output": {"required_approvals": ["Business Owner"], "required_reviews": [], "flags": []}},
            {"tool": "submit_triage_output", "input": {"summary": "Ready for approval", "risk_tier": "low", "recommendation": "ready_for_approval", "missing_documents": ["W-9", "Vendor Setup Form"], "blocking_issues": [], "policy_flags": [], "required_approvals": ["Business Owner"], "required_reviews": [], "draft_internal_ticket": "...", "consistency_issues": []}, "output": {"status": "received"}},
        ],
        "reflection": None,
        "message_count": 12,
    },

    "case_003": {
        "pre_screen": {
            "screen_result": "block",
            "block_reasons": [
                "SOC 2 Type II not provided — required for SaaS vendors with ACV > $25,000",
                "Data Processing Agreement not provided despite declared data access",
            ],
            "escalate_reasons": [
                "ACV $120,000 exceeds $50,000 — requires Procurement Manager + VP Finance",
                "Payment terms Net 90 require VP Finance review (≥ Net 60)",
                "PII data processing declared: 'Employee salary and performance data'",
                "AI functionality with potential data-training use — requires Legal + Executive review",
                "Contract term 36 months requires Legal review",
            ],
        },
        "triage_output": {
            "summary": (
                "TalentPulse AI is a high-risk HR AI platform requesting a 36-month contract at $120,000 ACV. "
                "Three blocking issues prevent proceeding: SOC 2 Type II and DPA are both missing, and AI "
                "data training opt-out has not been confirmed in writing despite the vendor's contract containing "
                "explicit model-training language. The platform processes highly sensitive employee PII "
                "(salary, performance ratings, attrition risk) and uses EU and APAC subprocessors, triggering "
                "GDPR and cross-border data transfer requirements. Payment terms of Net 90 and a 36-month "
                "term also require VP Finance and Legal sign-off. This case should not proceed until all "
                "three blocking issues are resolved."
            ),
            "risk_tier": "high",
            "recommendation": "blocked",
            "missing_documents": [
                "SOC 2 Type II report",
                "Data Processing Agreement (DPA)",
                "AI Training Opt-Out Confirmation (written)",
            ],
            "blocking_issues": [
                "SOC 2 Type II not provided — required for SaaS vendors with ACV > $25,000 (Security policy §3.1)",
                "Data Processing Agreement missing — required when vendor accesses employee personal data (Legal policy §2.4)",
                "AI training opt-out not confirmed — vendor contract permits use of employee data for model training; written opt-out required before signing (Data Handling policy §5.2)",
            ],
            "consistency_issues": [],
            "contract_legal_flags": [
                "Contract explicitly permits vendor to use customer/employee data to improve AI models — requires Legal + Security + Executive approval; opt-out must be confirmed before signing",
                "EU and APAC subprocessors detected — GDPR Data Transfer Impact Assessment and SCCs required",
                "Payment terms Net 90 exceed Net 60 threshold — VP Finance + Legal approval required",
            ],
            "policy_flags": [
                {
                    "policy": "Finance Approval Matrix",
                    "issue": "ACV $120,000 — requires Procurement Manager + VP Finance + CFO approval",
                    "severity": "warning",
                },
                {
                    "policy": "Finance Approval Matrix",
                    "issue": "Payment terms Net 90 exceed Net 60 — VP Finance + Legal required",
                    "severity": "blocking",
                },
                {
                    "policy": "Finance Approval Matrix",
                    "issue": "Contract term 36 months — Finance multi-year review required",
                    "severity": "warning",
                },
                {
                    "policy": "Legal Review Policy",
                    "issue": "AI model training clause confirmed in contract — Executive sign-off + written opt-out mandatory",
                    "severity": "blocking",
                },
                {
                    "policy": "Legal Review Policy",
                    "issue": "EU + APAC subprocessors — SCCs and DPIA required before signing",
                    "severity": "warning",
                },
                {
                    "policy": "Security Review Policy",
                    "issue": "Employee salary, performance, attrition data — highest sensitivity tier; Security review mandatory",
                    "severity": "warning",
                },
                {
                    "policy": "Data Handling Policy",
                    "issue": "Employee PII classified as RESTRICTED — AI training on this data class requires explicit written opt-out",
                    "severity": "blocking",
                },
            ],
            "required_approvals": [
                "Business Owner",
                "CFO",
                "Executive Sponsor",
                "Procurement Manager",
                "VP Finance",
            ],
            "required_reviews": [
                "Finance (multi-year contract)",
                "Legal",
                "Security",
                "VP Finance",
            ],
            "draft_vendor_followup": (
                "Subject: Critical Documents Required — TalentPulse AI Onboarding (Case 003)\n\n"
                "Dear TalentPulse AI Team,\n\n"
                "Thank you for your submission. Before we can proceed, the following are required:\n\n"
                "1. SOC 2 Type II Report — Most recent audit report (within 12 months).\n\n"
                "2. Data Processing Agreement (DPA) — Our standard DPA template is attached. Please "
                "complete and return with your Data Protection Officer's signature.\n\n"
                "3. AI Training Opt-Out Confirmation — Section 7.2 of your MSA permits use of client "
                "data for AI model training. We require written confirmation that our employee data "
                "will be excluded from all model training, benchmarking, and product improvement "
                "activities, or a contract amendment removing this clause.\n\n"
                "Please note that until these three items are received, we are unable to route this "
                "request for approval.\n\n"
                "Best regards,\nProcurement Team"
            ),
            "draft_internal_ticket": (
                "PROCUREMENT TRIAGE — Case 003: TalentPulse AI\n"
                "Status: BLOCKED — 3 critical issues must be resolved\n\n"
                "Blocking Issues:\n"
                "1. SOC 2 Type II missing\n"
                "2. DPA missing\n"
                "3. AI training opt-out not confirmed\n\n"
                "When unblocked, route to: Business Owner → Procurement Manager → VP Finance → CFO → Executive Sponsor\n"
                "Reviews required: Legal (AI clause + EU/APAC subprocessors), Security, Finance (multi-year)\n\n"
                "Do NOT proceed until all 3 blocking items are resolved."
            ),
        },
        "tool_calls": [
            {"tool": "lookup_budget", "input": {"cost_center": "CC-3005"}, "output": {"found": True, "cost_center": "CC-3005", "department": "HR", "annual_budget_remaining": 150000.0, "budget_owner": "Linda Park"}},
            {"tool": "check_existing_vendor", "input": {"vendor_name": "TalentPulse AI"}, "output": {"found": False, "similar_vendors": [], "flag_for_review": False}},
            {"tool": "calculate_total_contract_value", "input": {"annual_contract_value": 120000, "contract_term_months": 36, "one_time_fees": 15000}, "output": {"annual_contract_value": 120000, "contract_term_months": 36, "one_time_fees": 15000, "total_contract_value": 375000.0}},
            {"tool": "classify_data_sensitivity", "input": {"data_types": ["Employee salary", "Performance ratings", "Attrition risk scores", "Engagement survey responses"]}, "output": {"sensitivity_level": "restricted", "restricted_fields": ["Employee salary", "Performance ratings", "Attrition risk scores", "Engagement survey responses"], "confidential_fields": [], "security_review_required": True, "legal_review_required": True}},
            {"tool": "extract_contract_clauses", "input": {}, "output": {"ai_model_training": {"found": True, "excerpt": "...Customer data may be used to train, improve, and benchmark TalentPulse models...", "flags": ["Contract explicitly permits AI model training on employee data — Executive sign-off + written opt-out required"]}, "auto_renewal": {"found": True, "excerpt": "...automatically renews unless cancelled 90 days prior..."}, "limitation_of_liability": {"found": True, "excerpt": "...aggregate liability capped at 6 months of fees..."}, "governing_law": {"found": True, "excerpt": "...governed by the laws of Ireland..."}, "data_processing_agreement_ref": {"found": False, "excerpt": None}, "subprocessor_regions_detected": ["European Union", "APAC"], "all_legal_flags": ["AI model training on employee data confirmed", "Governing law: Ireland (outside US) — Legal review required", "EU + APAC subprocessors — SCCs and DPIA required"]}},
            {"tool": "validate_cross_document_consistency", "input": {"intake_acv": 120000, "intake_renewal_status": "new_vendor", "intake_subprocessors": ["DataBridge EU", "AnnotationWorks APAC"], "quote_annual_total": 120000, "vendor_found_in_register": False, "questionnaire_subprocessors": ["DataBridge EU", "AnnotationWorks APAC", "ModelOps Labs EU"]}, "output": {"issues_found": 1, "is_consistent": False, "issues": [{"type": "subprocessor_undeclared_in_intake", "severity": "warning", "description": "ModelOps Labs EU in questionnaire but not declared in intake"}]}},
            {"tool": "determine_required_approvals", "input": {"annual_contract_value": 120000, "total_contract_value": 375000, "contract_term_months": 36, "risk_tier": "high", "data_sensitivity": "restricted", "payment_terms": "Net 90", "has_eu_subprocessors": True, "has_apac_subprocessors": True, "has_ai_training": True, "budget_sufficient": True}, "output": {"required_approvals": ["Business Owner", "CFO", "Executive Sponsor", "Procurement Manager", "VP Finance"], "required_reviews": ["Finance (multi-year contract)", "Legal", "Security", "VP Finance"], "flags": ["VP Finance + Legal: Net 90 > Net 60", "Executive: AI training + restricted data + TCV > $250K"]}},
            {"tool": "submit_triage_output", "input": {"summary": "BLOCKED — 3 critical issues", "risk_tier": "high", "recommendation": "blocked", "missing_documents": ["SOC 2", "DPA", "AI Opt-Out"], "blocking_issues": ["SOC 2 missing", "DPA missing", "AI opt-out unconfirmed"], "policy_flags": [], "required_approvals": ["Business Owner", "Procurement Manager", "VP Finance", "CFO", "Executive Sponsor"], "required_reviews": ["Legal", "Security", "Finance", "VP Finance"], "draft_internal_ticket": "...", "consistency_issues": []}, "output": {"status": "received"}},
        ],
        "reflection": {
            "generator": {
                "risk_tier": "high",
                "recommendation": "blocked",
                "summary": "Three blocking issues + confirmed AI training on restricted employee PII + EU/APAC subprocessors.",
                "key_findings": [
                    "SOC 2 Type II and DPA both missing",
                    "AI model training on employee data confirmed in contract — Executive sign-off required",
                    "Net 90 payment terms exceed policy threshold",
                ],
            },
            "critic": {
                "agreement_level": "agree",
                "confirmed_findings": [
                    "Three blocking issues correctly identified — SOC 2, DPA, and AI opt-out are all non-negotiable",
                    "EU + APAC subprocessors correctly flagged; SCCs and DPIA requirement is accurate",
                    "5-approver chain (Business Owner → Procurement → VP Finance → CFO → Executive) is correct per Finance policy",
                ],
                "missed_findings": [
                    "Governing law (Ireland) should be flagged as a separate legal risk — non-US governing law requires additional Legal review",
                    "6-month liability cap (below 12 months of fees) should be flagged as below-standard",
                ],
                "over_flagged": [],
                "risk_assessment": "agree",
                "confidence": 95,
                "summary": (
                    "The generator's analysis is thorough and accurate. All three blocking issues are "
                    "correctly identified and well-justified. The critic adds two additional points: "
                    "the Ireland governing law clause and the below-standard liability cap, both of which "
                    "should be surfaced to Legal. Risk tier HIGH and recommendation BLOCKED are appropriate."
                ),
            },
            "final": {
                "risk_tier": "high",
                "risk_assessment": "agree",
                "adjustments": [
                    "Flag Ireland governing law as additional Legal review item",
                    "Flag 6-month liability cap as below standard — Legal to negotiate to 12 months",
                ],
            },
        },
        "message_count": 20,
    },
}


def get_mock_result(case_id: str) -> dict:
    return MOCK_RESULTS.get(case_id, {})
