"""
All app settings live here.

Settings are read from the `.env` file (or real environment variables).
Any file in the project can do `from app.config import settings` and use
e.g. `settings.mock_ai`, so nothing is hard-coded in multiple places.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # The default values below are used when .env doesn't mention a setting.
    app_name: str = "Lead Intel"
    database_url: str = "sqlite:///./data/leads.db"
    # "development" on your laptop, "production" on the live server. Production
    # refuses to start with demo passwords/keys, hides /docs, and adds security headers.
    environment: str = "development"
    show_docs: bool = False                    # production only: set true to keep /docs visible
    # What the live site offers (see app/features.py):
    #   "light" = only what really works today. A platform (WhatsApp, Instagram, Google, LinkedIn, Razorpay,
    #             call tracking, competitor data) is offered ONLY once its real keys are in .env: nothing runs in
    #             pretend mode, so owners are never shown something that doesn't really work.
    #   "full"  = everything, with pretend (mock) mode wherever keys are missing: for your laptop and the tests.
    #   ""      = automatic: "light" on the live server (ENVIRONMENT=production), "full" everywhere else.
    # Where owners pay you by hand while Razorpay is off (shown on the Billing page)
    pay_upi_id: str = ""
    pay_note: str = ""            # e.g. bank details, or "WhatsApp us the screenshot"
    launch_mode: str = ""
    sentry_dsn: str = ""                       # optional: sentry.io error alerts (free plan is enough)
    backup_dir: str = "./data/backups"         # nightly database backups (3am India time)
    backup_keep_days: int = 14
    # One-time: creates YOUR admin login on the live server at start-up, then delete both
    # variables in Railway. (Type them in Railway's dashboard yourself; min 12 characters.)
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""

    mock_ai: bool = True
    anthropic_api_key: str = ""
    # Two AI models: a smart one for big jobs (weekly growth report) and a
    # fast, cheaper one for small jobs done for every lead (tone, score).
    ai_model: str = "claude-opus-5-5"
    ai_model_fast: str = "claude-haiku-5-5"
    ai_timeout_seconds: int = 60
    # Run the AI workflow automatically on every new lead/message from a webhook
    auto_analyze: bool = True

    # The scheduler: publishes due posts and refreshes post numbers in the background
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 60       # how often it wakes up
    stats_refresh_hours: int = 6               # how often each post's numbers are re-read
    weekly_review_enabled: bool = True         # growth review for every business, Mondays from 9am

    # Reputation: "please review us" WhatsApp after a sale
    review_request_delay_hours: int = 3        # wait a bit after the sale before asking
    messages_from_hour: int = 10               # only message customers between 10am...
    messages_until_hour: int = 20              # ...and 8pm (India time)

    webhook_verify_token: str = "change-me"
    frontend_origin: str = "http://localhost:5173"

    # Login
    session_days: int = 30                     # how long you stay logged in on a device
    max_login_failures: int = 5                # wrong passwords allowed...
    login_lock_minutes: int = 15               # ...per this many minutes, before a short lock

    # Subscriptions and payments (Razorpay). While the keys are empty, payments
    # run in free MOCK mode: no real money, a "pretend pay" button instead.
    trial_days: int = 14                       # free trial for every new business
    payment_grace_days: int = 3                # a failed renewal keeps working this many extra days
    razorpay_key_id: str = ""                  # rzp_test_... or rzp_live_... (Dashboard → API Keys)
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""          # Dashboard → Webhooks (you choose it)
    razorpay_plan_starter: str = ""            # plan_... ids you create in Dashboard → Subscriptions → Plans
    razorpay_plan_growth: str = ""
    razorpay_plan_pro: str = ""

    # Security: one long random secret for this server. It locks the platform
    # keys we store and signs the "connect your account" links.
    # CHANGE IT before going live:  python -c "import secrets; print(secrets.token_urlsafe(48))"
    secret_key: str = "dev-only-secret-change-me"
    # This server's public address (Meta/Google send owners back here after "Connect")
    public_api_url: str = "http://127.0.0.1:8000"

    # Connecting real platforms. While a platform's app keys are empty, its
    # "Connect" button runs in free MOCK mode (pretend connection).
    meta_app_id: str = ""                      # developers.facebook.com → your app → App settings → Basic
    meta_app_secret: str = ""
    meta_graph_version: str = "v26.0"
    meta_whatsapp_config_id: str = ""          # Facebook Login for Business → Configurations (WhatsApp Embedded Signup)
    meta_pages_config_id: str = ""             # optional: a configuration for Facebook Pages (else plain scopes)
    instagram_app_id: str = ""                 # your app → Instagram → API setup with Instagram login
    instagram_app_secret: str = ""
    google_client_id: str = ""                 # console.cloud.google.com → APIs & Services → Credentials (OAuth client)
    google_client_secret: str = ""
    whatsapp_review_template: str = "review_request"   # WhatsApp template used for "please review us"
    whatsapp_template_language: str = "en"
    # Hot-lead alerts to the OWNER's phone (Task 28). Best: one Lead Intel WhatsApp number of your own
    # sends every owner's alerts (set both below, from your Meta app → WhatsApp → API setup). Without
    # them, alerts go from the business's own connected WhatsApp, or run in practice (mock) mode.
    alerts_whatsapp_phone_id: str = ""
    alerts_whatsapp_token: str = ""
    whatsapp_alert_template: str = "hot_lead_alert"     # WhatsApp template for owner alerts (utility)
    whatsapp_payment_template: str = "payment_reminder"  # WhatsApp template for "a gentle reminder: ₹... is due" (utility)
    reviews_sync_minutes: int = 30             # how often Google reviews are fetched

    # Photos and videos uploaded by owners (served publicly at /files/..., so
    # Instagram/Facebook/Google can fetch them when publishing)
    media_dir: str = "./data/media"
    max_photo_mb: int = 15
    max_video_mb: int = 100

    # Emails (password reset, welcome, trial reminders, receipts). While SMTP_HOST
    # is empty, emails run in MOCK mode: each one is saved as a file in
    # data/outbox/ that you can open in a browser to see exactly what was "sent".
    # Any provider works: Brevo (free 300/day), Zoho, Amazon SES, Gmail (app password)...
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True                 # port 587 → True; port 465 → use smtp_ssl instead
    smtp_ssl: bool = False
    email_from: str = "Lead Intel <hello@example.com>"   # use an address on YOUR domain
    email_reply_to: str = ""
    outbox_dir: str = "./data/outbox"
    company_name: str = "Lead Intel"           # your registered business name (receipts, legal pages)
    company_gstin: str = ""                    # optional: shown on receipts if you're GST-registered
    # Shown on the public website's Contact / Terms / Privacy pages. Razorpay checks these.
    company_address: str = ""                  # registered / operating address in India
    support_email: str = ""                    # e.g. support@yourdomain.in
    support_phone: str = ""                    # e.g. +91 98xxxxxxxx
    grievance_officer: str = ""                # a real person's name (required by Indian privacy rules)
    grievance_email: str = ""
    legal_city: str = "New Delhi"              # courts for disputes
    policies_updated: str = "18 October 2026"  # change when you edit the legal pages
    site_url: str = ""                         # the public website address, e.g. https://yourdomain.in (default: PUBLIC_API_URL)
    password_reset_minutes: int = 60
    trial_reminder_days: int = 3               # "your trial ends in 3 days"

    # Email lead reader: each business gets an address like leads-k3j9x2@<this domain>.
    # Owners auto-forward their Justdial / Sulekha / Practo lead emails there; an inbound
    # email service (e.g. Cloudflare Email Routing) passes each email to /webhooks/email.
    inbound_email_domain: str = "in.example.com"
    inbound_email_secret: str = "change-me-inbound"   # the email service must send this (X-Inbound-Key)

    # Competitor watch (Task 35): Google has no official ranking API, so real numbers need a
    # paid map-search data service, e.g. DataForSEO (dataforseo.com - no approval, just an
    # account and credit; roughly $0.0006-0.002 per search). While the login/password below
    # are empty, this runs in free MOCK mode with realistic, slowly-drifting pretend numbers.
    dataforseo_login: str = ""
    dataforseo_password: str = ""

    # Phone call tracking (Task 38): a tracking number per business, calls forwarded to the
    # owner, missed calls flagged, recordings saved. No single provider is used everywhere in
    # India; Exotel (exotel.com) is the reference here - paid per number + per minute, no
    # approval needed. While the credentials below are empty, this runs in free MOCK mode:
    # a demo number, and "Simulate a call" to try the feature before connecting a real one.
    calltracking_sid: str = ""
    calltracking_token: str = ""
    calltracking_subdomain: str = ""     # e.g. "api" (your Exotel account's API subdomain)

    # LinkedIn company-page posting (Task 40): posts for coaching, real estate, B2B businesses.
    # Needs Marketing Developer Platform approval from LinkedIn before real use.
    # While both keys are empty this runs in free MOCK mode.
    # developers.linkedin.com → Create App → Auth → OAuth 2.0 settings
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def meta_enabled(self) -> bool:
        return bool(self.meta_app_id and self.meta_app_secret)

    @property
    def instagram_enabled(self) -> bool:
        return bool(self.instagram_app_id and self.instagram_app_secret)

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def is_light(self) -> bool:
        """True = the 'only what really works' launch version (see launch_mode above)."""
        mode = self.launch_mode.strip().lower()
        return mode == "light" or (mode == "" and self.is_production)

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host)

    @property
    def payments_enabled(self) -> bool:
        """Real Razorpay is used only when both keys exist."""
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def ai_enabled(self) -> bool:
        """Real AI is used only when mock mode is off AND a key exists."""
        return not self.mock_ai and bool(self.anthropic_api_key)

    @property
    def linkedin_enabled(self) -> bool:
        return bool(self.linkedin_client_id and self.linkedin_client_secret)

    @property
    def mapsearch_enabled(self) -> bool:
        return bool(self.dataforseo_login and self.dataforseo_password)

    @property
    def calltracking_enabled(self) -> bool:
        return bool(self.calltracking_sid and self.calltracking_token and self.calltracking_subdomain)


@lru_cache
def get_settings() -> Settings:
    # lru_cache = read the .env file once, then reuse the same object.
    return Settings()


def _own_secret_key(current: "Settings") -> None:
    """Live server without SECRET_KEY set: make a strong random one ONCE and keep it on the
    server's private disk (/data/.secret_key), so it never has to be typed or shared."""
    import os
    import secrets
    from pathlib import Path

    if not current.is_production or current.secret_key != "dev-only-secret-change-me":
        return
    key_file = Path(os.environ.get("SECRET_KEY_FILE", "/data/.secret_key"))
    try:
        if not key_file.exists():
            key_file.parent.mkdir(parents=True, exist_ok=True)
            key_file.write_text(secrets.token_urlsafe(48))
            key_file.chmod(0o600)
        current.secret_key = key_file.read_text().strip()
    except OSError:
        pass                                # no disk: start-up then refuses with a clear message


settings = get_settings()
_own_secret_key(settings)
