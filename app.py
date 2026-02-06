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
    return gspread.authorize(creds).open_by_key(
        SPREADSHEET_ID
    ).worksheet(WORKSHEET_NAME)

sheet = get_sheet()

# ---------------- SESSION
st.session_state.setdefault("rep", None)
st.session_state.setdefault("admin", False)

# ---------------- UI
st.set_page_config("Lead Intelligence Portal", layout="wide")
st.title("🧠 Lead Intelligence Portal")

tabs = st.tabs(["📊 Dashboard", "🧑‍💼 Rep Drawer", "📁 My Leads", "🔐 Admin"])

# ======================================================
# DASHBOARD (TABLE)
# ======================================================
with tabs[0]:
    df = load_leads(sheet)
    st.dataframe(df, use_container_width=True)

# ======================================================
# HELPER: CARD RENDERER
# ======================================================
def render_lead_card(row, allow_pick=True):
    phone = row.get("phone", "")
    picked = str(row.get("picked", "")).lower() == "true"

    st.markdown(f"### 📞 {phone}")
    st.caption(row.get("name", ""))
    st.markdown(f"🏙️ **City:** {row.get('city', '')}")
    st.markdown(f"🔥 **Intent:** {row.get('intent_band', '')} ({row.get('intent_score', '')})")
    st.markdown(f"🕒 **Timeline:** {row.get('timeline', '')}")
    st.markdown(f"❗ **Objection:** {row.get('objection_type', '')}")
    st.markdown(f"📞 **Call Outcome:** {row.get('call_outcome', '')}")
    st.markdown(f"🩺 **Consultation:** {row.get('consultation_status', '')}")
    st.markdown(f"📌 **Status:** {row.get('status', '')}")

    st.divider()

    if picked:
        st.error(f"🔒 Picked by {row.get('picked_by', '')}")
    elif allow_pick:
        if st.button(
            "✅ Pick Lead",
            key=f"pick_{phone}",
            use_container_width=True,
        ):
            ok, msg = atomic_pick(
                sheet,
                phone=phone,
                rep_name=st.session_state.rep,
            )
            if ok:
                st.rerun()
            else:
                st.error(msg)

# ======================================================
# REP DRAWER (FIXED GRID)
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
        available = df[(df["picked"] != "TRUE") & (df["picked"] != True)]

        if available.empty:
            st.info("No available leads.")
        else:
            rows = [available.iloc[i:i+3] for i in range(0, len(available), 3)]

            for group in rows:
                cols = st.columns(3)
                for col, (_, row) in zip(cols, group.iterrows()):
                    with col:
                        render_lead_card(row, allow_pick=True)

# ======================================================
# MY LEADS (FIXED GRID)
# ======================================================
with tabs[2]:
    if not st.session_state.rep:
        st.info("Login as a rep to view your leads.")
    else:
        df = load_leads(sheet)
        mine = df[df["picked_by"] == st.session_state.rep]

        if mine.empty:
            st.info("You haven’t picked any leads yet.")
        else:
            rows = [mine.iloc[i:i+3] for i in range(0, len(mine), 3)]

            for group in rows:
                cols = st.columns(3)
                for col, (_, row) in zip(cols, group.iterrows()):
                    with col:
                        render_lead_card(row, allow_pick=False)

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
                st.success("Sheet updated successfully")