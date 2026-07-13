import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def is_smtp_configured() -> bool:
    return bool(os.getenv("SMTP_USER")) and bool(os.getenv("SMTP_PASSWORD"))


def send_html_email(to_email: str, subject: str, body_html: str) -> tuple[bool, str]:
    if not is_smtp_configured():
        return False, "SMTP is not configured. Set SMTP_USER and SMTP_PASSWORD in .env."

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = to_email
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())

        return True, ""
    except Exception as exc:
        return False, str(exc)
