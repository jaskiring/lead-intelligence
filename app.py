import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from sheets import (
    normalize_refrens_csv,
    load_leads,
    upsert_leads,
    atomic_pick,
)
from scoring import score_leads

# ======================================================
# CONFIG
# ======================================================
SPREADSHEET_ID = "1JjcxzsJpf-s92-w_Mc10K3dL_SewejThMLzj4O-7pbs"
WORKSHEET_NAME = "leads_master"

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
# SLA + SORT
# ======================================================
def compute_sla(df):
    if "last_refresh" not in df.columns:
        df["lead_age_days"] = ""
        df["sla_status"] = ""
        return df

    now = datetime.now(timezone.utc)

    def age_days(ts):
        try:
            return (now - datetime.fromisoformat(ts)).days
        except:
            return ""

    df["lead_age_days"] = df["last_refresh"].apply(age_days)

    def sla(row):
        if row.get("intent_band") == "High":
            if row.get("lead_age_days", 0) >= 7:
                return "URGENT"
            return "WITHIN_SLA"
        return ""

    df["sla_status"] = df.apply(sla, axis=1)
    return df


def sort_by_priority(df):
    sla_rank = {"URGENT": 0, "WITHIN_SLA": 1, "": 2}
    intent_rank = {"High": 0, "Medium": 1, "Low": 2}

    df["_sla_rank"] = df["sla_status"].map(sla_rank).fillna(3)
    df["_intent_rank"] = df["intent_band"].map(intent_rank).fillna(3)

    df = df.sort_values(
        by=["_sla_rank", "_intent_rank", "intent_score"],
        ascending=[True, True, False],
    )

    return df.drop(columns=["_sla_rank", "_intent_rank"], errors="ignore")

# ======================================================
# UI BASE
# ======================================================
st.set_page_config(page_title="Lead Intelligence Portal", layout="wide")
st.title("🧠 Lead Intelligence Portal")

st.markdown(
    """
    <style>
    .card {
        border-radius:12px;
        padding:14px;
        margin-bottom:16px;
        background:#020617;
        border:1px solid #1e293b;
    }
    .badge-urgent {
        background:#7f1d1d;
        color:white;
        padding:4px 8px;
        border-radius:6px;
        font-size:12px;
    }
    .badge-ok {
        background:#064e3b;
        color:white;
        padding:4px 8px;
        border-radius:6px;
        font-size:12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

tabs = st.tabs([
    "🧑‍💼 Rep Drawer",
    "📁 My Leads",
    "♻️ Recoverable Leads",
    "🔐 Admin",
])

# ======================================================
# CARD RENDERER
# ======================================================
def render_lead_card(row, allow_pick: bool):
    phone = row.get("phone", "")
    picked = str(row.get("picked", "")).lower() == "true"

    sla = row.get("sla_status", "")
    if sla == "URGENT":
        badge = "<span class='badge-urgent'>🔴 URGENT</span>"
    elif sla == "WITHIN_SLA":
        badge = "<span class='badge-ok'>🟢 Within SLA</span>"
    else:
        badge = ""

    st.markdown(
        f"""
        <div class="card">
        {badge}<br><br>
        <b>📞 {phone}</b><br>
        {row.get("name","")}<br><br>

        🏙 {row.get("city","")}<br>
        🔥 {row.get("intent_band","")} ({row.get("intent_score","")})<br>
        🕒 {row.get("timeline","")}<br>
        ❗ {row.get("objection_type","")}<br>
        🩺 {row.get("consultation_status","")}<br>
        📌 {row.get("status","")}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if picked:
        st.error(f"🔒 Picked by {row.get('picked_by','')}")
    elif allow_pick:
        if st.button("✅ Pick Lead", key=f"pick_{phone}", use_container_width=True):
            ok, msg = atomic_pick(sheet, phone, st.session_state.rep)
            if ok:
                st.rerun()
            else:
                st.error(msg)

# ======================================================
# REP DRAWER
# ======================================================
with tabs[0]:
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
        df = sort_by_priority(compute_sla(load_leads(sheet)))
        rows = [df.iloc[i:i+3] for i in range(0, len(df), 3)]
        for group in rows:
            cols = st.columns(3)
            for col, (_, row) in zip(cols, group.iterrows()):
                with col:
                    render_lead_card(row, allow_pick=True)

# ======================================================
# MY LEADS
# ======================================================
with tabs[1]:
    if st.session_state.rep:
        df = compute_sla(load_leads(sheet))
        mine = df[df["picked_by"] == st.session_state.rep]
        rows = [mine.iloc[i:i+3] for i in range(0, len(mine), 3)]
        for group in rows:
            cols = st.columns(3)
            for col, (_, row) in zip(cols, group.iterrows()):
                with col:
                    render_lead_card(row, allow_pick=False)

# ======================================================
# RECOVERABLE LEADS (NOW PICKABLE ✅)
# ======================================================
with tabs[2]:
    df = compute_sla(load_leads(sheet))

    recoverable = df[
        (df["intent_band"].isin(["High", "Medium"]))
        & (~df["consultation_status"].str.lower().isin(["done"]))
        & (
            df["status"].str.lower().isin(["lost", "offered but declined"])
            | df["status"].str.lower().str.contains("lost", na=False)
        )
    ]

    if recoverable.empty:
        st.info("No recoverable leads at the moment.")
    else:
        recoverable = sort_by_priority(recoverable)
        rows = [recoverable.iloc[i:i+3] for i in range(0, len(recoverable), 3)]

        for group in rows:
            cols = st.columns(3)
            for col, (_, row) in zip(cols, group.iterrows()):
                with col:
                    render_lead_card(row, allow_pick=True)

                    objection = str(row.get("objection_type","")).lower()
                    if "timing" in objection:
                        st.info("⏳ Retry angle: Create urgency (age, outcomes, slots)")
                    elif "cost" in objection:
                        st.info("💰 Retry angle: Reframe value / financing")
                    elif row.get("consultation_status","").lower() == "not offered":
                        st.info("🩺 Retry angle: Low-commitment consultation reassurance")
                    else:
                        st.info("🧠 Retry angle: Trust + education")

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
            if st.button("Run Scoring + Update"):
                clean = normalize_refrens_csv(raw)
                scored = score_leads(clean)
                scored["last_refresh"] = datetime.now(timezone.utc).isoformat()
                upsert_leads(sheet, scored)
                st.success("Sheet updated successfully")