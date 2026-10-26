"""
Presence Auditor - a checklist of the business's online presence.

No AI needed: these are yes/no facts, so plain rules are faster, free and
always correct. Each item is "ok", "warn" (needs attention) or "missing".

    ✓ Posting enough on Instagram / Facebook / Google this week?
    ✓ Every enquiry answered? Replies fast?
    ✓ Hot leads waiting?
    ✓ Listed on the industry's own apps (Practo for clinics, Zomato for restaurants...)?
    ✓ Something planned for next week?
    ✓ Good Google rating, every review answered, asking customers for reviews?
"""

from app.services.growth_facts import platform_name


def audit(f: dict) -> list[dict]:
    items: list[dict] = []
    content, tw = f["content"], f["this_week"]

    for platform, target in content["targets"].items():
        name = platform_name(platform)
        if platform not in content["accounts"]:
            items.append({"item": f"{name} account", "status": "missing",
                          "tip": f"Add your {name} account so we can plan and track posts there."})
            continue
        done = content["posted_this_week"].get(platform, 0)
        items.append({"item": f"{name}: {target}+ posts a week", "status": "ok" if done >= target else "warn",
                      "tip": f"Posted {done} this week." + ("" if done >= target else f" Aim for {target}.")})

    items.append({"item": "Every enquiry answered", "status": "ok" if not tw["never_replied"] else "warn",
                  "tip": "All answered." if not tw["never_replied"]
                  else f"{tw['never_replied']} still have no reply: answer them today."})
    reply = tw["median_reply_minutes"]
    if reply is not None:
        items.append({"item": "Reply within 1 hour", "status": "ok" if reply <= 60 else "warn",
                      "tip": f"Typical reply time: {reply:.0f} minutes."})
    if tw["hot_waiting"]:
        items.append({"item": "Hot leads followed up", "status": "warn",
                      "tip": f"{tw['hot_waiting']} hot leads are waiting: call them first."})

    for p in f["industry_platforms"][:3]:
        items.append({"item": f"Listed on {p['name']}", "status": "ok" if p["brings_leads"] else "missing",
                      "tip": "It's bringing you enquiries." if p["brings_leads"]
                      else f"No enquiries from {p['name']} in 90 days. Are you listed there with photos and reviews?"})

    rep = f.get("reputation")
    if rep:
        if rep["average_rating"] is not None:
            items.append({"item": "Rating 4.5+ stars", "status": "ok" if rep["average_rating"] >= 4.5 else "warn",
                          "tip": f"Average {rep['average_rating']:.1f}★ from {rep['reviews']} reviews."})
        items.append({"item": "Every review answered", "status": "ok" if not rep["unreplied"] else "warn",
                      "tip": "All answered." if not rep["unreplied"] else
                      f"{rep['unreplied']} reviews have no reply ({rep['needs_attention']} unhappy). Drafts are ready."})
        if not rep["has_review_link"]:
            items.append({"item": "Google review link set up", "status": "missing",
                          "tip": "Add your Google review link so happy customers get asked automatically."})
        else:
            items.append({"item": "Asking customers for reviews",
                          "status": "ok" if rep["requests_sent_30_days"] else "warn",
                          "tip": f"{rep['requests_sent_30_days']} requests sent in 30 days."
                          + ("" if rep["requests_sent_30_days"] else " Mark sales as 'won' to trigger them.")})

    planned = content["planned_next_7_days"]
    items.append({"item": "Next week's posts planned", "status": "ok" if len(planned) >= 4 else "warn",
                  "tip": f"{len(planned)} posts planned." + ("" if len(planned) >= 4 else " Use 'Plan my week'.")})
    return items


def weak_platforms(f: dict) -> list[str]:
    """Platforms needing attention: under-posted, missing, or bringing enquiries that don't buy."""
    weak = [p for p, target in f["content"]["targets"].items()
            if p not in f["content"]["accounts"] or f["content"]["posted_this_week"].get(p, 0) < target]
    ninety = f["ninety_days"]
    for s in ninety["sources"]:
        if (s["leads"] >= 5 and s["share_of_leads"] >= 15 and s["conversion_rate"] < ninety["conversion_rate"] / 2
                and s["key"] not in weak):
            weak.append(s["key"])
    return weak
