import os
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import streamlit as st
import pandas as pd
from parsers import load_case, load_policies
from agent import run_vendor_agent
from mock_data import get_mock_result

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_PATH = str(Path(__file__).parent.parent)
AUDIT_LOG = Path(__file__).parent / "audit_log.json"

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")

# Support both local .env and Streamlit Cloud secrets
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

CATEGORIES = ["Finance", "Legal", "Security", "Procurement", "Data Handling"]

CATEGORY_TOOL_MAP = {
    "Finance": ["lookup_budget", "calculate_total_contract_value", "determine_required_approvals"],
    "Legal": ["extract_contract_clauses"],
    "Security": ["classify_data_sensitivity"],
    "Procurement": ["check_existing_vendor", "validate_cross_document_consistency"],
    "Data Handling": ["classify_data_sensitivity"],
}

CATEGORY_POLICY_MAP = {
    "Finance": ["Finance", "finance_approval_matrix"],
    "Legal": ["Legal", "legal_review_policy"],
    "Security": ["Security", "security_review_policy"],
    "Procurement": ["Procurement", "procurement_policy", "vendor_risk_policy"],
    "Data Handling": ["Data Handling", "data_handling_policy"],
}

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "page": "overview",           # "overview" | "detail"
    "selected_case": None,
    "selected_category": None,
    "analyses": {},               # case_id → agent result dict
    "decisions": {},              # case_id → final decision
    "category_decisions": {},     # case_id → {category → decision dict}
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


def go_overview():
    st.session_state.page = "overview"
    st.session_state.selected_category = None


def go_detail(case_id: str):
    st.session_state.page = "detail"
    st.session_state.selected_case = case_id
    st.session_state.selected_category = None


def get_case_status(case_id: str) -> str:
    """Compute display status for a case."""
    result = st.session_state.analyses.get(case_id)
    final = st.session_state.decisions.get(case_id)
    if not result:
        return "⬜ Pending Analysis"
    if final:
        outcome = final.get("overall", "approved")
        return {"blocked": "🔴 Blocked", "escalated": "🟡 Escalated", "approved": "✅ Approved"}.get(
            outcome, "✅ Approved"
        )
    triage = result.get("triage_output") or {}
    pre = result.get("pre_screen") or {}
    blocking = triage.get("blocking_issues") or []
    if blocking or pre.get("screen_result") == "block":
        return "🔴 Pending Block"
    if pre.get("screen_result") == "escalate":
        return "🟡 Pending Escalate"
    rec = triage.get("recommendation", "")
    if rec in ("escalate_to_human", "pending_information"):
        return "🟡 Pending Escalate"
    return "🟢 Pending Approve"


def get_category_status(case_id: str, category: str) -> str:
    """Compute display status for a category within a case."""
    cat_dec = st.session_state.category_decisions.get(case_id, {}).get(category)
    if cat_dec:
        r = cat_dec.get("result", "approved")
        return {"blocked": "🔴 Blocked", "escalated": "🟡 Escalated", "approved": "✅ Approved"}.get(r, "✅ Approved")

    result = st.session_state.analyses.get(case_id)
    if not result:
        return "—"
    triage = result.get("triage_output") or {}
    blocking = triage.get("blocking_issues") or []
    flags = triage.get("policy_flags") or []
    keywords = CATEGORY_POLICY_MAP.get(category, [category])

    def matches(text: str) -> bool:
        t = text.lower()
        return any(k.lower() in t for k in keywords)

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
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🏢 Vendor Onboarding")
    st.caption("AI-assisted procurement triage")
    st.divider()
    st.subheader("Run Analysis")

    labels = [m["label"] for m in CASE_META.values()]
    selected_label = st.selectbox("Select case", labels, label_visibility="collapsed")
    run_case_id = CASE_ORDER[labels.index(selected_label)]

    mock_mode = st.toggle("🧪 Mock Mode (no API key needed)", value=not bool(_API_KEY))

    if mock_mode:
        st.caption("Mock mode: uses pre-built results, no API call.")
        can_run = True
    elif not _API_KEY:
        st.error("No API key. Enable Mock Mode above, or add key to .env / Streamlit Secrets.")
        can_run = False
    elif not _API_KEY.startswith("sk-ant-"):
        masked = _API_KEY[:14] + "..." + _API_KEY[-4:]
        st.error(f"⚠️ Key format invalid: `{masked}`")
        can_run = False
    else:
        masked = _API_KEY[:14] + "..." + _API_KEY[-4:]
        st.caption(f"🔑 `{masked}` (from {_KEY_SOURCE})")
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
    if mock_mode:
        result = get_mock_result(run_case_id)
        st.session_state.analyses[run_case_id] = result
        go_detail(run_case_id)
        st.rerun()
    else:
        with st.spinner(f"Analyzing {selected_label}…"):
            try:
                case_data = load_case(run_case_id, BASE_PATH)
                policies = load_policies(BASE_PATH)
                result = run_vendor_agent(case_data, policies, _API_KEY)
                st.session_state.analyses[run_case_id] = result
                go_detail(run_case_id)
                st.rerun()
            except Exception as exc:
                st.error(f"Error: {exc}")
                st.exception(exc)


