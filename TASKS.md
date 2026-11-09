# DK Knowledge Engine — 개발 작업표

상태: **T01 설계 완료, T02~T10 구현 PR #1~#9 및 보완 PR #11·#13·#14·#15까지 `main` 병합 완료. 실제 고객 PC 및 문서 현장 검증은 미완료.**  
기준 문서: [docs/T01_CONTRACT.md](docs/T01_CONTRACT.md)  
공통 목표: Windows 10/11 x64 · 완전 오프라인 · Docker 미사용 · localhost 허용 · GPU 불필요 목표 · 코드/모델/지식 DB 분리

## 변경 제한 및 공통 규칙

- 기준 계약과 무관한 기능을 추가하지 않는다. 추가 검토가 필요한 사항은 별도 제안으로 남긴다.
- 구현 작업을 시작할 때는 저장소 최신 `main`, 본 작업표 및 T01 기준 문서를 먼저 확인한다.
- 모델·검색·문서 입력은 각각 분리하되 범용 플러그인 프레임워크를 선제 구현하지 않는다.
- 제품별 원본 매뉴얼 및 자료의 재배포 권한을 확인한다. 공개 저장소에 실제 고객 자료·개인정보·대형 모델을 올리지 않는다.
- 요구사항에 있는 검증이 환경상 불가능하면 완료로 보고하지 말고 한계를 남긴다.
- 후속 작업에서 초기 계약을 바꿔야 하는 상황은 근거와 영향을 문서화한 후 검토한다.

## T01 — 요구사항 / 데이터·API 계약

**상태: T01 설계 계약 문서 승인 완료. 해당 구현은 후속 T02~T10을 통해 `main`에 반영됨.**

- 최초 범위: 문서 수집·색인, SQLite FTS5 검색, llama.cpp 연결, localhost API, 연동 예제, 오프라인 패키징.
- 추가 합의: 문서 추가·수정·삭제, 전체 재색인, 원본과 인덱스 분리, 여러 제품 재사용, 백엔드 교체 가능한 경계.
- 결과물: `docs/T01_CONTRACT.md`, `README.md`, `TASKS.md`.
- 완료 확인: 기준 범위 및 미확정 사항, 네 가지 API, 지식 DB의 출처/식별자/갱신 원칙이 명시되어 있어야 한다.

## T02 — Knowledge Builder 및 지식 갱신

**상태: 구현·Ubuntu/Windows CI 검증 완료, PR #1 `main` 병합.**

범위:
- PDF/DOCX/TXT/MD를 읽어 문서·청크·출처(페이지/절/상대 경로/해시)로 정규화.
- SQLite DB 및 FTS5 인덱스 생성.
- 신규 문서 추가, 수정, 삭제 및 전체 재생성 지원.
- 원본 파일은 유지하며 사용자용 DB 생성 과정과 분리.
- 한국어 문장 추출/인덱싱의 한계 기록.

완료 조건:
- 각 형식의 실제 샘플 문서로 추출 검증.
- 동일 원본을 반복 처리해 중복·누락 없음.
- 신규/변경/삭제 시 검색 결과와 출처가 일관되게 반영.
- 전체 재생성 결과와 증분 반영 결과 비교.
- 문제가 있는 PDF/스캔 등 미추출 내역 보고.
- DB 포맷·버전과 문서 ID 갱신 정책 명시.

산출물: `builder/knowledge_builder.py`, `tests/test_knowledge_builder.py`, `docs/T02_KNOWLEDGE_BUILDER.md`, `requirements-builder.txt`, `requirements-test.txt`, `.github/workflows/t02-tests.yml`.

로컬 검증: Python 3.13.5 / SQLite 3.46.1 / pypdf 5.9.0 / python-docx 1.2.0, 회귀 11개 통과. GitHub Actions Python 3.11 `ubuntu-latest` 및 `windows-latest`에서 각각 회귀 11개 통과 (run 41754439277). 실제 Windows 10/11 물리 PC 및 8GB RAM 성능 검증은 T07~T08에서 수행. 한국어 형태소 검색 한계 및 OCR 부재는 문서화, 검색 품질 개선은 T03.

변경 금지: LLM 추론·localhost API·별도 GUI 구현.

## T03 — 검색 모듈

**상태: 구현·Windows/Ubuntu CI 검증 완료, PR #2 `main` 병합.**

범위:
- `product_id`, 버전, `error_code`, `event_id`, `screen_id` 검색.
- SQLite FTS5 문서 검색과 출처 반환.
- 동일 조건 규칙 충돌의 처리 정책을 검증하고 문서화.
- 한국어 띄어쓰기·동의어 검색의 한계를 테스트.

