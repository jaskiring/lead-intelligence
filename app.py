import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from scoring import score_leads
from sheets import (
    normalize_refrens_csv,
    load_leads,
    upsert_leads,
    atomic_pick,
)

# ======================================================
# CONFIG
# ======================================================
WORKSHEET_NAME = "leads_master"
SPREADSHEET_ID = "1JjcxzsJpf-s92-w_Mc10K3dL_SewejThMLzj4O-7pbs"

ADMIN_PASSWORD = st.secrets["auth"]["admin_password"]
REP_PASSWORDS = st.secrets["auth"]["reps"]

# ======================================================
# GOOGLE SHEET
# ======================================================
@st.cache_resource
def get_sheet():
    from google.oauth2.service_account import Credentials
    import gspread

    creds = Credentials.from_service_account_info(
        st.secrets["google_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)

sheet = get_sheet()

# ======================================================
# SESSION
# ======================================================
st.session_state.setdefault("rep", None)
st.session_state.setdefault("admin", False)

# ======================================================
# SLA + PRIORITY
# ======================================================
def compute_sla_and_priority(row):
    last_refresh = row.get("last_refresh")
    intent = row.get("intent_band", "")

    try:
        last = datetime.fromisoformat(last_refresh)
        age_days = (datetime.now(timezone.utc) - last).days
    except Exception:
        return "", "⚪ No SLA", 4, "sla-none"

    # Priority: lower = more important
    if intent == "High":
        if age_days > 10:
            return age_days, "🔴 Breached", 1, "sla-breach"
        elif age_days > 7:
            return age_days, "🟡 At Risk", 2, "sla-risk"
        else:
            return age_days, "🟢 Within SLA", 3, "sla-ok"

    if intent == "Medium":
        if age_days > 14:
            return age_days, "🟡 At Risk", 2, "sla-risk"
        else:
            return age_days, "🟢 Within SLA", 3, "sla-ok"

    return age_days, "⚪ No SLA", 4, "sla-none"

# ======================================================
# UI
# ======================================================
st.set_page_config(page_title="Lead Intelligence Portal", layout="wide")
st.title("🧠 Lead Intelligence Portal")

st.markdown(
    """
    <style>
    .sla-ok { background:#0f172a; border-radius:12px; padding:14px; }
    .sla-risk { background:#3a2f00; border:2px solid #facc15; border-radius:12px; padding:14px; }
    .sla-breach { background:#3a0f0f; border:2px solid #ef4444; border-radius:12px; padding:14px; }
    .sla-none { background:#020617; border-radius:12px; padding:14px; }
    </style>
    """,
    unsafe_allow_html=True,
)

tabs = st.tabs([
    "📊 Dashboard",
    "🧑‍💼 Rep Drawer",
    "📂 My Leads",
    "🔐 Admin"
])

# ======================================================
# DASHBOARD
# ======================================================
with tabs[0]:
    df = load_leads(sheet)
    st.dataframe(df, use_container_width=True)

# ======================================================
# REP DRAWER (AUTO-SORTED)
# ======================================================
with tabs[1]:
    if not st.session_state.rep:
        name = st.selectbox("Your Name", list(REP_PASSWORDS.keys()))
        pwd = st.text_input("Password", type="password")
        if st.button("Login"):
            if REP_PASSWORDS.get(name) == pwd:
                st.session_state.rep = name
                st.rerun()
            else:
                st.error("Invalid password")
    else:
        st.success(f"Logged in as {st.session_state.rep}")

        df = load_leads(sheet)

        if df.empty:
            st.info("No leads available.")
        else:
            # ----- compute SLA + priority
            meta = df.apply(compute_sla_and_priority, axis=1, result_type="expand")
            df["age_days"], df["sla_status"], df["priority"], df["sla_class"] = meta.T.values

            # ----- auto sort
            df = df.sort_values(
                by=["priority", "intent_band", "age_days"],
                ascending=[True, False, False],
            )

            cols = st.columns(3)

            for idx, row in df.iterrows():
                with cols[idx % 3]:
                    phone = row.get("phone", "")
                    picked = str(row.get("picked", "")).lower() == "true"

                    st.markdown(
                        f"""
                        <div class="{row.sla_class}">
                        <h4>📞 {phone}</h4>
                        <b>{row.get("name","")}</b><br>
                        🏙 {row.get("city","")}<br><br>

                        🔥 Intent: <b>{row.intent_band}</b><br>
                        ⏱ Age: {row.age_days} days<br>
                        🚦 SLA: <b>{row.sla_status}</b><br><br>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    if picked:
                        st.error(f"🔒 Picked by {row.get('picked_by','')}")
                    else:
                        if st.button(
                            "✅ Pick Lead",
                            key=f"pick_{idx}_{phone}",
                            use_container_width=True,
                        ):
                            ok, msg = atomic_pick(sheet, phone, st.session_state.rep)
                            if ok:
                                st.rerun()
                            else:
                                st.error(msg)

# ======================================================
# MY LEADS (AUTO-SORTED)
# ======================================================
with tabs[2]:
    if not st.session_state.rep:
        st.info("Login to see your leads.")
    else:
        df = load_leads(sheet)
        df = df[df["picked_by"] == st.session_state.rep]

        if df.empty:
            st.info("No picked leads yet.")
        else:
            meta = df.apply(compute_sla_and_priority, axis=1, result_type="expand")
            df["age_days"], df["sla_status"], df["priority"], df["sla_class"] = meta.T.values

            df = df.sort_values(by=["priority", "age_days"])

            cols = st.columns(2)
            for idx, row in df.iterrows():
                with cols[idx % 2]:
                    st.markdown(
                        f"""
                        <div class="{row.sla_class}">
                        <h4>📞 {row.phone}</h4>
                        🏙 {row.city}<br><br>
                        🔥 {row.intent_band}<br>
                        ⏱ {row.age_days} days<br>
                        🚦 {row.sla_status}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

# ======================================================
# ADMIN
# ======================================================
with tabs[3]:
    if not st.session_state.admin:
        pwd = st.text_input("Admin Password", type="password")
        if st.button("Unlock Admin"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.admin = True
                st.success("Admin unlocked")
            else:
                st.error("Wrong password")
    else:
        file = st.file_uploader("Upload Refrens CSV", type="csv")
        if file:
            raw = pd.read_csv(file)
            st.dataframe(raw.head())

            if st.button("Run Scoring + Update"):
                clean = normalize_refrens_csv(raw)
                scored = score_leads(clean)
                scored["last_refresh"] = datetime.now(timezone.utc).isoformat()
                upsert_leads(sheet, scored)
                st.success("Sheet updated correctly")