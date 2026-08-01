"""
Email service (SMTP).

Uses Python's built-in `smtplib` — no third-party dependency required. When
`EMAIL_ENABLED` is False (the default in development), emails are logged instead
of sent, so you can develop without a mail server and read the verification link
straight from the console.
"""

import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger("vibe.email")


def _send(to: str, subject: str, html_body: str, text_body: str) -> None:
    if not settings.EMAIL_ENABLED:
        logger.info("[email disabled] To=%s | %s\n%s", to, subject, text_body)
        return

    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        if settings.SMTP_TLS:
            server.starttls()
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)
    logger.info("Sent email to %s (%s)", to, subject)


def send_verification_email(to: str, full_name: str, token: str) -> None:
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    subject = "Verify your Vibe Control account"
    text_body = (
        f"Hi {full_name},\n\n"
        f"Welcome to Vibe Control! Confirm your email to activate your account:\n"
        f"{verify_url}\n\n"
        f"If you didn't sign up, you can ignore this message."
    )
    html_body = f"""\
    <div style="font-family:system-ui,Arial,sans-serif;max-width:480px;margin:auto">
      <h2 style="color:#111">Welcome to Vibe Control</h2>
      <p>Hi {full_name}, confirm your email to start creating.</p>
      <p style="margin:28px 0">
        <a href="{verify_url}"
           style="background:#6d28d9;color:#fff;padding:12px 22px;border-radius:10px;
                  text-decoration:none;font-weight:600">Verify email</a>
      </p>
      <p style="color:#666;font-size:13px">
        Or paste this link into your browser:<br>{verify_url}
      </p>
    </div>"""
    _send(to, subject, html_body, text_body)