완료 조건:
- 제품/버전 간 결과 혼합 방지.
- 문서 추가·교체·삭제가 검색에 반영.
- 무매칭·중복/충돌 조건에서 임의의 잘못된 문서 반환하지 않음.
- 재현 가능한 테스트 및 결과 기록.

산출물: `search/knowledge_search.py`, `tests/test_knowledge_search.py`, `tests/test_search_integration.py`, `docs/T03_KNOWLEDGE_SEARCH.md`.

초기 버전 정책: 숫자·점 버전만 비교, 버전 경계 포함, 미지원 버전 표현은 일치시키지 않음. 여러 동일 우선순위 규칙은 임의 선택 없이 충돌 처리. 한국어 형태소 검색은 지원하지 않으며 한계를 테스트로 기록. 검색 모듈은 읽기 전용이고 HTTP/LLM 기능 없음.

검증: 로컬 검색 회귀 13개 통과. GitHub Actions Python 3.11의 Windows/Ubuntu에서 T02+T03 전체 회귀 **각 25개 통과** ([run 41756062442](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41756062442)). 초기 Windows 실행의 테스트 SQLite 연결 종료 오류를 수정하고 재검증 완료. 실제 대상 사무용 PC 성능 측정은 T08 범위.

변경 금지: 외부 벡터 DB 또는 임베딩 검색을 자동 채택하지 않음.

## T04 — 소형 LLM 연결

**상태: 구현·자동 및 실모델 CPU 검증 완료, PR #3 `main` 병합.**

범위:
- llama.cpp 기반 Qwen3 1.7B GGUF CPU 실행.
- 검색된 근거를 이용해 한국어 답변 생성.
- 근거 없음 처리, 출처 연결, 응답 성능 측정.
- 모델/추론 런타임 호출 경계를 최소한으로 분리.

완료 조건:
- 다운로드 아티팩트의 출처·버전·해시·라이선스 기록.
- 실제 CPU 실행 및 답변/출처 검증.
- 모델 호출 없는 정확한 오류 규칙 경로 유지.
- 외부 통신 없이 실행 가능.

산출물: `llm/local_llm.py`, `tests/test_local_llm.py`, `tests/smoke_t04_cpu.py`, `docs/T04_LOCAL_LLM.md`, `.github/workflows/t04-cpu-smoke.yml`.

모델 기준: ggml-org/Qwen3-1.7B-GGUF Q4_K_M (SHA-256: d2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5), llama.cpp v0.8.0 CPU 후보. 매 요청 시 모델 새로 적재하는 CLI형으로, 장시간 유지하는 실행 정책은 T05와 별도 검토. 모델 파일과 실행 바이너리는 저장소에 포함하지 않음.

실측 검증: [Windows/Ubuntu 38개 회귀 모두 통과](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41761185105), [Ubuntu llama.cpp CPU + Qwen3 Q4_K_M 실추론 성공](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41761185104). SHA-256 일치, 매뉴얼 포트 3308 근거 답변·출처 정상, 해당 CI 환경에서 호출 5.27초. Windows 10/11 8GB 실기와 평균 성능은 미검증(T08).

변경 금지: 모델 파인튜닝 및 다른 런타임 어댑터 구현.

## T05 — localhost API

**상태: 구현·Windows/Ubuntu CI 검증 완료, PR #4 `main` 병합.**

범위:
- `GET /health`, `POST /search`, `POST /chat`, `POST /event`.
- 로컬 바인딩, 요청/응답 유효성 및 제품별 데이터 경계.
- 웹 Origin/CORS 및 로컬 접근 통제 정책 검증.

완료 조건:
- T01의 네 API 계약에 대한 통합 테스트.
- `127.0.0.1`에서만 리슨.
- 무매칭/근거 없음/오류 규칙 충돌의 일관성 확인.
- 외부 사이트에서 임의 호출 가능한 구성 방지 검증.

산출물: `api/localhost_api.py`, `api/__init__.py`, `tests/test_localhost_api.py`, `docs/T05_LOCALHOST_API.md`.

검증: [GitHub Actions Windows/Ubuntu Python 3.11 각각 **56개 통과**](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41762883450). T02 Builder로 생성한 DB를 실제 localhost TCP에 연동하여 API 4종, 제품·버전 경계, 오류 규칙, 출처, 근거 없는 질문, 동시 LLM 요청 제한, Host/Origin/CORS, Private Network preflight, JSON 오류·모델 시간 초과 등을 검증. HTTP 테스트의 LLM은 모의 생성기; 실제 Qwen CPU 검증은 T04에서 별도 통과. 브라우저에서 내부망 웹 프로그램의 실제 호출은 T06에서 검증.

