"""
Content Planner agent - plans the next 7 days of posts for one business.

It's given:
  - the business profile (industry, services, brand voice, target audience)
  - which platforms the business has accounts on
  - WHAT HAS WORKED for this business (content_stats.py: ₹ and enquiries per pillar)
  - which services actually earn money (analytics)
  - upcoming festivals (festivals.py)
  - posts already planned this week (so it doesn't double-book a day)

It returns a plan: for each post → day, platform, format (reel/photo...),
pillar, a title, the idea, and WHY (tied to the data, so the owner trusts it).

The posts are saved as "ideas". The Writer agent (next task) then writes the
actual caption, hashtags and reel script for each one.

Same 4-part pattern: form → brief → mock rules → run.
"""

from datetime import date, timedelta
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.agents.llm import AIResult, get_llm
from app.models import POST_KINDS
from app.platforms import POSTING_PLATFORMS
from app.schemas import Pillar

PostPlatform = Literal[POSTING_PLATFORMS]
PostKindType = Literal[POST_KINDS]


# 1. The form ----------------------------------------------------------------------
class PlannedPost(BaseModel):
    day: int = Field(ge=0, le=13, description="0 = first day of the plan, 1 = next day...")
    time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="Posting time, 24h India time, e.g. 19:00")
    platform: PostPlatform
    kind: PostKindType
    pillar: Pillar
    title: str = Field(max_length=100, description="Short name for the post")
    idea: str = Field(max_length=400, description="What the post shows/says, in 1-2 sentences")
    why: str = Field(max_length=250, description="Why this post, based on the business's own data or a festival")


class WeekPlan(BaseModel):
    strategy: str = Field(max_length=500, description="2-3 sentences: the idea behind this week's plan, for the owner")
    posts: list[PlannedPost] = Field(min_length=1, max_length=14)


# 2. The brief ---------------------------------------------------------------------
SYSTEM = (
    "You are a social media strategist for small local businesses in India. You plan one week of posts "
    "that bring CUSTOMERS, not just likes. Rules:\n"
    "- Base every choice on the business's own results you are given. Favour content pillars that brought "
    "enquiries and revenue. Trend/meme posts get reach but rarely customers: at most 1 per week.\n"
    "- Only use platforms the business has an account on. Typical week: Instagram 4-5 posts (at least 2 reels), "
    "Facebook 1-2, Google Business Profile 1-2 (offers and reviews work well there).\n"
    "- If a festival is coming up, plan a festive OFFER before it (not only a greeting).\n"
    "- Feature the services that earn the most money.\n"
    "- Don't put a post on a day/platform that already has one planned.\n"
    "- Every 'why' must point to a number or a festival, in plain words for a busy owner."
)


def build_prompt(context: dict) -> str:
    b = context["business"]
    stats = context["stats"]
    pillar_lines = "\n".join(
        f"  - {g['name']}: {g['posts']} posts, avg reach {g['avg_reach']}, {g['enquiries']} enquiries, "
        f"{g['sales']} sales, ₹{g['revenue_per_post']} per post" for g in stats["by_pillar"]) or "  (no posts yet)"
    kind_lines = ", ".join(f"{g['name']} avg reach {g['avg_reach']}" for g in stats["by_kind"]) or "(none)"
    events = "\n".join(f"  - {e['date']} ({e['days_away']} days away): {e['name']}: {e['angle']}"
                       for e in context["events"]) or "  (none)"
    taken = "\n".join(f"  - day {t['day']} {t['platform']}: {t['title']}" for t in context["taken"]) or "  (none)"
    return (
        f"Business: {b['name']} ({b['industry']}) in {b.get('area') or ''} {b['city']}\n"
        f"About: {b['description']}\nServices: {', '.join(b['services'])}\n"
        f"Brand voice: {b['brand_voice']}\nTarget audience: {b['target_audience']}\n"
        f"Accounts on: {', '.join(context['platforms'])}\n\n"
        f"Plan {context['days']} days starting {context['start']} (day 0 = {context['start_weekday']}).\n\n"
        f"Their results, last {stats['days']} days (by content pillar, best earners first):\n{pillar_lines}\n"
        f"By format: {kind_lines}\nCurrent posting per week: {stats['posts_per_week']}\n"
        f"Best hour to post: {stats['best_hour']}\nKey findings:\n"
        + "\n".join(f"  - {f}" for f in stats["findings"]) +
        f"\n\nServices that earn the most: {', '.join(context['top_services']) or 'unknown'}\n"
        f"Upcoming festivals/events:\n{events}\nAlready planned this week:\n{taken}"
    )


