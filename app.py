"""
TPZ Daily Ads Digest — Web Application
=======================================
A hosted dashboard that:
  - Shows your latest digest report in the browser
  - Lets you manage API credentials via a settings page
  - Runs the digest automatically every morning
  - Emails the report to your team
  - Has a "Run Now" button for on-demand reports
  - Shows DoD and WoW performance trends

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
from klaviyo_client import KlaviyoClient
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
    "KLAVIYO_API_KEY",
    "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN",
    "GOOGLE_CUSTOMER_ID", "GOOGLE_DEVELOPER_TOKEN",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
    "RESEND_API_KEY",
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


def save_report(date: str, brand: str, html: str, meta_data: dict, google_data: dict, shopify_data: dict, klaviyo_data: dict = None):
    """Save a report with detailed metrics for DoD/WoW comparisons."""
    meta_summary = meta_data.get("account_summary", {})
    google_summary = google_data.get("account_summary", {})
    shop_summary = shopify_data.get("summary", {})

    meta_spend = float(meta_summary.get("spend", 0))
    google_spend = float(google_summary.get("spend", 0))

    from meta_ads import MetaAdsClient
    meta_purchases = MetaAdsClient.extract_purchase_metrics(meta_summary)

    report = {
        "date": date,
        "brand": brand,
        "generated_at": datetime.now().isoformat(),
        "html": html,
        # Summary metrics for DoD/WoW
        "shopify_orders": shop_summary.get("total_orders", 0),
        "shopify_revenue": shop_summary.get("net_revenue", 0),
        "shopify_aov": shop_summary.get("average_order_value", 0),
        "shopify_new_customer_rate": shop_summary.get("new_customer_rate", 0),
        "shopify_units": shop_summary.get("total_units_sold", 0),
        "meta_spend": meta_spend,
        "google_spend": google_spend,
        "total_spend": round(meta_spend + google_spend, 2),
        "meta_clicks": int(meta_summary.get("clicks", 0)),
        "google_clicks": int(google_summary.get("clicks", 0)),
        "meta_roas": meta_purchases["roas"],
        "meta_purchases": meta_purchases["purchases"],
        "meta_cpm": float(meta_summary.get("cpm", 0)),
        "meta_ctr": float(meta_summary.get("ctr", 0)),
        "google_roas": float(google_summary.get("roas", 0)),
        "google_conversions": float(google_summary.get("conversions", 0)),
        "platform_claimed_revenue": meta_purchases["purchase_value"] + float(google_summary.get("conversion_value", 0)),
        "klaviyo_emails_sent": (klaviyo_data or {}).get("summary", {}).get("emails_sent", 0),
        "klaviyo_revenue": (klaviyo_data or {}).get("summary", {}).get("revenue_attributed", 0),
        "klaviyo_open_rate": (klaviyo_data or {}).get("summary", {}).get("open_rate", 0),
        "klaviyo_click_rate": (klaviyo_data or {}).get("summary", {}).get("click_rate", 0),
    }

    filename = f"{date}_{brand}.json"
    (REPORTS_DIR / filename).write_text(json.dumps(report))
    return filename


def load_comparison_data(date: str, brand: str) -> dict:
    """Load previous day and previous week data for DoD/WoW comparison."""
    from datetime import datetime as dt

    target = dt.strptime(date, "%Y-%m-%d")
    prev_day = (target - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_week = (target - timedelta(days=7)).strftime("%Y-%m-%d")

    def load_report(d):
        filepath = REPORTS_DIR / f"{d}_{brand}.json"
        if filepath.exists():
            try:
                data = json.loads(filepath.read_text())
                # Only return if it has the detailed metrics
                if "shopify_revenue" in data:
                    return data
            except (json.JSONDecodeError, IOError):
                pass
        return None

    return {
        "prev_day": load_report(prev_day),
        "prev_day_date": prev_day,
        "prev_week": load_report(prev_week),
        "prev_week_date": prev_week,
    }


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
        klaviyo_data = {"platform": "klaviyo", "date": date or "sample", "summary": {"emails_sent": 1250, "emails_delivered": 1220, "emails_opened": 488, "emails_clicked": 61, "open_rate": 40.0, "click_rate": 5.0, "unsubscribes": 2, "revenue_attributed": 892.50, "sms_sent": 0, "sms_clicked": 0}, "campaigns": [], "flows_summary": {"emails_sent": 800, "revenue_attributed": 645.00}}
    else:
        errors = []

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
                if not meta_data.get("campaigns"):
                    errors.append(f"Meta: Connected but returned 0 campaigns for {date}.")
            except Exception as e:
                errors.append(f"Meta API error: {e}")
                logger.error(f"Meta error: {e}", exc_info=True)
        else:
            missing = []
            if not settings.get("META_ACCESS_TOKEN"):
                missing.append("Access Token")
            if not settings.get("META_AD_ACCOUNT_ID"):
                missing.append("Ad Account ID")
            errors.append(f"Meta: Skipped — missing {', '.join(missing)}")

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
                errors.append(f"Google Ads error: {e}")
                logger.error(f"Google error: {e}", exc_info=True)

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
                logger.info(f"Shopify: {shopify_data['summary']['total_orders']} orders")
            except Exception as e:
                errors.append(f"Shopify error: {e}")
                logger.error(f"Shopify error: {e}", exc_info=True)

        # Klaviyo
        klaviyo_data = {"platform": "klaviyo", "date": date, "summary": {"emails_sent": 0, "emails_delivered": 0, "emails_opened": 0, "emails_clicked": 0, "open_rate": 0, "click_rate": 0, "unsubscribes": 0, "revenue_attributed": 0, "sms_sent": 0, "sms_clicked": 0}, "campaigns": [], "flows_summary": {"emails_sent": 0, "revenue_attributed": 0}}
        if settings.get("KLAVIYO_API_KEY"):
            try:
                kl_client = KlaviyoClient(
                    private_api_key=settings["KLAVIYO_API_KEY"],
                )
                klaviyo_data = kl_client.get_daily_report(date)
                logger.info(f"Klaviyo: {klaviyo_data['summary']['emails_sent']} emails sent, ${klaviyo_data['summary']['revenue_attributed']} attributed revenue")
            except Exception as e:
                errors.append(f"Klaviyo error: {e}")
                logger.error(f"Klaviyo error: {e}", exc_info=True)

        # Surface errors
        try:
            for err in errors:
                flash(err, "error")
        except RuntimeError:
            pass

    # ── Load comparison data for DoD/WoW ─────────────────
    comparison = load_comparison_data(date, brand)

    # ── AI Analysis ──────────────────────────────────────
    if not settings.get("ANTHROPIC_API_KEY"):
        raise ValueError("Anthropic API key is required")

    analyzer = AIAnalyzer(api_key=settings["ANTHROPIC_API_KEY"])
    analysis = await analyzer.analyze(
        meta_data=meta_data,
        google_data=google_data,
        shopify_data=shopify_data,
        klaviyo_data=klaviyo_data,
        date=date,
        brand=brand,
        comparison=comparison,
    )

    # ── Build report ─────────────────────────────────────
    builder = ReportBuilder()
    html_report = builder.build(
        meta_data=meta_data,
        google_data=google_data,
        shopify_data=shopify_data,
        klaviyo_data=klaviyo_data,
        analysis=analysis,
        date=date,
        brand=brand,
        comparison=comparison,
    )

    # ── Save report ──────────────────────────────────────
    save_report(date, brand, html_report, meta_data, google_data, shopify_data, klaviyo_data)

    # ── Send email ───────────────────────────────────────
    recipients_raw = settings.get("RECIPIENT_EMAILS", "")
    recipients = [e.strip() for e in recipients_raw.split(",") if e.strip()]

    has_resend = bool(settings.get("RESEND_API_KEY"))
    has_smtp = bool(settings.get("SMTP_USER") and settings.get("SMTP_PASSWORD"))

    email_error = None
    if (has_resend or has_smtp) and recipients:
        try:
            sender = EmailSender(
                smtp_host=settings.get("SMTP_HOST", "smtp.gmail.com"),
                smtp_port=int(settings.get("SMTP_PORT", "587")),
                smtp_user=settings.get("SMTP_USER", ""),
                smtp_password=settings.get("SMTP_PASSWORD", ""),
                from_email=settings.get("FROM_EMAIL", settings.get("SMTP_USER", "")),
                resend_api_key=settings.get("RESEND_API_KEY", ""),
            )
            subject = f"{brand} Daily Ads Digest — {date}"
            sender.send(to_emails=recipients, subject=subject, html_body=html_report)
            logger.info(f"Email sent to {', '.join(recipients)}")
        except Exception as e:
            email_error = f"Email failed: {e}"
            logger.error(f"Email error: {e}", exc_info=True)
    else:
        missing = []
        if not has_resend and not has_smtp:
            missing.append("Resend API Key or SMTP credentials")
        if not recipients:
            missing.append("Recipient Emails")
        email_error = f"Email: Skipped — missing {', '.join(missing)}"
        logger.warning(email_error)

    if email_error:
        try:
            flash(email_error, "error")
        except RuntimeError:
            pass

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
        "klaviyo": bool(settings.get("KLAVIYO_API_KEY")),
        "google": bool(settings.get("GOOGLE_CLIENT_ID") and settings.get("GOOGLE_REFRESH_TOKEN")),
        "email": bool(settings.get("RESEND_API_KEY") or (settings.get("SMTP_USER") and settings.get("SMTP_PASSWORD"))),
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
        "KLAVIYO_API_KEY",
        "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN", "GOOGLE_DEVELOPER_TOKEN",
        "SMTP_PASSWORD", "RESEND_API_KEY",
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


@app.route("/test-email", methods=["POST"])
@login_required
def test_email():
    settings = load_settings()
    recipients_raw = settings.get("RECIPIENT_EMAILS", "")
    recipients = [e.strip() for e in recipients_raw.split(",") if e.strip()]

    has_resend = bool(settings.get("RESEND_API_KEY"))
    has_smtp = bool(settings.get("SMTP_USER") and settings.get("SMTP_PASSWORD"))

    if not has_resend and not has_smtp:
        flash("Email not configured — enter a Resend API key or SMTP credentials in Settings.", "error")
        return redirect(url_for("settings_page"))
    if not recipients:
        flash("No recipient emails configured in Settings.", "error")
        return redirect(url_for("settings_page"))

    try:
        sender = EmailSender(
            smtp_host=settings.get("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=int(settings.get("SMTP_PORT", "587")),
            smtp_user=settings.get("SMTP_USER", ""),
            smtp_password=settings.get("SMTP_PASSWORD", ""),
            from_email=settings.get("FROM_EMAIL", settings.get("SMTP_USER", "")),
            resend_api_key=settings.get("RESEND_API_KEY", ""),
        )
        html = """<div style="font-family:sans-serif;padding:40px;text-align:center;">
            <h1 style="color:#6366f1;">TPZ Ads Digest</h1>
            <p style="font-size:18px;color:#333;">Email is working! Your daily digest will arrive here.</p>
            <p style="color:#888;font-size:13px;">This is a test email sent from your Ads Digest dashboard.</p>
        </div>"""
        sender.send(to_emails=recipients, subject="TPZ Ads Digest — Test Email", html_body=html)
        flash(f"Test email sent to {', '.join(recipients)}!", "success")
    except Exception as e:
        flash(f"Email failed: {e}", "error")
        logger.error(f"Test email failed: {e}", exc_info=True)

    return redirect(url_for("settings_page"))


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