정책: `127.0.0.1`에만 바인딩, Host 정확 검사, 브라우저 Origin은 기본 동일 Origin 및 명시 허용한 Origin만. Origin 없는 Windows 로컬 프로세스는 접근 가능하며 이는 인증 수단이 아님. 채팅은 동시 1회, 검색·이벤트는 별도 처리. Docker·외부 서버·인증 서비스 미포함.

변경 금지: 인증 서비스·온라인 기능 추가.

## T06 — 웹·Windows 연동 예제

**상태: 웹/Windows 연동 및 Windows/Ubuntu CI 검증 완료, PR #5와 HTTPS LNA 보완 PR #13까지 `main` 병합. 기업 브라우저 현장 검증은 별도.**

범위:
- JavaScript 기반 웹 프로그램에서 질문/오류·상태 이벤트 호출.
- C# Windows 프로그램에서 동일 API 호출.
- 화면 표시와 출처 연결 예제.
- 브라우저 보안 정책의 실제 적용 가능성 확인.

완료 조건:
- 실제 Windows 브라우저 및 C# 환경에서 동작.
- 브라우저의 localhost 접근 정책으로 차단되는 경우 한계 기록.
- 두 예제의 API 의미 및 응답 처리 동일.

산출물: `integrations/web/`, `integrations/windows/KnowledgeHelpDemo/`(.NET 10 WPF), `integrations/windows/KnowledgeHelpSmoke/`, `tests/t06_fixture.py`, `tests/t06_browser.mjs`, `tests/t06_windows_smoke.py`, `docs/T06_INTEGRATIONS.md`, `.github/workflows/t06-integrations.yml`.

검증: Windows/Ubuntu Headless Chromium의 실제 루프백 HTTP 호출, 허용되지 않은 브라우저 Origin 차단, Windows WPF 컴파일·동일 C# 클라이언트 소스의 HTTP 호출. 단, 브라우저가 다른 주소 공간의 HTTPS 사내 웹페이지에서 LNA `loopback-network` 권한을 요청하는 상황은 CI 루프백 테스트만으로 검증되지 않으므로 별도 Windows 실기 검증 필요.

자동 검증 결과: [T06 Actions run 41772218386](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41772218386) Windows Chromium 성공, Ubuntu Chromium 성공, Windows WPF 0 warnings/0 errors 빌드 및 동일 C# 클라이언트의 health/search/event/chat 실제 HTTP 호출 성공. [T02~T05 전체 회귀 run 41772218397](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41772218397) 성공. 실제 HTTPS 사내 웹→localhost LNA 승인 및 Windows 8GB 실기는 미검증.

변경 금지: 사용자 제품 코드 직접 수정.

## T07 — 오프라인 배포 및 지식 갱신 패키징

**상태: Windows ZIP·실모델·DB 교체/롤백 자동 CI 검증 완료, PR #6 `main` 병합. DB 중단 복구 보완 PR #11도 `main` 병합(고객 실기 검증 별도).**

범위:
- 엔진 실행 파일·llama.cpp 런타임·GGUF·지식 DB·설정 묶음.
- 사용자 PC에서 PDF 변환이나 인덱스 생성을 하지 않는 배포 방식.
- 제작자 PC에서 DB 갱신 후 전체 DB 교체 패키지 생성.
- 라이선스, 파일 무결성, DB/엔진 호환성 확인.

완료 조건:
- 새 Windows x64 PC에서 Docker·인터넷·GPU 없이 설치/실행 검증.
- DB 업데이트 후 이전 내용 수정·삭제가 반영됨.
- 기존 코드와 지식 DB의 독립적인 교체 가능성 검증.
- 업데이트 중 손상/부분 적용 방지 및 되돌림 절차 기록.

산출물: `distribution/server_entry.py`, `distribution/Build-Portable.ps1`, `distribution/templates/`, `tests/test_distribution.py`, `tests/t07_prepare_db.py`, `tests/t07_package_smoke.py`, `.github/workflows/t07-portable-windows.yml`, `docs/T07_WINDOWS_PACKAGE.md`.

구성: PyInstaller onedir 엔진, llama.cpp v0.8.0 CPU·OpenSSL 비활성·정적 라이브러리/MSVC 런타임 실행 파일, SHA-256 검증한 Qwen3 1.7B Q4_K_M GGUF, 사전 생성한 SQLite FTS5 DB, 설정, 라이선스, 개별 파일 무결성 manifest. 지식 DB는 별도 SHA와 SQLite 검사 후 전체 교체·롤백하며 사용자 환경에서 재색인하지 않음. 정식 Release/tag 미생성.

