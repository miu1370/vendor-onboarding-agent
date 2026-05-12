import os
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import streamlit as st
import pandas as pd
from parsers import load_case, load_policies
from agent import run_vendor_agent

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_PATH = str(Path(__file__).parent.parent)
DOCS_PATH = Path(BASE_PATH) / "docs"
CASES_PATH = Path(BASE_PATH) / "cases"
AUDIT_LOG = Path(__file__).parent / "audit_log.json"

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")

_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

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
        "category": "SaaS AI Analytics",
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
        "category": "HR AI",
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

POLICY_VERSIONS = {
    "finance_approval_matrix": "v1.2.0",
    "vendor_risk_policy": "v2.0.1",
    "security_review_policy": "v1.5.3",
    "legal_review_policy": "v1.1.2",
    "data_handling_policy": "v2.3.0",
    "procurement_policy": "v1.0.4",
    "communication_policy": "v1.0.1",
}

FILE_ICONS = {".xlsx": "📊", ".csv": "📋", ".pdf": "📕", ".md": "📝", ".txt": "✉️"}

CASE_MANIFESTS = {
    "case_001": {
        "title": "Case 001 · Northstar Analytics",
        "description": "SaaS AI analytics vendor, high ACV, missing compliance docs, possible duplicate in register.",
        "expected_risk": "high",
        "expected_recommendation": "blocked",
        "expected_blocking_count": 2,
    },
    "case_002": {
        "title": "Case 002 · Workspace Depot",
        "description": "Office supplies renewal, low ACV, no data access, two admin docs missing.",
        "expected_risk": "low",
        "expected_recommendation": "ready_for_approval",
        "expected_blocking_count": 0,
    },
    "case_003": {
        "title": "Case 003 · TalentPulse AI",
        "description": "HR AI platform, high ACV, employee PII, EU+APAC subprocessors, AI training clause.",
        "expected_risk": "high",
        "expected_recommendation": "blocked",
        "expected_blocking_count": 3,
    },
}

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "page": "Overview",
    "analyses": {},
    "decisions": {},
    "hitl_state": {},
    "selected_case": None,
    "test_scores": [],
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def write_audit_log(entry: dict):
    if AUDIT_LOG.exists():
        data = json.loads(AUDIT_LOG.read_text())
    else:
        data = {"entries": []}
    data["entries"].append(entry)
    AUDIT_LOG.write_text(json.dumps(data, indent=2))


def get_hitl(case_id: str) -> dict:
    if case_id not in st.session_state.hitl_state:
        st.session_state.hitl_state[case_id] = {
            "action": None,
            "show_form": False,
        }
    return st.session_state.hitl_state[case_id]


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🏢 Vendor Onboarding")
    st.caption("AI-assisted procurement triage")
    st.divider()

    page_choice = st.radio(
        "Navigation",
        ["Overview", "Knowledge Base", "Test Cases"],
        index=["Overview", "Knowledge Base", "Test Cases"].index(st.session_state.page),
        label_visibility="collapsed",
    )
    if page_choice != st.session_state.page:
        st.session_state.page = page_choice
        st.rerun()

    st.divider()
    st.subheader("Run Analysis")

    labels = [m["label"] for m in CASE_META.values()]
    selected_label = st.selectbox("Select case", labels, label_visibility="collapsed")
    run_case_id = CASE_ORDER[labels.index(selected_label)]

    if not _API_KEY:
        st.error("ANTHROPIC_API_KEY not set in .env")
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
    with st.spinner(f"Analyzing {selected_label}…"):
        try:
            case_data = load_case(run_case_id, BASE_PATH)
            policies = load_policies(BASE_PATH)
            result = run_vendor_agent(case_data, policies, _API_KEY)
            st.session_state.analyses[run_case_id] = result
            st.session_state.selected_case = run_case_id
            st.session_state.page = "Overview"
            if run_case_id in st.session_state.hitl_state:
                del st.session_state.hitl_state[run_case_id]
            st.rerun()
        except Exception as exc:
            st.error(f"Error: {exc}")
            st.exception(exc)


