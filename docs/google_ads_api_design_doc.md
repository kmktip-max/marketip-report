# 마케팁 광고 보고서 자동화 도구 — Google Ads API 설계 문서

> 구글 Ads API 기본 액세스(Basic Access) 심사 제출용 설계 문서
> 최종 갱신: 2026-06-25 · 상태: 테스트 계정 연결 검증 완료

---

## 1. 도구 개요

| 항목 | 내용 |
|---|---|
| **도구 이름** | 마케팁 광고 보고서 자동화 도구 (MarketIP Ad Report Automation) |
| **도구 유형** | 보고용(READ-ONLY) 도구 — 조회만 수행, 변경(mutate) 없음 |
| **배포 URL** | https://marketip-ad.streamlit.app |
| **운영 주체** | 마케팁 (대한민국 디지털 광고 대행사) |
| **스택** | Python 3 · Streamlit · 공식 google-ads Python 라이브러리 · Supabase |

---

## 2. 도구 목적

광고주별 **Google Ads 성과 데이터를 조회**하여 **월간 광고 성과 보고서를 생성**하고,
완성된 보고서를 **광고주에게 이메일로 발송**한다.

- 마케팁이 대행 운영하는 광고주 계정의 월간 성과를 정기 보고하기 위한 내부 운영 도구.
- 데이터는 보고서 생성 목적에만 사용하며, 재판매·리마케팅·외부 공유를 하지 않는다.
- 계정/캠페인/예산/입찰의 생성·수정·삭제를 일절 수행하지 않는다(조회 전용).

---

## 3. 사용하는 Google Ads API

**호출 서비스: `GoogleAdsService.Search` (GAQL 읽기 쿼리) 단독.**
`*.Mutate` 계열 서비스는 전혀 사용하지 않는다.

| 조회 종류 | 리소스(FROM) | 주요 필드 |
|---|---|---|
| **Customer 조회** | `customer` | customer.id, customer.descriptive_name, currency_code, time_zone |
| **Campaign 성과 조회** | `campaign` | campaign.id, name, advertising_channel_type, status |
| **Metrics 조회** | `campaign` / `ad_group` / `keyword_view` / `search_term_view` 등 | impressions, clicks, ctr, average_cpc, cost_micros, conversions, cost_per_conversion, conversions_value |

- `cost_micros`는 1,000,000으로 나누어 원(KRW) 환산.
- ROAS = 전환가치 / 비용 × 100, **전환가치가 있을 때만 표시**(없으면 `-`).
- 호출 빈도: 광고주당 월 1회 정기 + 직원 온디맨드 미리보기. 호출량 적음.

---

## 4. 테스트 환경

구글 Ads API 심사팀 안내에 따라, 운영 계정과 분리된 **별도 테스트 MCC·테스트 광고계정**을 생성하여 검증했다.

| 항목 | 값 |
|---|---|
| **Developer Token 발급 MCC** | 9503661650 (운영 MCC, Pending 상태 토큰) |
| **테스트 Login Customer ID** | 8617741709 (심사용 테스트 MCC) |
| **테스트 광고계정 Customer ID** | 7658924339 (테스트 MCC 아래 생성) |

> 참고: Developer Token의 발급 MCC와 `login_customer_id`가 반드시 동일할 필요는 없다.
> 현재 목적은 **Pending Developer Token으로 테스트 계정을 조회**하는 것이며, 이를 실제로 검증했다.

---

## 5. 테스트 결과 (2026-06-25 검증)

`login_customer_id=8617741709`, `customer_id=7658924339` 기준으로 실제 API를 호출하여 검증 완료.

| 검증 항목 | 결과 |
|---|---|
| 1. 테스트 광고계정 이름 조회 | ✅ 성공 — 계정명 **"마케팁 API 테스트 광고계정"** (통화 KRW, TZ Asia/Seoul) |
| 2. 캠페인 조회 요청 | ✅ 성공 — API 요청 정상 응답 |
| 3. 캠페인 0건 처리 | ✅ 캠페인이 0건이어도 **요청 자체가 성공하면 연결 성공**으로 처리 |
| 4. 운영 MCC 950 미호출 | ✅ 검증 중 운영 MCC·실광고계정은 **호출하지 않음** |

