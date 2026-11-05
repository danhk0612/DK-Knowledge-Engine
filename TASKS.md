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
| [#13 HTTPS 웹→localhost LNA](https://github.com/danhk0612/DK-Knowledge-Engine/pull/13) | [Windows/Ubuntu Chromium, Windows C# 3/3](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41975739790), [T02 회귀 2/2](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41975739783) | 실제 사내 HTTPS·Chrome/Edge LNA 권한 및 기업 정책 |
| [#14 Windows PowerShell 5.1 판정](https://github.com/danhk0612/DK-Knowledge-Engine/pull/14) | [T07 빌드·T08 기능 7/7](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41980402764), [T02 회귀 2/2](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41980402564) | 실사용 Windows PC·실제 고객 질문 |
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
