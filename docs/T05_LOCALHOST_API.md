# T05 — localhost HTTP/JSON API

T02 지식 DB와 T03 검색·T04 LLM 계층을 로컬 HTTP로 제공하는 서버입니다. Windows/Linux 개발 환경에서 Python 3.11 이상으로 실행합니다. 사용자용 독립 패키지(T07), JavaScript/C# 연동 예제(T06)는 아직 구현하지 않았습니다.

## 실행

프로젝트 루트에서:

\`\`\`powershell
python -m api.localhost_api --database .\output\knowledge.db --port 8765
\`\`\`

LLM 답변까지 사용하려면 사전에 보관된 **llama-completion** 실행 파일과 Qwen3 GGUF 파일을 함께 지정합니다.

\`\`\`powershell
python -m api.localhost_api --database .\output\knowledge.db --port 8765 --llama-cli C:\ai-runtime\llama-completion.exe --model C:\ai-runtime\Qwen3-1.7B-Q4_K_M.gguf
\`\`\`

기존 T04 인자 호환을 위해 옵션 이름은 \`--llama-cli\`로 남아 있지만 **실행 파일은 llama-completion**입니다. 자동 모델 다운로드나 외부 서버 접속은 하지 않습니다. LLM 파일을 지정하지 않으면 \`/search\`, \`/event\`, \`/health\`만 정상 작동하고 \`/chat\`은 503입니다.

## API

Base URL: \`http://127.0.0.1:8765\`. POST는 UTF-8 \`Content-Type: application/json\` 객체만 지원합니다.

| 메서드 | 요청 | 응답 |
|---|---|---|
| \`GET /health\` | 없음 | \`status\`, \`engine_version\`, \`knowledge_version\`, \`llm_ready\` |
| \`POST /search\` | \`product_id\`, \`query\`, 선택 \`version\` | \`results\` (문서명·발췌·출처·페이지) |
| \`POST /chat\` | \`product_id\`, \`question\`, 선택 \`version\` | \`answer\`, \`grounded\`, \`sources\`, 추론 시 \`elapsed_seconds\` |
| \`POST /event\` | \`product_id\`, \`event_id\` 또는 \`error_code\`, 선택 \`version\`, \`screen_id\` | \`matched\`, 성공 시 \`rule_id\`, \`title\`, \`content\`, \`source\` |

\`knowledge_version\`은 현재 지식 DB의 **스키마 버전 1**을 뜻하며 내용 갱신 날짜가 아닙니다. \`/event\`는 T03 승인 규칙만 조회하며 모델을 호출하지 않습니다. 충돌은 \`{"matched":false,"reason":"ambiguous_rules"}\`로 반환합니다.

## 브라우저 CORS / 로컬 접근 통제

리스너는 **127.0.0.1(IPv4)에만 바인딩**합니다. Host 헤더도 \`127.0.0.1:<port>\`를 강제합니다. 허용된 Origin이 아니면 처리 전에 403으로 차단합니다.

기본적으로 브라우저에서 허용되는 Origin은 API 자신의 Origin만입니다. 다른 웹 애플리케이션이 필요할 때 정확한 Origin을 명시합니다.

\`\`\`powershell
python -m api.localhost_api --database .\output\knowledge.db --allow-origin https://your-application.example
\`\`\`

- 와일드카드, \`Origin: null\`, 신뢰하지 않는 사이트는 허용하지 않습니다.
- OPTIONS 사전 요청은 POST 및 Content-Type만 허용하며, 필요한 경우 \`Access-Control-Allow-Private-Network: true\`도 반환합니다.
- 브라우저의 Private Network Access, Local Network Access, HTTPS→localhost 정책은 브라우저별 차이가 있으므로 **실제 웹 프로그램은 T06에서 검증해야 합니다**.
- Origin이 없는 Windows 네이티브 클라이언트의 로컬 호출은 허용합니다. 이는 계정 인증 기능이 아니며 **PC에 설치된 다른 프로그램의 접근까지 막지는 않습니다**.
- 허용한 웹사이트는 로컬 검색·CPU 추론에 접근할 수 있으므로 신뢰 가능한 Origin만 등록합니다.

## 오류 및 동시성

400: 잘못된 필드·버전·JSON / 403: Host·Origin 제한 / 413: 32KiB 초과 / 415: JSON이 아닌 콘텐츠 / 429: LLM 사용 중 / 503: DB 또는 LLM 이용 불가.

동시에 활성화되는 LLM 추론은 1개로 제한합니다. 검색과 오류 규칙 조회는 LLM 추론 중에도 가능합니다. T04 방식은 요청마다 모델을 다시 적재하므로 향후 메모리·시작 시간 개선의 여지는 있으나, 모델 서버 전환은 이번 작업 범위에 포함하지 않습니다.

## 검증

\`\`\`powershell
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
\`\`\`

실제 TCP localhost 포트로 문서 검색, 정확 규칙, CORS/Host 거부, JSON 검증, 동시 호출을 테스트합니다. HTTP 테스트의 LLM 생성은 모의 객체로 대체하며, Qwen3 실제 CPU 추론은 T04의 별도 CI에서 검증한 결과를 사용합니다.
