"""
Analytics service - the calculator. Plain maths, NO AI.

This is an important design choice from the plan:
    ordinary code CALCULATES the numbers  →  the AI only EXPLAINS them.
So the AI can never invent a statistic. Every number here can be checked.

For one business, over the last N days, it answers:
    overview   How many enquiries, sales, ₹ revenue, reply speed?
    sources    Which platform brings enquiries, and which brings MONEY?
    funnel     How many got contacted → quoted → booked → won?
    timing     Busiest hours and days. Do fast replies win more?
    services   Which services are asked about most, and which sell?
    trend      Week by week: going up or down?
    highlights The most important findings, written as plain sentences.

How it works: load this business's leads for the period once, then count
and add things up in Python. Simple to read, and fast enough for the
few thousand leads a local business gets.
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Lead
from app.platforms import PLATFORMS

IST = timezone(timedelta(hours=5, minutes=30))
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
FUNNEL = ["new", "contacted", "quoted", "booked", "won"]
STAGE_ORDER = {stage: i for i, stage in enumerate(FUNNEL)}        # "lost" isn't a stage
# Reply-speed groups, in minutes
SPEED_BUCKETS = [("under 15 min", 0, 15), ("15-60 min", 15, 60), ("1-4 hours", 60, 240),
                 ("4-24 hours", 240, 1440), ("over a day", 1440, 10**9)]


# ---------------------------------------------------------------------------
# Report shapes (what each calculation returns)
# ---------------------------------------------------------------------------
class Overview(BaseModel):
    days: int
    leads: int
    won: int
    lost: int
    open: int                         # still in progress
    conversion_rate: float            # % of leads that became sales
    revenue: int                      # ₹ from won leads
    avg_sale: int                     # ₹ per won lead
    hot_open: int                     # hot leads not yet won/lost
    never_replied: int                # leads nobody answered
    median_reply_minutes: Optional[float]
    leads_last_7_days: int
    leads_previous_7_days: int
    change_vs_previous_week: Optional[float]   # % up (+) or down (-)


class SourceStats(BaseModel):
    source: str
    name: str
    leads: int
    share_of_leads: float             # %
    won: int
    conversion_rate: float            # %
    revenue: int
    share_of_revenue: float           # %
    avg_score: Optional[float]
    median_reply_minutes: Optional[float]


class FunnelStep(BaseModel):
    stage: str
    reached: int                      # leads that got AT LEAST this far
    percent_of_all: float


class Funnel(BaseModel):
    steps: list[FunnelStep]
    lost: int


class SpeedStats(BaseModel):
    reply_speed: str
    leads: int
    won: int
    conversion_rate: float


class Timing(BaseModel):
    leads_by_hour: dict[int, int]     # hour of day (India time) → leads
    leads_by_day: dict[str, int]
    peak_hour: Optional[int]
    peak_day: Optional[str]
    conversion_by_reply_speed: list[SpeedStats]


class ServiceStats(BaseModel):
    service: str
    leads: int
    won: int
    conversion_rate: float
    revenue: int


class WeekStats(BaseModel):
    week_start: str                   # Monday of that week, e.g. "2026-10-12"
    leads: int
    won: int
    revenue: int


class Summary(BaseModel):
    overview: Overview
    sources: list[SourceStats]
    funnel: Funnel
    timing: Timing
    services: list[ServiceStats]
    trend: list[WeekStats]
    highlights: list[str]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _utc(dt: datetime) -> datetime:
    """SQLite gives times back without a timezone; ours are always UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _pct(part: float, whole: float) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def _reply_minutes(lead: Lead) -> Optional[float]:
    if lead.first_response_at is None:
        return None
    return max(0.0, (_utc(lead.first_response_at) - _utc(lead.created_at)).total_seconds() / 60)


def _median(values: list[float]) -> Optional[float]:
    return round(median(values), 1) if values else None


