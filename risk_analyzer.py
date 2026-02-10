def analyze_risk(text: str) -> str:
    """
    Rule-based risk analyzer for misinformation.
    Uses keyword patterns inspired by recent misinformation incidents.
    """

    text = text.lower()

    # 🔴 HIGH RISK — common misinformation / viral hoaxes
    high_risk_keywords = [
        # Celebrity death / scandals
        "dead", "death", "dies", "passed away", "found dead",
        "celebrity death", "actor dead", "singer dead",
        "taylor swift", "elon musk", "donald trump", "joe biden",
        "narendra modi", "virat kohli", "cristiano ronaldo",
        "epstein", "prince harry", "kim kardashian",

        # Political misinformation
        "assassination", "assassinated", "coup", "martial law",
        "election fraud", "rigged election", "ballot stuffing",
        "deep state", "false flag",

        # Health misinformation
        "cure", "miracle cure", "secret cure",
        "covid hoax", "vaccine kills", "vaccine death",
        "cancer cure hidden", "big pharma lie",

        # Financial scams / panic
        "market crash", "bank collapse", "economy will collapse",
        "crypto scam", "bitcoin crash", "ponzi scheme",

        # War / crisis misinformation
        "world war 3", "nuclear attack", "missile strike",
        "invasion imminent", "terror attack"
    ]

    # 🟡 MEDIUM RISK — unverified or misleading claims
    medium_risk_keywords = [
        "claims", "claim", "report says", "sources say",
        "allegedly", "leaked", "leak", "insider says",
        "breaking", "shocking", "exposed",
        "conspiracy", "theory", "unconfirmed",
        "viral video", "trending rumor"
    ]

    # 🔵 LOW RISK — neutral / factual language
    low_risk_keywords = [
        "announced", "official", "confirmed", "according to",
        "statement", "press release", "study finds",
        "research shows", "data indicates"
    ]

    # 🔍 Scoring logic
    for word in high_risk_keywords:
        if word in text:
            return "High"

    for word in medium_risk_keywords:
        if word in text:
            return "Medium"

    for word in low_risk_keywords:
        if word in text:
            return "Low"

    # Default (neutral but cautious)
    return "Medium"