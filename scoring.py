import pandas as pd

CORE_CITIES = ["Mumbai", "Surat", "Indore", "Pune"]

# ======================================================
# SCORING
# ======================================================
def score_leads(df: pd.DataFrame) -> pd.DataFrame:
    def present(x):
        return pd.notna(x) and str(x).strip() != ""

    # ---------------- Medical / Need
    def medical_score(reason):
        if not present(reason):
            return 0
        r = str(reason).lower()
        if "power" in r:
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

    # ---------------- Timeline / Urgency
    def timeline_score(t):
        if not present(t):
            return 0
        t = str(t).lower()
        if "7" in t or "15" in t:
            return 20
        if "30" in t:
            return 16
        if "1" in t and "3" in t:
            return 10
        if "3" in t and "6" in t:
            return 5
        return 0

    # ---------------- Location
    def location_score(city):
        if not present(city):
            return 0
        return 10 if city.strip() in CORE_CITIES else 6

    # ---------------- Conversation Quality
    def conversation_score(row):
        score = 0

        outcome = str(row.get("call_outcome", "")).lower()
        consult = str(row.get("consultation_status", "")).lower()
        objection = str(row.get("objection_type", "")).lower()

        if outcome == "positive":
            score += 10
        elif outcome == "neutral":
            score += 5

        if consult == "scheduled":
            score += 12
        elif consult == "done":
            score += 15
        elif consult == "not offered":
            score += 2

        if objection in ["timing", "cost"]:
            score += 3
        if "not interested" in objection:
            score -= 10

        return score

    scores, bands, states = [], [], []

    for _, row in df.iterrows():
        parts = [
            row.get("reason"),
            row.get("timeline"),
            row.get("city"),
            row.get("call_outcome"),
            row.get("consultation_status"),
        ]

        # -------- Minimum data gate
        if sum(present(p) for p in parts) < 3:
            scores.append("")
            bands.append("Insufficient Data")
            states.append("Open")
            continue

        score = (
            medical_score(row.get("reason"))
            + timeline_score(row.get("timeline"))
            + location_score(row.get("city"))
            + conversation_score(row)
        )

        scores.append(score)

        if score >= 70:
            band = "High"
            state = "High Intent"
        elif score >= 40:
            band = "Medium"
            state = "Follow-up"
        else:
            band = "Low"
            state = "Follow-up"

        # Lost but recoverable is resolved later in UI / filters
        bands.append(band)
        states.append(state)

    df["intent_score"] = scores
    df["intent_band"] = bands
    df["lead_state"] = states

    return df