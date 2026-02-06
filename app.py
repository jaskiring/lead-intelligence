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
    return gspread.authorize(creds).open_by_key(
        SPREADSHEET_ID
    ).worksheet(WORKSHEET_NAME)

sheet = get_sheet()

# ======================================================
# SESSION
# ======================================================
st.session_state.setdefault("rep", None)
st.session_state.setdefault("admin", False)

# ======================================================
# SLA + PRIORITY
# ======================================================
def compute_sla(row):
    try:
        last = datetime.fromisoformat(row.get("last_refresh"))
        age_days = (datetime.now(timezone.utc) - last).days
    except Exception:
        return "", "⚪ No SLA", "sla-none", 4

    intent = row.get("intent_band")

    if intent == "High":
        if age_days > 10:
            return age_days, "🔴 Breached", "sla-breach", 1
        elif age_days > 7:
            return age_days, "🟡 At Risk", "sla-risk", 2
        else:
            return age_days, "🟢 Within SLA", "sla-ok", 3

    if intent == "Medium":
        if age_days > 14:
            return age_days, "🟡 At Risk", "sla-risk", 2
        else:
            return age_days, "🟢 Within SLA", "sla-ok", 3

    return age_days, "⚪ No SLA", "sla-none", 4

# ======================================================
# UI BASE
# ======================================================
st.set_page_config(page_title="Lead Intelligence Portal", layout="wide")
st.title("🧠 Lead Intelligence Portal")

st.markdown(
    """
    <style>
    .card { border-radius:10px; padding:12px; margin-bottom:12px; }
    .sla-ok { background:#0f172a; }
    .sla-risk { background:#3a2f00; border:1px solid #facc15; }
    .sla-breach { background:#3a0f0f; border:1px solid #ef4444; }
    .sla-none { background:#020617; }
    .muted { color:#94a3b8; font-size:12px; }
    </style>
    """,
    unsafe_allow_html=True,
)

tabs = st.tabs([
    "📊 Dashboard",
    "🧑‍💼 Rep Drawer",
    "📂 My Leads",
    "🔥 SLA War Room",
    "🔐 Admin",
])

# ======================================================
# DASHBOARD
# ======================================================
with tabs[0]:
    st.dataframe(load_leads(sheet), use_container_width=True)

# ======================================================
# REP DRAWER (COMPACT PROFILE CARDS)
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
        df = df[df["picked"].astype(str).str.lower() != "true"]

        meta = df.apply(compute_sla, axis=1, result_type="expand")
        df["age"], df["sla"], df["sla_class"], df["priority"] = meta.T.values
        df = df.sort_values(by=["priority", "age"])

        cols = st.columns(3)
        for i, row in df.iterrows():
            with cols[i % 3]:
                st.markdown(
                    f"""
                    <div class="card {row.sla_class}">
                    <b>📞 {row.phone}</b><br>
                    🏙 {row.city}<br>
                    <span class="muted">{row.name}</span><br><br>

                    🔥 {row.intent_band} ({row.intent_score})<br>
                    🕒 {row.timeline}<br>
                    ❗ {row.objection_type}<br>
                    📞 {row.call_outcome}<br>
                    🩺 {row.consultation_status}<br><br>

                    ⏱ {row.age} days | {row.sla}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if st.button("Pick Lead", key=f"pick_{row.phone}"):
                    ok, msg = atomic_pick(sheet, row.phone, st.session_state.rep)
                    if ok:
                        st.rerun()
                    else:
                        st.error(msg)

# ======================================================
# MY LEADS (SAME CARD, READ-ONLY)
# ======================================================
with tabs[2]:
    if not st.session_state.rep:
        st.info("Login to see your leads.")
    else:
        df = load_leads(sheet)
        df = df[df["picked_by"] == st.session_state.rep]

        meta = df.apply(compute_sla, axis=1, result_type="expand")
        df["age"], df["sla"], df["sla_class"], df["priority"] = meta.T.values
        df = df.sort_values(by=["priority", "age"])

        cols = st.columns(3)
        for i, row in df.iterrows():
            with cols[i % 3]:
                st.markdown(
                    f"""
                    <div class="card {row.sla_class}">
                    <b>📞 {row.phone}</b><br>
                    🏙 {row.city}<br>
                    <span class="muted">{row.name}</span><br><br>

                    🔥 {row.intent_band} ({row.intent_score})<br>
                    🕒 {row.timeline}<br>
                    ❗ {row.objection_type}<br>
                    📞 {row.call_outcome}<br>
                    🩺 {row.consultation_status}<br><br>

                    ⏱ {row.age} days | {row.sla}<br>
                    🔒 Picked by you
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

# ======================================================
# 🔥 SLA WAR ROOM (ADMIN TABLE)
# ======================================================
with tabs[3]:
    if not st.session_state.admin:
        st.info("Admin access required.")
    else:
        df = load_leads(sheet)
        meta = df.apply(compute_sla, axis=1, result_type="expand")
        df["age"], df["sla"], _, df["priority"] = meta.T.values

        critical = df[df["priority"] <= 2].sort_values(by=["priority", "age"])
        st.dataframe(
            critical[
                [
                    "phone",
                    "name",
                    "city",
                    "intent_band",
                    "age",
                    "sla",
                    "picked_by",
                ]
            ],
            use_container_width=True,
        )

# ======================================================
# ADMIN UPLOAD
# ======================================================
with tabs[4]:
    if not st.session_state.admin:
        pwd = st.text_input("Admin Password", type="password")
        if st.button("Unlock Admin"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.admin = True
            else:
                st.error("Wrong password")
    else:
        file = st.file_uploader("Upload Refrens CSV", type="csv")
        if file:
            raw = pd.read_csv(file)
            if st.button("Run Scoring + Update"):
                clean = normalize_refrens_csv(raw)
                scored = score_leads(clean)
                scored["last_refresh"] = datetime.now(timezone.utc).isoformat()
                upsert_leads(sheet, scored)
                st.success("Sheet updated")