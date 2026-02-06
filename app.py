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
def compute_sla(row):
    last_refresh = row.get("last_refresh")
    intent = row.get("intent_band")

    try:
        last = datetime.fromisoformat(last_refresh)
        age_days = (datetime.now(timezone.utc) - last).days
    except Exception:
        return "", "⚪ No SLA", 4

    if intent == "High":
        if age_days > 10:
            return age_days, "🔴 Breached", 1
        elif age_days > 7:
            return age_days, "🟡 At Risk", 2
        else:
            return age_days, "🟢 Within SLA", 3

    if intent == "Medium":
        if age_days > 14:
            return age_days, "🟡 At Risk", 2
        else:
            return age_days, "🟢 Within SLA", 3

    return age_days, "⚪ No SLA", 4

# ======================================================
# UI
# ======================================================
st.set_page_config(page_title="Lead Intelligence Portal", layout="wide")
st.title("🧠 Lead Intelligence Portal")

tabs = st.tabs([
    "📊 Dashboard",
    "🧑‍💼 Rep Drawer",
    "📂 My Leads",
    "🔥 SLA War Room",
    "🔐 Admin"
])

# ======================================================
# DASHBOARD
# ======================================================
with tabs[0]:
    df = load_leads(sheet)
    st.dataframe(df, use_container_width=True)

# ======================================================
# REP DRAWER
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

        if df.empty:
            st.info("No available leads.")
        else:
            cols = st.columns(3)
            for idx, row in df.iterrows():
                with cols[idx % 3]:
                    st.markdown(
                        f"""
                        **📞 {row.phone}**  
                        🔥 {row.intent_band}  
                        🏙 {row.city}
                        """
                    )
                    if st.button("Pick Lead", key=f"pick_{idx}_{row.phone}"):
                        ok, msg = atomic_pick(sheet, row.phone, st.session_state.rep)
                        if ok:
                            st.rerun()
                        else:
                            st.error(msg)

# ======================================================
# MY LEADS
# ======================================================
with tabs[2]:
    if not st.session_state.rep:
        st.info("Login to view your leads.")
    else:
        df = load_leads(sheet)
        df = df[df["picked_by"] == st.session_state.rep]

        if df.empty:
            st.info("No picked leads.")
        else:
            st.dataframe(df, use_container_width=True)

# ======================================================
# 🔥 SLA WAR ROOM (ADMIN VIEW)
# ======================================================
with tabs[3]:
    if not st.session_state.admin:
        st.info("Admin access required.")
    else:
        df = load_leads(sheet)

        meta = df.apply(compute_sla, axis=1, result_type="expand")
        df["lead_age_days"], df["sla_status"], df["priority"] = meta.T.values

        critical = df[
            (df["sla_status"].isin(["🔴 Breached", "🟡 At Risk"]))
            & (df["intent_band"].isin(["High", "Medium"]))
        ].sort_values(by=["priority", "lead_age_days"], ascending=[True, False])

        if critical.empty:
            st.success("🎉 No SLA issues right now.")
        else:
            st.error("🔥 SLA Issues Requiring Attention")
            st.dataframe(
                critical[
                    [
                        "phone",
                        "name",
                        "city",
                        "intent_band",
                        "lead_age_days",
                        "sla_status",
                        "picked_by",
                    ]
                ],
                use_container_width=True,
            )

# ======================================================
# ADMIN
# ======================================================
with tabs[4]:
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