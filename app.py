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
# SLA + SORTING
# ======================================================
def compute_sla(df: pd.DataFrame) -> pd.DataFrame:
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


def sort_for_rep_drawer(df: pd.DataFrame) -> pd.DataFrame:
    priority = {
        "URGENT": 0,
        "WITHIN_SLA": 1,
        "": 2,
    }
    intent_rank = {
        "High": 0,
        "Medium": 1,
        "Low": 2,
    }

    df["_sla_rank"] = df["sla_status"].map(priority).fillna(3)
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
# CARD RENDERER (WITH SLA + ACTION)
# ======================================================
def render_lead_card(row, allow_pick: bool):
    phone = row.get("phone", "")
    picked = str(row.get("picked", "")).lower() == "true"

    # SLA Badge
    sla = row.get("sla_status", "")
    if sla == "URGENT":
        sla_badge = "<span class='badge-urgent'>🔴 URGENT – ACTION NEEDED</span>"
    elif sla == "WITHIN_SLA":
        sla_badge = "<span class='badge-ok'>🟢 Within SLA</span>"
    else:
        sla_badge = ""

    st.markdown(
        f"""
        <div class="card">
        {sla_badge}<br><br>
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

    # Action Hint
    if row.get("intent_band") == "High" and row.get("consultation_status") != "Done":
        st.info(
            "🧠 **Suggested action:** Reassurance + urgency (age, outcomes, consultation booking)"
        )

    # Pick Control
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
# REP DRAWER (ALL LEADS, SORTED)
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
        df = compute_sla(df)
        df = sort_for_rep_drawer(df)

        if df.empty:
            st.info("No leads available.")
        else:
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
    if not st.session_state.rep:
        st.info("Login to view your leads.")
    else:
        df = load_leads(sheet)
        df = compute_sla(df)
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
# RECOVERABLE LOST LEADS
# ======================================================
with tabs[2]:
    df = load_leads(sheet)
    df = compute_sla(df)
    df = sort_for_rep_drawer(df)

    recoverable = df[
        (df["status"].str.lower() == "lost") &
        (df["intent_band"].isin(["High", "Medium"])) &
        (df["consultation_status"].str.lower() != "done") &
        (~df["objection_type"].str.lower().isin(
            ["not interested", "spam", "invalid"]
        ))
    ]

    if recoverable.empty:
        st.info("No recoverable lost leads right now.")
    else:
        rows = [recoverable.iloc[i:i+3] for i in range(0, len(recoverable), 3)]

        for group in rows:
            cols = st.columns(3)
            for col, (_, row) in zip(cols, group.iterrows()):
                with col:
                    render_lead_card(row, allow_pick=False)

                    # Retry strategy
                    objection = row.get("objection_type", "").lower()

                    if "timing" in objection:
                        strategy = "Create urgency (age, outcomes, limited slots)"
                    elif "cost" in objection or "insurance" in objection:
                        strategy = "Reframe value, financing, outcomes"
                    elif "no response" in objection:
                        strategy = "Soft re-entry + reassurance"
                    else:
                        strategy = "Rebuild trust + low-commitment consultation"

                    st.warning(f"🔁 Suggested retry: {strategy}")
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