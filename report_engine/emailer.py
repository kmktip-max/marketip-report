import smtplib
import os
from email.message import EmailMessage
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
    plain = (
        f"안녕하세요, {client_name} 담당자님.\n\n"
        f"{period_label} 광고 성과 보고서({since} ~ {until})를 보내드립니다.\n"
        "HTML 형식의 보고서를 확인해 주세요.\n\n"
        "감사합니다.\nadmarketip"
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_email
    msg.set_content(plain, charset="utf-8")
    msg.add_alternative(html_body, subtype="html", charset="utf-8")

    with smtplib.SMTP_SSL(host, port, local_hostname="localhost") as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
