# T06 — 사내 HTTPS 사이트에서 localhost LNA 현장 검증

**상태:** 검사 도구의 Node 단위 테스트와 모의 HTTPS 페이지→실제 localhost API의 Windows·Ubuntu Chromium 통합 테스트 완료. 실제 회사 PC·사내 HTTPS 도메인·조직 정책에서의 통과 여부는 **미검증**이며 운영자가 확인해야 합니다. 이 절차는 서비스 설정/권한을 우회하지 않습니다.

## 목적 및 범위

- Windows Chrome/Edge에서 **실제 사용할 HTTPS 사내 페이지 → 같은 PC의 http://127.0.0.1:8765** 연결을 검사합니다.
- 기존 API의 **GET /health**와 **POST /search**만 호출합니다. 검색 질의는 고정 예시이며 LLM 추론, 실제 고객 답변·문서 출력, 지식 DB 갱신은 하지 않습니다.
- `tests/t06_lna_field_probe.js`는 DevTools에 운영자가 직접 실행하는 임시 검사 코드로, **버튼을 누르기 전에는 네트워크 호출하지 않습니다**. 결과를 콘솔에만 표시하고 파일·외부 서버로 보내지 않습니다.
- 기존 T06 웹 예제의 `targetAddressSpace: "loopback"`·CORS JSON 방식을 사용하지만 **사내 프로그램 통합/권한 승인을 자동화하지 않습니다**.

## 준비

1. 조직에서 허가한 **시험용 Windows PC와 HTTPS 웹페이지**를 사용합니다. 실제 고객 데이터를 포함한 서비스에서 시험하기 전 담당자의 허가를 받습니다.
2. 같은 PC에 시험용 T07 Windows ZIP을 압축 해제한 뒤 `Verify-AIHelp.ps1`로 검증합니다. 기존 실행 중인 엔진을 정상 종료합니다.
3. `config/settings.json`의 `allowed_origins` 배열에 **페이지의 정확한 HTTPS Origin**(스킴·호스트·비기본 포트 포함)을 추가합니다. 다른 모델/제품 설정을 덮어쓰거나 `*`를 사용하지 않습니다. 예시는 `https://intranet.example`이며 실제 주소가 아닙니다.
4. `Start-AIHelp.cmd`를 실행합니다. 개발자 컴퓨터의 Python이나 별도 외부 API 서버를 요구하지 않습니다. 브라우저와 엔진은 **같은 PC**에 있어야 합니다.
5. Chrome에서는 `chrome://policy`, Edge에서는 `edge://policy`를 **조회만** 하여 관련 관리 정책이 있는지 확인합니다. 정책 수정·우회·테스트 목적의 전역 보안 해제는 하지 않습니다.

## 실행

1. 시험할 **실제 사내 HTTPS 페이지**를 브라우저로 열고 주소 표시줄에서 올바른 사이트인지 확인합니다.
2. DevTools의 **Sources → Snippets**에서 새 스니펫을 만들고, 저장소의 `tests/t06_lna_field_probe.js`를 **내용 확인 후 그대로** 붙여 넣어 실행합니다. 회사 정책에서 DevTools 사용을 허용하지 않는다면 실행하지 않고 IT 관리자에게 현장 검증 방법을 요청합니다.
3. 화면 우측 아래 임시 **“DK 로컬 API 연결 검사”** 버튼을 클릭합니다. HTTPS 보안 컨텍스트가 아니라면 이 도구는 네트워크 호출을 하지 않습니다.
4. 브라우저가 **로컬 장치/루프백 접근 권한**을 요청한다면 승인 또는 거부하여 시험합니다. 첫 검사에서는 조직이 허용하는 경우에만 **승인**하고, 이후 필요 시 사이트 설정에서 **거부/차단**한 상태를 별도로 시험합니다. 실제 회사 정책 때문에 설정 변경이 막혔다면 강제로 해제하지 않습니다.
5. Console에서 `DK_LNA_FIELD_PROBE_RESULT` 문자열을 찾아 JSON 결과를 확인합니다. 출력은 프로토콜, 보안 컨텍스트, 요청 HTTP 상태, 허용 상태, 시간만 포함하며 **사이트 호스트명·질문/답변·출처 경로를 기록하지 않습니다**. 운영자가 브라우저 버전·회사 정책·승인/거부 결과를 별도로 기록합니다.
6. 검사 후 임시 버튼을 지우려면 콘솔에 아래 명령을 입력하거나 페이지를 새로고침합니다.