# 3. The mock: a sensible rule-based planner ---------------------------------------
DEFAULT_ORDER = ["offer", "testimonial", "transformation", "tips", "behind_the_scenes"]
KIND_FOR = {
    "instagram": {"offer": "reel", "transformation": "reel", "trend": "reel", "testimonial": "carousel",
                  "tips": "carousel", "behind_the_scenes": "reel", "festival": "story"},
    "facebook": {"offer": "photo", "transformation": "video", "testimonial": "photo", "tips": "photo",
                 "behind_the_scenes": "video", "festival": "photo", "trend": "video"},
    "google": {}, "youtube": {}, "linkedin": {},
}
IDEAS = {
    "offer": ("{event}special offer on {service}", "Show the {service} result, the price and a clear deadline. End with: DM 'BOOK' or WhatsApp us."),
    "transformation": ("Before → after: {service}", "15-second reel: the 'before', a few seconds of the work, then the 'after' reveal. End with how to book."),
    "testimonial": ("Customer story: {service}", "A happy customer's photo with their words and a 5-star rating. Ask permission first!"),
    "tips": ("3 tips about {service}", "A useful carousel: 3 common mistakes or questions about {service}, with simple answers."),
    "behind_the_scenes": ("Meet the team", "Show the people and the care behind {service}. Faces build trust."),
    "trend": ("Trending audio × {service}", "Use one trending audio with a funny, relatable moment about {service}."),
    "festival": ("Happy {event_name}!", "A warm festive greeting from the team, with a small festive touch from the business."),
}


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def _many(count: int, word: str) -> str:
    """1 enquiry, 2 enquiries."""
    if count == 1:
        return f"1 {word}"
    return f"{count} {word[:-1] + 'ies' if word.endswith('y') else word + 's'}"


def _why(pillar: str, stats: dict, platform: str) -> str:
    by = {g["name"]: g for g in stats["by_pillar"]}
    g = by.get(pillar)
    if g and g["revenue_per_post"]:
        return f"'{pillar}' posts earned you ₹{g['revenue_per_post']:,} per post ({_many(g['enquiries'], 'enquiry')})."
    if g and g["enquiries"]:
        return f"'{pillar}' posts brought {_many(g['enquiries'], 'enquiry')} from {g['posts']} posts."
    if pillar == "transformation":
        return "Before/after reels reach the most people; they keep the account growing."
    if platform == "google":
        return "People who find you on Google are ready to buy; a fresh post keeps your profile active."
    return "Adds variety and builds trust, so the selling posts work better."


