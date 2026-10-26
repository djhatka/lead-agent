"""
"Am I ready to go live?" A checklist of settings that are still on their
demo/default values. Used by GET /admin/launch-check (and Task 26).
"""

from app.config import settings

DEFAULTS = {"secret_key": "dev-only-secret-change-me", "webhook_verify_token": "change-me",
            "inbound_email_secret": "change-me-inbound"}


def checks() -> list[dict]:
    s = settings
    items = [
        ("SECRET_KEY changed from the demo value", s.secret_key != DEFAULTS["secret_key"] and len(s.secret_key) >= 32,
         'python -c "import secrets; print(secrets.token_urlsafe(48))" → SECRET_KEY'),
        ("WEBHOOK_VERIFY_TOKEN changed", s.webhook_verify_token != DEFAULTS["webhook_verify_token"], "any long random text"),
        ("INBOUND_EMAIL_SECRET changed", s.inbound_email_secret != DEFAULTS["inbound_email_secret"], "any long random text"),
        ("PUBLIC_API_URL is a public https address", s.public_api_url.startswith("https://"), "e.g. https://api.yourdomain.in"),
        ("FRONTEND_ORIGIN is the live dashboard", s.frontend_origin.startswith("https://"), "e.g. https://app.yourdomain.in"),
        ("Company details on the legal pages", all([s.company_address, s.support_email, s.support_phone]),
         "COMPANY_NAME, COMPANY_ADDRESS, SUPPORT_EMAIL, SUPPORT_PHONE"),
        ("Grievance officer named", bool(s.grievance_officer and s.grievance_email), "GRIEVANCE_OFFICER, GRIEVANCE_EMAIL"),
        ("Real AI switched on", s.ai_enabled, "MOCK_AI=false and ANTHROPIC_API_KEY"),
        ("Real payments (Razorpay)", s.payments_enabled and all([s.razorpay_webhook_secret, s.razorpay_plan_starter,
                                                                  s.razorpay_plan_growth, s.razorpay_plan_pro]),
         "RAZORPAY_KEY_ID/SECRET, RAZORPAY_WEBHOOK_SECRET, the three RAZORPAY_PLAN_ ids"),
        ("Real emails (SMTP)", s.email_enabled and "example.com" not in s.email_from, "SMTP_HOST... and EMAIL_FROM on your domain"),
        ("Meta app (WhatsApp, Facebook)", s.meta_enabled, "META_APP_ID, META_APP_SECRET, META_WHATSAPP_CONFIG_ID"),
        ("Instagram app", s.instagram_enabled, "INSTAGRAM_APP_ID, INSTAGRAM_APP_SECRET"),
        ("Google app", s.google_enabled, "GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET"),
        ("Lead-email domain set", s.inbound_email_domain != "in.example.com", "INBOUND_EMAIL_DOMAIN"),
        ("One-time admin variables removed", not (s.bootstrap_admin_email or s.bootstrap_admin_password),
         "delete BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD in Railway after the first start"),
    ]
    must = {"SECRET_KEY changed from the demo value", "WEBHOOK_VERIFY_TOKEN changed", "INBOUND_EMAIL_SECRET changed",
            "PUBLIC_API_URL is a public https address", "FRONTEND_ORIGIN is the live dashboard",
            "Company details on the legal pages", "Grievance officer named"}
    return [{"item": name, "ok": bool(ok), "must_have": name in must, "how": how} for name, ok, how in items]