def load_leads(db: Session, business_id: int, days: int) -> list[Lead]:
    """All of one business's leads from the last `days` days (with AI analysis)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    query = (select(Lead).where(Lead.business_id == business_id, Lead.created_at >= since)
             .options(selectinload(Lead.analysis)))
    return list(db.scalars(query))


# ---------------------------------------------------------------------------
# The calculations
# ---------------------------------------------------------------------------
def overview(leads: list[Lead], days: int) -> Overview:
    won = [l for l in leads if l.status == "won"]
    revenue = sum(l.job_value or 0 for l in won)
    replies = [m for m in map(_reply_minutes, leads) if m is not None]

    now = datetime.now(timezone.utc)
    last_7 = sum(1 for l in leads if _utc(l.created_at) >= now - timedelta(days=7))
    prev_7 = sum(1 for l in leads if now - timedelta(days=14) <= _utc(l.created_at) < now - timedelta(days=7))

    return Overview(
        days=days,
        leads=len(leads),
        won=len(won),
        lost=sum(1 for l in leads if l.status == "lost"),
        open=sum(1 for l in leads if l.status not in ("won", "lost")),
        conversion_rate=_pct(len(won), len(leads)),
        revenue=revenue,
        avg_sale=round(revenue / len(won)) if won else 0,
        hot_open=sum(1 for l in leads if l.analysis and l.analysis.priority == "hot"
                     and l.status not in ("won", "lost")),
        never_replied=sum(1 for l in leads if l.first_response_at is None),
        median_reply_minutes=_median(replies),
        leads_last_7_days=last_7,
        leads_previous_7_days=prev_7,
        change_vs_previous_week=_pct(last_7 - prev_7, prev_7) if prev_7 else None,
    )


def sources(leads: list[Lead]) -> list[SourceStats]:
    groups: dict[str, list[Lead]] = defaultdict(list)
    for lead in leads:
        groups[lead.source].append(lead)
    total_revenue = sum(l.job_value or 0 for l in leads if l.status == "won")

    result = []
    for source, group in groups.items():
        won = [l for l in group if l.status == "won"]
        revenue = sum(l.job_value or 0 for l in won)
        scores = [l.analysis.score for l in group if l.analysis]
        replies = [m for m in map(_reply_minutes, group) if m is not None]
        platform = PLATFORMS.get(source)
        result.append(SourceStats(
            source=source, name=platform.name if platform else source,
            leads=len(group), share_of_leads=_pct(len(group), len(leads)),
            won=len(won), conversion_rate=_pct(len(won), len(group)),
            revenue=revenue, share_of_revenue=_pct(revenue, total_revenue),
            avg_score=round(sum(scores) / len(scores), 1) if scores else None,
            median_reply_minutes=_median(replies),
        ))
    return sorted(result, key=lambda s: -s.leads)


def funnel(leads: list[Lead]) -> Funnel:
    """How far did leads get? A won lead also counts as contacted, quoted and booked.
    (Lost leads count up to the furthest stage we can be sure of: contacted if
    someone replied, otherwise new.)"""
    def furthest(lead: Lead) -> int:
        if lead.status == "lost":
            return STAGE_ORDER["contacted"] if lead.first_response_at else STAGE_ORDER["new"]
        return STAGE_ORDER.get(lead.status, 0)

    reached = Counter()
    for lead in leads:
        for i in range(furthest(lead) + 1):
            reached[i] += 1
    steps = [FunnelStep(stage=stage, reached=reached[i], percent_of_all=_pct(reached[i], len(leads)))
             for i, stage in enumerate(FUNNEL)]
    return Funnel(steps=steps, lost=sum(1 for l in leads if l.status == "lost"))


def timing(leads: list[Lead]) -> Timing:
    hours = Counter(_utc(l.created_at).astimezone(IST).hour for l in leads)
    days = Counter(DAY_NAMES[_utc(l.created_at).astimezone(IST).weekday()] for l in leads)

    # Only finished leads (won or lost) tell us whether reply speed mattered
    finished = [l for l in leads if l.status in ("won", "lost")]
    speed = []
    for label, low, high in SPEED_BUCKETS:
        group = [l for l in finished if (m := _reply_minutes(l)) is not None and low <= m < high]
        won = sum(1 for l in group if l.status == "won")
        speed.append(SpeedStats(reply_speed=label, leads=len(group), won=won, conversion_rate=_pct(won, len(group))))
    never = [l for l in finished if l.first_response_at is None]
    speed.append(SpeedStats(reply_speed="never replied", leads=len(never),
                            won=sum(1 for l in never if l.status == "won"),
                            conversion_rate=_pct(sum(1 for l in never if l.status == "won"), len(never))))

    return Timing(
        leads_by_hour={h: hours.get(h, 0) for h in range(24)},
        leads_by_day={d: days.get(d, 0) for d in DAY_NAMES},
        peak_hour=hours.most_common(1)[0][0] if hours else None,
        peak_day=days.most_common(1)[0][0] if days else None,
        conversion_by_reply_speed=speed,
    )


def services(leads: list[Lead]) -> list[ServiceStats]:
    groups: dict[str, list[Lead]] = defaultdict(list)
    for lead in leads:
        groups[lead.service or "Not clear yet"].append(lead)
    result = []
    for service, group in groups.items():
        won = [l for l in group if l.status == "won"]
        result.append(ServiceStats(service=service, leads=len(group), won=len(won),
                                   conversion_rate=_pct(len(won), len(group)),
                                   revenue=sum(l.job_value or 0 for l in won)))
    return sorted(result, key=lambda s: (-s.revenue, -s.leads))


def trend(leads: list[Lead]) -> list[WeekStats]:
    weeks: dict[str, list[Lead]] = defaultdict(list)
    for lead in leads:
        day = _utc(lead.created_at).astimezone(IST).date()
        monday = day - timedelta(days=day.weekday())
        weeks[monday.isoformat()].append(lead)
    return [WeekStats(week_start=week, leads=len(group),
                      won=sum(1 for l in group if l.status == "won"),
                      revenue=sum(l.job_value or 0 for l in group if l.status == "won"))
            for week, group in sorted(weeks.items())]


# ---------------------------------------------------------------------------
# Highlights: the most important findings as plain sentences
# (still plain rules, no AI; the AI agents in Task 17 build on these)
# ---------------------------------------------------------------------------
def highlights(ov: Overview, srcs: list[SourceStats], tm: Timing, svcs: list[ServiceStats]) -> list[str]:
    notes: list[str] = []
    if not ov.leads:
        return ["No enquiries in this period yet."]

    big = [s for s in srcs if s.leads >= 5]        # ignore tiny sources when judging volume/rates
    earners = [s for s in srcs if s.revenue > 0]    # but money is money, however few leads
    if big:
        most = max(big, key=lambda s: s.leads)
        richest = max(earners, key=lambda s: s.revenue) if earners else None
        if richest is None:
            notes.append(f"{most.name} brings the most enquiries ({most.share_of_leads:.0f}%), "
                         f"but no source has produced a sale yet.")
        elif most.source != richest.source:
            notes.append(f"{most.name} brings the most enquiries ({most.share_of_leads:.0f}%), "
                         f"but {richest.name} brings the most money ({richest.share_of_revenue:.0f}% of revenue).")
        else:
            notes.append(f"{most.name} is your best channel: most enquiries ({most.share_of_leads:.0f}%) "
                         f"and most revenue ({most.share_of_revenue:.0f}%).")
        for s in big:
            if s.share_of_leads >= 15 and s.conversion_rate < ov.conversion_rate / 2:
                notes.append(f"{s.name}: lots of enquiries ({s.leads}) but only {s.conversion_rate:.0f}% buy. "
                             f"The content attracts people, but not buyers.")
        best_rate = max(big, key=lambda s: s.conversion_rate)
        if best_rate.conversion_rate >= ov.conversion_rate * 1.5:
            notes.append(f"{best_rate.name} leads convert best ({best_rate.conversion_rate:.0f}% vs "
                         f"{ov.conversion_rate:.0f}% overall). Worth getting more of them.")

    def combined(buckets: list[SpeedStats]) -> tuple[int, float]:
        leads = sum(b.leads for b in buckets)
        return leads, _pct(sum(b.won for b in buckets), leads)

    fast_n, fast_rate = combined(tm.conversion_by_reply_speed[:2])      # within 1 hour
    slow_n, slow_rate = combined(tm.conversion_by_reply_speed[3:])      # 4+ hours or never
    if fast_n >= 5 and slow_n >= 5 and fast_rate > slow_rate * 1.3:
        notes.append(f"Speed wins: replies within 1 hour convert {fast_rate:.0f}% "
                     f"vs {slow_rate:.0f}% when the reply takes 4+ hours.")

    if ov.never_replied:
        notes.append(f"{ov.never_replied} enquiries never got a reply. Those are customers left on the table.")
    if ov.hot_open:
        notes.append(f"{ov.hot_open} hot leads are still open. Call them first.")
    if tm.peak_hour is not None:
        notes.append(f"Busiest day: {tm.peak_day}. Busiest hour: around {tm.peak_hour % 12 or 12}"
                     f"{'am' if tm.peak_hour < 12 else 'pm'}. Make sure someone can reply then.")
    if svcs and svcs[0].revenue:
        notes.append(f"Top earner: {svcs[0].service} (₹{svcs[0].revenue:,} from {svcs[0].won} sales).")
    if (ov.change_vs_previous_week is not None and abs(ov.change_vs_previous_week) >= 20
            and max(ov.leads_last_7_days, ov.leads_previous_7_days) >= 5):       # ignore tiny numbers
        word = "up" if ov.change_vs_previous_week > 0 else "down"
        notes.append(f"Enquiries are {word} {abs(ov.change_vs_previous_week):.0f}% compared with the week before.")
    return notes


def summary(db: Session, business_id: int, days: int = 90) -> Summary:
    """Everything at once: used by the dashboard home page and the AI growth agents."""
    leads = load_leads(db, business_id, days)
    ov, srcs, tm, svcs = overview(leads, days), sources(leads), timing(leads), services(leads)
    return Summary(overview=ov, sources=srcs, funnel=funnel(leads), timing=tm, services=svcs,
                   trend=trend(leads), highlights=highlights(ov, srcs, tm, svcs))
