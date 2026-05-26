API 퀵스타트
소개
FMP란 무엇인가요?

업데이트 실시간 및 과거 주가, 회사 재무, 시장 뉴스, 주식 분석 도구 등 다양한 정보를 확인하세요. 100개 이상의 엔드포인트
를 통해 필요한 모든 금융 및 주식 시장 데이터가 한 곳에 모여 있습니다.

누구를 위한 거야?

저희는 개인용과 상업용 모두를 지원하며, 개발자, 애널리스트, 퀀트, 핀테크 스타트업, 투자은행 등 다양한 대상을 지원합니다

시작하기
API 키를 받으세요

API 키는 대시보드의 API 키에 있습니다.

요청을 승인하려면 모든 요청 끝에 ?apikey="[.env의 FMP_API 을 참조]" 추가하세요.

API 기본 사항
기본 URL

FMP API는 다음 경로를 통해 접근 가능합니다:

https://financialmodelingprep.com/stable/

인증 예시

접근 하려는 API 엔드포인트의 매개변수로 API 키를 전달하기만 하면 됩니다.

결말:

https://financialmodelingprep.com/stable/search-symbol?query=AAPL

이 기능은 Postman이나 curl 같은 어떤 브라우저나 HTTP 클라이언트에서 테스트할 수 있습니다.

인기 있는 API 엔드포인트
모든 100+ 엔드포인트에 대한 API 문서를 참조하세요.

엔드포인트 앞에 기본 URL을 꼭 추가하세요: https://financialmodelingprep.com/stable/

아래 예시를 클릭해서 직접 체험해 보세요!

종착점

예시

설명

/search-name?query={name}

/search-name?query=apple

아무 회사든 검색해서 주식 티커 심볼을 찾으세요.

/재고 목록

/재고 목록

이용 가능한 모든 회사 목록을 확인하세요

/인용문?symbol={symbol}

/인용?심볼=GCUSD

실시간 주식 시세

/historical-price-eod/full?symbol={symbol}

/historical-price-eod/full?symbol=AAPL

전체 가격 및 거래량 데이터, 시작, 최고, 저가, 종가, 거래량 등을 포함합니다.

/profile?symbol={symbol}

/프로필?symbol=AAPL

상세한 회사 프로필 데이터, 주요 재무 및 운영 정보

/income-statement?symbol={symbol}

/inincome-statement?symbol=AAPL

상장기업, 비상장 기업 및 ETF의 실시간 손익계산서 데이터

오류 코드
일반적인 오류 코드

코드

의미

해결 방법

403

유효하지 않거나 누락된 API 키

각 엔드포인트 끝에 API 키가 추가되는지 확인하세요. 대시보드를 통해 API 키가 정확한지 다시 한 번 확인하세요

429

요청이 너무 많음 (속도 한도 초과)

멀티스레드를 실행할 경우 코드에 시간 지연을 추가하거나 스레드 수를 줄이세요

500