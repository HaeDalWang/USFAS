# USFAS — US Fundamental Alert System
> FMP 전용 데이터 기반 미국장 촉매(Catalyst) 감지 알람 시스템
> HCSES(https://github.com/HaeDalWang/HCSES)와 독립 운영 | 자동 매매 없음 | 리포트 + Discord 알람까지

---

## 0. 설계 철학

### HCSES와의 차이
| | HCSES | USFAS |
|---|---|---|
| 데이터 | 가격 + PBR (yfinance) | 펀더멘털 + 내부자 (FMP) |
| 포착 대상 | 가격이 싸진 순간 (후행) | 뭔가 바뀌려는 순간 (선행/동행) |
| 보유 관점 | 단기 (수일~수주) | 중기 (2주~3개월) |
| 알람 성격 | "지금 싸다" | "곧 오를 촉매가 생겼다" |

### 핵심 원칙
- **촉매(Catalyst) + 미반응(Under-reaction) 동시 확인** — 둘 중 하나만이면 알람 없음
- 승률보다 기대값 (Expected Value) 추구 — 틀릴 때 얼마나 잃는지가 더 중요
- 조건 모호하면 False (보수적 원칙, HCSES 계승)
- 자동 매매 없음 — 알람과 리포트까지가 시스템의 끝

---

## 1. 알람 타입 정의

### TYPE-1: 어닝 미반응 서프라이즈 (Earnings Under-reaction)

```
"좋은 실적인데 시장이 아직 덜 올렸다"

발생 시점: 어닝 발표 후 1~2 거래일 이내
기대 보유: 2~4주
기대 수익: 5~15%
예상 빈도: 어닝 시즌(분기 4회)마다 1~3종목
승률 기대: ~60%
```

**조건 (전부 AND)**
```
[ ] EPS 서프라이즈 > +10%         (컨센서스 대비 실제 EPS)
[ ] 매출 서프라이즈 > +3%         (단순 비용 절감이 아닌 진짜 성장 확인)
[ ] 가이던스: 상향 or 유지         (하향이면 즉시 탈락)
[ ] 어닝 후 주가 변동 < +5%       (이미 많이 오른 것 제외)
[ ] 기관 소유비율 > 50%           (기관이 관심 있는 종목만)
[ ] VIX < 28                      (극단적 공포장 제외)
```

**FMP API 매핑**
```python
obb.equity.estimates.historical(symbol, provider="fmp")
  → actual_eps, estimated_eps → EPS 서프라이즈 계산
  → actual_revenue, estimated_revenue → 매출 서프라이즈 계산

obb.equity.estimates.consensus(symbol, provider="fmp")
  → 가이던스 방향 확인

obb.equity.price.historical(symbol, provider="fmp")
  → 어닝 발표일 D+1, D+2 주가 변동률

obb.equity.ownership.institutional(symbol, provider="fmp")
  → institutional_ownership_percentage
```

---

### TYPE-2: 내부자 클러스터 매수 (Insider Cluster Buying)

```
"내부자 여러 명이 같은 시기에 자기 돈으로 공개 매수했다"

발생 시점: SEC Form 4 제출 감지 즉시
기대 보유: 1~3개월
기대 수익: 10~30% (or 더 빠짐)
예상 빈도: 월 0~2회 (불규칙)
승률 기대: ~55~60%
```

**조건 (전부 AND)**
```
[ ] 30일 내 C레벨(CEO/CFO/COO/사내이사) 2인 이상 매수
[ ] 전부 공개 시장 매수 (옵션 행사 제외 — transaction_type = 'P')
[ ] 총 매수 금액 합산 > $500,000
[ ] 주가: 52주 고점 대비 -25% 이상 하락 구간
[ ] VIX < 28
[ ] 최근 분기 EPS: 흑자 (적자 기업 내부자 매수는 의미 다름)
```

**FMP API 매핑**
```python
obb.equity.ownership.insider_trading(symbol, provider="fmp")
  → filing_date, transaction_type, shares, value, officer_title
  → transaction_type == 'P' 필터 (공개 매수만)
  → officer_title에서 C레벨 파싱

obb.equity.price.historical(symbol, provider="fmp")
  → 52주 고점 대비 현재 하락폭 계산

obb.equity.fundamental.income(symbol, provider="fmp")
  → 최근 분기 EPS 흑자 확인
```

---

## 2. Global Kill-Switch

```
아래 조건 중 하나라도 True → 전체 스캔 중단

[ ] VIX > 28
[ ] US 10Y 전일 대비 +15bp 이상 급등
[ ] DXY 20일 볼린저 상단 돌파 (달러 급등 = 리스크오프)
```

Kill-Switch 발동 시 → Discord에 별도 알람만 발송, 종목 스캔 없음

---

## 3. 손절 기준 (계획서에 명시)

> 시스템이 틀릴 때 얼마나 잃는지가 수익만큼 중요하다

```
TYPE-1 손절: 진입 후 -8% 또는 다음 어닝 전 청산
TYPE-2 손절: 진입 후 -12% 또는 내부자 매수 후 90일

리포트에 손절 가격 계산값을 반드시 포함할 것
```

---

## 4. 시스템 아키텍처

```
[EventBridge Scheduler]
  ├─ 매일 장 마감 후 22:30 KST — TYPE-2 스캔 (내부자)
  └─ 어닝 시즌 중 매일 — TYPE-1 스캔 (어닝 서프라이즈)
        │
        ▼
[ECS Fargate Task]  ← Lambda 불가 (OpenBB ~500MB+)
  │
  ├── Unit 1: DataCollector
  │     ├─ FMP API → 종목별 데이터 수집
  │     ├─ yfinance → 가격/52주 데이터 (FMP fallback)
  │     └─ DynamoDB 저장
  │
  ├── Unit 2: CatalystDetector
  │     ├─ Kill-Switch 체크
  │     ├─ TYPE-1 조건 평가 (어닝 서프라이즈)
  │     ├─ TYPE-2 조건 평가 (내부자 클러스터)
  │     └─ 조건 충족 시 → ReportGenerator 호출
  │
  ├── Unit 3: ReportGenerator
  │     ├─ HTML 리포트 생성 (Plotly + Jinja2)
  │     ├─ S3 업로드 → presigned URL
  │     └─ AlertingEngine 호출
  │
  └── Unit 4: AlertingEngine
        └─ Discord Webhook 발송
```

---

## 5. 리포트 구성

### TYPE-1 리포트 구성
```
┌─────────────────────────────────────────┐
│  [TYPE-1] 어닝 미반응 서프라이즈         │
│  NVDA | Score: 조건 4/5 충족            │
├─────────────────────────────────────────┤
│  촉매 요약 카드                          │
│  • EPS 서프라이즈: +18.4%               │
│  • 매출 서프라이즈: +7.2%               │
│  • 가이던스: 상향 (+12%)                │
│  • 어닝 후 주가 변동: +2.1% (미반응)    │
├─────────────────────────────────────────┤
│  어닝 서프라이즈 히스토리 (8분기 바차트) │
├─────────────────────────────────────────┤
│  주가 차트 (60일 + 어닝 발표일 마킹)    │
├─────────────────────────────────────────┤
│  기관 소유비율 추이                      │
├─────────────────────────────────────────┤
│  손절 가이드                            │
│  • 현재가: $142.30                      │
│  • 손절선 (-8%): $130.92               │
│  • 청산 기한: 2026-08-18 (다음 어닝 2일 전) │
├─────────────────────────────────────────┤
│  Kill-Switch 현황: VIX 18.2 ✅ ...     │
└─────────────────────────────────────────┘
```

### TYPE-2 리포트 구성
```
┌─────────────────────────────────────────┐
│  [TYPE-2] 내부자 클러스터 매수          │
│  META | 30일 내 임원 3인 동시 매수      │
├─────────────────────────────────────────┤
│  내부자 매수 요약 카드                   │
│  • 매수 인원: CEO + CFO + 사내이사      │
│  • 총 매수금액: $2.4M                   │
│  • 매수 기간: 12일 (밀집도 높음)        │
│  • 52주 고점 대비: -38% 구간            │
├─────────────────────────────────────────┤
│  내부자 거래 타임라인                    │
│  (날짜별 매수/매도 시각화)              │
├─────────────────────────────────────────┤
│  주가 차트 (1년 + 내부자 매수 마킹)     │
├─────────────────────────────────────────┤
│  최근 4분기 EPS (흑자 확인용)           │
├─────────────────────────────────────────┤
│  손절 가이드                            │
│  • 현재가: $487.20                      │
│  • 손절선 (-12%): $428.74              │
│  • 최대 보유: 2026-08-25 (90일, 수익/손실 무관 청산) │
└─────────────────────────────────────────┘
```

---

## 6. Discord 알람 포맷

### TYPE-1
```
⚡ [USFAS TYPE-1] 어닝 미반응 서프라이즈

📊 **NVDA** — NVIDIA Corporation
섹터: Technology | 시총: $3.5T

✅ 조건 체크
├ EPS 서프라이즈    +18.4%  ✅
├ 매출 서프라이즈   +7.2%   ✅
├ 가이던스          상향    ✅
├ 어닝 후 주가변동  +2.1%   ✅ (미반응)
└ 기관 소유비율     67%     ✅

📉 손절 기준: -8% | $130.92
📅 청산 기한: 2026-08-18 (다음 어닝 2일 전)

🌡️ VIX: 18.2 ✅ | 10Y: 4.35% ✅
📄 리포트: [링크](https://s3-url)

⚠️ 투자 권유 아님 | 승률 ~60% | 손절 필수
```

### TYPE-2
```
🔍 [USFAS TYPE-2] 내부자 클러스터 매수

📊 **META** — Meta Platforms
섹터: Technology | 시총: $1.4T

👤 내부자 매수 현황 (30일)
├ CEO         $1.1M 매수 (5일 전)
├ CFO         $0.8M 매수 (9일 전)
└ 사내이사    $0.5M 매수 (12일 전)
  합계: $2.4M | 전부 공개시장 매수

📍 현재 위치: 52주 고점 대비 -38%
📉 손절 기준: -12% | $428.74
📅 최대 보유: 2026-08-25 (90일, 수익/손실 무관 청산)

🌡️ VIX: 18.2 ✅ | 10Y: 4.35% ✅
📄 리포트: [링크](https://s3-url)

⚠️ 투자 권유 아님 | 승률 ~55% | 손절 필수
```

---

## 7. 기술 스택

| 항목 | 선택 | 비고 |
|------|------|------|
| Language | Python 3.12 | |
| 데이터 레이어 | OpenBB Platform | `pip install openbb` |
| Primary Provider | FMP (Financial Modeling Prep) | 어닝/내부자 데이터 |
| Fallback Provider | yfinance | 가격/52주 데이터 |
| 인프라 | AWS ECS Fargate + EventBridge | Lambda 패키지 한도 초과 |
| IaC | AWS SAM or Terraform | CDK 사용 X |
| DB | DynamoDB | |
| 리포트 저장 | S3 + presigned URL | |
| 차트 | Plotly (HTML 인라인 임베드) | |
| 템플릿 | Jinja2 | |
| 알람 | Discord Webhook | |
| 비밀 관리 | AWS Secrets Manager | |

---

## 8. 프로젝트 구조

```
usfas/
├── src/
│   ├── data_collector/
│   │   ├── handler.py
│   │   ├── fmp_client.py          # OpenBB FMP 래퍼 + fallback 로직
│   │   └── dynamo_writer.py
│   │
│   ├── catalyst_detector/
│   │   ├── handler.py             # 메인 오케스트레이터
│   │   ├── kill_switch.py         # VIX / 10Y / DXY
│   │   ├── type1_earnings.py      # 어닝 미반응 서프라이즈 조건 평가
│   │   ├── type2_insider.py       # 내부자 클러스터 매수 조건 평가
│   │   └── models.py              # AlertSignal 데이터클래스
│   │
│   ├── report_generator/
│   │   ├── handler.py
│   │   ├── chart_builder.py       # Plotly 차트 생성
│   │   ├── html_renderer.py       # Jinja2 렌더링
│   │   ├── s3_uploader.py
│   │   └── templates/
│   │       ├── type1_report.html.j2
│   │       └── type2_report.html.j2
│   │
│   ├── alerting_engine/
│   │   ├── handler.py
│   │   └── discord_client.py
│   │
│   └── shared/
│       ├── config.py              # 상수, 임계값
│       ├── dynamo_client.py
│       ├── secrets.py
│       └── exceptions.py
│
├── tests/unit/
│   ├── test_kill_switch.py
│   ├── test_type1_earnings.py
│   └── test_type2_insider.py
│
├── Dockerfile
├── template.yaml                  # AWS SAM (ECS Task 정의)
├── config.yaml                    # 종목 유니버스 + 파라미터
├── requirements.txt
└── README.md
```

---

## 9. config.yaml

```yaml
universe:
  symbols:
    - AAPL
    - MSFT
    - NVDA
    - META
    - GOOGL
    - AMZN
    - JPM
    - TSLA
    - AMD
    - NFLX
    # 추가 종목은 여기에

providers:
  primary: fmp
  fallback: yfinance

kill_switch:
  vix_max: 28
  us10y_daily_bp_max: 15
  dxy_use_bollinger: true
  dxy_bollinger_period: 20

type1_earnings:
  eps_surprise_min_pct: 10.0        # EPS 서프라이즈 최소 +10%
  revenue_surprise_min_pct: 3.0     # 매출 서프라이즈 최소 +3%
  post_earnings_move_max_pct: 5.0   # 어닝 후 주가 변동 최대 +5%
  institutional_ownership_min: 50.0 # 기관 소유비율 최소 50%
  scan_days_after_earnings: 2       # 어닝 발표 후 며칠 이내까지 감지

type2_insider:
  min_executives: 2                 # 최소 C레벨 인원 수
  min_total_value_usd: 500000       # 총 매수금액 최소 $500K
  lookback_days: 30                 # 몇 일 이내 매수 묶어서 볼지
  price_drawdown_min_pct: 25.0      # 52주 고점 대비 최소 -25%
  require_profitable: true          # 최근 분기 EPS 흑자 필수

stop_loss:
  type1_pct: 8.0                    # TYPE-1 손절 -8%
  type1_exit_days_before_earnings: 2 # 다음 어닝 N일 전 청산
  type2_pct: 12.0                   # TYPE-2 손절 -12%
  type2_max_hold_days: 90           # TYPE-2 최대 보유 90일 (수익/손실 무관 청산)

report:
  s3_bucket: usfas-reports
  presigned_url_expiry_days: 7

secrets:
  fmp_api_key: arn:aws:secretsmanager:ap-northeast-2:xxx:secret:usfas/fmp-api-key
  discord_webhook: arn:aws:secretsmanager:ap-northeast-2:xxx:secret:usfas/discord-webhook
```

---

## 10. 구현 순서 (코딩 에이전트 작업 순서)

```
Phase 1 — 기반 구조
  [ ] shared/ 구현 (config 로더, exceptions, models)
  [ ] fmp_client.py 구현
      - OpenBB FMP wrapper
      - provider fallback (FMP 실패 시 yfinance)
      - 재시도 로직 (3회)
  [ ] kill_switch.py 구현 + 단위 테스트

Phase 2 — 촉매 감지 엔진
  [ ] type1_earnings.py 구현 + 단위 테스트
      - EPS/매출 서프라이즈 계산
      - 어닝 후 미반응 확인
      - 기관 소유비율 확인
  [ ] type2_insider.py 구현 + 단위 테스트
      - Form 4 공개시장 매수 필터
      - 클러스터 감지 (30일 내 복수 임원)
      - 52주 하락폭 계산
  [ ] catalyst_detector/handler.py (오케스트레이터)

Phase 3 — 데이터 파이프라인
  [ ] DynamoDB 테이블 생성 (SAM template.yaml)
  [ ] data_collector/handler.py
  [ ] 로컬 E2E: 데이터 수집 → 조건 평가 → 콘솔 출력

Phase 4 — 리포트 + 알람
  [ ] chart_builder.py (Plotly 차트: TYPE-1용 3종, TYPE-2용 3종)
  [ ] Jinja2 HTML 템플릿 2종
  [ ] s3_uploader.py
  [ ] discord_client.py

Phase 5 — 인프라 배포
  [ ] Dockerfile (openbb[all] + 의존성)
  [ ] SAM template.yaml ECS Task 정의
  [ ] EventBridge 스케줄 설정
  [ ] 실 환경 E2E 테스트

Phase 6 — 검증 (4주)
  [ ] 실제 알람 수신하되 매매 없이 관찰
  [ ] 알람 발생 시 D+7, D+14, D+30 수익률 기록
  [ ] FP(False Positive) 비율 확인
  [ ] config.yaml 파라미터 튜닝
```

---

## 11. 예상 월간 AWS 비용

| 서비스 | 산출 근거 | 월 예상 비용 |
|--------|-----------|-------------|
| ECS Fargate (DataCollector) | 0.25vCPU/0.5GB × 10분 × 30일 | $0.08 |
| ECS Fargate (CatalystDetector) | 0.25vCPU/0.5GB × 10분 × 30일 | $0.08 |
| ECS Fargate (ReportGenerator) | 알람 발생 시만 (월 ~5회 기준) | $0.01 |
| DynamoDB | ~3,000 WCU + 10,000 RCU/월 | $0.01 |
| S3 리포트 저장 | ~50MB/월 | $0.00 |
| EventBridge | ~60 이벤트/월 | $0.00 |
| Secrets Manager | 2 시크릿 | $0.80 |
| CloudWatch Logs | ~200MB/월 | $0.15 |
| ECR 이미지 | ~1GB | $0.10 |
| **합계** | | **~$1.23/월** |

> FMP 무료 티어 250 req/day 기준 20종목 이내 운영 가능
> 20종목 초과 시 FMP Starter ($15/월) 필요

---

## 12. 코딩 에이전트 주의사항

```
1. transaction_type 필터 필수
   - TYPE-2는 반드시 'P' (공개시장 매수)만 카운트
   - 옵션 행사('A'), 증여('G') 등은 제외

2. 어닝 날짜 파싱 주의
   - FMP 어닝 발표일 기준 D+0, D+1, D+2 주가만 확인
   - D+3 이후는 TYPE-1 조건에서 스킵

3. 멱등성 보장
   - 같은 종목의 같은 어닝/내부자 이벤트로 중복 알람 금지
   - DynamoDB에 processed_events 테이블로 관리

4. 종목 실패 격리 (Bulkhead)
   - 종목 하나 FMP 호출 실패 시 해당 종목만 스킵
   - 나머지 종목 스캔 계속

5. 리포트는 외부 CDN 없이 자급
   - Plotly 차트 base64 인라인 임베드
   - 오프라인에서도 렌더링 가능해야 함

6. 손절 가격은 리포트와 Discord 메시지 양쪽에 모두 표시
   - 있으면 좋은 게 아니라 필수 항목

7. config.yaml 파라미터는 코드에 하드코딩 금지
   - 모든 임계값은 config.yaml에서만 관리
```

---

*USFAS v0.2 — 2026-05-26*
*TYPE-1: 어닝 미반응 서프라이즈 | TYPE-2: 내부자 클러스터 매수*
*FMP API 기반 | HCSES와 독립 운영*