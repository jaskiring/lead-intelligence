import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from scoring import score_leads
from sheets import load_leads, upsert_leads, atomic_pick

# -----------------------
# CONFIG
# -----------------------
WORKSHEET_NAME = "leads_master"
SPREADSHEET_ID = "1JjcxzsJpf-s92-w_Mc10K3dL_SewejThMLzj4O-7pbs"

ADMIN_PASSWORD = st.secrets["auth"]["admin_password"]
REP_PASSWORDS = st.secrets["auth"]["reps"]

# -----------------------
# SESSION
# -----------------------
if "rep_name" not in st.session_state:
    st.session_state.rep_name = None

if "admin_ok" not in st.session_state:
    st.session_state.admin_ok = False

# -----------------------
# GOOGLE SHEET
# -----------------------
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
    return client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)

sheet = get_sheet()

# -----------------------
# UI
# -----------------------
st.set_page_config(page_title="Lead Intelligence Portal", layout="wide")
st.title("🧠 Lead Intelligence Portal")

tabs = st.tabs(["📊 Dashboard", "🧑‍💼 Rep Drawer", "🔐 Admin"])

# =======================
# DASHBOARD
# =======================
with tabs[0]:
    df = load_leads(sheet)
    st.dataframe(df, use_container_width=True)

# =======================
# REP DRAWER
# =======================
with tabs[1]:
    if not st.session_state.rep_name:
        name = st.selectbox("Your Name", list(REP_PASSWORDS.keys()))
        pwd = st.text_input("Password", type="password")

        if st.button("Start Session"):
            if REP_PASSWORDS.get(name) == pwd:
                st.session_state.rep_name = name
                st.rerun()
            else:
                st.error("Invalid password")
    else:
        st.success(f"Logged in as {st.session_state.rep_name}")

        df = load_leads(sheet)

        cols = st.columns(3)

        for i, row in df.iterrows():
            col = cols[i % 3]
            phone = str(row.get("phone"))
            picked = row.get("picked")
            picked_by = row.get("picked_by")

            with col:
                st.markdown(f"""
                <div style="padding:16px;border-radius:12px;
                background:#0f172a;opacity:{0.5 if picked else 1}">
                <b>📱 {phone}</b><br>
                Intent: {row.get("intent_band")}<br>
                </div>
                """, unsafe_allow_html=True)

                if picked:
                    st.error(f"🔒 Picked by {picked_by}")
                else:
                    if st.button("✅ Pick Lead", key=f"pick_{i}_{phone}"):
                        success, msg = atomic_pick(
                            sheet, phone, st.session_state.rep_name
                        )
                        if success:
                            st.success("Lead picked")
                            st.rerun()
                        else:
                            st.error(msg)

# =======================
# ADMIN
# =======================
with tabs[2]:
    if not st.session_state.admin_ok:
        pwd = st.text_input("Admin Password", type="password")
        if st.button("Unlock Admin"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.admin_ok = True
                st.rerun()
            else:
                st.error("Wrong password")
    else:
        uploaded = st.file_uploader("Upload Refrens CSV", type=["csv"])
        if uploaded:
            df = pd.read_csv(uploaded)
            if st.button("Run Scoring + Update"):
                scored = score_leads(df)
                scored["last_refresh"] = datetime.now(timezone.utc).isoformat()
                upsert_leads(sheet, scored)
                st.success("Updated")