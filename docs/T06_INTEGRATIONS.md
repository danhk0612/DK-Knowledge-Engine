# T06 — 웹·Windows 프로그램 연동 예제

- 상태: T06 검증 대상. 실제 클라이언트 설치·고객 프로그램 통합과 오프라인 배포는 T07~T08에서 별도 확인.
- 기준: T05 `http://127.0.0.1:8765` API 네 종류, 정확한 제품 ID와 버전 전달, 근거 출처 표시.
- 사용한 외부 라이브러리: **실행 예제에는 없음**(브라우저 기본 `fetch`, .NET 기본 `HttpClient`). Playwright는 GitHub Actions의 브라우저 테스트에서만 사용.

## 1. 웹(JavaScript)

파일: `integrations/web/index.html`, `app.js`, `api-client.js`

인터넷이 없는 PC에서도 실행할 수 있으나 **`file://`로 직접 열지 말고 실제 웹 서버에서 HTTP(S)로 제공**해야 합니다. 모듈 스크립트는 웹 서버의 Origin을 이용하며 T05가 `Origin: null`을 차단합니다.

예를 들어 **동일 PC의 로컬 예제 서버**에서 `http://127.0.0.1:8766/`으로 제공한다면, T05 API의 정확한 Origin 허용 목록에 추가해야 합니다.

```powershell
python -m api.localhost_api --database .\output\knowledge.db --port 8765 --allow-origin http://127.0.0.1:8766
cd integrations/web
python -m http.server 8766 --bind 127.0.0.1
```

위 명령은 **각각 다른 터미널**에서 실행합니다. `--llama-cli`와 `--model`을 지정하지 않으면 AI 질문 버튼만 503을 반환합니다. 실제 모델을 사용하는 실행 방법은 [T05](T05_LOCALHOST_API.md)를 참고하십시오.

실제 내부망 웹페이지에서 사용할 경우에는 위 `--allow-origin`을 해당 웹페이지의 정확한 Origin(예: `https://intranet.example`)으로 설정합니다. `api-client.js`의 API 주소는 사용자 PC의 `127.0.0.1:8765`로 고정되어 있습니다.

버튼은 `/health`, `/search`, `/chat`, `/event`를 각각 호출하며, 제목/본문/출처는 `textContent`로 표시합니다. 원본 문서가 HTML 태그를 포함하더라도 실행하지 않습니다. `source_path`는 출처 메타데이터일 뿐, 브라우저에서 바로 열 수 있는 문서 URL을 뜻하지 않습니다.

## 2. Windows(C# WPF)

파일: `integrations/windows/KnowledgeHelpDemo` (.NET 10, WPF)

```powershell
dotnet build integrations/windows/KnowledgeHelpDemo/KnowledgeHelpDemo.csproj -c Release
dotnet run --project integrations/windows/KnowledgeHelpDemo/KnowledgeHelpDemo.csproj
```

WPF 창에서 제품 ID·버전·질문·이벤트·오류 코드를 입력하면 동일 PC의 T05 API를 `HttpClient`로 호출합니다. `KnowledgeHelpClient.cs`가 호출 코드를 담당하며, 예제 WPF 창은 결과 텍스트와 문서 상대 경로를 표시합니다.

**Origin 헤더가 없는 네이티브 프로그램**의 호출을 T05가 허용하므로 브라우저용 `--allow-origin` 지정은 필요 없습니다. 그 대신 같은 PC의 다른 로컬 프로세스도 API에 접근할 수 있습니다. 운영 환경에 맞춘 인증 정책은 이번 범위에서 구현하지 않았습니다.

`KnowledgeHelpSmoke`는 **같은 C# 클라이언트 소스**를 링크해서 GUI 없이 실제 localhost API를 호출하는 CI 검증용 콘솔 프로젝트입니다. WPF 창 자체의 GUI 상호작용 자동화와 고객 프로그램에 직접 삽입한 테스트는 하지 않았습니다.

## 3. 실제 브라우저 보안 정책

Chrome 142 이후 웹사이트→로컬 PC 또는 인트라넷 사이트→루프백 요청에는 **Local Network Access(LNA)** 권한 승인이 요구될 수 있습니다. Chrome 145 이후에는 `loopback-network` 권한이 더 세분화되어 있습니다.

- 페이지가 HTTPS 등 **Secure Context**여야 하고, 사용자가 사이트에 대한 로컬 접근 권한을 허용해야 할 수 있습니다.
- T05가 제공하는 Origin/CORS 허용은 브라우저의 LNA 권한 승인을 **대신하지 않습니다**.
- 과거의 `Access-Control-Allow-Private-Network`만으로 현행 브라우저 권한 요구가 해결되지 않습니다.
- 회사 PC 정책이나 브라우저 정책으로 로컬 네트워크 접근이 차단될 수 있습니다.
- 개발용으로 **루프백 웹페이지 → 루프백 API**를 호출하는 자동화는 LNA 승인을 요구하지 않을 수 있습니다. 이 결과만으로 외부/인트라넷 HTTPS 페이지에서의 동작을 일반화할 수 없습니다.

참고: [Chrome Local Network Access 공식 가이드](https://developer.chrome.com/docs/modern-web-guidance/guides/security/local-network-access), [Chrome Enterprise 릴리스 노트](https://support.google.com/chrome/a/answer/10314655?hl=ko).

### 별도 수동 검증 시나리오

실제 사용할 Windows Chrome/Edge 브라우저에서 HTTPS 사내 웹페이지를 열고, T05의 `--allow-origin`에 해당 사이트 Origin을 등록한 뒤 `fetch('http://127.0.0.1:8765/search', ...)`를 호출해야 합니다. 다음 항목을 확인합니다.

1. 사이트의 보안 컨텍스트 여부와 브라우저의 로컬 네트워크/루프백 권한 표시 및 허용 가능 여부.
2. 권한 허용 이후 CORS 프리플라이트와 POST 성공 여부, 반대로 거부 시 호출 차단.
3. 인터넷이 차단된 사용자 PC에서 실제 프로그램과 API가 함께 실행될 때의 동작.
4. Chrome/Edge 및 조직 정책별 차이. CI에 포함되지 않은 Windows 실기·사내 웹 운영 조건은 검증되지 않았다고 기록.

## 4. 자동 검증 범위

- `tests/t06_fixture.py`: 문서·오류 규칙을 T02에서 DB로 생성하고, T05 API를 실제 `127.0.0.1:8765` TCP 포트에서 가동.
- `tests/t06_browser.mjs`: Windows/Ubuntu의 **실제 Headless Chromium**에서 웹 UI 네 API, 출처 표시, 문서 HTML 비실행, 허용하지 않은 웹 Origin 차단 검증.
- `tests/t06_windows_smoke.py`: **Windows**에서 WPF 프로젝트 빌드 후 공유 `KnowledgeHelpClient.cs`를 이용하여 `/health`, `/search`, `/event`, `/chat` 호출 검증.
- `.github/workflows/t06-integrations.yml`: 개발·검증용 Playwright/Chromium과 .NET SDK 다운로드. **사용자 배포 환경**에서는 Playwright, Node, 외부 서비스가 필요하지 않습니다.
- HTTP 테스트의 LLM 출력은 모의 생성기를 사용합니다. 실제 GGUF 추론은 T04의 독립 검증 결과를 따릅니다.

개발·CI 용도로만 도구 다운로드가 필요할 수 있으나, 프로젝트에서 요구하는 **사용자 실행 시 완전 오프라인** 원칙은 유지됩니다.
