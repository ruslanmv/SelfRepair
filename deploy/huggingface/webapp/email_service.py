"""Transactional email for SelfRepair auth flows, via Mailtrap.

Sending is best-effort and non-blocking (dispatched on a background thread).
If Mailtrap is not configured or a send fails, the failure is logged and the
caller still completes — in demo mode the verification/reset link can be shown
in the UI instead (controlled by ``SELFREPAIR_DEMO_LINKS``).
"""
from __future__ import annotations

import logging
import os
import threading

logger = logging.getLogger(__name__)

_TOKEN = os.environ.get("MAILTRAP_TOKEN", "")
_SENDER_EMAIL = os.environ.get("MAILTRAP_SENDER", "hello@demomailtrap.co")
_SENDER_NAME = os.environ.get("MAILTRAP_SENDER_NAME", "SelfRepair")


def configured() -> bool:
    return bool(_TOKEN)


def demo_links_enabled() -> bool:
    return os.environ.get("SELFREPAIR_DEMO_LINKS", "0") == "1"


def _send_sync(to_email: str, subject: str, text: str, html: str | None) -> bool:
    if not _TOKEN:
        logger.info("Mailtrap not configured; skipping email to %s (%s).", to_email, subject)
        return False
    try:
        import mailtrap as mt

        mail = mt.Mail(
            sender=mt.Address(email=_SENDER_EMAIL, name=_SENDER_NAME),
            to=[mt.Address(email=to_email)],
            subject=subject,
            text=text,
            html=html or None,
            category="SelfRepair Auth",
        )
        client = mt.MailtrapClient(token=_TOKEN)
        client.send(mail)
        logger.info("Sent '%s' email to %s.", subject, to_email)
        return True
    except Exception as exc:  # pragma: no cover - network/provider dependent
        logger.warning("Email send to %s failed: %s", to_email, exc)
        return False


def send_async(to_email: str, subject: str, text: str, html: str | None = None) -> None:
    threading.Thread(
        target=_send_sync, args=(to_email, subject, text, html), daemon=True
    ).start()


def _wrap(title: str, body_html: str, cta_label: str, cta_url: str) -> str:
    return f"""\
<div style="font-family:Arial,Helvetica,sans-serif;background:#000402;padding:32px;color:#6cf3a0">
  <div style="max-width:480px;margin:auto;background:#050d09;border:1px solid rgba(0,255,102,.18);border-radius:12px;padding:28px">
    <h1 style="color:#d2ffdf;font-size:20px;margin:0 0 6px">SelfRepair</h1>
    <p style="color:#34c873;font-size:12px;letter-spacing:.12em;text-transform:uppercase;margin:0 0 18px">{title}</p>
    {body_html}
    <p style="margin:24px 0">
      <a href="{cta_url}" style="display:inline-block;background:#00ff66;color:#001a0a;font-weight:700;
         text-decoration:none;padding:12px 22px;border-radius:10px">{cta_label}</a>
    </p>
    <p style="color:#1f8a52;font-size:12px;word-break:break-all">Or paste this link: {cta_url}</p>
  </div>
</div>"""


def send_verification_email(to_email: str, link: str) -> None:
    text = (
        "Welcome to SelfRepair.\n\n"
        f"Confirm your email to activate your account:\n{link}\n\n"
        "This link expires in 24 hours. If you didn't sign up, ignore this email."
    )
    html = _wrap(
        "Confirm your email",
        "<p style='color:#6cf3a0'>Welcome to SelfRepair. Confirm your email to activate your account.</p>",
        "Verify email",
        link,
    )
    send_async(to_email, "Confirm your SelfRepair account", text, html)


def send_reset_email(to_email: str, link: str) -> None:
    text = (
        "We received a request to reset your SelfRepair password.\n\n"
        f"Reset it here:\n{link}\n\n"
        "This link expires in 1 hour. If you didn't request this, ignore this email."
    )
    html = _wrap(
        "Reset your password",
        "<p style='color:#6cf3a0'>We received a request to reset your SelfRepair password.</p>",
        "Reset password",
        link,
    )
    send_async(to_email, "Reset your SelfRepair password", text, html)
