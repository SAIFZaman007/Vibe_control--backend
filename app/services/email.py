"""
Email service (SMTP).
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


def send_otp_email(to: str, full_name: str, code: str) -> None:
    """Email a 6-digit signup verification code."""
    minutes = settings.OTP_EXPIRE_MINUTES
    subject = f"Your Vibe Control code: {code}"
    text_body = (
        f"Hi {full_name},\n\n"
        f"Your Vibe Control verification code is: {code}\n\n"
        f"It expires in {minutes} minutes. If you didn't sign up, ignore this email."
    )
    # Spaced digits render nicely and are easy to read/copy.
    spaced = " ".join(code)
    html_body = f"""\
    <div style="font-family:system-ui,Arial,sans-serif;max-width:480px;margin:auto;color:#14121A">
      <h2 style="margin:0 0 4px">Verify your email</h2>
      <p style="color:#6B7280;margin:0 0 24px">Hi {full_name}, enter this code to activate your account.</p>
      <div style="font-size:34px;font-weight:800;letter-spacing:10px;
                  background:#F7F7F8;border:1px solid #E7E7EA;border-radius:14px;
                  padding:20px;text-align:center;color:#7C3AED">{spaced}</div>
      <p style="color:#6B7280;font-size:13px;margin-top:20px">
        This code expires in {minutes} minutes. If you didn't request it, you can safely ignore this email.
      </p>
    </div>"""
    _send(to, subject, html_body, text_body)
