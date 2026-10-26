"""
The platform list - every place a business can get customers from.

This is the ONE place where platforms are defined. The database rules,
the webhooks, the dashboard dropdowns and (later) the AI's "where should
you be listed?" check all read this list.

To support a new platform, add ONE line below. Nothing else needs changing.

Each platform has:
    key         short id stored in the database, e.g. "justdial"
    name        how it's shown to people, e.g. "Justdial"
    category    what kind of place it is (see CATEGORIES)
    connection  how leads from it reach our app:
                  "api"    - the platform rings our doorbell itself (WhatsApp, Instagram...)
                  "email"  - it emails the business each lead; we can read those emails later
                  "manual" - staff add these leads by hand (or via the universal door)
    industries  which kinds of business it matters for ("all" = every business)
    can_post    can the business publish posts there? (used by the social media features)
"""

from dataclasses import dataclass

CATEGORIES = {
    "messaging": "Chat apps",
    "social": "Social media",
    "search_maps": "Search & maps",
    "directory": "Local directories",
    "marketplace": "Industry apps & marketplaces",
    "own": "Business's own channels",
    "offline": "Offline",
}

ALL = ("all",)


@dataclass(frozen=True)
class Platform:
    key: str
    name: str
    category: str
    connection: str
    industries: tuple = ALL
    can_post: bool = False

    def fits(self, industry: str) -> bool:
        """Is this platform relevant for a business in this industry?"""
        return self.industries == ALL or industry in self.industries


_LIST = [
    # --- Chat apps ---------------------------------------------------------------
    Platform("whatsapp", "WhatsApp", "messaging", "api"),
    Platform("sms", "SMS", "messaging", "manual"),
    # --- Social media --------------------------------------------------------------
    Platform("instagram", "Instagram", "social", "api", can_post=True),
    Platform("facebook", "Facebook", "social", "api", can_post=True),
    Platform("youtube", "YouTube", "social", "manual", can_post=True),
    Platform("linkedin", "LinkedIn", "social", "manual", ("coaching", "real_estate", "other"), can_post=True),
    # --- Search & maps -------------------------------------------------------------
    Platform("google", "Google (Search & Maps)", "search_maps", "api", can_post=True),   # Google Business Profile posts
    Platform("apple_maps", "Apple Maps", "search_maps", "manual"),
    Platform("bing", "Bing Places", "search_maps", "manual"),
    # --- Local directories ---------------------------------------------------------
    Platform("justdial", "Justdial", "directory", "email"),
    Platform("sulekha", "Sulekha", "directory", "email"),
    Platform("indiamart", "IndiaMART", "directory", "api", ("retail", "other")),
    Platform("tradeindia", "TradeIndia", "directory", "email", ("retail", "other")),
    # --- Industry apps & marketplaces ----------------------------------------------
    Platform("practo", "Practo", "marketplace", "email", ("clinic",)),
    Platform("lybrate", "Lybrate", "marketplace", "email", ("clinic",)),
    Platform("zomato", "Zomato", "marketplace", "manual", ("restaurant", "cafe")),
    Platform("swiggy", "Swiggy", "marketplace", "manual", ("restaurant", "cafe")),
    Platform("eazydiner", "EazyDiner", "marketplace", "manual", ("restaurant", "cafe")),
    Platform("magicpin", "Magicpin", "marketplace", "manual", ("restaurant", "cafe", "salon", "retail")),
    Platform("cultfit", "Cult.fit", "marketplace", "manual", ("gym",)),
    Platform("fitpass", "Fitpass", "marketplace", "manual", ("gym",)),
    Platform("urban_company", "Urban Company", "marketplace", "manual", ("salon",)),
    Platform("fresha", "Fresha", "marketplace", "manual", ("salon",)),
    Platform("urbanpro", "UrbanPro", "marketplace", "email", ("coaching",)),
    Platform("superprof", "Superprof", "marketplace", "email", ("coaching",)),
    Platform("99acres", "99acres", "marketplace", "email", ("real_estate",)),
    Platform("magicbricks", "MagicBricks", "marketplace", "email", ("real_estate",)),
    Platform("housing", "Housing.com", "marketplace", "email", ("real_estate",)),
    Platform("nobroker", "NoBroker", "marketplace", "email", ("real_estate",)),
    Platform("cardekho", "CarDekho", "marketplace", "email", ("auto_service", "car_detailing")),
    # --- The business's own channels -------------------------------------------------
    Platform("website", "Website", "own", "api"),
    Platform("email", "Email", "own", "manual"),
    Platform("phone_call", "Phone call", "own", "manual"),
    # --- Offline ---------------------------------------------------------------------
    Platform("walk_in", "Walk-in", "offline", "manual"),
    Platform("referral", "Referral (word of mouth)", "offline", "manual"),
    Platform("other", "Other", "offline", "manual"),
]

# A dictionary for quick lookups: PLATFORMS["justdial"].name → "Justdial"
PLATFORMS: dict[str, Platform] = {p.key: p for p in _LIST}


# Platforms where a business can publish posts
POSTING_PLATFORMS = tuple(p.key for p in _LIST if p.can_post)


def platforms_for(industry: str) -> list[Platform]:
    """The platforms that matter for one kind of business."""
    return [p for p in _LIST if p.fits(industry)]