def mock_plan(context: dict) -> dict:
    stats, days, platforms = context["stats"], context["days"], context["platforms"]
    services = context["top_services"] or context["business"]["services"] or ["our services"]
    hour = stats["best_hour"] if stats["best_hour"] is not None else 19

    # Rank pillars by what earned money / enquiries for THIS business
    judged = [g for g in stats["by_pillar"] if g["posts"] >= 3 and (g["revenue"] or g["enquiries"])]
    ranked = [g["name"] for g in judged if g["name"] not in ("trend", "festival")]
    ranked += [p for p in DEFAULT_ORDER if p not in ranked]
    top1, top2 = ranked[0], ranked[1]
    # A third, different pillar for variety (never the same idea three times)
    third = next(p for p in ranked + DEFAULT_ORDER if p not in (top1, top2, "transformation"))

    taken = {(t["day"], t["platform"]) for t in context["taken"]}
    slots: list[tuple[int, str, str]] = []      # (day, platform, pillar)
    if "instagram" in platforms:
        middle = "transformation" if "transformation" not in (top1, top2) else third
        for day, pillar in zip([0, 1, 3, 4, 6], [top1, middle, top2, third, top1]):
            slots.append((day, "instagram", pillar))
    if "facebook" in platforms:
        slots.append((2, "facebook", top2))
    if "google" in platforms:
        slots.append((5, "google", top1 if top1 in ("offer", "testimonial") else "offer"))

    def free(day: int, platform: str) -> bool:
        return 0 <= day < days and (day, platform) not in taken

    # A festival coming up? Put a festive OFFER on the nearest free day before it,
    # and a greeting on the day itself.
    event = next((e for e in context["events"] if e["days_away"] < days + 3), None)
    festive_placed = False
    if event and "instagram" in platforms:
        d = event["days_away"]
        offer_day = next((x for x in (d - 2, d - 1, d - 3, d - 4, 0, 1) if free(x, "instagram")), None)
        if offer_day is not None:
            slots = [s for s in slots if not (s[0] == offer_day and s[1] == "instagram")]
            slots.append((offer_day, "instagram", "offer*"))
            festive_placed = True
        if d < days:
            # Never overwrite the festive offer with the greeting: the offer brings customers
            greet_on = next((pl for pl in ("instagram", "facebook") if pl in platforms and free(d, pl)
                             and not (pl == "instagram" and d == offer_day)), None)
            if greet_on:
                slots = [s for s in slots if not (s[0] == d and s[1] == greet_on)]
                slots.append((d, greet_on, "festival"))

    posts = []
    used: set[tuple[str, str]] = set()           # (pillar, service) already planned this week
    for i, (day, platform, pillar) in enumerate(sorted(slots)):
        if day >= days or (day, platform) in taken:
            continue
        festive = pillar == "offer*"
        pillar = "offer" if festive else pillar
        # Same idea twice in a week? Use the next service instead (never repeat a post)
        order = [services[(i + k) % len(services)] for k in range(len(services))]
        service = next((sv for sv in order if (pillar + ("*" if festive else ""), sv) not in used), order[0])
        used.add((pillar + ("*" if festive else ""), service))
        title, idea = IDEAS[pillar]
        fill = {"service": service, "event": f"{event['name']} " if festive else "",
                "event_name": event["name"] if event else "festival"}
        why = (f"{event['name']} is on {event['date']}: people plan and spend before festivals."
               if (festive or pillar == "festival") and event else _why(pillar, stats, platform))
        posts.append({
            "day": day, "time": f"{(hour + (i % 2)) % 24:02d}:{(i * 15) % 60:02d}", "platform": platform,
            "kind": KIND_FOR.get(platform, {}).get(pillar, "photo"), "pillar": pillar,
            "title": _capital(title.format(**fill))[:100], "idea": idea.format(**fill)[:400], "why": why[:250],
        })

    strategy = (f"More '{top1}' and '{top2}' posts, because they brought you customers. "
                f"Reels for reach, a Google post for ready-to-buy searchers"
                + (f", and a {event['name']} offer before the festival." if festive_placed else ".")
                + " Trend posts are skipped this week: they got likes but no sales.")
    return {"strategy": strategy[:500], "posts": posts or [{
        "day": 0, "time": f"{hour:02d}:00", "platform": platforms[0] if platforms else "instagram",
        "kind": "photo", "pillar": "offer", "title": f"Offer on {services[0]}",
        "idea": "A simple offer post with price and how to book.", "why": "A starting point."}]}


# 4. The run -----------------------------------------------------------------------
def run_planner(context: dict) -> AIResult[WeekPlan]:
    return get_llm().ask(
        system=SYSTEM, prompt=build_prompt(context), schema=WeekPlan,
        mock=lambda: mock_plan(context), smart=True, max_tokens=3000,   # a big job → the smart model
    )


def week_start_default(today: date) -> date:
    """Plans start tomorrow by default."""
    return today + timedelta(days=1)


def tidy(plan: WeekPlan, context: dict) -> tuple[list[PlannedPost], list[str]]:
    """Safety checks on the plan (especially the real AI's): drop posts on
    platforms without an account, outside the dates, or on a taken slot,
    and allow at most 2 posts per day per platform."""
    kept, dropped = [], []
    taken = {(t["day"], t["platform"]) for t in context["taken"]}
    per_slot: dict[tuple[int, str], int] = {}
    for p in plan.posts:
        reason: Optional[str] = None
        if p.platform not in context["platforms"]:
            reason = f"no {p.platform} account"
        elif p.day >= context["days"]:
            reason = "outside the plan dates"
        elif (p.day, p.platform) in taken:
            reason = "that day already has a post"
        elif per_slot.get((p.day, p.platform), 0) >= 2:
            reason = "too many posts that day"
        if reason:
            dropped.append(f"Skipped '{p.title}': {reason}")
            continue
        per_slot[(p.day, p.platform)] = per_slot.get((p.day, p.platform), 0) + 1
        kept.append(p)
    return kept, dropped
