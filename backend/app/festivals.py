"""
Festival & special-day calendar for India - so content can be planned around
the moments people actually care about (and spend money on).

Two kinds of dates:
  FIXED_DAYS   same date every year (Christmas, Independence Day, Yoga Day...)
  LUNAR_DAYS   move every year with the Hindu lunar calendar (Diwali, Holi...)
               → these need updating once a year. Dates below were checked
                 against published 2026-27 festival calendars in Oct 2026.

Each event says which industries it matters for, and an "angle": a hint the
Content Planner can use, e.g. Diwali + car detailing = "pre-Diwali shine".
"""

from dataclasses import dataclass
from datetime import date, timedelta

ALL = ("all",)


@dataclass(frozen=True)
class Event:
    name: str
    industries: tuple = ALL
    angle: str = ""

    def fits(self, industry: str) -> bool:
        return self.industries == ALL or industry in self.industries


# (month, day): Event
FIXED_DAYS: dict[tuple[int, int], Event] = {
    (1, 1): Event("New Year", ALL, "new year, new you: resolutions and fresh starts"),
    (1, 26): Event("Republic Day", ALL, "patriotic greeting; long-weekend offer"),
    (2, 14): Event("Valentine's Day", ("salon", "restaurant", "cafe", "gym", "retail"), "couple offers, gifting"),
    (3, 8): Event("Women's Day", ALL, "celebrate women customers and staff; ladies' special"),
    (3, 20): Event("World Oral Health Day", ("clinic",), "free dental check-up camp, smile tips"),
    (4, 7): Event("World Health Day", ("clinic", "gym"), "health check-ups, fitness tips"),
    (6, 21): Event("International Yoga Day", ("gym", "clinic"), "free yoga session, wellness tips"),
    (8, 15): Event("Independence Day", ALL, "patriotic greeting; freedom sale"),
    (9, 5): Event("Teachers' Day", ("coaching",), "thank your teachers; student stories"),
    (9, 29): Event("World Heart Day", ("gym", "clinic"), "heart-healthy habits, cardio challenge"),
    (10, 2): Event("Gandhi Jayanti", ALL, "simple greeting; cleanliness drive"),
    (11, 14): Event("Children's Day", ("clinic", "coaching", "restaurant", "cafe", "retail"), "kids' specials"),
    (12, 25): Event("Christmas", ALL, "festive greeting; year-end offers"),
    (12, 31): Event("New Year's Eve", ("restaurant", "cafe", "salon", "car_detailing"), "party-ready looks, bookings"),
}

LUNAR_DAYS: dict[date, Event] = {
    # 2026
    date(2026, 10, 20): Event("Dussehra", ALL, "victory of good; festive offer"),
    date(2026, 10, 29): Event("Karwa Chauth", ("salon", "retail", "restaurant"), "mehendi, makeup and outfit bookings"),
    date(2026, 11, 6): Event("Dhanteras", ("car_detailing", "auto_service", "retail", "real_estate"),
                             "auspicious day to buy: new-car care packages"),
    date(2026, 11, 8): Event("Diwali", ALL, "biggest festival: pre-Diwali offers, festive greetings, gift vouchers"),
    date(2026, 11, 11): Event("Bhai Dooj", ("salon", "restaurant", "retail"), "sibling offers, gifting"),
    date(2026, 11, 13): Event("Chhath Puja", ALL, "festive greeting"),
    # 2027
    date(2027, 2, 11): Event("Vasant Panchami", ("coaching", "retail"), "new beginnings, learning"),
    date(2027, 3, 6): Event("Maha Shivratri", ALL, "festive greeting"),
    date(2027, 3, 22): Event("Holi", ALL, "colours: before/after Holi care (skin, hair, car paint!)"),
    date(2027, 4, 15): Event("Ram Navami", ALL, "festive greeting"),
    date(2027, 8, 17): Event("Raksha Bandhan", ("salon", "retail", "restaurant"), "sibling gifting"),
    date(2027, 8, 25): Event("Janmashtami", ALL, "festive greeting"),
    date(2027, 9, 4): Event("Ganesh Chaturthi", ALL, "auspicious new beginnings"),
    date(2027, 9, 30): Event("Navratri begins", ("gym", "restaurant", "salon", "retail"), "garba fitness, fasting menus, looks"),
    date(2027, 10, 9): Event("Dussehra", ALL, "victory of good; festive offer"),
    date(2027, 10, 29): Event("Diwali", ALL, "biggest festival: pre-Diwali offers, festive greetings, gift vouchers"),
}


def upcoming(start: date, days: int, industry: str, look_ahead: int = 10) -> list[dict]:
    """Events between `start` and `start + days + look_ahead` that matter for this industry.
    look_ahead: a festival 10 days away still needs promotion THIS week."""
    end = start + timedelta(days=days + look_ahead)
    found: list[dict] = []
    day = start
    while day <= end:
        event = FIXED_DAYS.get((day.month, day.day)) or LUNAR_DAYS.get(day)
        if event and event.fits(industry):
            found.append({"date": day.isoformat(), "name": event.name, "angle": event.angle,
                          "days_away": (day - start).days})
        day += timedelta(days=1)
    return found