~~~js
document.getElementById("dk-knowledge-lna-field-probe")?.remove();
~~~

## 판정

| 항목 | 기대 조건과 해석 |
|---|---|
| HTTPS·보안 컨텍스트 | `origin_scheme=https:`, `secure_context=true`. 아니면 검사를 시작하지 않음 |
| 승인 후 GET /health | `health.result=ok`, HTTP 200, 실제 DK 엔진 JSON 형식 확인 |
| 승인 후 POST /search | `search.result=ok`, HTTP 200, `results` 배열 확인(빈 배열도 정상). LLM은 호출하지 않음 |
| 권한/조직 정책 | `permission_after=granted`일 수 있으나 일부 버전·정책 예외에서는 `unsupported`, `prompt` 등도 가능. **HTTP 성공과 함께** 해석 |
| 권한 거부 | 정책상 거부 테스트가 허용된다면 요청 차단을 DevTools의 Network/Console에서 확인. 예외 정책이 있으면 거부 효과를 주장하지 않음 |
| `fetch_rejected` | LNA 거부 외에도 **CSP `connect-src`·CORS·혼합 콘텐츠·API 미실행·네트워크 장애**일 수 있음. 이 JSON 하나만으로 원인 판단 금지 |
| 인증·배포 적합성 | 이 테스트만으로 보증할 수 없음. 고객 문서 정확성, 실행 파일 서명·라이선스·물리적 오프라인은 별개 |

**참고:** GET이 실패하면 POST는 실행되지 않습니다. HTTP 403이 브라우저에 읽히지 않고 `TypeError`로 보일 수도 있습니다. `Access-Control-Allow-Origin`, 브라우저 권한, 페이지의 CSP `connect-src`는 서로 다른 제약입니다. 읽기 제한으로 인한 차단인지 개발자 도구의 *Network* 및 *Console*에서 확인합니다. 고객의 실제 질문·API 응답 본문·사내 URL 및 정책 전문을 공개 GitHub 이슈에 복사하지 않습니다.

### Chrome·Edge 정책 검토

- Chrome 공식 가이드: [Local Network Access](https://developer.chrome.com/docs/modern-web-guidance/guides/security/local-network-access). 루프백 대상은 `loopback-network` 권한이며 **HTTPS 보안 컨텍스트와 명시적인 사용자 동작**이 중요합니다. `targetAddressSpace: "loopback"`는 혼합 콘텐츠 판정에 정보를 제공하지만 사용자 권한을 우회하지 않습니다.
- Edge 공식 가이드: [Local Network Access](https://learn.microsoft.com/en-us/deployedge/ms-edge-local-network-access). 회사가 관리하는 브라우저는 사이트 권한 외에도 관리 정책의 영향을 받습니다.
- Edge 기업 정책의 예: [LoopbackNetworkAllowedForUrls](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/loopbacknetworkallowedforurls) (지원 버전별 차이), 대응되는 차단 정책. 정책의 허용 예외로 요청이 성공한 경우 **사용자 승인 프롬프트를 거쳤다고 기록하지 않습니다**.

## 결과 기록 및 보류 조건

사내 비공개 기록에 PC·브라우저/버전, 실제 시험 페이지의 Origin, 정확한 `allowed_origins` 적용 확인, LNA 사이트 권한과 관리 정책의 **적용 여부**, 승인/거부별 GET·POST HTTP/차단 결과, DevTools 오류 분류 및 재현 여부를 기록합니다. 콘솔 검사의 단순 성공은 **고객 프로그램이 실제로 통합됐다는 의미가 아닙니다**.

자동 테스트 `tests/t06_lna_field_probe.test.mjs`는 네트워크 실행 전 사용자 클릭, HTTPS 아닌 출처에서 요청 없음, 권한 거부 시 후속 POST 생략, 응답·질문 비기록만 검사합니다. 이 단위 테스트는 실제 권한 UI를 검증하지 않습니다.

**실제 회사 PC와 허가된 HTTPS 사이트에서 승인·거부 상황을 검증하기 전에는 이 현장 항목을 완료 처리하지 않습니다.**