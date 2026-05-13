import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.naver.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")


def send_report(to_email, client_name, period, since, until, html_body,
                smtp_user=None, smtp_password=None, smtp_host=None, smtp_port=None):
    user = smtp_user or SMTP_USER
    password = smtp_password or SMTP_PASSWORD
    host = smtp_host or SMTP_HOST
    port = smtp_port or SMTP_PORT

    period_label = "주간" if period == "weekly" else "월간"
    subject = f"[광고 성과 보고서] {client_name} | {period_label} ({since} ~ {until})"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = user
    msg["To"] = to_email

    plain = (
        f"안녕하세요, {client_name} 담당자님.\n\n"
        f"{period_label} 광고 성과 보고서({since} ~ {until})를 보내드립니다.\n\n"
        "감사합니다.\nadmarketip"
    )

    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL(host, port, local_hostname="localhost") as smtp:
        smtp.login(user, password)
        smtp.sendmail(user, to_email, msg.as_bytes().decode("utf-8", errors="replace"))
