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
# UI BASE
# ======================================================
st.set_page_config(page_title="Lead Intelligence Portal", layout="wide")
st.title("🧠 Lead Intelligence Portal")

st.markdown(
    """
    <style>
    .card {
        border-radius:10px;
        padding:12px;
        margin-bottom:14px;
        background:#020617;
        border:1px solid #1e293b;
    }
    .muted {
        color:#94a3b8;
        font-size:12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

tabs = st.tabs([
    "🧑‍💼 Rep Drawer",
    "📁 My Leads",
    "🔐 Admin",
])

# ======================================================
# CARD RENDERER (LOCKED)
# ======================================================
def render_lead_card(row, allow_pick: bool):
    phone = row.get("phone", "")
    picked = str(row.get("picked", "")).lower() == "true"

    st.markdown(
        f"""
        <div class="card">
        <b>📞 {phone}</b><br>
        <span class="muted">{row.get("name","")}</span><br><br>

        🏙 <b>City:</b> {row.get("city","")}<br>
        🔥 <b>Intent:</b> {row.get("intent_band","")} ({row.get("intent_score","")})<br>
        🕒 <b>Timeline:</b> {row.get("timeline","")}<br>
        🩺 <b>Consultation:</b> {row.get("consultation_status","")}<br>
        ❗ <b>Objection:</b> {row.get("objection_type","")}<br>
        📞 <b>Call Outcome:</b> {row.get("call_outcome","")}<br>
        📌 <b>Status:</b> {row.get("status","")}<br>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if picked:
        st.error(f"🔒 Picked by {row.get('picked_by','')}")
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
        st.success(f"Logged in as {st.session_state.rep}")

        df = load_leads(sheet)
        available = df[df["picked"].astype(str).str.lower() != "true"]

        if available.empty:
            st.info("No available leads.")
        else:
            rows = [
                available.iloc[i:i+3]
                for i in range(0, len(available), 3)
            ]

            for group in rows:
                cols = st.columns(3)
                for col, (_, row) in zip(cols, group.iterrows()):
                    with col:
                        render_lead_card(row, allow_pick=True)

# ======================================================
# MY LEADS
# ======================================================
with tabs[1]:
    if not st.session_state.rep:
        st.info("Login to view your leads.")
    else:
        df = load_leads(sheet)
        mine = df[df["picked_by"] == st.session_state.rep]

        if mine.empty:
            st.info("You haven’t picked any leads yet.")
        else:
            rows = [
                mine.iloc[i:i+3]
                for i in range(0, len(mine), 3)
            ]

            for group in rows:
                cols = st.columns(3)
                for col, (_, row) in zip(cols, group.iterrows()):
                    with col:
                        render_lead_card(row, allow_pick=False)

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
            st.dataframe(raw.head())

            if st.button("Run Scoring + Update"):
                clean = normalize_refrens_csv(raw)
                scored = score_leads(clean)
                scored["last_refresh"] = datetime.now(timezone.utc).isoformat()
                upsert_leads(sheet, scored)
                st.success("Sheet updated successfully")