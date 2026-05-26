# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

USFAS (US Fundamental Alert System) — FMP API 기반 미국장 촉매 감지 알람 시스템.
자동 매매 없음. 알람 + HTML 리포트까지가 시스템의 끝.

## Commands

```bash
# 의존성 설치
pip install -r requirements.txt

# 단위 테스트 전체
pytest tests/unit/ -v --cov=src --cov-report=term-missing

# 단일 테스트 파일
pytest tests/unit/test_kill_switch.py -v

# 단일 테스트 함수
pytest tests/unit/test_type1_earnings.py::test_eps_surprise_calculation -v

# 취약점 스캔
pip-audit

# Docker 빌드
docker build -t usfas:local .

# 로컬 E2E (환경변수 필요)
python -m src.catalyst_detector.handler --dry-run
```

## Architecture

4개 Unit이 순서대로 실행되는 파이프라인:

```
EventBridge Scheduler
  └─ ECS Fargate Task
       ├─ Unit 1: DataCollector   — FMP API → DynamoDB
       ├─ Unit 2: CatalystDetector — Kill-Switch → TYPE-1/2 조건 평가
       ├─ Unit 3: ReportGenerator  — Plotly + Jinja2 → S3
       └─ Unit 4: AlertingEngine   — Discord Webhook
```

`src/shared/config.py`가 `config.yaml`을 로드하고 모든 임계값을 제공한다. 임계값은 코드에 하드코딩하지 않는다.

`src/shared/secrets.py`가 AWS Secrets Manager에서 FMP API 키와 Discord Webhook URL을 가져온다.

## Signal Types

**TYPE-1 (어닝 미반응 서프라이즈)**: 어닝 발표 후 D+0~D+2 이내만 유효. D+3 이후는 스킵.

**TYPE-2 (내부자 클러스터 매수)**: `transaction_type == 'P'` (공개시장 매수)만 카운트. 옵션 행사(`'A'`), 증여(`'G'`) 제외.

**Kill-Switch**: VIX > 28 또는 US 10Y 전일 대비 +15bp 이상 또는 DXY 20일 볼린저 상단 돌파 시 전체 스캔 중단. 종목 스캔 없이 Discord 알람만 발송.

## Key Constraints

**멱등성**: 동일 종목의 동일 어닝/내부자 이벤트로 중복 알람 금지. DynamoDB `processed_events` 테이블로 관리.

**Bulkhead**: 종목 하나 FMP 호출 실패 시 해당 종목만 스킵, 나머지 계속 진행.

**리포트 자급**: Plotly 차트를 base64 인라인 임베드. 외부 CDN 없이 오프라인 렌더링 가능해야 함.

**손절 가격**: 리포트와 Discord 메시지 양쪽에 모두 필수 표시.

## FMP API

- Base URL: `https://financialmodelingprep.com/stable/`
- 인증: 모든 요청에 `?apikey={key}` 쿼리 파라미터
- 무료 티어: 250 req/day → 20종목 이내 운영
- 재시도: 실패 시 3회 재시도 (`src/data_collector/fmp_client.py`)
- 429 응답 시 지수 백오프 적용

## Infrastructure

- `template.yaml` — AWS SAM, ECS Task 정의 + EventBridge 스케줄
- `config.yaml` — 종목 유니버스, 임계값, S3 버킷명, Secrets Manager ARN
- Lambda 불가 (OpenBB ~500MB+) → ECS Fargate 사용
