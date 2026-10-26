"""
Priority Router - decides "call this customer NOW, or the normal queue?"

No AI here: just clear rules, so the owner always knows why a lead is hot.

    HOT if any of these:
      - score 70 or more                       (very likely to buy)
      - frustrated AND score 40 or more        (about to go to a competitor)
      - urgent AND score 65 or more            (wants it very soon)
    otherwise NORMAL.

These numbers were tuned on the demo data so that roughly 1 in 5 leads is hot.
If everything is "hot", the owner stops trusting the alert.
"""

HOT_SCORE = 70
FRUSTRATED_HOT_SCORE = 40
URGENT_HOT_SCORE = 65


def decide_priority(score: int, sentiment: str) -> tuple[str, str]:
    """Returns ("hot" or "normal", the reason in plain words)."""
    if score >= HOT_SCORE:
        return "hot", f"High score ({score}): very likely to buy."
    if sentiment == "frustrated" and score >= FRUSTRATED_HOT_SCORE:
        return "hot", f"Frustrated customer (score {score}): reply now before they go elsewhere."
    if sentiment == "urgent" and score >= URGENT_HOT_SCORE:
        return "hot", f"Urgent request (score {score}): they want it soon."
    return "normal", f"Score {score}, {sentiment} tone: reply in the normal queue."
