"""
Email sender — sends the HTML report via Resend (HTTP API)
or SMTP as fallback for non-Railway deployments.

Resend free tier: 100 emails/day, 3000/month. More than enough.
"""

import smtplib
import ssl
import logging

logger = logging.getLogger("ads-digest.email")


class EmailSender:
    def __init__(
        self,
        smtp_host: str = "",
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_password: str = "",
        from_email: str = "",
        resend_api_key: str = "",
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_email = from_email
        self.resend_api_key = resend_api_key

    def send(self, to_emails: list[str], subject: str, html_body: str):
        """Send email via Resend API (preferred) or SMTP fallback."""
        if self.resend_api_key:
            self._send_resend(to_emails, subject, html_body)
        elif self.smtp_user and self.smtp_password:
            self._send_smtp(to_emails, subject, html_body)
        else:
            raise Exception("No email method configured. Add a Resend API key or SMTP credentials.")

    def _send_resend(self, to_emails: list[str], subject: str, html_body: str):
        """Send via Resend HTTP API — works on Railway."""
        import requests

        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {self.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": f"TPZ Ads Digest <{self.from_email}>",
                "to": to_emails,
                "subject": subject,
                "html": html_body,
            },
            timeout=30,
        )

        if resp.status_code in (200, 201):
            logger.info(f"Email sent via Resend to {len(to_emails)} recipient(s)")
        else:
            error = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            raise Exception(f"Resend API {resp.status_code}: {error}")

    def _send_smtp(self, to_emails: list[str], subject: str, html_body: str):
        """Send via SMTP — for non-Railway deployments."""
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"TPZ Ads Digest <{self.from_email}>"
        msg["To"] = ", ".join(to_emails)
        msg.attach(MIMEText("Your daily ads digest is ready.", "plain"))
        msg.attach(MIMEText(html_body, "html"))

        # Try STARTTLS first, then SSL
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, to_emails, msg.as_string())
            logger.info(f"Email sent via STARTTLS to {len(to_emails)} recipient(s)")
            return
        except Exception as e:
            logger.warning(f"STARTTLS failed: {e}")

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.smtp_host, 465, timeout=30, context=context) as server:
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, to_emails, msg.as_string())
            logger.info(f"Email sent via SSL to {len(to_emails)} recipient(s)")
        except Exception as e:
            raise Exception(f"SMTP failed (STARTTLS and SSL). Error: {e}")
