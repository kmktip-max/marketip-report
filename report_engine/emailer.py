import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.header import Header
from dotenv import load_dotenv

load_dotenv()

# .strip() — 시크릿에 줄바꿈(\r)이 섞여도 호스트/인증이 깨지지 않도록 방어
SMTP_HOST = (os.getenv("SMTP_HOST", "").strip() or "smtp.naver.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "").strip() or "465")
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()


def send_report(to_email, client_name, period, since, until, html_body,
                smtp_user=None, smtp_password=None, smtp_host=None, smtp_port=None):
    user = smtp_user or SMTP_USER
    password = smtp_password or SMTP_PASSWORD
    host = smtp_host or SMTP_HOST
    port = smtp_port or SMTP_PORT

    period_label = {"weekly": "주간", "biweekly": "격주", "monthly": "월간"}.get(period, "월간")
    subject = f"[광고 성과 보고서] {client_name} | {period_label} ({since} ~ {until})"
    filename = f"광고보고서_{client_name}_{since[:7]}.html"

    plain = f"""안녕하세요, {client_name} 담당자님.

{period_label} 광고 성과 보고서({since} ~ {until})를 보내드립니다.

첨부된 HTML 파일을 다운로드 후 브라우저(크롬, 엣지)로 열어보시면
키워드별 성과 차트와 상세 분석을 확인하실 수 있습니다.

감사합니다.
admarketip | {user}"""

    msg = MIMEMultipart()
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = user
    msg["To"] = to_email

    msg.attach(MIMEText(plain, "plain", "utf-8"))

    # HTML 파일 첨부
    html_bytes = html_body.encode("utf-8")
    attachment = MIMEApplication(html_bytes, Name=filename)
    attachment["Content-Disposition"] = f'attachment; filename="{filename}"'
    attachment["Content-Type"] = f'text/html; charset=utf-8; name="{filename}"'
    msg.attach(attachment)

    with smtplib.SMTP_SSL(host, port, local_hostname="localhost", timeout=30) as smtp:
        smtp.login(user, password)
        smtp.sendmail(user, to_email, msg.as_string())


def send_verification_email(to_email, code,
                            smtp_user=None, smtp_password=None,
                            smtp_host=None, smtp_port=None):
    """가입 이메일 인증코드 발송 (6자리)."""
    user     = smtp_user or SMTP_USER
    password = smtp_password or SMTP_PASSWORD
    host     = smtp_host or SMTP_HOST
    port     = int(smtp_port or SMTP_PORT)
    if not user or not password:
        raise RuntimeError("SMTP 설정(SMTP_USER/SMTP_PASSWORD)이 없습니다.")

    subject = "[마케팁] 이메일 인증코드"
    body = (
        "안녕하세요, 마케팁입니다.\n\n"
        f"가입 이메일 인증코드는 [ {code} ] 입니다.\n"
        "가입 화면 인증코드 입력칸에 위 6자리를 입력해 주세요. (10분간 유효)\n\n"
        "본 메일을 요청하지 않으셨다면 무시하셔도 됩니다.\n\n"
        "마케팁"
    )
    msg = MIMEMultipart()
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"]    = user
    msg["To"]      = to_email
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL(host, port, local_hostname="localhost", timeout=30) as smtp:
        smtp.login(user, password)
        smtp.sendmail(user, to_email, msg.as_string())
