import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from scoring import score_leads
from sheets import open_sheet, load_leads, upsert_leads, atomic_pick


# -----------------------
# CONFIG
# -----------------------
SPREADSHEET_ID = "1JjcxzsJpf-s92-w_Mc10K3dL_SewejThMLzj4O-7pbs"
WORKSHEET_NAME = "leads_master"

ADMIN_PASSWORD = st.secrets["auth"]["admin_password"]
REP_PASSWORDS = dict(st.secrets["auth"]["reps"])


# -----------------------
# SESSION
# -----------------------
if "rep_name" not in st.session_state:
    st.session_state.rep_name = None

if "admin_ok" not in st.session_state:
    st.session_state.admin_ok = False


# -----------------------
# SHEET
# -----------------------
@st.cache_resource
def get_sheet():
    return open_sheet(SPREADSHEET_ID, WORKSHEET_NAME)


sheet = get_sheet()


# -----------------------
# UI
# -----------------------
st.set_page_config(page_title="Lead Intelligence Portal", layout="wide")
st.title("🧠 Lead Intelligence Portal")

tabs = st.tabs(["📊 Dashboard", "🧑‍💼 Rep Drawer", "🔐 Admin"])


# ======================
# DASHBOARD
# ======================
with tabs[0]:
    df = load_leads(sheet)
    if df.empty:
        st.info("No leads yet")
    else:
        st.dataframe(df, use_container_width=True)


# ======================
# REP DRAWER
# ======================
with tabs[1]:
    if not st.session_state.rep_name:
        name = st.selectbox("Your Name", list(REP_PASSWORDS.keys()))
        pwd = st.text_input("Password", type="password")
        if st.button("Start Session"):
            if REP_PASSWORDS[name] == pwd:
                st.session_state.rep_name = name
                st.success("Session started")
            else:
                st.error("Wrong password")
    else:
        df = load_leads(sheet)
        available = df[(df["picked"] != True) | (df["picked"].isna())]

        for _, row in available.iterrows():
            with st.expander(f"{row['phone']} | {row['intent_band']}"):
                if st.button("Pick Lead", key=row["phone"]):
                    ok, msg = atomic_pick(
                        sheet,
                        phone=row["phone"],
                        rep_name=st.session_state.rep_name,
                    )
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)


# ======================
# ADMIN
# ======================
with tabs[2]:
    if not st.session_state.admin_ok:
        pwd = st.text_input("Admin Password", type="password")
        if st.button("Unlock"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.admin_ok = True
                st.success("Admin unlocked")
            else:
                st.error("Wrong password")
    else:
        uploaded = st.file_uploader("Upload Refrens CSV", type="csv")
        if uploaded:
            df = pd.read_csv(uploaded)
            scored = score_leads(df)
            scored["last_refresh"] = datetime.now(timezone.utc).isoformat()
            upsert_leads(sheet, scored, lead_key="phone")
            st.success("Leads updated")