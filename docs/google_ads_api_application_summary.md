# Google Ads API — Basic Access Application Summary

> Submission-ready summary for the Google Ads API access review.
> Tool: **MarketIP Ad Report Automation** · Last updated: 2026-06-25

---

## 1. Tool name
**MarketIP Ad Report Automation Tool** (마케팁 광고 보고서 자동화 도구)

## 2. Tool purpose
Retrieves per-advertiser **Google Ads performance data** to generate **monthly performance reports** and **email them to the advertisers** we manage. It is a **read-only reporting tool** — it performs no create/update/delete (mutate) operations of any kind.

- Company: MarketIP, a digital advertising agency in South Korea.
- Live app: https://marketip-ad.streamlit.app (Python 3 + Streamlit, official `google-ads` Python client).
- Data is used solely to produce reports for advertiser accounts we manage; never resold, never used for remarketing or external sharing.

## 3. Google Ads API usage
Calls **only** `GoogleAdsService.Search` (GAQL read queries). No `*.Mutate` services are used.

| Purpose | Resource | Key fields |
|---|---|---|
| Customer lookup | `customer` | id, descriptive_name, currency_code, time_zone |
| Campaign performance | `campaign` | id, name, advertising_channel_type, status |
| Metrics | `campaign` / `ad_group` / `keyword_view` / `search_term_view` | impressions, clicks, ctr, average_cpc, cost_micros, conversions, cost_per_conversion, conversions_value |

`cost_micros` ÷ 1,000,000 → KRW. ROAS = conversions_value / cost × 100, shown only when conversion value exists. Low call volume: roughly once per advertiser per month plus on-demand previews by staff.

## 4. Test environment
A dedicated test MCC and test ad account were created (per Google review guidance), separate from production.

| Item | Value |
|---|---|
| Developer Token issuing MCC | **9503661650** (production MCC; token currently Pending) |
| Test Login Customer ID | **8617741709** (test MCC) |
| Test ad account Customer ID | **7658924339** (under the test MCC) |

Note: the Developer Token's issuing MCC and `login_customer_id` need not be identical. The goal is to query a **test account with a Pending Developer Token**, which we verified.

## 5. Test result (verified 2026-06-25)
Live API calls with `login_customer_id=8617741709`, `customer_id=7658924339`:

1. **Test ad account name lookup — SUCCESS.** Returned account name "마케팁 API 테스트 광고계정" (currency KRW, time zone Asia/Seoul).
2. **Campaign query request — SUCCESS.** API request returned normally.
3. **Zero campaigns is treated as success** — when 0 campaigns are returned, the request itself succeeding is treated as a successful connection.
4. Production MCC (950) and real ad accounts were **not** called during testing.

**Conclusion: connection to the test account succeeded.** No re-authentication needed (refresh token valid).

## 6. Security
- Tokens/secrets are **never displayed** in the UI, previews, or diagnostics (only length/presence is shown).
- All credentials live only in **`.streamlit/secrets.toml`** (local) and Streamlit Cloud Secrets / environment variables.
- **`.gitignore`** excludes `.env`, `.streamlit/secrets.toml`, and OAuth JSON (`client_secret*.json`) — no secrets in source control.
- **No sensitive values are written to logs**; verification logs report only lengths and pass/fail.

## 7. User flow
1. Save the **Google Customer ID** in the Advertiser Management screen.
2. In Monthly Report, select media = **Google**.
3. **Environment-variable validation** (abort, no API call, if required keys are missing).
4. **Customer ID validation** (abort if missing/invalid).
5. **Google Ads API query** (`GoogleAdsService.Search`, GAQL) by login_customer_id + customer_id.
6. **Report HTML generation.**
7. **Preview** (staff review KPIs and per-campaign/keyword tables).
8. **Email send** of the finished report to the advertiser.

Access control: operates only behind internal staff (admin) login; advertisers receive only the finished report by email.

## 8. Prohibited behavior (enforced in code)
1. **No Naver API fallback on Google failure** — if the selected media is Google, the Naver API is never called; failures are surfaced, not substituted.
2. **No arbitrary Customer IDs** — only IDs stored in Advertiser Management are used; no hardcoded or guessed IDs.
3. **No production accounts before approval** — until Basic Access is granted, only the test account (7658924339) is called; real ad accounts are not.

## 9. Policy compliance
Read-only reporting tool; no mutate operations; RMF not applicable. Data used only to produce reports for managed advertiser accounts; never resold or used for remarketing. Developer contact kept current in the API Center. Complies with the Google Ads API Terms of Service.