검증 증거: [Windows Actions run 41786316047](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41786316047)에서 실제 ZIP 생성·압축 해제·무결성·127.0.0.1 API·CPU 모델 `/chat`·DB 업데이트·롤백·잘못된 해시 및 스크립트 변조 차단까지 성공. 샘플 DB가 포함된 아티팩트이며 Release 아님. Windows/Ubuntu 62개 자동 회귀 테스트도 통과. 물리적 네트워크 차단과 Windows 10/11 8GB 실기는 미검증(T08).

변경 금지: 온라인 업데이트 서버, 델타 패치 시스템 선제 구축.

## T08 — 통합 검증 및 모델 비교

**상태: 모델 비교·Windows 포터블/PowerShell 자동 기능 검증 완료, PR #7 및 PowerShell 5.1 판정 보완 PR #14 `main` 병합. 하드웨어 성능 실측은 필수 게이트에서 제외; 실제 고객 매뉴얼·오프라인·보안 정책은 현장 미검증.**

범위:
- 대표적인 사용 설명서/트러블슈팅 질문과 오류 이벤트 테스트.
- 모델/실행 옵션을 사용자가 선택할 수 있도록 구성. 고정 하드웨어 규격과 성능 실측은 승인 필수 조건에서 제외.
- Qwen3 1.7B 대 Qwen3.5 2B 품질/속도 비교.
- 오프라인·재배포·여러 제품 자료 격리·갱신 검증.

완료 조건:
- 테스트 명령·환경·기대/실제 결과를 기록.
- 객관적인 근거로 기본 모델과 배포 사양 결정.
- 성능 목표 미달이나 모델 사용 불가능 시 완료로 가장하지 않음.

산출물(검증 준비): `tests/t08_windows_benchmark.py`, `tests/t08_model_comparison.py`, `.github/workflows/t08-benchmarks.yml`, `tests/t08_field_check.ps1`, `tests/t08_field_cases_sample.json`, `.github/workflows/t08-field-validation.yml`, `docs/T08_VALIDATION.md`, `docs/T08_FIELD_CHECKLIST.md`.

실행 증거: [T08 최종 CI run 41951563077](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41951563077) 두 벤치마크 작업 성공; [Windows/Ubuntu 62개 자동 회귀 41951563057](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41951563057) 통과. Windows 호스팅 RAM 16GB에서 실제 T07 ZIP의 한국어 답변 3/3, 프로세스 합산 RSS 최고 약 2253MiB, 요청 중앙값 10.24~12.30초(서로 다른 CI 반복). Qwen3 1.7B와 Qwen3.5 2B 모두 5/5 제한된 한국어 매뉴얼 정답 토큰 검사 통과; 서로 다른 CI 반복에서 중앙값 Qwen3 2.57~4.42초, Qwen3.5 2.34~4.22초. 호스트/표본 편차가 커서 **기본 모델 변경 근거 불충분**, 현재 T07 Qwen3 1.7B 유지.

현장 도구 검증: [Windows PowerShell 5.1 field kit CI run 41953982849](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41953982849), 포터블 T07 샘플 ZIP의 검색·오류·LLM 2회·제품/버전 격리·근거 없음 사례 총 7/7 통과. 냉시작 0.553초, 추론 6.947/6.765초, 메모리 표본 피크 2253MiB. **Windows Server 2025 약 16GB CI 기기이며 8GB 실기/물리 오프라인으로 표시하지 않음.** 스크립트는 원본 질문·답변 내용을 보고서에 보관하지 않으며 로컬 운영자가 현장에서 실행해야 함.

검증 구분: GitHub 호스팅 Windows는 **실제 8GB 고객 PC가 아님**. 모델 비교는 동일 llama.cpp v0.9.0/CPU에서 Qwen3 1.7B와 Qwen3.5 2B를 5개의 정형 질문으로 비교하는 탐색 실험으로, T07 배포 런타임 v0.8.0을 변경하지 않음. 고객 PC의 고정 RAM/CPU 사양은 이제 완료 조건이 아님. 완전 네트워크 차단·사내 HTTPS LNA·SmartScreen/서명·실제 고객 문서 정답률은 별도 현장 검증 후에만 완료로 판정.

## 실행 순서

```text
T01 (완료)
 ├─ T02 문서·지식 DB
 └─ T04 로컬 LLM 초기 실행 검증 (T02와 병렬 가능)
       ↓
T03 검색 (T02의 DB 필요)
       ↓
T05 API 통합 (T03·T04 결과 필요)
       ↓
T06 웹·Windows 연동
       ↓
T07 오프라인 패키지
       ↓
T08 최종 검증
```

