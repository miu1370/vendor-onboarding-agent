import os
from pathlib import Path
from dotenv import load_dotenv
import streamlit as st
from parsers import load_case, load_policies
from agent import run_vendor_agent

BASE_PATH = str(Path(__file__).parent.parent)

# Load .env from the vendor_agent/ directory (or parent)
load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")  # also check repo root

_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

st.set_page_config(
    page_title="Vendor Onboarding Agent",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
for _k, _v in {
    "view": "home",
    "result": None,
    "case_id": None,
    "submitted": False,
    "human_decision": None,
    "human_notes": "",
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ---------------------------------------------------------------------------
# Sidebar — always visible
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## Vendor Onboarding Agent")
    st.caption("AI-assisted procurement triage")
    st.divider()

    if st.button("← Overview", use_container_width=True):
        st.session_state.view = "home"
        st.rerun()

    st.subheader("Select Case")
    CASES = {
        "Case 001 · Northstar Analytics": "case_001",
        "Case 002 · Workspace Depot": "case_002",
        "Case 003 · TalentPulse AI": "case_003",
    }
    selected_label = st.selectbox(
        "case", list(CASES.keys()), label_visibility="collapsed"
    )
    case_id = CASES[selected_label]

    if not _API_KEY:
        st.error("ANTHROPIC_API_KEY not set in environment.")
        can_run = False
    else:
        can_run = True

    run_btn = st.button(
        "▶ Run Agent Analysis",
        type="primary",
        disabled=not can_run,
        use_container_width=True,
    )

    st.divider()
    st.caption(
        "**Agent may:** summarize, flag issues, draft messages, recommend routing.\n\n"
        "**Agent may NOT:** approve vendors, commit spend, send external comms."
    )

# ---------------------------------------------------------------------------
# Run agent
# ---------------------------------------------------------------------------
if run_btn and can_run:
    with st.spinner(f"Parsing {case_id} and running agent…"):
        try:
            case_data = load_case(case_id, BASE_PATH)
            policies = load_policies(BASE_PATH)
            result = run_vendor_agent(case_data, policies, _API_KEY)
            st.session_state.result = result
            st.session_state.case_id = case_id
            st.session_state.submitted = False
            st.session_state.human_decision = None
            st.session_state.human_notes = ""
            st.session_state.view = "analysis"
            st.rerun()
        except Exception as exc:
            st.error(f"Error during agent run: {exc}")
            st.exception(exc)

# ===========================================================================
# HOME PAGE
# ===========================================================================
if st.session_state.view == "home":

    st.markdown(
        "<h1 style='margin-bottom:4px'>🏢 Vendor Onboarding Agent</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "AI-assisted procurement triage — reviews vendor packages against internal policies "
        "and produces structured recommendations for the human procurement owner.",
    )
    st.divider()

    # ── How it works ──────────────────────────────────────────────────────
    st.subheader("How it works")
    st.markdown(
        """
<div style="display:flex;align-items:flex-start;gap:0;margin:16px 0 24px 0;">

  <div style="flex:1;background:#EEF2FF;border-radius:12px;padding:18px 14px;text-align:center;min-height:160px;">
    <div style="font-size:2em">📄</div>
    <div style="font-weight:700;font-size:1em;margin:8px 0 4px">1 · Parse</div>
    <div style="color:#555;font-size:0.82em;line-height:1.6">
      Intake form <em>xlsx</em><br>
      Quote <em>csv</em><br>
      Contract <em>pdf</em><br>
      Security Q <em>md</em><br>
      Vendor email <em>txt</em>
    </div>
  </div>

  <div style="color:#bbb;font-size:1.8em;padding:58px 6px 0">›</div>

  <div style="flex:1;background:#F0FFF4;border-radius:12px;padding:18px 14px;text-align:center;min-height:160px;">
    <div style="font-size:2em">🔧</div>
    <div style="font-weight:700;font-size:1em;margin:8px 0 4px">2 · Tools</div>
    <div style="color:#555;font-size:0.82em;line-height:1.6">
      Budget lookup<br>
      Vendor register<br>
      Contract value<br>
      Data sensitivity<br>
      <strong>Contract clauses</strong> ✦<br>
      <strong>Cross-doc check</strong> ✦
    </div>
  </div>

  <div style="color:#bbb;font-size:1.8em;padding:58px 6px 0">›</div>

  <div style="flex:1;background:#FFFBF0;border-radius:12px;padding:18px 14px;text-align:center;min-height:160px;">
    <div style="font-size:2em">📋</div>
    <div style="font-weight:700;font-size:1em;margin:8px 0 4px">3 · Policy</div>
    <div style="color:#555;font-size:0.82em;line-height:1.6">
      Finance matrix<br>
      Legal triggers<br>
      Security rules<br>
      Vendor risk tiers<br>
      Data handling<br>
      Comms policy
    </div>
  </div>

  <div style="color:#bbb;font-size:1.8em;padding:58px 6px 0">›</div>

  <div style="flex:1;background:#FFF5F5;border-radius:12px;padding:18px 14px;text-align:center;min-height:160px;">
    <div style="font-size:2em">📊</div>
    <div style="font-weight:700;font-size:1em;margin:8px 0 4px">4 · Output</div>
    <div style="color:#555;font-size:0.82em;line-height:1.6">
      Risk tier<br>
      Missing docs<br>
      Blocking issues<br>
      Approval routing<br>
      Contract flags<br>
      Draft comms
    </div>
  </div>

  <div style="color:#bbb;font-size:1.8em;padding:58px 6px 0">›</div>

  <div style="flex:1;background:#F5F0FF;border-radius:12px;padding:18px 14px;text-align:center;min-height:160px;">
    <div style="font-size:2em">👤</div>
    <div style="font-weight:700;font-size:1em;margin:8px 0 4px">5 · Approve</div>
    <div style="color:#555;font-size:0.82em;line-height:1.6">
      Human reviews<br>
      Edits drafts<br>
      Records decision<br>
      Routes to:<br>
      Legal · Finance<br>
      Security · Owner
    </div>
  </div>

</div>
<p style="font-size:0.78em;color:#888;margin-top:-8px">✦ New tools added in v2</p>
""",
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Test cases ─────────────────────────────────────────────────────────
    st.subheader("Test Cases")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            """
<div style="background:#fff5f5;border-left:5px solid #e53e3e;border-radius:10px;padding:18px;">
  <div style="font-size:0.75em;color:#999;font-weight:600;letter-spacing:.05em">CASE 001</div>
  <div style="font-size:1.15em;font-weight:700;margin:4px 0 2px">Northstar Analytics</div>
  <div style="font-size:0.82em;color:#666">SaaS AI · $85,000/yr · 24 months · Net 60</div>
  <div style="margin:10px 0">
    <span style="background:#e53e3e;color:#fff;padding:2px 10px;border-radius:20px;font-size:0.75em;font-weight:600">HIGH RISK</span>
  </div>
  <div style="font-size:0.82em;color:#444;line-height:1.7">
    ✗ Missing SOC 2 Type II<br>
    ✗ Missing DPA<br>
    ⚠ EU subprocessor (Clearbit)<br>
    ⚠ Ambiguous AI training clause<br>
    ⚠ Possible duplicate in register<br>
    ⚠ Net 60 → VP Finance review
  </div>
</div>""",
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            """
<div style="background:#f0fff4;border-left:5px solid #38a169;border-radius:10px;padding:18px;">
  <div style="font-size:0.75em;color:#999;font-weight:600;letter-spacing:.05em">CASE 002</div>
  <div style="font-size:1.15em;font-weight:700;margin:4px 0 2px">Workspace Depot</div>
  <div style="font-size:0.82em;color:#666">Office Supplies · $12,000/yr · 12 months · Net 30</div>
  <div style="margin:10px 0">
    <span style="background:#38a169;color:#fff;padding:2px 10px;border-radius:20px;font-size:0.75em;font-weight:600">LOW RISK</span>
  </div>
  <div style="font-size:0.82em;color:#444;line-height:1.7">
    ✓ Existing vendor renewal<br>
    ✓ No system access or data<br>
    ✗ Missing tax form (W-9)<br>
    ✗ Missing vendor setup form<br>
    ⚠ Budget $18K vs ACV $12K — tight<br>
    ⚠ Business owner approval only
  </div>
</div>""",
            unsafe_allow_html=True,
        )

    with c3:
        st.markdown(
            """
<div style="background:#fffaf0;border-left:5px solid #dd6b20;border-radius:10px;padding:18px;">
  <div style="font-size:0.75em;color:#999;font-weight:600;letter-spacing:.05em">CASE 003</div>
  <div style="font-size:1.15em;font-weight:700;margin:4px 0 2px">TalentPulse AI</div>
  <div style="font-size:0.82em;color:#666">HR AI · $120,000/yr · 36 months · Net 90</div>
  <div style="margin:10px 0">
    <span style="background:#dd6b20;color:#fff;padding:2px 10px;border-radius:20px;font-size:0.75em;font-weight:600">BLOCKED</span>
  </div>
  <div style="font-size:0.82em;color:#444;line-height:1.7">
    ✗ Missing SOC 2 Type II<br>
    ✗ Missing DPA<br>
    ✗ AI opt-out not in quote<br>
    ⚠ EU + APAC subprocessors<br>
    ⚠ Net 90 → VP Finance + Legal<br>
    ⚠ Employee salary / performance PII<br>
    ⚠ 5 required approvers + Executive
  </div>
</div>""",
            unsafe_allow_html=True,
        )

    st.divider()
    st.info("Select a case in the sidebar and click **▶ Run Agent Analysis** to begin.")


# ===========================================================================
# ANALYSIS PAGE
# ===========================================================================
elif st.session_state.view == "analysis":

    result = st.session_state.result
    if not result or st.session_state.case_id != case_id:
        st.info("Run the agent analysis first using the sidebar.")
        st.stop()

    triage = result.get("triage_output")
    if not triage:
        st.error("Agent did not produce a triage output.")
        st.json(result)
        st.stop()

    risk = triage.get("risk_tier", "unknown").upper()
    rec = triage.get("recommendation", "unknown")
    n_blocking = len(triage.get("blocking_issues") or [])
    n_missing = len(triage.get("missing_documents") or [])
    n_consistency = len(triage.get("consistency_issues") or [])
    n_contract = len(triage.get("contract_legal_flags") or [])
    n_tools = len(result.get("tool_calls", []))

    REC_LABELS = {
        "ready_for_approval": "✅ Ready for approval routing",
        "pending_information": "⏳ Pending — hold for info",
        "escalate_to_human": "🔺 Escalate to human owner",
        "blocked": "🚫 Blocked — do not proceed",
    }

    # ── Header metrics ────────────────────────────────────────────────────
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Risk Tier", risk)
    col2.metric("Blocking Issues", n_blocking)
    col3.metric("Missing Documents", n_missing)
    col4.metric("Consistency Issues", n_consistency)
    col5.metric("Contract Flags", n_contract)

    st.markdown(
        f"**Agent recommendation:** {REC_LABELS.get(rec, rec)} &nbsp;·&nbsp; "
        f"{n_tools} tool calls made",
        unsafe_allow_html=True,
    )
    st.divider()

    tabs = st.tabs([
        "📋 Summary & Flags",
        "✅ Approval Routing",
        "📂 Missing Documents",
        "📑 Contract Analysis",
        "✉️ Draft Communications",
        "🔧 Tool Call Log",
        "👤 Human Approval Gate",
    ])

    # ── Tab 0: Summary & Flags ────────────────────────────────────────────
    with tabs[0]:
        st.subheader("Triage Summary")
        st.write(triage.get("summary", ""))

        blocking = triage.get("blocking_issues") or []
        if blocking:
            st.error(f"**{len(blocking)} Blocking Issue(s)** — request cannot proceed as-is:")
            for issue in blocking:
                st.markdown(f"- {issue}")

        consistency = triage.get("consistency_issues") or []
        if consistency:
            st.warning(f"**{len(consistency)} Cross-Document Inconsistency(ies):**")
            for issue in consistency:
                st.markdown(f"- {issue}")

        st.subheader("Policy Flags")
        flags = triage.get("policy_flags") or []
        if flags:
            for flag in flags:
                sev = flag.get("severity", "info")
                label = f"**[{flag['policy']}]** {flag['issue']}"
                if sev == "blocking":
                    st.error(label)
                elif sev == "warning":
                    st.warning(label)
                else:
                    st.info(label)
        else:
            st.success("No policy flags raised.")

    # ── Tab 1: Approval Routing ───────────────────────────────────────────
    with tabs[1]:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Required Sign-offs")
            for a in triage.get("required_approvals") or []:
                st.markdown(f"- ✅ **{a}**")
        with col2:
            st.subheader("Required Reviews")
            for r in triage.get("required_reviews") or []:
                st.markdown(f"- 🔍 **{r}**")

    # ── Tab 2: Missing Documents ──────────────────────────────────────────
    with tabs[2]:
        missing = triage.get("missing_documents") or []
        if missing:
            st.warning(f"{len(missing)} document(s) missing or incomplete:")
            for doc in missing:
                st.markdown(f"- {doc}")
        else:
            st.success("All required documents are present.")

    # ── Tab 3: Contract Analysis ──────────────────────────────────────────
    with tabs[3]:
        st.subheader("Contract Clause Extraction")

        # Find the extract_contract_clauses tool call result
        contract_result = None
        for call in result.get("tool_calls", []):
            if call["tool"] == "extract_contract_clauses":
                contract_result = call["output"]
                break

        if contract_result:
            legal_flags = contract_result.get("all_legal_flags") or []
            if legal_flags:
                st.error(f"**{len(legal_flags)} Legal Flag(s) detected in contract:**")
                for f in legal_flags:
                    st.markdown(f"- {f}")
            else:
                st.success("No non-standard legal clauses detected.")

            st.divider()
            st.subheader("Clause-by-Clause Findings")

            clauses = {
                "AI / Model Training": contract_result.get("ai_model_training"),
                "Auto-Renewal": contract_result.get("auto_renewal"),
                "Limitation of Liability": contract_result.get("limitation_of_liability"),
                "Governing Law": contract_result.get("governing_law"),
                "Data Retention": contract_result.get("data_retention_clause"),
                "Termination Rights": contract_result.get("termination_rights"),
                "DPA Reference": contract_result.get("data_processing_agreement_ref"),
                "Subprocessor Clause": contract_result.get("subprocessor_clause"),
            }

            regions = contract_result.get("subprocessor_regions_detected") or []
            if regions:
                st.warning(f"Subprocessor regions detected in contract: {', '.join(regions)}")

            for clause_name, clause_data in clauses.items():
                if not clause_data:
                    continue
                found = clause_data.get("found", False)
                icon = "🔴" if (not found and clause_name in ("DPA Reference",)) else ("✓" if found else "–")
                with st.expander(f"{icon} {clause_name} — {'found' if found else 'not detected'}"):
                    if found and clause_data.get("excerpt"):
                        st.code(clause_data["excerpt"], language=None)
                    if clause_data.get("flags"):
                        for flag in clause_data["flags"]:
                            st.warning(flag)
                    if not found:
                        st.caption("Pattern not found in contract text.")
        else:
            st.info("Contract clause extraction tool was not called in this run.")

        # Cross-doc consistency detail
        st.divider()
        st.subheader("Cross-Document Consistency Check")
        consistency_result = None
        for call in result.get("tool_calls", []):
            if call["tool"] == "validate_cross_document_consistency":
                consistency_result = call["output"]
                break

        if consistency_result:
            issues = consistency_result.get("issues") or []
            if not issues:
                st.success("All cross-document checks passed.")
            else:
                for issue in issues:
                    sev = issue.get("severity", "info")
                    desc = issue.get("description", "")
                    if sev == "blocking":
                        st.error(f"**[{issue['type']}]** {desc}")
                    elif sev == "warning":
                        st.warning(f"**[{issue['type']}]** {desc}")
                    else:
                        st.info(f"**[{issue['type']}]** {desc}")
        else:
            st.info("Cross-document consistency check was not called in this run.")

    # ── Tab 4: Draft Communications ───────────────────────────────────────
    with tabs[4]:
        followup = triage.get("draft_vendor_followup", "")
        ticket = triage.get("draft_internal_ticket", "")

        if followup:
            st.subheader("DRAFT: Vendor Follow-up Email")
            st.caption("⚠️ DRAFT — requires human review and approval before sending.")
            st.text_area("", followup, height=280, key="followup_area")
        else:
            st.info("No vendor follow-up email needed.")

        if ticket:
            st.subheader("DRAFT: Internal Procurement Ticket")
            st.text_area("", ticket, height=220, key="ticket_area")

    # ── Tab 5: Tool Call Log ──────────────────────────────────────────────
    with tabs[5]:
        calls = result.get("tool_calls", [])
        st.subheader(f"Tool Calls ({len(calls)})")
        for i, call in enumerate(calls, 1):
            with st.expander(f"{i}. {call['tool']}"):
                c_in, c_out = st.columns(2)
                with c_in:
                    st.caption("Input")
                    st.json(call["input"])
                with c_out:
                    st.caption("Output")
                    st.json(call["output"])

    # ── Tab 6: Human Approval Gate ────────────────────────────────────────
    with tabs[6]:
        st.subheader("Human Approval Gate")
        st.info(
            "As the procurement owner, you have reviewed the analysis above. "
            "Your decision is required before any routing or external communications proceed."
        )
        st.markdown(f"**Agent recommendation:** {REC_LABELS.get(rec, rec)}")
        st.divider()

        if st.session_state.submitted:
            decision = st.session_state.human_decision
            notes = st.session_state.human_notes

            st.success(f"Decision recorded: **{decision}**")
            if notes:
                st.markdown(f"**Notes:** {notes}")

            # ── Downstream routing visualization ─────────────────────────
            st.divider()
            st.subheader("What happens next")

            approvals = triage.get("required_approvals") or []
            reviews = triage.get("required_reviews") or []

            if "Approve" in decision:
                st.markdown("**This case will be routed to:**")
                cols = st.columns(max(len(reviews), 1))
                review_icons = {
                    "Legal": "⚖️",
                    "Security": "🔒",
                    "Finance": "💰",
                    "VP Finance": "💰",
                    "FP&A": "💰",
                }
                for i, rev in enumerate(reviews):
                    icon = next((v for k, v in review_icons.items() if k in rev), "🔍")
                    cols[i % len(cols)].metric(icon + " " + rev.split(" (")[0], "Review pending")

                st.markdown("**Sign-off chain:**")
                st.markdown(" → ".join(f"**{a}**" for a in approvals))

                followup = triage.get("draft_vendor_followup", "")
                if followup:
                    st.markdown("**Pending action:** Send vendor follow-up (requires your sign-off on the draft in the Communications tab.)")

            elif "Request more information" in decision:
                st.markdown("**Next step:** Send the draft vendor follow-up email (Communications tab) after your review.")
                st.markdown("**Case status:** On hold — awaiting vendor response before re-triage.")

            elif "Reject" in decision:
                st.markdown("**Next step:** Notify the requester with the reason below.")
                st.code(notes or "(no reason provided)", language=None)

            elif "Escalate" in decision:
                st.markdown("**Next step:** Flag for senior procurement review.")
                st.markdown("**Escalation notes:**")
                st.code(notes or "(no notes provided)", language=None)

            st.divider()
            if st.button("Reset decision"):
                st.session_state.submitted = False
                st.rerun()

        else:
            decision = st.radio(
                "Your decision:",
                [
                    "Approve routing — forward to required reviewers",
                    "Request more information — hold for vendor response",
                    "Reject — return to requester with reason",
                    "Escalate — flag for senior procurement review",
                ],
                key="human_decision_radio",
            )
            notes = st.text_area(
                "Notes / reason (required for Reject or Escalate):",
                height=100,
                key="human_notes_area",
            )
            if st.button("Submit Decision", type="primary"):
                st.session_state.human_decision = decision
                st.session_state.human_notes = notes
                st.session_state.submitted = True
                st.rerun()
