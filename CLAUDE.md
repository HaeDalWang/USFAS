# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

USFAS (US Fundamental Alert System) — FMP API 기반 미국장 촉매 감지 알람 시스템.
자동 매매 없음. 알람 + HTML 리포트까지가 시스템의 끝.

**배포 상태**: AWS ap-northeast-2 운영 중 (ECS Fargate + EventBridge)

## Commands

```bash
# Python 3.12 venv 설정
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 단위 테스트 전체
pytest tests/unit/ -v --cov=src --cov-report=term-missing

# 단일 테스트 파일
pytest tests/unit/test_kill_switch.py -v

# Discord 테스트 알림 발송 (웹훅 동작 확인용)
python scripts/test_alert.py

# Docker 빌드 (ECS 배포용, linux/amd64 필수)
docker build --platform linux/amd64 -t usfas:latest .

# ECR 푸시 후 SAM 재배포
docker tag usfas:latest 863422182520.dkr.ecr.ap-northeast-2.amazonaws.com/usfas:latest
docker push 863422182520.dkr.ecr.ap-northeast-2.amazonaws.com/usfas:latest
sam deploy --no-confirm-changeset
```

## Architecture

4개 Unit이 순서대로 실행되는 파이프라인:

```
EventBridge Scheduler (매일 22:30 KST)
  └─ ECS Fargate Task
       ├─ DataCollector    FMP API → 조건 평가
       ├─ CatalystDetector Kill-Switch → TYPE-1/2 조건 평가
       ├─ ReportGenerator  Plotly + Jinja2 → S3 (base64 인라인)
       └─ AlertingEngine   Discord Webhook
```

진입점: `src/data_collector/handler.py::run()` → 시그널 생성 후 `src/alerting_engine/handler.py::process_signal()` 호출.

`src/shared/config.py`가 `config.yaml`을 로드. 임계값은 코드에 하드코딩하지 않는다.

`src/shared/secrets.py`가 AWS Secrets Manager에서 FMP API 키(`usfas/fmp-api-key`)와 Discord Webhook URL(`usfas/discord-webhook`)을 가져온다.

## Signal Types

**TYPE-1 (어닝 미반응 서프라이즈)**: 어닝 발표 후 D+0~D+2 이내만 유효. D+3 이후 스킵.

**TYPE-2 (내부자 클러스터 매수)**: `transactionType == 'P'` (공개시장 매수)만 카운트. 옵션 행사(`'A'`), 증여(`'G'`) 제외. **FMP Starter 플랜($15/월) 필요** — 현재 free tier에서 insider-trading 엔드포인트 403.

**Kill-Switch**: VIX > 28 또는 US 10Y 전일 대비 +15bp 이상 또는 DXY 20일 볼린저 상단 돌파 시 알람 메시지 상단에 경고 배너 추가. 스캔은 계속 진행.

## FMP API 실제 엔드포인트 (검증 완료)

| 엔드포인트 | 상태 | 비고 |
|---|---|---|
| `GET /stable/earnings?symbol=` | ✅ | 어닝 데이터. 필드: `epsActual`, `epsEstimated`, `revenueActual`, `revenueEstimated` |
| `GET /stable/historical-price-eod/full?symbol=` | ✅ | 가격 데이터 |
| `GET /stable/income-statement?symbol=` | ✅ | 손익계산서 |
| `GET /stable/insider-trading?symbol=` | ❌ 403 | FMP Starter 필요 |
| `GET /stable/institutional-ownership?symbol=` | ❌ 403 | FMP Starter 필요 → yfinance fallback 사용 중 |

## Key Constraints

**멱등성**: 동일 이벤트 중복 알람 금지. DynamoDB `usfas-processed-events` 테이블로 관리.

**Bulkhead**: 종목 하나 실패 시 해당 종목만 스킵, 나머지 계속 진행.

**리포트 자급**: Plotly 차트 base64 인라인 임베드. 외부 CDN 없이 오프라인 렌더링.

**손절 가격**: 리포트와 Discord 메시지 양쪽에 필수 표시.

## AWS 리소스 (ap-northeast-2)

| 리소스 | 이름 |
|---|---|
| CloudFormation Stack | usfas |
| ECS Cluster | usfas-cluster |
| ECR | 863422182520.dkr.ecr.ap-northeast-2.amazonaws.com/usfas |
| DynamoDB | usfas-processed-events, usfas-market-data |
| S3 | usfas-reports |
| Secrets Manager | usfas/fmp-api-key, usfas/discord-webhook |
| EventBridge | 매일 13:30 UTC (22:30 KST) |
