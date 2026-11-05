# T06 — 웹·Windows 프로그램의 T05 API 연동

이번 범위는 T05 API 4종을 호출하는 **독립된 예제**입니다. 기존 사용자 제품 코드, T05 정책, DB/모델 및 T07 패키징은 수정하지 않습니다.

## 1. 준비

T02 Builder로 지식 DB를 만들고, 해당 PC에서 API를 시작합니다.

~~~powershell
python -m api.localhost_api --database .\output\knowledge.db --port 8765
~~~

`/chat`까지 사용하려면 기존 T04의 로컬 llama-completion 실행 파일과 GGUF를 함께 지정하십시오. [T05](T05_LOCALHOST_API.md) 문서를 참조하십시오.

**주의:** `127.0.0.1`은 웹사이트 서버가 아닌 **브라우저·Windows 앱을 사용하는 PC 자신**입니다. 이 예제는 다른 PC의 AI 엔진에 접속하지 않습니다.

## 2. JavaScript 웹 예제

파일: `examples/web/knowledge-client.mjs`, `examples/web/index.html`.

~~~javascript
import { KnowledgeClient } from "./knowledge-client.mjs";
const client = new KnowledgeClient(8765);

const search = await client.search("example-program", "DB 연결 실패", "2.1.0");
const chat = await client.chat("example-program", "연결 오류 해결 방법", "2.1.0");
const event = await client.event(
  "example-program", "DB-1001", "connection_failed", "database_settings", "2.1.0"
);
const health = await client.health();
~~~

예제는 제품·버전·질문·오류 코드를 입력받고 **버튼 클릭**으로 네 API를 호출합니다. 화면에 응답과 `document_id`, `source_path`, `page_from`을 표시하고 `textContent`만 사용해 문서 내용을 HTML로 실행하지 않습니다.

**T05에는 원본 PDF 파일을 반환하는 경로가 없으므로 출처 URL을 임의로 만들지 않았습니다.** 기존 웹 프로그램에 문서 뷰어가 있다면 그쪽에서 `document_id`나 `source_path`를 이용해 연결해야 합니다.

### 로컬 페이지 실행

두 터미널에서 각각:

~~~powershell
python -m http.server 8080 --bind 127.0.0.1 --directory examples/web
python -m api.localhost_api --database .\output\knowledge.db --port 8765 --allow-origin http://127.0.0.1:8080
~~~

브라우저에서 `http://127.0.0.1:8080/index.html`을 연 뒤 제품 ID와 버전을 실제 DB에 맞추십시오. `file://` 페이지는 `Origin: null`로 차단될 수 있습니다.

### 사내 웹사이트 접근과 LNA

실제 웹사이트가 `https://help.example.com`이라면 API 서버에 `--allow-origin https://help.example.com`을 지정해야 합니다. 하지만 **CORS 허용은 브라우저의 로컬 접근 권한을 대신하지 못합니다.**

2026년 11월 기준 Chrome·Edge 가이드에 따르면:

- HTTP 사내망 사이트에서는 Local Network Access(LNA) 권한 요청이 제한될 수 있으므로 **HTTPS 보안 컨텍스트**를 권장합니다.
- Chrome에서는 `loopback-network` 권한을 조회할 수 있습니다. 지원하지 않는 브라우저에서 예제는 조회 실패를 처리하며, 구형 통합 `local-network-access` 권한 조회는 사용하지 않습니다.
- 최초 로컬 연결은 **사용자 버튼 클릭**으로 시작합니다. `fetch`에 `targetAddressSpace: "loopback"`을 명시합니다.
- 차단되면 브라우저 사이트 권한, API 실행 상태, 허용 Origin을 확인합니다.
- T05가 제공하는 구식 Private Network Access 프리플라이트 응답만으로 새 브라우저의 사용자 권한 승인을 우회할 수 없습니다.

근거: [Chrome 공식 LNA 가이드](https://developer.chrome.com/docs/modern-web-guidance/guides/security/local-network-access), [Microsoft Edge 공식 안내](https://learn.microsoft.com/en-us/deployedge/ms-edge-local-network-access).

## 3. C# Windows 예제

파일: `examples/windows/Program.cs`, `examples/windows/KnowledgeClientExample.csproj`. .NET 8 기본 `HttpClient`, `System.Net.Http.Json`, `System.Text.Json`만 사용하며 추가 NuGet 패키지는 없습니다.

~~~powershell
dotnet run --project examples/windows/KnowledgeClientExample.csproj -- 8765 example-program - health
dotnet run --project examples/windows/KnowledgeClientExample.csproj -- 8765 example-program 2.1.0 search "데이터베이스 연결 실패"
dotnet run --project examples/windows/KnowledgeClientExample.csproj -- 8765 example-program 2.1.0 chat "DB 연결 오류 해결 방법"
dotnet run --project examples/windows/KnowledgeClientExample.csproj -- 8765 example-program 2.1.0 event DB-1001 connection_failed database_settings
~~~

`-`는 버전이나 이벤트 등 미지정 값을 뜻합니다. C# 예제는 브라우저의 Origin 헤더를 보내지 않는 네이티브 요청이며 응답 JSON에 포함된 출처를 그대로 보여 줍니다.

## 4. 검증과 한계

- 기본 Python 회귀: `python -m unittest discover -s tests -v`.
- Windows 브라우저/C# E2E: `.github/workflows/t06-client-e2e.yml`.
- 실제 T02 Builder 생성 DB + T05 loopback 서버 + Windows .NET 8 콘솔 앱 + Chrome/Edge 브라우저에서 네 API와 출처 표시를 검증합니다.
- 허용되지 않은 별도 localhost 웹 Origin의 CORS 차단도 검증합니다.
- HTTPS 외부 사이트 LNA의 **사용자 승인창은 headless CI만으로 완전 검증할 수 없습니다**. CI의 가상 HTTPS Origin은 진단에만 사용하며, 실제 기업 웹사이트의 LNA 허용을 보증하지 않습니다.
- T06 API 테스트의 모델 응답은 모의 생성기를 사용합니다. GGUF의 실제 CPU 추론은 T04에서 별도 검증한 결과를 사용합니다.