# ===========================================================================
# PAGE: OVERVIEW
# ===========================================================================
if st.session_state.page == "overview":

    # Stats
    n_total = len(CASE_ORDER)
    n_analyzed = sum(1 for c in CASE_ORDER if c in st.session_state.analyses)
    n_decided = sum(1 for c in CASE_ORDER if c in st.session_state.decisions)

    st.markdown("## Vendor Onboarding Pipeline")
    s1, s2, s3 = st.columns(3)
    s1.metric("Total Cases", n_total)
    s2.metric("Analyzed", n_analyzed)
    s3.metric("Decisions Recorded", n_decided)
    st.divider()

    # Build pipeline dataframe
    rows = []
    for case_id, meta in CASE_META.items():
        result = st.session_state.analyses.get(case_id)
        triage = (result.get("triage_output") or {}) if result else {}
        intake = {}
        if result:
            case_data_cached = load_case(case_id, BASE_PATH) if False else None
        rows.append({
            "Case": meta["label"].split(" · ")[0],
            "Vendor": meta["vendor"],
            "Category": meta["category"],
            "ACV": f"${meta['acv']:,}",
            "Risk": (
                f"{RISK_COLOR.get(triage.get('risk_tier','').upper(), '⚪')} {triage.get('risk_tier','').upper()}"
                if result else "—"
            ),
            "Status": get_case_status(case_id),
        })

    df = pd.DataFrame(rows)

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
        clicked_case = CASE_ORDER[selected_rows[0]]
        go_detail(clicked_case)
        st.rerun()

    st.caption("Click a row to open the vendor detail page.")

    with st.expander("ℹ️ How it works", expanded=False):
        st.markdown(
            """
**1 · Parse** — xlsx intake, csv quote, pdf contract, md security questionnaire, txt vendor email

**2 · Tools** — budget lookup · vendor register · TCV calculation · data sensitivity
classification · contract clause extraction · cross-document validation

**3 · Policy** — finance approval matrix · legal triggers · security rules · data handling · comms policy

**4 · Generate** — risk tier, missing docs, blocking issues, approval routing, contract flags,
draft communications *(Generator-Critic reflection for medium/high risk)*

**5 · Approve** — human reviews each policy category, records decisions, submits final outcome
"""
        )


