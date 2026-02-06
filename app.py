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
# SLA LOGIC
# ======================================================
def compute_sla(row):
    last_refresh = row.get("last_refresh")
    if not last_refresh:
        return "", "⚪ No SLA"

    try:
        last = datetime.fromisoformat(last_refresh)
        age_days = (datetime.now(timezone.utc) - last).days
    except Exception:
        return "", "⚪ No SLA"

    intent = row.get("intent_band")

    if intent == "High":
        if age_days <= 7:
            return age_days, "🟢 Within SLA"
        elif age_days <= 10:
            return age_days, "🟡 At Risk"
        else:
            return age_days, "🔴 Breached"

    if intent == "Medium":
        if age_days <= 14:
            return age_days, "🟢 Within SLA"
        else:
            return age_days, "🟡 At Risk"

    return age_days, "⚪ No SLA"

# ======================================================
# UI
# ======================================================
st.set_page_config(page_title="Lead Intelligence Portal", layout="wide")
st.title("🧠 Lead Intelligence Portal")

tabs = st.tabs([
    "📊 Dashboard",
    "🧑‍💼 Rep Drawer",
    "📂 My Leads",
    "🔐 Admin"
])

# ======================================================
# DASHBOARD
# ======================================================
with tabs[0]:
    df = load_leads(sheet)
    st.dataframe(df, use_container_width=True)

# ======================================================
# REP DRAWER (ALL AVAILABLE LEADS)
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
                    age_days, sla_status = compute_sla(row)

                    st.markdown(
                        f"""
                        ### 📞 {phone}
                        **{row.get("name", "")}**  
                        🏙️ {row.get("city", "")}
                        """
                    )

                    st.divider()

                    st.markdown(
                        f"""
                        🔥 **Intent**: `{row.get("intent_band", "")}`  
                        📊 **Score**: {row.get("intent_score", "")}  
                        🕒 **Timeline**: {row.get("timeline", "")}
                        """
                    )

                    st.divider()

                    st.markdown(
                        f"""
                        ⏱ **Lead Age**: {age_days} days  
                        🚦 **SLA**: {sla_status}
                        """
                    )

                    st.divider()

                    if picked:
                        st.error(f"🔒 Picked by {row.get('picked_by', '')}")
                    else:
                        if st.button(
                            "✅ Pick Lead",
                            key=f"pick_{idx}_{phone}",
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
# MY LEADS (PICKED BY ME)
# ======================================================
with tabs[2]:
    if not st.session_state.rep:
        st.info("Please login as a rep to view your leads.")
    else:
        df = load_leads(sheet)
        my_leads = df[
            (df["picked"].astype(str).str.lower() == "true")
            & (df["picked_by"] == st.session_state.rep)
        ]

        if my_leads.empty:
            st.info("You have not picked any leads yet.")
        else:
            cols = st.columns(2)

            for idx, row in my_leads.iterrows():
                with cols[idx % 2]:
                    age_days, sla_status = compute_sla(row)

                    st.markdown(
                        f"""
                        ### 📞 {row.get("phone", "")}
                        🏙️ {row.get("city", "")}

                        🔥 **Intent**: `{row.get("intent_band", "")}`  
                        ⏱ **Lead Age**: {age_days} days  
                        🚦 **SLA**: {sla_status}
                        """
                    )

                    st.markdown(
                        f"""
                        🕒 **Timeline**: {row.get("timeline", "")}  
                        📞 **Call Outcome**: {row.get("call_outcome", "")}  
                        ❗ **Objection**: {row.get("objection_type", "")}
                        """
                    )

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
                st.success("Sheet updated correctly")