**다음 단계:** 통합된 `main`으로 Windows 시험용 ZIP을 빌드·검증하고 Git으로 소스를 내려받은 시험 PC에서 기능·오프라인 작동을 검증한다. 실제 Windows 10/11 환경에서 사내 HTTPS 브라우저 정책/LNA 승인·거부, SmartScreen/서명, 고객 문서의 정답성과 재배포 라이선스를 확인하기 전에는 **정식 고객 배포 적합**으로 판정하지 않는다. 하드웨어별 속도·RAM 측정은 필수 조건이 아니다.

## 추가 검증 PR (2026-11-05 기준, `main` 병합 완료)

| PR | 자동 검증 완료 범위 | 현장 미완료 |
|---|---|---|
| [#13 HTTPS 웹→localhost LNA](https://github.com/danhk0612/DK-Knowledge-Engine/pull/13) | [Windows/Ubuntu Chromium, Windows C# 3/3](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41985270058), [T02 회귀 2/2](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41985270102) | 실제 사내 HTTPS·Chrome/Edge LNA 권한 및 기업 정책 |
| [#14 Windows PowerShell 5.1 판정](https://github.com/danhk0612/DK-Knowledge-Engine/pull/14) | [T07 빌드·T08 기능 7/7](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41984774214), [T02 회귀 2/2](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41984774166) | 실사용 Windows PC·실제 고객 질문 |
| [#15 T10 품질 기대값 검증](https://github.com/danhk0612/DK-Knowledge-Engine/pull/15) | [Windows/Ubuntu 단위 검증 및 실제 모델·인공 DB 14/14](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41981987505), [T02 회귀 2/2](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41981987468) | 고객 매뉴얼 정답성과 근거의 담당자 검토 |

위 PR #13~#15는 `main`에 병합되었고 각 PR HEAD의 자동 CI가 통과했다. 이 수치는 **합성 테스트 자료**에만 해당하며, 실제 사내 PC 검증·법적 재배포 승인으로 간주하지 않는다. 시험용 ZIP을 실제 PC에서 확인할 때에는 사용한 Git 커밋과 ZIP 검증 결과를 함께 기록한다.

## T09 — 선택형 로컬 모델 및 추론 설정

**상태: 모델·런타임 설정 기능 구현과 Windows 실모델/ChatML 검증 완료, PR #8 `main` 병합.**

범위:
- Windows 포터블 `config/settings.json`의 `model.file`, `model.runtime`, `threads`, `context_size`, `max_tokens`, `timeout_seconds`, `gpu_layers`, `prompt_mode` 선택.
- 기본 Qwen3 1.7B CPU 설정 및 기존 T07 설정 파일 호환 유지.
- 모델은 `models/`, llama.cpp 호환 실행 파일은 `runtime/` 하위에서 지정. 사용자가 직접 파일을 제공하며 인터넷·자동 다운로드·하드웨어 등급 자동 판정은 없음.
- T05 API 엔드포인트·JSON 계약 및 T02/T03 지식 DB/갱신 방식 보존. 모델별 호환성은 사용자가 선택한 GGUF와 해당 llama.cpp 버전에 따라 달라짐.

검증: `tests/test_model_selection.py`, `tests/t09_config_smoke.py`, `.github/workflows/t09-model-configuration.yml`. 기본 GGUF 및 이름이 다른 동일 GGUF의 파일 선택·CPU 추론 검증은 CI에서 수행; 모든 모델 종류·GPU 조합 지원은 주장하지 않음.

문서: [T09 모델 및 실행 설정](docs/T09_MODEL_CONFIGURATION.md).

변경 금지: PR 직접 병합, Release/tag, 자동 모델 다운로드/추천, unrelated 제품 코드 수정.

T09 Windows 검증: [Actions run 41955872865](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41955872865) 성공. 현재 코드로 포터블 EXE를 빌드하여 기본 Qwen3 답변, 동일 GGUF의 다른 파일명 선택과 다른 런타임 EXE 선택, 2스레드 설정, raw_chatml 답변, 누락 모델 거부를 확인. 별도 [Windows/Ubuntu 각각 69개 회귀 41955872746](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41955872746) 통과. GPU 런타임·다른 아키텍처 GGUF는 미검증이며 보장하지 않음.

사양 측정 정책: T08 현장 도구에서 하드웨어/성능 측정 기능을 제거하고 [Windows 기능 확인 CI 41956675584](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41956675584) 7/7 통과. 고객 매뉴얼·브라우저·보안/오프라인 검증은 별개로 남김.

## T10 — 근거 출처·정답성·오프라인/배포 보안 검증

**상태: Windows/Ubuntu 평가기 및 실제 Windows 모델·인공 매뉴얼 14/14 자동 검증 완료, PR #9와 공백 품질 기준 보완 PR #15 `main` 병합. 실제 고객 문서·현장 오프라인·보안 평가는 미검증.**

범위:
- 개발자 환경에서 실제 검색 결과와 /chat에 표시된 문서·청크·페이지 출처를 대조하고 정답·금지 키워드를 별도로 평가.
- 다중 제품·이전 버전·무근거 질문과 오류 이벤트의 올바른 격리 점검.
- HTTP Host/Origin/OPTIONS 경계 및 기존 T07/T09 패키지 SHA·라이선스 파일 존재 검증.
- 실제 고객 매뉴얼은 사내 PC에만 저장하고, 자동 보고서는 질문·답변 원문과 출처 경로를 포함하지 않음.
- 물리적 오프라인, 사내 브라우저 정책·SmartScreen/코드 서명, 실매뉴얼 정답성은 별도 현장 검토로 구분.

산출물: `tests/t10_fixture.py`, `tests/t10_cases_sample.json`, `tests/t10_eval.py`, `tests/t10_run_portable.py`, `tests/test_t10_quality_eval.py`, `.github/workflows/t10-validation.yml`, `docs/T10_VALIDATION.md`.

변경 금지: 기존 T07/T09 API/모델·설정/지식 DB 계약 변경, 시스템 사양/성능 벤치마크 재개, 고객 매뉴얼 공개, PR 직접 병합·Release/tag.

검증 증거: [Windows·Ubuntu 5개 단위 테스트 및 Windows 실모델 14/14 통합 CI 41958831101](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41958831101). 인공 DB 교체·무결성, 제품/버전 격리, 모델 정답 키워드, 실제 검색 청크 인용, Host/Origin 제한 통과. 고객 자료 미사용. 사양 측정은 재개하지 않음. 실고객 지식 DB의 실제 정답성, 물리적 오프라인, 사내 브라우저 정책/서명/법적 재배포 검증은 별도 남음.

## T11 — 실기 Qwen3 추론 기본 설정 안정화

**상태: PR #22 `main` 병합.** 실제 73-청크 PDF에서 기존 Qwen3 Jinja mode가 미완성 `<think>` 구간으로 실패한 반면 `raw_chatml`이 동작했으므로 Windows 포터블 기본 설정 및 구설정 대체값을 후자로 변경했다. 기존 모드 명시 선택은 유지한다. T07/T09 실모델 Windows CI와 Windows/Ubuntu 단위 회귀가 통과했다.

## T12 — 관리자/사용자 Windows GUI 분리

**상태: 초기 구현 및 CI 검증 진행 중.** C#/.NET 10 WPF 프로그램을 `apps/Admin`, `apps/Client`로 각각 분리한다. Admin은 원본 문서 폴더/지식 DB 재생성·AI QA·사용자 패키지 제작을, Client는 AI 질문·검색·엔진 제어·DB 갱신 및 롤백을 맡는다. 배포용 ZIP에는 Client GUI·런타임·모델·DB와 기존 검증 스크립트만 포함하고 관리자 EXE·Builder 소스·원본 문서를 포함하지 않는다. 관리자 PC의 Python/Builder 의존성 통합·실 GUI 클릭 검증·서명/SmartScreen 등은 후속 단계에서 완료한다.

## T13 — 관리자 GUI 문서 CRUD 및 독립 배포 ZIP

**상태: PR #25 구현 및 Windows 독립형 Admin/Client CI 검증 완료. 실제 제작자 PC GUI 클릭 시험은 미완료.** 원본 PDF/DOCX/TXT/MD 파일을 제품별로 추가·교체·삭제하고, 사용자가 명시적으로 DB 재생성 버튼을 눌러 변경을 반영한다. 개별 문서/제품 범위와 메타데이터 규칙은 유지한다. 독립형 Admin ZIP에는 PyInstaller로 묶은 Builder, 자체 포함 Admin/Client WPF EXE와 검증된 엔진·모델 템플릿을 포함한다. 제작자 PC에는 Python/Git/.NET SDK를 요구하지 않으며 Client ZIP에는 Admin·Builder를 포함하지 않는다. 정식 Release·코드 서명·자동 업데이트·현장 버튼 클릭은 후속 검증이다.

## T14 — 임의 원본문서 폴더 통합 관리 및 개발용 Python 자동 확인

**상태: 소스 수정 및 배포 전 문서화 완료. 사용자 요청에 따라 이번 변경의 테스트·실행 파일 재빌드·Release는 진행하지 않음.**

- Builder는 원본 폴더 최상위 또는 임의 하위 폴더의 PDF/DOCX/TXT/MD를 읽는다. 제품별 `<product_id>/manuals` 및 `rules` 구조는 기존과 호환한다. 그 외 문서는 `--default-product-id`(Admin GUI의 일반 폴더 문서 제품 ID)로 지정하며, 제품 ID가 바뀌면 기존 지식 DB 갱신에도 반영한다.
- 관리자 문서 목록은 원본 폴더 전체를 대상으로 한다. 처음부터 복사해 둔 문서와 GUI에서 추가한 문서를 같은 목록에서 교체·삭제할 수 있다. GUI의 파일 추가는 선택한 원본 폴더 최상위로 복사한다.
- Windows 절대 경로 및 폴더 위치는 고정하지 않는다. DB 출력은 원본 폴더 안/밖 모두 가능하지만 원본문서 덮어쓰기, 지정 폴더 밖으로의 관리 작업, 심볼릭 링크를 통한 폴더 우회는 허용하지 않는다.
- 개발용 Admin에서 venv/PATH/py 런처의 Python 및 `pypdf`·`python-docx` 존재를 검사하여 실행 파일 경로를 자동 입력한다. 독립형 Admin은 동봉된 Builder를 사용한다.
- 변경한 기존 스모크 코드의 호출 형식은 수정했지만 **테스트 명령은 실행하지 않았으며 통과했다고 주장하지 않는다.** ZIP/EXE 빌드, Windows GUI 동작, 실제 매뉴얼 색인 및 사용자 패키지 제작은 배포 승인 전 확인 항목으로 남긴다.
- 기존 오프라인·Docker 불필요·Client/Admin 분리·API/DB 스키마 정책은 유지한다.

## T14 후속 — 관리자 기본값 및 반복 패키징

**범위:** 관리자 실행 시 원본 문서·지식 DB·사용자 출력 폴더 기본값을 사용자별 영구 위치로 설정하고, 동봉 엔진 경로를 자동 지정한다. 기존 문서 추가는 현재 원본 폴더로 자동 복사한다. 사용자 Client 패키징은 출력 폴더가 존재해도 새로 생성한 파일만 덮어쓰며 무관한 파일은 보존한다. ZIP은 격리 작업 폴더에서 검증 후 내보낸다.

기존 PR #26의 T14 문서 인식·AI 검색 구현은 유지하며 새로운 파일 갱신 방식에 대한 CI 및 실기 확인 결과를 별도 기록한다. 고객용 정식 Release·서명 및 `main` 병합은 별도 결정이다.

## T15 — 공개 사전 배포 준비

**상태: v0.1.0-preview.1 배포 준비 브랜치에서 작업.** 사용자용 README, Admin/Client 빠른 시작, MIT 프로젝트 LICENSE, 제3자 의존성 고지, 버전별 릴리스 노트 및 Release 초안 생성 절차를 마련한다. 관리자/사용자 ZIP 안에 안내·라이선스 파일을 포함하고 Client의 불변 매니페스트에 해당 파일의 해시를 기록한다. 공개 릴리스는 성공한 같은 main 커밋의 통합 CI Run ID와 두 ZIP을 확인한 후 **Draft prerelease**로 생성하며 자동 공개하지 않는다.

**공개 전 제한:** unsigned ZIP/SmartScreen, 실제 고객 문서 권리·데이터, Python/PyInstaller 및 transitive dependency의 완전한 라이선스 고지, Windows 현장 적합성은 별도 승인 대상. 첫 preview의 사용자 ZIP은 합성 샘플 DB만 포함한다.

## T16 — 배포용 GGUF 모델 선택 및 DB/답변 경로 분리 설명

**상태: 개발 브랜치에서 구현·CI 검증 진행.** 관리자는 사용자 패키지 제작 시 컴퓨터의 GGUF 파일을 선택해 Client ZIP에 포함할 수 있다. 선택 파일이 없으면 기본 Qwen3가 유지되며, 선택 시 기본 모델 대신 GGUF 복사, 설정 파일 경로/프롬프트 형식 업데이트, 매니페스트 모델 SHA-256 재계산을 수행한다. 호환 모델의 GGUF 채팅 템플릿 사용을 위한 일반 `jinja` 모드를 추가하고 기존 Qwen3 모드는 유지한다. 지원하지 않는 모델 아키텍처·런타임의 자동 업데이트는 범위 밖이다.

Knowledge Builder는 모델 기반 임베딩/OCR/LLM 처리를 하지 않으며 기존 pypdf·python-docx 텍스트 추출 및 SQLite FTS5 검색 방식을 변경하지 않는다. 진단 방법은 `docs/T16_MODEL_PACKAGING.md`에 기록. 새 스키마·백엔드·다운로드·신규 서비스·정식 Release는 추가하지 않는다.

## T17 — PDF 추출·한국어 검색·근거 기반 답변 품질 개선

**상태: T16 기반 개발 브랜치에서 구현·CI 검증 진행.** 제작자용 옵션으로 PDF layout 추출·텍스트가 없는 PDF 페이지의 오프라인 Tesseract/Poppler OCR을 추가한다. 품질 보고서는 문서별 추출 글자·청크·경고를 기록하고 관리자에서 직접 열 수 있다. 사용자 측에는 DB 스키마를 바꾸지 않는 한국어 복합어 띄어쓰기 검색 보완을 적용한다. 근거 최대 5개와 번호·페이지를 표시하는 다단계 프롬프트를 사용하고 신규 기본 CPU 패키지의 생성 토큰 상한을 384로 높인다. 기존 T10 증거 평가의 근거 상한 및 T14 일반 원본문서 제품 분리 검사를 정합화한다.

**제약:** OCR 도구는 제작자 PC에 사전 설치해야 하며 사용자 ZIP에는 넣지 않는다. 전체 문서 OCR·의미 검색/임베딩 모델·제작용 생성 LLM은 아직 포함하지 않는다. 고객별 정답률 개선은 실제 승인된 PDF와 평가 질문 세트로 별도 검증이 필요하다. [docs/T17_QUALITY_PIPELINE.md](docs/T17_QUALITY_PIPELINE.md).

## T18 — 고사양 제작용 LLM 검색 보강 (경량 사용자 유지)

**개발 브랜치:** `feat/t18-author-knowledge-enrichment`. Builder에서 선택한 로컬 llama.cpp/GGUF 또는 이미 실행 중인 localhost 호환 고성능 LLM으로 문서 청크의 검색 질문과 용어를 오프라인 생성한다. 생성된 값은 근거가 아닌 별도 SQLite FTS5 보조 검색 힌트로만 기록하고, 반환하는 근거는 원본 청크로 제한한다. Client는 새 실행 모델이나 서비스 없이 기존 SQLite와 사용자용 별도 GGUF를 유지한다. schema_version=1 유지, 구형 DB 검색 호환, 제품/버전 분리, 원본문서 변경 시 색인 정리 회귀 테스트 추가.

한계: 사용자 질문의 의미 임베딩·벡터 검색은 별도 단계이며, 생성된 검색 힌트에 오탐 가능성이 있어 고객 정답 질의 집합으로 비교해야 한다. [사용법](docs/T18_AUTHOR_ENRICHMENT.md).

## T19 — 선택형 경량 임베딩 하이브리드 검색

**개발 브랜치:** `feat/t19-optional-lightweight-embeddings`. 관리자에서 선택한 임베딩 GGUF·llama-embedding 실행 파일로 문서 벡터를 사전 생성하고, 사용자 쪽에는 요청할 경우에만 동일 SHA-256 임베딩 GGUF와 경량 실행 파일을 포함한다. 기존 키워드 검색·T18 사전 생성 힌트는 유지하고 선택적 cosine 기반 하이브리드 검색을 추가한다. 모델·차원·완성 여부는 DB에 저장하고 Client 패키징과 실행에서 검증한다. 기본 Client는 생성형 소형 GGUF와 FTS5만 사용하며 임베딩 모델은 탑재하지 않는다.

**제약:** 짧은 사용자 질문마다 임베딩 GGUF 콜드 로딩으로 지연이 발생할 수 있다. 전체 청크를 SQLite에서 순차 비교하므로 대량 DB의 의미 검색은 성능 검증이 필요하다. 모델 정확도, v0.8.0 호환성, 고객 문서 정답률은 실모델·실문서 검증 필요. [문서](docs/T19_OPTIONAL_SEMANTIC_SEARCH.md).

## T22 — 기본 사용자 패키지 DB 경량화

**개발 브랜치:** `feat/t22-light-client-db-compaction`. 관리자의 지식 DB에 T19 임베딩 벡터가 있더라도 의미 검색을 선택하지 않은 Client를 만들 때만 **분리된 스테이징 DB 사본**에서 `chunk_embeddings`·`embedding_metadata`를 제거하고 SQLite `VACUUM`으로 축소한다. 원본 관리자 DB와 의미 검색을 선택한 Client에는 영향이 없다. 패키지에 포함된 frozen API의 제한적 `--compact-no-embeddings` 작업으로 실행하므로 별도 Python·SQLite 도구 설치가 불필요하다. T12 합성 DB 전체 통합 패키징에서 원본 DB 불변·소형 DB·API 무결성·의미 검색 DB 보존을 함께 확인한다.