# ===========================================================================
# OVERVIEW PAGE
# ===========================================================================
if st.session_state.page == "Overview":

    # Build pipeline dataframe
    rows = []
    for case_id, meta in CASE_META.items():
        result = st.session_state.analyses.get(case_id)
        decision = st.session_state.decisions.get(case_id)
        if result:
            triage = result.get("triage_output") or {}
            risk_raw = triage.get("risk_tier", "?").upper()
            risk = f"{RISK_COLOR.get(risk_raw, '⚪')} {risk_raw}"
            rec_raw = triage.get("recommendation", "?")
            rec = REC_LABELS.get(rec_raw, rec_raw.replace("_", " ").title())
            status = "Reviewed" if decision else "Analyzed"
        else:
            risk = "—"
            rec = "—"
            status = "Pending"
        rows.append({
            "Case": meta["label"].split(" · ")[0],
            "Vendor": meta["vendor"],
            "Category": meta["category"],
            "ACV": f"${meta['acv']:,}",
            "Risk": risk,
            "Recommendation": rec,
            "Status": status,
        })

    df = pd.DataFrame(rows)

    col_left, col_right = st.columns([2, 3], gap="large")

    # ── Left: Pipeline Table ───────────────────────────────────────────────
    with col_left:
        n_analyzed = sum(1 for r in rows if r["Status"] != "Pending")
        st.markdown("### Vendor Pipeline")
        st.caption(f"{n_analyzed} of {len(rows)} cases analyzed")

        event = st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
            key="pipeline_table",
        )

        selected_rows = (
            event.selection.rows
            if event.selection and hasattr(event.selection, "rows")
            else []
        )
        if selected_rows:
            st.session_state.selected_case = CASE_ORDER[selected_rows[0]]

        with st.expander("ℹ️ How it works", expanded=False):
            st.markdown(
                """
**1 · Parse** — xlsx intake, csv quote, pdf contract, md security questionnaire, txt vendor email

**2 · Tools** — budget lookup · vendor register · TCV calculation · data sensitivity
classification · contract clause extraction · cross-document validation

**3 · Policy** — finance approval matrix · legal triggers · security rules · data handling · comms policy

**4 · Generate** — risk tier, missing docs, blocking issues, approval routing, contract flags,
draft communications  *(Generator-Critic reflection for medium/high risk)*

**5 · Approve** — human reviews AI recommendation, edits drafts, records decision
"""
            )

    # ── Right: Detail Drawer ───────────────────────────────────────────────
    with col_right:
        selected_case = st.session_state.selected_case

        if not selected_case:
            st.markdown("### Detail Drawer")
            st.info("Select a row from the pipeline table to view analysis details.")
            st.stop()

        meta = CASE_META[selected_case]
        result = st.session_state.analyses.get(selected_case)

        st.markdown(f"### {meta['label']}")
        st.caption(f"{meta['category']} · ${meta['acv']:,} ACV/yr")

        if not result:
            st.info(
                "No analysis yet. Select this case in the sidebar and click **▶ Run Agent Analysis**."
            )
            st.stop()

        triage = result.get("triage_output") or {}
        pre_screen = result.get("pre_screen") or {}
        reflection = result.get("reflection")
        tool_calls = result.get("tool_calls", [])

        risk_raw = triage.get("risk_tier", "?").upper()
        rec_raw = triage.get("recommendation", "?")

        # Metrics row
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Risk", f"{RISK_COLOR.get(risk_raw, '⚪')} {risk_raw}")
        m2.metric("Blocking", len(triage.get("blocking_issues") or []))
        m3.metric("Missing Docs", len(triage.get("missing_documents") or []))
        m4.metric("Tool Calls", len(tool_calls))

        st.markdown(f"**{REC_LABELS.get(rec_raw, rec_raw)}**")

        # Pre-screen badge
        screen_result = pre_screen.get("screen_result", "")
        if screen_result == "block":
            st.error(
                f"⛔ Pre-screen: BLOCK — {len(pre_screen.get('block_reasons', []))} deterministic block condition(s) detected"
            )
        elif screen_result == "escalate":
            st.warning(
                f"⚠️ Pre-screen: ESCALATE — {len(pre_screen.get('escalate_reasons', []))} escalation trigger(s) detected"
            )
        else:
            st.success("✅ Pre-screen: No immediate block or escalate triggers")

        st.divider()

        # Analysis tabs
        tab_labels = ["📋 Analysis", "🔄 Reflection Log", "🔧 Tool Log", "✉️ Drafts"]
        atab0, atab1, atab2, atab3 = st.tabs(tab_labels)

        # ── Tab 0: Analysis ────────────────────────────────────────────────
        with atab0:
            st.write(triage.get("summary", ""))

            blocking = triage.get("blocking_issues") or []
            if blocking:
                st.error(f"**{len(blocking)} Blocking Issue(s)** — request cannot proceed as-is:")
                for b in blocking:
                    st.markdown(f"- {b}")

            consistency = triage.get("consistency_issues") or []
            if consistency:
                st.warning(f"**{len(consistency)} Cross-Document Inconsistency(ies):**")
                for c in consistency:
                    st.markdown(f"- {c}")

            flags = triage.get("policy_flags") or []
            if flags:
                st.subheader("Policy Flags")
                for flag in flags:
                    sev = flag.get("severity", "info")
                    label = f"**[{flag['policy']}]** {flag['issue']}"
                    if sev == "blocking":
                        st.error(label)
                    elif sev == "warning":
                        st.warning(label)
                    else:
                        st.info(label)

            approvals = triage.get("required_approvals") or []
            reviews = triage.get("required_reviews") or []
            if approvals or reviews:
                st.subheader("Required Approvals & Reviews")
                ac1, ac2 = st.columns(2)
                with ac1:
                    st.caption("Sign-offs")
                    for a in approvals:
                        st.markdown(f"- ✅ {a}")
                with ac2:
                    st.caption("Reviews")
                    for r in reviews:
                        st.markdown(f"- 🔍 {r}")

            contract_flags = triage.get("contract_legal_flags") or []
            if contract_flags:
                st.subheader("Contract Legal Flags")
                for f in contract_flags:
                    st.warning(f"- {f}")

            missing = triage.get("missing_documents") or []
            if missing:
                st.subheader("Missing Documents")
                for d in missing:
                    st.markdown(f"- 📄 {d}")

        # ── Tab 1: Reflection Log ─────────────────────────────────────────
        with atab1:
            if not reflection:
                st.info(
                    "Reflection (Generator-Critic) log is only produced for **medium** and "
                    "**high** risk cases. Run a medium/high-risk case to see a critic review."
                )
            else:
                gen = reflection.get("generator", {})
                critic = reflection.get("critic", {})
                final = reflection.get("final", {})

                agree_icon = {"agree": "🟢", "partial": "🟡", "disagree": "🔴"}.get(
                    critic.get("agreement_level", "agree"), "⚪"
                )
                conf = critic.get("confidence", "?")
                risk_assess = critic.get("risk_assessment", "agree")

                st.markdown(
                    f"**Critic verdict:** {agree_icon} {critic.get('agreement_level', '?').title()} "
                    f"· **Confidence:** {conf}% · **Risk assessment:** {risk_assess.replace('_', ' ').title()}"
                )
                st.write(critic.get("summary", ""))
                st.divider()

                rc1, rc2 = st.columns(2)
                with rc1:
                    st.subheader("Generator")
                    st.caption(
                        f"Risk: {gen.get('risk_tier', '?').upper()} · {gen.get('recommendation', '?').replace('_', ' ')}"
                    )
                    for f in gen.get("key_findings", []):
                        if f:
                            st.markdown(f"- {f}")

                with rc2:
                    st.subheader("Critic")
                    confirmed = critic.get("confirmed_findings", [])
                    missed = critic.get("missed_findings", [])
                    over = critic.get("over_flagged", [])
                    if confirmed:
                        st.caption("✓ Confirmed findings:")
                        for f in confirmed:
                            st.markdown(f"- {f}")
                    if missed:
                        st.caption("⚠ Missed / under-weighted:")
                        for f in missed:
                            st.markdown(f"- {f}")
                    if over:
                        st.caption("↓ Over-flagged:")
                        for f in over:
                            st.markdown(f"- {f}")

                if final.get("adjustments"):
                    with st.expander("Final adjustments from critic"):
                        for adj in final["adjustments"]:
                            st.markdown(f"- {adj}")

        # ── Tab 2: Tool Call Log ──────────────────────────────────────────
        with atab2:
            st.caption(f"{len(tool_calls)} tool calls executed")
            for i, call in enumerate(tool_calls, 1):
                with st.expander(f"{i}. {call['tool']}"):
                    tc1, tc2 = st.columns(2)
                    with tc1:
                        st.caption("Input")
                        st.json(call["input"])
                    with tc2:
                        st.caption("Output")
                        st.json(call["output"])

        # ── Tab 3: Drafts ─────────────────────────────────────────────────
        with atab3:
            followup = triage.get("draft_vendor_followup", "")
            ticket = triage.get("draft_internal_ticket", "")
            if followup:
                st.warning("⚠️ DRAFT — requires human approval before sending")
                st.subheader("Vendor Follow-up Email")
                st.text_area("", followup, height=240, key=f"followup_{selected_case}")
            if ticket:
                st.subheader("Internal Procurement Ticket")
                st.text_area("", ticket, height=180, key=f"ticket_{selected_case}")
            if not followup and not ticket:
                st.info("No draft communications generated for this case.")

        # ── HITL Action Buttons ───────────────────────────────────────────
        st.divider()
        st.subheader("Human Decision")

        hitl = get_hitl(selected_case)
        decision = st.session_state.decisions.get(selected_case)

        if decision:
            action_labels = {
                "approve": "✅ Approved AI Suggestion",
                "modify": "✏️ Modified & Accepted",
                "reject": "❌ Rejected",
                "draft_email": "📧 Sent for Draft Email Review",
            }
            st.success(f"**Decision recorded:** {action_labels.get(decision['action'], decision['action'])}")
            if decision.get("justification"):
                st.markdown(f"**Justification:** {decision['justification']}")
            st.caption(f"Recorded at {decision['timestamp']}")
            if st.button("↩ Reset decision", key=f"reset_{selected_case}"):
                del st.session_state.decisions[selected_case]
                if selected_case in st.session_state.hitl_state:
                    del st.session_state.hitl_state[selected_case]
                st.rerun()

        elif hitl.get("show_form"):
            action = hitl["action"]
            action_title = {
                "modify": "✏️ Modify & Accept — provide justification",
                "reject": "❌ Reject — provide reason",
                "draft_email": "📧 Send for Draft Email Review — add notes",
            }.get(action, action)
            st.markdown(f"**{action_title}**")

            justification = st.text_area(
                "Justification / notes (required):",
                key=f"just_{selected_case}",
                height=100,
            )
            bc1, bc2 = st.columns(2)
            with bc1:
                if st.button("✓ Confirm", type="primary", key=f"confirm_{selected_case}"):
                    if not justification.strip():
                        st.error("Justification is required.")
                    else:
                        now = datetime.now()
                        entry = {
                            "case_id": selected_case,
                            "vendor": meta["vendor"],
                            "action": action,
                            "justification": justification,
                            "timestamp": now.isoformat(),
                            "ai_recommendation": rec_raw,
                            "risk_tier": risk_raw,
                        }
                        write_audit_log(entry)
                        st.session_state.decisions[selected_case] = {
                            "action": action,
                            "justification": justification,
                            "timestamp": now.strftime("%H:%M %b %d"),
                        }
                        del st.session_state.hitl_state[selected_case]
                        st.rerun()
            with bc2:
                if st.button("Cancel", key=f"cancel_{selected_case}"):
                    hitl["show_form"] = False
                    st.rerun()

        else:
            st.caption(f"AI recommendation: **{REC_LABELS.get(rec_raw, rec_raw)}**")
            btn1, btn2, btn3, btn4 = st.columns(4)
            with btn1:
                if st.button("✅ Approve", use_container_width=True, key=f"approve_{selected_case}"):
                    now = datetime.now()
                    write_audit_log({
                        "case_id": selected_case,
                        "vendor": meta["vendor"],
                        "action": "approve",
                        "justification": "Approved AI suggestion without modification",
                        "timestamp": now.isoformat(),
                        "ai_recommendation": rec_raw,
                        "risk_tier": risk_raw,
                    })
                    st.session_state.decisions[selected_case] = {
                        "action": "approve",
                        "justification": "",
                        "timestamp": now.strftime("%H:%M %b %d"),
                    }
                    st.rerun()
            with btn2:
                if st.button("✏️ Modify", use_container_width=True, key=f"modify_{selected_case}"):
                    hitl["action"] = "modify"
                    hitl["show_form"] = True
                    st.rerun()
            with btn3:
                if st.button("📧 Draft Email", use_container_width=True, key=f"email_{selected_case}"):
                    hitl["action"] = "draft_email"
                    hitl["show_form"] = True
                    st.rerun()
            with btn4:
                if st.button("❌ Reject", use_container_width=True, key=f"reject_{selected_case}"):
                    hitl["action"] = "reject"
                    hitl["show_form"] = True
                    st.rerun()