**결론: 테스트 계정 기준 API 연결 성공.** 재인증 불필요(Refresh Token 정상 동작).

---

## 6. 보안

- **토큰·시크릿을 화면에 노출하지 않는다.** (UI·미리보기·진단 화면 모두 값 비표시, 길이/존재 여부만 표기)
- 모든 자격증명은 **`.streamlit/secrets.toml`** (로컬) 및 Streamlit Cloud Secrets / 환경변수에만 저장.
- **`.gitignore`** 로 `.env`, `.streamlit/secrets.toml`, OAuth JSON(`client_secret*.json`) 등을 모두 추적 제외 → 소스 관리에 비밀값이 올라가지 않음.
- **로그에 민감값을 출력하지 않는다.** 검증·진단 시 토큰 값 대신 길이(len)나 성공/실패만 기록.
- 토큰 생성용 임시 스크립트는 사용 후 즉시 삭제.

---

## 7. 사용자 흐름 (Data Flow)

```
[광고주 관리]  →  Google Customer ID 저장 (숫자만 정규화)
      │
[월간보고서]   →  매체 선택: "Google" 선택
      │
      ├─ ① 환경변수 검증 (check_google_env) — 필수 키 누락 시 중단, API 미호출
      │
      ├─ ② Customer ID 검증 — 미입력/형식오류 시 중단
      │
      ├─ ③ Google Ads API 조회 (GoogleAdsService.Search, GAQL)
      │        login_customer_id + customer_id 기준 캠페인/메트릭 조회
      │
      ├─ ④ 보고서 HTML 생성 (build_google_report_html)
      │
      ├─ ⑤ 미리보기 (직원이 화면에서 KPI·캠페인/키워드 표 확인)
      │
      └─ ⑥ 이메일 발송 — 완성된 보고서를 광고주에게 전송
```

접근 통제: 내부 직원(관리자) 로그인 뒤에서만 동작. 광고주는 완성된 보고서를 이메일로만 수령.

---

## 8. 금지 처리 (Fail-safe 규칙)

도구에 다음을 **코드 레벨로 강제**한다.

1. **Google 실패 시 네이버 API fallback 금지** — 매체가 Google이면 네이버 API를 절대 호출하지 않는다. 실패는 실패로 표시하고, 다른 매체 데이터로 대체하지 않는다.
2. **임의 Customer ID 사용 금지** — 광고주 관리에 저장된 ID만 사용. 하드코딩·추측 ID 호출 없음.
3. **운영 실계정은 승인 전 호출 금지** — 기본 액세스 승인 전에는 테스트 계정(7658924339)만 호출하고, 실광고계정(예: 557-105-1142)은 호출하지 않는다.

---

## 9. 정책 준수 요약

- 조회 전용(read-only) 보고 도구 — mutate 없음, RMF(Required Minimum Functionality) 비해당.
- 데이터는 대행 운영 광고주의 보고서 생성에만 사용 — 재판매·외부 공유·리마케팅 없음.
- 개발자 연락 이메일을 API 센터에 최신으로 유지.
- Google Ads API 이용약관(Terms of Service) 준수.

---

## 부록. 관련 코드 위치

| 파일 | 역할 |
|---|---|
| `report_engine/google_ads_api.py` | API 클라이언트 빌드, GAQL 쿼리, 보고서 데이터/ HTML 생성, 연결검증 (네이버 호출 없음) |
| `pages/월간보고서.py` | 매체 분기(네이버/구글/카카오), 구글 Customer ID 입력, 환경변수 진단, 미리보기·발송 |
| `.streamlit/secrets.toml` | 자격증명(GOOGLE_ADS_*) — git 무시 |
