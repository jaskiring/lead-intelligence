import streamlit as st
import pandas as pd
from datetime import datetime, timezone
import logging

from scoring import score_leads
from sheets import (
    normalize_refrens_csv,
    load_leads,
    upsert_leads,
    atomic_pick,
)

# ---------------- LOGGING
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger(__name__)

# ---------------- CONFIG
WORKSHEET_NAME = "leads_master"
SPREADSHEET_ID = "1JjcxzsJpf-s92-w_Mc10K3dL_SewejThMLzj4O-7pbs"

ADMIN_PASSWORD = st.secrets["auth"]["admin_password"]
REP_PASSWORDS = st.secrets["auth"]["reps"]

# ---------------- GOOGLE SHEET
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

# ---------------- SESSION
st.session_state.setdefault("rep", None)
st.session_state.setdefault("admin", False)

# ---------------- UI
st.set_page_config("Lead Intelligence Portal", layout="wide")
st.title("🧠 Lead Intelligence Portal")

tabs = st.tabs(["📊 Dashboard", "🧑‍💼 Rep Drawer", "🔐 Admin"])

# ======================================================
# DASHBOARD
# ======================================================
with tabs[0]:
    df = load_leads(sheet)

    st.subheader("DEBUG")
    st.write("Columns:", list(df.columns))
    st.write("Phone sample:", df.get("phone", "").head(10).tolist())

    st.subheader("Leads")
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

        if df.empty:
            st.info("No leads available.")
        else:
            cols = st.columns(3)

            for idx, row in df.iterrows():
                with cols[idx % 3]:
                    phone = row.get("phone", "")
                    picked = str(row.get("picked", "")).lower() == "true"

                    st.markdown(
                        f"""
                        **📞 {phone}**  
                        🎯 Intent: **{row.get("intent_band", "")}**  
                        🕒 Timeline: {row.get("timeline", "")}  
                        🏙 City: {row.get("city", "")}  
                        """
                    )

                    if picked:
                        st.error(f"🔒 Picked by {row.get('picked_by', '')}")
                    else:
                        if st.button(
                            "✅ Pick Lead",
                            key=f"pick_{idx}_{phone}",
                        ):
                            ok, msg = atomic_pick(
                                sheet,
                                phone=phone,
                                rep_name=st.session_state.rep,
                            )
                            if ok:
                                st.success("Lead picked")
                                st.rerun()
                            else:
                                st.error(msg)

# ======================================================
# ADMIN
# ======================================================
with tabs[2]:
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
            st.write("Preview:")
            st.dataframe(raw.head())

            if st.button("Run Scoring + Update"):
                clean = normalize_refrens_csv(raw)
                scored = score_leads(clean)
                scored["last_refresh"] = datetime.now(timezone.utc).isoformat()

                upsert_leads(sheet, scored)
                st.success("Sheet updated correctly")