"""자동 정기발송용 날짜 유틸 — 주말 발송 회피."""
from datetime import date, timedelta


def shift_to_weekday(d: date) -> date:
    """발송 예정일이 주말이면 다음 월요일로 민다.

    월요일로 밀면(당기지 않음) 직전 기간(2주/한 달) 데이터가 주말까지 온전히
    포함되고, 담당자도 평일에 확인할 수 있다.
      · 토요일 → +2일(월요일)
      · 일요일 → +1일(월요일)
    """
    wd = d.weekday()  # Mon=0 .. Sun=6
    if wd == 5:
        return d + timedelta(days=2)
    if wd == 6:
        return d + timedelta(days=1)
    return d