# ===========================================================================
# PAGE: DETAIL
# ===========================================================================
elif st.session_state.page == "detail":

    selected_case = st.session_state.selected_case
    if not selected_case:
        go_overview()
        st.rerun()

    meta = CASE_META[selected_case]
    result = st.session_state.analyses.get(selected_case)

    # ── Back button ──────────────────────────────────────────────────────────
    if st.button("← Back to Overview"):
        go_overview()
        st.rerun()

    st.markdown(f"## {meta['label']}")

    if not result:
        st.info("No analysis yet. Select this case in the sidebar and click **▶ Run Agent Analysis**.")
        st.stop()

    triage = result.get("triage_output") or {}
    pre_screen = result.get("pre_screen") or {}
    reflection = result.get("reflection")
    tool_calls = result.get("tool_calls", [])

    risk_raw = triage.get("risk_tier", "?").upper()
    rec_raw = triage.get("recommendation", "?")
    blocking = triage.get("blocking_issues") or []

    # ── Quick Summary ────────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Risk Level", f"{RISK_COLOR.get(risk_raw, '⚪')} {risk_raw}")
    m2.metric("Blocking Issues", len(blocking))
    m3.metric("Missing Docs", len(triage.get("missing_documents") or []))
    m4.metric("ACV", f"${meta['acv']:,}")

    st.markdown(f"**AI Recommendation:** {REC_LABELS.get(rec_raw, rec_raw)}")

    if blocking:
        st.error(f"⛔ {len(blocking)} Blocking Issue(s) — resolve before proceeding")

    st.divider()

    # ── Category List (left) + Category Detail (right) ───────────────────────
    col_cat, col_detail = st.columns([1, 2])

    with col_cat:
        st.markdown("**Policy Categories**")
        if not st.session_state.selected_category:
            # Auto-select first category with a problem
            for cat in CATEGORIES:
                s = get_category_status(selected_case, cat)
                if "Block" in s or "Escalate" in s:
                    st.session_state.selected_category = cat
                    break
            if not st.session_state.selected_category:
                st.session_state.selected_category = CATEGORIES[0]

        for cat in CATEGORIES:
            status = get_category_status(selected_case, cat)
            is_active = st.session_state.selected_category == cat
            label = f"{cat}   {status}"
            if st.button(
                label,
                key=f"cat_{selected_case}_{cat}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.selected_category = cat
                st.rerun()

    with col_detail:
        active_cat = st.session_state.selected_category or CATEGORIES[0]
        cat_status = get_category_status(selected_case, active_cat)

        st.markdown(f"### {active_cat}   {cat_status}")
        st.divider()

        # Policy flags for this category
        all_flags = triage.get("policy_flags") or []
        keywords = CATEGORY_POLICY_MAP.get(active_cat, [active_cat])
        cat_flags = [
            f for f in all_flags
            if any(k.lower() in f.get("policy", "").lower() or k.lower() in f.get("issue", "").lower()
                   for k in keywords)
        ]

        # Blocking issues for this category
        cat_blocking = [
            b for b in blocking
            if any(k.lower() in b.lower() for k in keywords)
        ]

        if cat_blocking:
            st.markdown("**Blocking Issues**")
            for b in cat_blocking:
                with st.expander(f"🔴 {b[:80]}{'…' if len(b) > 80 else ''}", expanded=True):
                    st.write(b)

        if cat_flags:
            st.markdown("**Policy Flags**")
            for flag in cat_flags:
                sev = flag.get("severity", "info")
                icon = {"blocking": "🔴", "warning": "⚠️", "info": "ℹ️"}.get(sev, "ℹ️")
                expanded = sev == "blocking"
                with st.expander(
                    f"{icon} [{flag.get('policy','')}] {flag.get('issue','')[:70]}",
                    expanded=expanded,
                ):
                    st.markdown(f"**Policy:** {flag.get('policy','')}")
                    st.markdown(f"**Issue:** {flag.get('issue','')}")
                    st.markdown(f"**Severity:** {sev}")

        if not cat_blocking and not cat_flags:
            st.success("No issues detected for this category.")

        # AI Thinking expander
        cat_tools = CATEGORY_TOOL_MAP.get(active_cat, [])
        relevant_calls = [c for c in tool_calls if c["tool"] in cat_tools]
        with st.expander("🤖 AI Reasoning — click to expand", expanded=False):
            if relevant_calls:
                for call in relevant_calls:
                    st.markdown(f"**Tool: `{call['tool']}`**")
                    tc1, tc2 = st.columns(2)
                    with tc1:
                        st.caption("Input")
                        st.json(call["input"])
                    with tc2:
                        st.caption("Output")
                        st.json(call["output"])
            else:
                st.caption("No tool calls mapped to this category.")

            if reflection:
                gen = reflection.get("generator", {})
                critic = reflection.get("critic", {})
                st.divider()
                st.caption("Generator-Critic reflection")
                rc1, rc2 = st.columns(2)
                with rc1:
                    st.caption("Generator key findings")
                    for f in gen.get("key_findings", []):
                        if f:
                            st.markdown(f"- {f}")
                with rc2:
                    st.caption("Critic notes")
                    for f in critic.get("missed_findings", []):
                        st.markdown(f"- ⚠ {f}")
                    for f in critic.get("confirmed_findings", []):
                        st.markdown(f"- ✓ {f}")

        # Category HITL
        st.divider()
        st.markdown(f"**Human Decision — {active_cat}**")
        cat_dec = st.session_state.category_decisions.get(selected_case, {}).get(active_cat)

        if cat_dec:
            result_label = {"approved": "✅ Approved", "escalated": "🟡 Escalated", "blocked": "🔴 Blocked"}.get(
                cat_dec["result"], cat_dec["result"]
            )
            override_note = " (Override)" if cat_dec["action"] == "override" else ""
            st.success(f"**Decision recorded:** {result_label}{override_note}")
            if cat_dec.get("justification"):
                st.markdown(f"**Justification:** {cat_dec['justification']}")
            st.caption(f"Recorded at {cat_dec['timestamp']}")
            if st.button("↩ Reset", key=f"reset_cat_{selected_case}_{active_cat}"):
                if selected_case in st.session_state.category_decisions:
                    st.session_state.category_decisions[selected_case].pop(active_cat, None)
                st.rerun()

        else:
            # Determine AI recommendation for this category
            ai_result = "approved"
            if "Block" in cat_status:
                ai_result = "blocked"
            elif "Escalate" in cat_status:
                ai_result = "escalated"

            confirm_label = {
                "blocked": "🔴 Confirm Block",
                "escalated": "🟡 Confirm Escalate",
                "approved": "✅ Confirm Approve",
            }[ai_result]

            h1, h2 = st.columns(2)
            confirm_clicked = h1.button(
                confirm_label, type="primary", key=f"confirm_cat_{selected_case}_{active_cat}"
            )
            override_clicked = h2.button(
                "✏️ Override", key=f"override_cat_{selected_case}_{active_cat}"
            )

            override_key = f"show_override_{selected_case}_{active_cat}"
            if override_key not in st.session_state:
                st.session_state[override_key] = False

            if confirm_clicked:
                now = datetime.now()
                if selected_case not in st.session_state.category_decisions:
                    st.session_state.category_decisions[selected_case] = {}
                st.session_state.category_decisions[selected_case][active_cat] = {
                    "action": "confirm",
                    "result": ai_result,
                    "justification": "",
                    "timestamp": now.strftime("%H:%M %b %d"),
                }
                st.rerun()

            if override_clicked:
                st.session_state[override_key] = True

            if st.session_state[override_key]:
                just = st.text_area(
                    "Justification (required):",
                    key=f"just_{selected_case}_{active_cat}",
                    height=80,
                )
                override_result = st.radio(
                    "Override decision:",
                    ["approved", "escalated", "blocked"],
                    key=f"override_result_{selected_case}_{active_cat}",
                    horizontal=True,
                )
                oc1, oc2 = st.columns(2)
                if oc1.button("✓ Confirm Override", type="primary", key=f"confirm_override_{selected_case}_{active_cat}"):
                    if not just.strip():
                        st.error("Justification is required.")
                    else:
                        now = datetime.now()
                        if selected_case not in st.session_state.category_decisions:
                            st.session_state.category_decisions[selected_case] = {}
                        st.session_state.category_decisions[selected_case][active_cat] = {
                            "action": "override",
                            "result": override_result,
                            "justification": just,
                            "timestamp": now.strftime("%H:%M %b %d"),
                        }
                        st.session_state[override_key] = False
                        st.rerun()
                if oc2.button("Cancel", key=f"cancel_override_{selected_case}_{active_cat}"):
                    st.session_state[override_key] = False
                    st.rerun()

    # ── Final Submit ─────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### Final Submit")

    cat_decisions_for_case = st.session_state.category_decisions.get(selected_case, {})
    decided = [c for c in CATEGORIES if c in cat_decisions_for_case]
    remaining = len(CATEGORIES) - len(decided)

    if remaining > 0:
        st.info(f"Complete {remaining} remaining category review(s) to submit final decision.")
        st.progress(len(decided) / len(CATEGORIES))
    else:
        # Summary table
        summary_rows = []
        for cat in CATEGORIES:
            dec = cat_decisions_for_case[cat]
            result_icon = {"approved": "✅ Approved", "escalated": "🟡 Escalated", "blocked": "🔴 Blocked"}.get(
                dec["result"], dec["result"]
            )
            override_note = f"Yes — {dec['justification'][:50]}" if dec["action"] == "override" else "No"
            summary_rows.append({"Category": cat, "Decision": result_icon, "Override?": override_note})

        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

        # Overall decision
        all_results = [cat_decisions_for_case[c]["result"] for c in CATEGORIES]
        if "blocked" in all_results:
            overall = "blocked"
            overall_label = "🔴 Blocked"
        elif "escalated" in all_results:
            overall = "escalated"
            overall_label = "🟡 Escalated"
        else:
            overall = "approved"
            overall_label = "✅ Approved"

        st.markdown(f"**Overall Decision: {overall_label}**")

        final_decision = st.session_state.decisions.get(selected_case)
        if final_decision:
            st.success(f"Final decision already submitted: **{overall_label}**")
            st.caption(f"Submitted at {final_decision.get('timestamp', '')}")
            if st.button("↩ Reset Final Decision", key=f"reset_final_{selected_case}"):
                del st.session_state.decisions[selected_case]
                st.rerun()
        else:
            if st.button("Submit Final Decision", type="primary", key=f"submit_{selected_case}"):
                now = datetime.now()
                entry = {
                    "case_id": selected_case,
                    "vendor": meta["vendor"],
                    "overall": overall,
                    "category_decisions": cat_decisions_for_case,
                    "timestamp": now.isoformat(),
                    "ai_recommendation": rec_raw,
                    "risk_tier": risk_raw,
                }
                write_audit_log(entry)
                st.session_state.decisions[selected_case] = {
                    "overall": overall,
                    "timestamp": now.strftime("%H:%M %b %d"),
                }
                go_overview()
                st.rerun()
