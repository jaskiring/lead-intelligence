import pandas as pd

CORE_CITIES = ["Mumbai", "Pune", "Surat", "Indore"]

# ======================================================
# HELPERS
# ======================================================
def present(x):
    return pd.notna(x) and str(x).strip() != ""


# ======================================================
# SCORING
# ======================================================
def score_leads(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]

    # -----------------------------
    # MEDICAL REASON
    # -----------------------------
    def medical_score(reason):
        if not present(reason):
            return 0
        r = str(reason).lower()
        if "high eye power" in r or "power" in r:
            return 40
        if "medical" in r:
            return 35
        if "lifestyle" in r:
            return 25
        if "cosmetic" in r:
            return 15
        if "explor" in r:
            return 5
        return 0

    # -----------------------------
    # TIMELINE
    # -----------------------------
    def timeline_score(t):
        if not present(t):
            return 0
        t = str(t).lower()
        if "15" in t:
            return 20
        if "30" in t:
            return 16
        if "1-3" in t or "1 to 3" in t:
            return 10
        if "3-6" in t:
            return 5
        if "not decided" in t:
            return 2
        return 0

    # -----------------------------
    # CITY
    # -----------------------------
    def location_score(city):
        if not present(city):
            return 0
        return 10 if city in CORE_CITIES else 6

    # -----------------------------
    # CALL OUTCOME
    # -----------------------------
    def call_score(outcome):
        if not present(outcome):
            return 0
        o = str(outcome).lower()
        if o == "positive":
            return 10
        if o == "neutral":
            return 6
        if o == "negative":
            return 2
        return 0

    # -----------------------------
    # CONSULTATION
    # -----------------------------
    def consultation_score(status):
        if not present(status):
            return 0
        s = str(status).lower()
        if s == "scheduled":
            return 12
        if s == "done":
            return 15
        if "declined" in s:
            return 6
        if s == "not offered":
            return 2
        return 0

    intent_scores = []
    intent_bands = []
    lead_states = []

    for _, row in df.iterrows():
        score = (
            medical_score(row.get("reason"))
            + timeline_score(row.get("timeline"))
            + location_score(row.get("city"))
            + call_score(row.get("call_outcome"))
            + consultation_score(row.get("consultation_status"))
        )

        intent_scores.append(score)

        if score >= 70:
            band = "High"
        elif score >= 40:
            band = "Medium"
        else:
            band = "Low"

        intent_bands.append(band)

        if band == "High":
            lead_states.append("High Intent")
        else:
            lead_states.append("Follow-up")

    df["intent_score"] = intent_scores
    df["intent_band"] = intent_bands
    df["lead_state"] = lead_states

    return df