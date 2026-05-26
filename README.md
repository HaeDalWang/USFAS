# USFAS — US Fundamental Alert System
> "왜 지금 이 종목인가"를 데이터로 설명하는 미국장 촉매 감지 시스템

FMP 전용 데이터 기반으로 어닝 미반응 서프라이즈(Earnings Under-reaction)와
내부자 클러스터 매수(Insider Cluster Buying)가 동시에 충족되는 순간을 포착하여
Discord로 고위험/고수익 진입 신호를 송출합니다.
월 $1.23, 완전 서버리스, 촉매가 있을 때만 울린다.

## 왜 만들었나

HCSES가 "언제 가격이 싸지는가"를 알려준다면,
USFAS는 "왜 지금 올라야 하는가"를 알려줍니다.

- 가격이 싼 것만으로는 부족했음 — 싼 채로 더 빠질 수 있음
- 오를 이유(촉매)가 생겼을 때만 진입하고 싶었음
- 손해를 감수하더라도 기대값이 높은 순간만 포착하면 됨

결과적으로 "촉매 + 미반응이 동시에 확인됐을 때만 True"라는 원칙 하에
HCSES와 독립적으로 운영되는 미국장 전용 알람 시스템입니다.

---

## 알람 타입

### TYPE-1 — 어닝 미반응 서프라이즈

> "좋은 실적인데 시장이 아직 덜 올렸다"

발생 시점: 어닝 발표 후 D+0~D+2 이내만 유효

| 조건 | 기준 |
|------|------|
| EPS 서프라이즈 | > +10% |
| 매출 서프라이즈 | > +3% |
| 가이던스 | 상향 또는 유지 (하향 즉시 탈락) |
| 어닝 후 주가 변동 | < +5% (이미 많이 오른 것 제외) |
| 기관 소유비율 | > 50% |

손절: 진입 후 **-8%** 또는 다음 어닝 2일 전 청산

### TYPE-2 — 내부자 클러스터 매수

> "내부자 여러 명이 같은 시기에 자기 돈으로 공개 매수했다"

발생 시점: SEC Form 4 제출 감지 즉시

| 조건 | 기준 |
|------|------|
| C레벨 임원 수 | 30일 내 2인 이상 |
| 거래 유형 | 공개시장 매수(`P`)만 — 옵션 행사(`A`), 증여(`G`) 제외 |
| 총 매수금액 | > $500,000 |
| 주가 위치 | 52주 고점 대비 -25% 이상 하락 구간 |
| 최근 분기 EPS | 흑자 |

손절: 진입 후 **-12%** 또는 90일 후 무조건 청산

---

## Kill-Switch

VIX > 28, US 10Y 전일 대비 +15bp 이상, DXY 20일 볼린저 상단 돌파 중 하나라도 해당되면
알람 메시지 상단에 경고 배너가 붙습니다. 스캔은 계속 진행됩니다.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ Kill-Switch 작동 중! 매우 주의하세요
사유: VIX 29.4 > 28.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 아키텍처

```
EventBridge Scheduler (매일 22:30 KST)
  └─ ECS Fargate Task
       ├─ DataCollector    FMP API → DynamoDB
       ├─ CatalystDetector Kill-Switch → TYPE-1/2 조건 평가
       ├─ ReportGenerator  Plotly + Jinja2 → S3 (base64 인라인, 오프라인 렌더링)
       └─ AlertingEngine   Discord Webhook
```

- **멱등성**: 동일 이벤트 중복 알람 없음 (`usfas-processed-events` DynamoDB)
- **Bulkhead**: 종목 하나 실패해도 나머지 계속 진행
- **Fallback**: FMP 3회 재시도 실패 시 yfinance로 자동 전환

---

## 시작하기

```bash
# Python 3.12 가상환경
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 테스트
pytest tests/unit/ -v --cov=src --cov-report=term-missing
```

---

## 설정

`config.yaml`에서 모든 파라미터를 관리합니다. 코드에 하드코딩 없음.

```yaml
universe:
  symbols: [AAPL, MSFT, NVDA, META, GOOGL, AMZN, JPM, TSLA, AMD, NFLX]

kill_switch:
  vix_max: 28.0
  us10y_daily_bp_max: 15.0

type1_earnings:
  eps_surprise_min_pct: 10.0
  scan_days_after_earnings: 2   # D+3 이후는 스킵

type2_insider:
  min_executives: 2
  min_total_value_usd: 500000
  lookback_days: 30
```

> FMP 무료 티어 250 req/day 기준 20종목 이내 운영 가능.
> 20종목 초과 시 FMP Starter ($15/월) 필요.

---

## 배포

### 사전 준비

```bash
# AWS Secrets Manager에 시크릿 생성
aws secretsmanager create-secret \
  --name usfas/fmp-api-key \
  --region ap-northeast-2 \
  --secret-string '{"api_key": "YOUR_FMP_API_KEY"}'

aws secretsmanager create-secret \
  --name usfas/discord-webhook \
  --region ap-northeast-2 \
  --secret-string '{"webhook_url": "YOUR_DISCORD_WEBHOOK_URL"}'
```

### Docker 빌드 & ECR 푸시

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=ap-northeast-2
ECR_URI=$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/usfas

aws ecr create-repository --repository-name usfas --region $REGION
aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin $ECR_URI

docker build --platform linux/amd64 -t usfas:latest .
docker tag usfas:latest $ECR_URI:latest
docker push $ECR_URI:latest
```

### SAM 배포

```bash
# samconfig.toml의 SubnetId를 본인 서브넷으로 수정 후
sam deploy --no-confirm-changeset
```

---

## AWS 비용

| 서비스 | 월 예상 비용 |
|--------|-------------|
| ECS Fargate (스캔 태스크) | $0.16 |
| DynamoDB | $0.01 |
| S3 리포트 저장 | $0.00 |
| EventBridge | $0.00 |
| Secrets Manager | $0.80 |
| CloudWatch Logs | $0.15 |
| ECR 이미지 | $0.10 |
| **합계** | **~$1.23** |

---

## 관련 프로젝트

- [HCSES](https://github.com/HaeDalWang/HCSES) — 한국장 가격 기반 알람 시스템 (PBR + 가격 모멘텀)

---

*자동 매매 없음. 알람과 리포트까지가 시스템의 끝.*
*⚠️ 투자 권유 아님 | 손절 필수*
