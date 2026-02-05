import streamlit as st
import pandas as pd
from datetime import datetime

from scoring import score_leads
from sheets import connect_sheet, load_leads, upsert_leads

# -----------------------
# CONFIG
# -----------------------
WORKSHEET_NAME = "leads_master"

ADMIN_PASSWORD = "admin123"
REP_PASSWORDS = {
    "Rahul": "rahul123",
    "Amit": "amit123",
    "Priya": "priya123",
}

# -----------------------
# AUTH / SESSION
# -----------------------
if "rep_name" not in st.session_state:
    st.session_state.rep_name = None

if "admin_ok" not in st.session_state:
    st.session_state.admin_ok = False

# -----------------------
# GOOGLE SHEETS CONNECT
# -----------------------
@st.cache_resource
@st.cache_resource
def get_sheet():
    from google.oauth2.service_account import Credentials
    import gspread

    creds = Credentials.from_service_account_info(
        st.secrets["google_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )

    client = gspread.authorize(creds)
    sheet = client.open_by_key(
        "1JjcxzsJpf-s92-w_Mc10K3dL_SewejThMLzj4O-7pbs"
    ).worksheet(WORKSHEET_NAME)

    return sheet
    from google.oauth2.service_account import Credentials
    import json

    creds_dict = json.loads(st.secrets["service_account_json"])
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )

    import gspread
    client = gspread.authorize(creds)
    sheet = client.open_by_key(
        "1JjcxzsJpf-s92-w_Mc10K3dL_SewejThMLzj4O-7pbs"
    ).worksheet(WORKSHEET_NAME)

    return sheet
sheet = get_sheet()

# -----------------------
# UI
# -----------------------
st.set_page_config(page_title="Lead Intelligence Portal", layout="wide")
st.title("🧠 Lead Intelligence Portal")

tabs = st.tabs(["📊 Dashboard", "🧑‍💼 Rep Drawer", "🔐 Admin"])

# =======================
# DASHBOARD (READ-ONLY)
# =======================
with tabs[0]:
    st.subheader("All Leads")

    df = load_leads(sheet)

    if df.empty:
        st.info("No leads yet. Waiting for admin upload.")
    else:
        # Sorting: recent first, high intent first
        if "last_refresh" in df.columns:
            df = df.sort_values(
                by=["last_refresh", "intent_score"],
                ascending=[False, False]
            )

        st.dataframe(df, use_container_width=True)

# =======================
# REP DRAWER (PICK ONLY)
# =======================
with tabs[1]:
    st.subheader("Rep Drawer")

    if not st.session_state.rep_name:
        name = st.selectbox("Your Name", list(REP_PASSWORDS.keys()))
        pwd = st.text_input("Password", type="password")
        if st.button("Start Session"):
            if REP_PASSWORDS.get(name) == pwd:
                st.session_state.rep_name = name
                st.success(f"Session started for {name}")
            else:
                st.error("Invalid password")
    else:
        st.success(f"Logged in as {st.session_state.rep_name}")

        df = load_leads(sheet)

        if df.empty:
            st.info("No leads available.")
        else:
            available = df[(df["picked"] != True) | (df["picked"].isna())]

            st.write("### Available Leads")
            for idx, row in available.iterrows():
                with st.expander(f"{row.get('phone')} | {row.get('intent_band')}"):
                    st.write(f"Intent Score: {row.get('intent_score')}")
                    st.write(f"Lead State: {row.get('lead_state')}")

                    if st.button("Pick Lead", key=f"pick_{idx}"):
                        # Update only pick fields
                        row_update = row.copy()
                        row_update["picked"] = True
                        row_update["picked_by"] = st.session_state.rep_name
                        row_update["picked_at"] = datetime.now().isoformat()

                        upsert_leads(sheet, pd.DataFrame([row_update]), lead_key="phone")
                        st.success("Lead picked. Please update Refrens as well.")
                        st.rerun()

# =======================
# ADMIN PANEL
# =======================
with tabs[2]:
    st.subheader("Admin Panel")

    if not st.session_state.admin_ok:
        admin_pwd = st.text_input("Admin Password", type="password")
        if st.button("Unlock Admin"):
            if admin_pwd == ADMIN_PASSWORD:
                st.session_state.admin_ok = True
                st.success("Admin unlocked")
            else:
                st.error("Wrong password")
    else:
        uploaded = st.file_uploader("Upload Refrens CSV", type=["csv"])
        if uploaded:
            df = pd.read_csv(uploaded)

            st.write("Preview:")
            st.dataframe(df.head())

            if st.button("Run Scoring + Update"):
                scored = score_leads(df)
                scored["last_refresh"] = datetime.now().isoformat()

                upsert_leads(sheet, scored, lead_key="phone")
                st.success("Sheet updated successfully")