"""
Email sender — sends the HTML report via SMTP.
Supports Gmail, SES, SendGrid, or any SMTP server.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging

logger = logging.getLogger("ads-digest.email")


class EmailSender:
    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        from_email: str,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_email = from_email

    def send(self, to_emails: list[str], subject: str, html_body: str):
        """Send an HTML email to one or more recipients."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"TPZ Ads Digest <{self.from_email}>"
        msg["To"] = ", ".join(to_emails)

        # Plain-text fallback
        plain_text = "Your daily ads digest is ready. View this email in an HTML-capable client."
        msg.attach(MIMEText(plain_text, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, to_emails, msg.as_string())
            logger.info(f"Email sent successfully to {len(to_emails)} recipient(s)")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            raise