# ===========================================================================
# KNOWLEDGE BASE PAGE
# ===========================================================================
elif st.session_state.page == "Knowledge Base":

    st.markdown("## Knowledge Base")
    st.caption("Internal procurement policies referenced by the agent during triage.")
    st.divider()

    policy_files = sorted(DOCS_PATH.glob("*.md"))

    if not policy_files:
        st.error(f"No policy documents found at {DOCS_PATH}")
    else:
        for pf in policy_files:
            name = pf.stem
            title = name.replace("_", " ").title()
            version = POLICY_VERSIONS.get(name, "v1.0.0")
            content = pf.read_text()

            with st.expander(f"📄 {title}  ·  `{version}`", expanded=False):
                st.markdown(content)


# ===========================================================================
# TEST CASES PAGE
# ===========================================================================
elif st.session_state.page == "Test Cases":

    st.markdown("## Test Cases & Evaluation")
    st.caption("Vendor onboarding packages included in this package, with expected agent outcomes.")
    st.divider()

    for case_id, manifest in CASE_MANIFESTS.items():
        result = st.session_state.analyses.get(case_id)
        status_badge = ""
        if result:
            triage = result.get("triage_output") or {}
            risk_raw = triage.get("risk_tier", "?").upper()
            status_badge = f"  ·  {RISK_COLOR.get(risk_raw, '⚪')} {risk_raw}"

        with st.expander(f"**{manifest['title']}**{status_badge}", expanded=True):
            st.caption(manifest["description"])
            tc1, tc2 = st.columns([1, 2])

            with tc1:
                st.markdown("**Expected outcomes**")
                st.markdown(f"- Risk tier: `{manifest['expected_risk']}`")
                st.markdown(f"- Recommendation: `{manifest['expected_recommendation']}`")
                st.markdown(f"- Min blocking issues: `{manifest['expected_blocking_count']}`")

                if result:
                    triage = result.get("triage_output") or {}
                    actual_risk = triage.get("risk_tier", "?")
                    actual_rec = triage.get("recommendation", "?")
                    actual_blocking = len(triage.get("blocking_issues") or [])
                    st.markdown("**Actual results**")
                    st.markdown(
                        f"- Risk: {'✅' if actual_risk == manifest['expected_risk'] else '❌'} `{actual_risk}`"
                    )
                    st.markdown(
                        f"- Rec: {'✅' if actual_rec == manifest['expected_recommendation'] else '❌'} `{actual_rec}`"
                    )
                    st.markdown(
                        f"- Blocking: {'✅' if actual_blocking >= manifest['expected_blocking_count'] else '❌'} `{actual_blocking}`"
                    )

            with tc2:
                st.markdown("**File manifest**")
                case_dir = CASES_PATH / case_id
                if case_dir.exists():
                    for fpath in sorted(case_dir.iterdir()):
                        icon = FILE_ICONS.get(fpath.suffix, "📄")
                        size_kb = fpath.stat().st_size / 1024
                        st.markdown(f"{icon} `{fpath.name}` &nbsp; {size_kb:.1f} KB")
                else:
                    st.warning(f"Case directory not found: {case_dir}")

    st.divider()
    st.subheader("Batch Evaluation")

    analyzed = [cid for cid in CASE_ORDER if cid in st.session_state.analyses]
    unanalyzed = [cid for cid in CASE_ORDER if cid not in st.session_state.analyses]

    if unanalyzed:
        st.warning(
            f"{len(unanalyzed)} case(s) not yet analyzed: "
            + ", ".join(CASE_META[c]["vendor"] for c in unanalyzed)
        )

    if st.button(
        "▶ Run Evaluation on All Analyzed Cases",
        type="primary",
        disabled=len(analyzed) == 0,
    ):
        scores = []
        for case_id in analyzed:
            manifest = CASE_MANIFESTS[case_id]
            triage = (st.session_state.analyses[case_id].get("triage_output") or {})
            actual_risk = triage.get("risk_tier", "?")
            actual_rec = triage.get("recommendation", "?")
            actual_blocking = len(triage.get("blocking_issues") or [])

            risk_ok = actual_risk == manifest["expected_risk"]
            rec_ok = actual_rec == manifest["expected_recommendation"]
            block_ok = actual_blocking >= manifest["expected_blocking_count"]
            score = sum([risk_ok, rec_ok, block_ok])

            scores.append({
                "Case": manifest["title"].split(" · ")[0],
                "Vendor": manifest["title"].split(" · ", 1)[-1],
                "Risk ✓": "✅" if risk_ok else f"❌  got `{actual_risk}`",
                "Rec ✓": "✅" if rec_ok else f"❌  got `{actual_rec}`",
                "Blocking ✓": "✅" if block_ok else f"❌  got {actual_blocking}",
                "Score": f"{score}/3",
            })
        st.session_state.test_scores = scores

    if st.session_state.test_scores:
        scores = st.session_state.test_scores
        passed = sum(1 for s in scores if s["Score"] == "3/3")
        st.metric("Cases passing all checks", f"{passed}/{len(scores)}")
        st.dataframe(
            pd.DataFrame(scores),
            use_container_width=True,
            hide_index=True,
        )
