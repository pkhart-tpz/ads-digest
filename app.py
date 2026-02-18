"""
TPZ Daily Ads Digest — Web Application
=======================================
A hosted dashboard that:
  - Shows your latest digest report in the browser
  - Lets you manage API credentials via a settings page
  - Runs the digest automatically every morning
  - Emails the report to your team
  - Has a "Run Now" button for on-demand reports

Deploy to Railway (free) with one click.
"""

import os
import json
import asyncio
import logging
import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from apscheduler.schedulers.background import BackgroundScheduler

# ── Local modules ────────────────────────────────────────
from meta_ads import MetaAdsClient
from google_ads_client import GoogleAdsClient
from shopify_client import ShopifyClient
from analyzer import AIAnalyzer
from email_sender import EmailSender
from report_builder import ReportBuilder
from sample_data import get_sample_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ads-digest-web")

# ── App setup ────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

DATA_DIR = Path(os.environ.get("DATA_DIR", "/tmp/ads-digest-data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"
REPORTS_DIR = DATA_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Simple auth ──────────────────────────────────────────
# Set DASHBOARD_PASSWORD env var to protect the dashboard.
# If not set, the app is open (fine for private Railway deploys).
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if DASHBOARD_PASSWORD and not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ── Settings helpers ─────────────────────────────────────

SETTING_KEYS = [
    "BRAND_NAME",
    "SHOPIFY_SHOP_DOMAIN", "SHOPIFY_CLIENT_ID", "SHOPIFY_CLIENT_SECRET",
    "ANTHROPIC_API_KEY",
    "META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID",
    "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN",
    "GOOGLE_CUSTOMER_ID", "GOOGLE_DEVELOPER_TOKEN",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
    "FROM_EMAIL", "RECIPIENT_EMAILS",
    "SCHEDULE_HOUR", "SCHEDULE_MINUTE", "SCHEDULE_TIMEZONE",
]

DEFAULTS = {
    "BRAND_NAME": "SMBL",
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": "587",
    "SCHEDULE_HOUR": "7",
    "SCHEDULE_MINUTE": "0",
    "SCHEDULE_TIMEZONE": "America/Denver",
}


def load_settings() -> dict:
    """Load settings from file, falling back to env vars then defaults."""
    saved = {}
    if SETTINGS_FILE.exists():
        try:
            saved = json.loads(SETTINGS_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            pass

    settings = {}
    for key in SETTING_KEYS:
        settings[key] = saved.get(key) or os.environ.get(key, DEFAULTS.get(key, ""))
    return settings


def save_settings(settings: dict):
    """Persist settings to disk."""
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))


def get_report_list() -> list:
    """Get list of saved reports, newest first."""
    reports = []
    for f in sorted(REPORTS_DIR.glob("*.json"), reverse=True):
        try:
            meta = json.loads(f.read_text())
            reports.append({
                "filename": f.name,
                "date": meta.get("date", ""),
                "brand": meta.get("brand", ""),
                "generated_at": meta.get("generated_at", ""),
                "orders": meta.get("shopify_orders", 0),
                "revenue": meta.get("shopify_revenue", 0),
                "spend": meta.get("total_spend", 0),
            })
        except (json.JSONDecodeError, IOError):
            pass
    return reports[:30]  # Keep last 30


def save_report(date: str, brand: str, html: str, meta_data: dict, google_data: dict, shopify_data: dict):
    """Save a report to disk."""
    meta_spend = float(meta_data.get("account_summary", {}).get("spend", 0))
    google_spend = float(google_data.get("account_summary", {}).get("spend", 0))

    report = {
        "date": date,
        "brand": brand,
        "generated_at": datetime.now().isoformat(),
        "html": html,
        "shopify_orders": shopify_data.get("summary", {}).get("total_orders", 0),
        "shopify_revenue": shopify_data.get("summary", {}).get("net_revenue", 0),
        "total_spend": round(meta_spend + google_spend, 2),
    }

    filename = f"{date}_{brand}.json"
    (REPORTS_DIR / filename).write_text(json.dumps(report))
    return filename


# ── Digest pipeline ──────────────────────────────────────

async def run_digest_async(date: str = None, test_mode: bool = False):
    """Run the full digest pipeline."""
    settings = load_settings()

    if date is None:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    brand = settings.get("BRAND_NAME", "SMBL")
    logger.info(f"Running digest for {brand} — {date}")

    # ── Pull data ────────────────────────────────────────
    if test_mode:
        meta_data, google_data, shopify_data = get_sample_data()
    else:
        # Meta
        meta_data = {"platform": "meta", "date": date, "account_summary": {}, "campaigns": [], "ad_sets": [], "ads": []}
        if settings.get("META_ACCESS_TOKEN") and settings.get("META_AD_ACCOUNT_ID"):
            try:
                meta_client = MetaAdsClient(
                    access_token=settings["META_ACCESS_TOKEN"],
                    ad_account_id=settings["META_AD_ACCOUNT_ID"],
                )
                meta_data = meta_client.get_daily_report(date)
                logger.info(f"Meta: {len(meta_data.get('campaigns', []))} campaigns")
            except Exception as e:
                logger.error(f"Meta error: {e}")

        # Google
        google_data = {"platform": "google", "date": date, "account_summary": {}, "campaigns": [], "ad_groups": [], "ads": []}
        if settings.get("GOOGLE_CLIENT_ID") and settings.get("GOOGLE_REFRESH_TOKEN"):
            try:
                google_client = GoogleAdsClient(
                    client_id=settings["GOOGLE_CLIENT_ID"],
                    client_secret=settings["GOOGLE_CLIENT_SECRET"],
                    refresh_token=settings["GOOGLE_REFRESH_TOKEN"],
                    customer_id=settings["GOOGLE_CUSTOMER_ID"],
                    developer_token=settings["GOOGLE_DEVELOPER_TOKEN"],
                )
                google_data = google_client.get_daily_report(date)
                logger.info(f"Google: {len(google_data.get('campaigns', []))} campaigns")
            except Exception as e:
                logger.error(f"Google error: {e}")

        # Shopify
        shopify_data = {"platform": "shopify", "date": date, "summary": {"total_orders": 0, "net_revenue": 0, "average_order_value": 0, "new_customer_rate": 0, "total_discount_amount": 0, "total_revenue": 0, "total_refunds": 0, "total_units_sold": 0, "new_customers": 0, "returning_customers": 0}, "top_products": [], "discount_codes": {}, "hourly_orders": [], "orders": [], "inventory_alerts": []}
        if settings.get("SHOPIFY_CLIENT_ID") and settings.get("SHOPIFY_CLIENT_SECRET"):
            try:
                shopify_client = ShopifyClient(
                    shop_domain=settings["SHOPIFY_SHOP_DOMAIN"],
                    client_id=settings["SHOPIFY_CLIENT_ID"],
                    client_secret=settings["SHOPIFY_CLIENT_SECRET"],
                )
                shopify_data = shopify_client.get_daily_report(date)
                inventory_alerts = shopify_client.get_inventory_alerts(threshold=10)
                shopify_data["inventory_alerts"] = inventory_alerts
                logger.info(f"Shopify: {shopify_data['summary']['total_orders']} orders")
            except Exception as e:
                logger.error(f"Shopify error: {e}")

    # ── AI Analysis ──────────────────────────────────────
    if not settings.get("ANTHROPIC_API_KEY"):
        raise ValueError("Anthropic API key is required")

    analyzer = AIAnalyzer(api_key=settings["ANTHROPIC_API_KEY"])
    analysis = await analyzer.analyze(
        meta_data=meta_data,
        google_data=google_data,
        shopify_data=shopify_data,
        date=date,
        brand=brand,
    )

    # ── Build report ─────────────────────────────────────
    builder = ReportBuilder()
    html_report = builder.build(
        meta_data=meta_data,
        google_data=google_data,
        shopify_data=shopify_data,
        analysis=analysis,
        date=date,
        brand=brand,
    )

    # ── Save report ──────────────────────────────────────
    save_report(date, brand, html_report, meta_data, google_data, shopify_data)

    # ── Send email ───────────────────────────────────────
    recipients_raw = settings.get("RECIPIENT_EMAILS", "")
    recipients = [e.strip() for e in recipients_raw.split(",") if e.strip()]

    if settings.get("SMTP_USER") and settings.get("SMTP_PASSWORD") and recipients:
        try:
            sender = EmailSender(
                smtp_host=settings.get("SMTP_HOST", "smtp.gmail.com"),
                smtp_port=int(settings.get("SMTP_PORT", "587")),
                smtp_user=settings["SMTP_USER"],
                smtp_password=settings["SMTP_PASSWORD"],
                from_email=settings.get("FROM_EMAIL", settings["SMTP_USER"]),
            )
            subject = f"📊 {brand} Daily Ads Digest — {date}"
            sender.send(to_emails=recipients, subject=subject, html_body=html_report)
            logger.info(f"Email sent to {', '.join(recipients)}")
        except Exception as e:
            logger.error(f"Email error: {e}")
    else:
        logger.warning("Email not configured — skipping send")

    return html_report


def run_digest_sync(date=None, test_mode=False):
    """Synchronous wrapper for the scheduler."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_digest_async(date=date, test_mode=test_mode))
        loop.close()
    except Exception as e:
        logger.error(f"Scheduled digest failed: {e}")


# ── Scheduler ────────────────────────────────────────────

scheduler = BackgroundScheduler()


def setup_scheduler():
    """Set up the daily digest schedule."""
    scheduler.remove_all_jobs()
    settings = load_settings()
    hour = int(settings.get("SCHEDULE_HOUR", 7))
    minute = int(settings.get("SCHEDULE_MINUTE", 0))
    tz = settings.get("SCHEDULE_TIMEZONE", "America/Denver")

    scheduler.add_job(
        run_digest_sync,
        "cron",
        hour=hour,
        minute=minute,
        timezone=tz,
        id="daily_digest",
        replace_existing=True,
    )
    logger.info(f"Scheduled daily digest at {hour:02d}:{minute:02d} ({tz})")


# ── Routes ───────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if not DASHBOARD_PASSWORD:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        if request.form.get("password") == DASHBOARD_PASSWORD:
            session["authenticated"] = True
            return redirect(url_for("dashboard"))
        flash("Incorrect password", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("authenticated", None)
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    reports = get_report_list()
    settings = load_settings()
    next_run = None
    jobs = scheduler.get_jobs()
    if jobs:
        next_run = jobs[0].next_run_time

    # Check which integrations are configured
    integrations = {
        "shopify": bool(settings.get("SHOPIFY_CLIENT_ID") and settings.get("SHOPIFY_CLIENT_SECRET")),
        "meta": bool(settings.get("META_ACCESS_TOKEN") and settings.get("META_AD_ACCOUNT_ID")),
        "google": bool(settings.get("GOOGLE_CLIENT_ID") and settings.get("GOOGLE_REFRESH_TOKEN")),
        "email": bool(settings.get("SMTP_USER") and settings.get("SMTP_PASSWORD")),
        "ai": bool(settings.get("ANTHROPIC_API_KEY")),
    }

    return render_template("dashboard.html",
        reports=reports,
        integrations=integrations,
        brand=settings.get("BRAND_NAME", "SMBL"),
        next_run=next_run,
    )


@app.route("/report/<filename>")
@login_required
def view_report(filename):
    filepath = REPORTS_DIR / filename
    if not filepath.exists():
        flash("Report not found", "error")
        return redirect(url_for("dashboard"))
    data = json.loads(filepath.read_text())
    return data.get("html", "<p>Report data missing</p>")


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_page():
    if request.method == "POST":
        settings = {}
        for key in SETTING_KEYS:
            val = request.form.get(key, "").strip()
            settings[key] = val
        save_settings(settings)
        setup_scheduler()
        flash("Settings saved!", "success")
        return redirect(url_for("settings_page"))

    settings = load_settings()

    # Mask sensitive values for display
    SENSITIVE_KEYS = [
        "SHOPIFY_CLIENT_SECRET", "ANTHROPIC_API_KEY", "META_ACCESS_TOKEN",
        "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN", "GOOGLE_DEVELOPER_TOKEN",
        "SMTP_PASSWORD",
    ]
    masked = {}
    for key in SETTING_KEYS:
        val = settings.get(key, "")
        if key in SENSITIVE_KEYS and val:
            masked[key] = val[:8] + "•" * max(0, len(val) - 12) + val[-4:] if len(val) > 12 else "•" * len(val)
        else:
            masked[key] = val

    return render_template("settings.html", settings=settings, masked=masked)


@app.route("/run", methods=["POST"])
@login_required
def run_now():
    date = request.form.get("date")
    test_mode = request.form.get("test") == "1"
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_digest_async(date=date, test_mode=test_mode))
        loop.close()
        flash(f"Digest generated for {date or 'yesterday'}!", "success")
    except Exception as e:
        flash(f"Error: {str(e)}", "error")
        logger.error(f"Manual run failed: {e}", exc_info=True)
    return redirect(url_for("dashboard"))


@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


# ── Start ────────────────────────────────────────────────

if not scheduler.running:
    setup_scheduler()
    scheduler.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
