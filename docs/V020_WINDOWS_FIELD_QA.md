# v0.2.0 Windows 현장 검증 — Admin · Client

> **시험용 ZIP 기준**입니다. 실제 고객 문서가 아니라 GitHub Actions가 포함한 예제 지식 DB를 대상으로 검사합니다. 자동 CI 검증과 달리 Windows 알림 영역·사용자 입력·화면 표시를 실제 PC에서 확인하는 절차입니다. 모든 검사를 마치기 전에는 정식 배포로 판단하지 않습니다.

## 1. 동일 커밋의 시험용 ZIP 준비

1. [T12 Windows GUIs 실행 기록](https://github.com/danhk0612/DK-Knowledge-Engine/actions/workflows/t12-windows-guis.yml)에서 **PR #41 브랜치 `feature/v020-batched-admin-client`의 가장 최근 성공 실행**을 선택합니다. `head SHA`를 기록합니다.
2. 실행의 **Artifacts**에서 `DK-Knowledge-Engine-Admin-Win-x64-T13` 및 `DK-Knowledge-Engine-Client-Win-x64-T12`를 다운로드합니다. GitHub Actions 아티팩트 보관 기간은 7일이며, 다운로드 파일 안에 실제 프로그램 ZIP이 들어 있습니다.
3. 두 프로그램 ZIP을 **서로 다른 빈 폴더**에 풀어주세요. Admin과 Client를 같은 폴더에 합치지 않습니다. EXE 단독 복사도 하지 않습니다. Client는 `.NET 자체 포함 DLL`, `*.deps.json`, `*.runtimeconfig.json`이 EXE와 같은 폴더에 있어야 실행됩니다.
4. 실제 회사/고객 자료나 외부 네트워크를 사용하지 않는 테스트부터 진행합니다. 기존에 실행 중인 `DK-Knowledge-API.exe`가 있으면 상태를 기록하고 포트가 충돌하지 않도록 합니다.

GitHub CLI를 쓰는 경우:

```powershell
$repo = "danhk0612/DK-Knowledge-Engine"
$runId = 0  # 위 T12 성공 실행에서 확인한 run ID로 교체
if ($runId -eq 0) { throw "T12 성공 실행 번호를 입력하세요." }
gh run view $runId -R $repo --json status,conclusion,headSha --jq '{status,conclusion,headSha}'
gh run download $runId -R $repo -n DK-Knowledge-Engine-Admin-Win-x64-T13 -D .\admin-artifact
gh run download $runId -R $repo -n DK-Knowledge-Engine-Client-Win-x64-T12 -D .\client-artifact
```

## 2. Client 실행 전 필수 검사

Client 폴더의 `DK-Knowledge-Client.exe`와 `coreclr.dll`, `hostfxr.dll`, `PresentationFramework.dll`, `DK-Knowledge-Client.deps.json`, `DK-Knowledge-Client.runtimeconfig.json`이 존재해야 합니다.

```powershell
$client = "D:\Tests\DK-Knowledge-Engine-Client"  # 실제 압축 해제 위치
powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $client "Verify-AIHelp.ps1") -Root $client
if ($LASTEXITCODE -ne 0) { throw "Client 패키지 무결성 검사 실패" }
Get-Content (Join-Path $client "package-info.json") -Raw | ConvertFrom-Json |
  Select-Object product_id,product_name,product_version,app_name,icon_file
```

예상 결과: `PACKAGE_VERIFY_OK`. 인공 샘플 제품 ID는 `example-program`, 버전은 `2.0.0`입니다. 최신 T12 시험용 Client는 사용자 지정 앱 이름 `Example Help Client`와 사용자 지정 아이콘을 테스트하도록 생성합니다. 앱 이름과 아이콘은 사용자 제품마다 변경할 수 있습니다.

## Windows CI에서 이미 자동 확인하는 화면 동작

`tests/v020_client_gui_smoke.ps1`은 다중 파일 Client EXE를 실제로 시작하고 Windows UI Automation을 사용해 **프로그램명 표시 → 설정 탭 포트 변경·저장 → API 도구 URL 갱신 → X 버튼 창 숨김과 프로세스 유지**를 시험합니다. GitHub Actions의 T12 `gui-build` 작업에서 실행합니다.

`tests/v020_client_engine_gui_smoke.ps1`은 **최종 Client ZIP 조립 이후** T12 `client-package` 작업에서 실행합니다. 실제 WPF 버튼으로 로컬 엔진을 시작하고, 현재 제품의 DB 사본으로 **DB 업데이트 → 엔진 PID 변경과 재기동 → DB 롤백 → PID 재변경과 재기동 → 엔진 중지**를 확인합니다. 이전 DB의 SHA-256과 복구 결과도 비교합니다. 이 시험은 인공 데이터가 들어 있는 동일 제품 DB 사본을 사용하므로, **서로 다른 버전의 실제 고객 문서 내용이 바뀌는 경우**까지 검증하지는 않습니다.

두 검증 모두 GitHub Actions의 Windows CI에서만 수행한 것이며, 아래 항목의 **사용자 PC 실기 확인을 대체하지 않습니다.** 특히 트레이 아이콘 표시·우클릭 메뉴, 실제 고객 문서의 변경 내용 확인, 사내 보안 정책은 사용자 환경에서 별도로 검사해야 합니다.

## 3. Client 화면·엔진·트레이 수동 확인

| 순서 | 동작 | 합격 기준 |
|---|---|---|
| 1 | Client EXE 더블클릭 | 바로 종료되지 않고, 질문 화면이 표시됨. 제품명·버전·프로그램명 일치 |
| 2 | 설정 → 엔진 시작 → 상태 확인 | `127.0.0.1:8765`의 `/health` 응답, 엔진 상태가 준비로 표시됨 |
| 3 | AI 질문 → 예제 매뉴얼의 설치/설정 질문 입력 | 실제 CPU 모델로 답변을 받고, 검색 근거가 있다면 출처 표시 |
| 4 | 문서 검색 → 예제 문서 키워드 | 샘플 문서와 출처가 표시됨 |
| 5 | API 도구 → `GET /health`, `POST /search`, `POST /chat`, `POST /event` 각각 실행 | 요청 편집·전송이 가능하고 HTTP 상태 코드·응답 JSON이 표시됨. `/event` 결과는 입력한 샘플 이벤트에 따라 달라질 수 있음 |
| 6 | 창 우상단 X 클릭 | 프로세스가 종료되지 않고 창만 숨겨짐. 알림 영역에 선택한 아이콘 표시 |
| 7 | 트레이 아이콘 더블클릭 / 우클릭 메뉴 | 창 다시 열기, 질문·엔진 시작/중지·DB 관리·설정 이동 가능 |
| 8 | 트레이 우클릭 → 종료 | 프로그램과 **자신이 시작한** 엔진만 종료됨. 별도 실행 중인 다른 제품의 엔진은 강제로 종료하지 않음 |

**주의:** 엔진/트레이 메뉴 작업은 다른 애플리케이션이 사용 중인 포트를 차지했을 때 성공으로 간주하지 않습니다. Windows SmartScreen이나 보안 정책을 무시하고 우회하지 않습니다.

## 4. Client API 포트 변경 실기

1. 설정에서 이 Client가 시작한 엔진을 **중지**합니다.
2. 충돌하지 않는 테스트 포트(예: `18765`)를 입력하고 **포트 저장**을 누릅니다.
3. `config/settings.json`의 `port`가 `18765`인지 확인합니다. 제품 ID와 버전은 변경되지 않아야 합니다.
4. 엔진을 다시 시작한 뒤 `http://127.0.0.1:18765/health`에 정상 연결되는지 확인합니다. API 도구에 표시되는 URL도 새 포트여야 합니다.
5. 테스트 종료 시 엔진을 중지하고 기존 `8765`로 돌립니다. Windows 방화벽에서 외부 접근을 허용할 필요가 없습니다.

## 5. Client 지식 DB 업데이트·롤백 실기

1. Client 엔진이 실행 중이면 **지식 DB 관리** 탭에서 작업합니다. 새 `knowledge.db`는 **같은 제품 ID**로 만든 검증된 DB만 사용합니다. 다른 제품 ID나 여러 제품이 섞인 DB는 거부되어야 합니다.
2. 예제 DB의 별도 복사본으로도 버튼 처리 및 백업 생성은 시험할 수 있습니다. 실제 내용 변경까지 검사하려면 Admin에서 동일 제품 ID로 문서를 하나 추가하고 DB를 다시 생성합니다.
3. **DB 업데이트** 후 `knowledge/knowledge.previous.db` 백업이 생성되고 `Verify-AIHelp.ps1` 검증에 합격하는지 확인합니다.
4. 엔진이 Client 소유였다면 업데이트 후 자동 재시작하는지 확인합니다.
5. **이전 DB 복구**를 누른 후 초기 문서 검색 결과로 돌아오는지 확인합니다. 실행 중인 타 제품 엔진을 종료하거나 변경해서는 안 됩니다.
6. 실패·중단 이후 `knowledge.pending.json`이 남았다면 `Update-Knowledge.ps1 -Recover` 안내에 따라 처리하며, 직접 DB 파일을 덮어쓰지 않습니다.

## 6. 독립형 Admin 제작 검증

1. Admin EXE를 열고 제품 정보 입력·저장, 기본 경로·폴더 열기, 문서 추가·교체·삭제를 확인합니다.
2. PDF·DOCX·TXT·MD 샘플로 지식 DB를 재생성하고 품질 보고서를 확인합니다.
3. **프로그램명**과 **PNG/ICO 아이콘**을 지정하여 사용자 ZIP을 생성합니다. Client EXE 아이콘·창/트레이 아이콘·제품 정보가 일치해야 합니다.
4. Client ZIP에 다른 제품 문서·규칙·벡터, 원본 PDF/DOCX, Admin EXE 및 Builder가 포함되지 않는지 확인합니다.
5. 제작 PC에 Git·Python·.NET SDK가 없어도 ZIP 생성이 가능한지 확인합니다(실제 PC에는 Windows PowerShell 5.1과 운영체제 필수 요소가 필요).
6. 일반 검색·선택한 GGUF·선택형 의미 검색을 각각 **설정한 경우에만** 테스트합니다. 임베딩 옵션은 DB 제작에 사용한 인코더와 동일한 GGUF를 지정해야 합니다.

## 완료 기준

**CI 통과와 현장 검증은 별도**입니다. 위 실기 점검 결과를 날짜, Windows 버전, 프로그램 ZIP의 Git SHA, 통과/실패 항목, 예외 로그와 함께 기록합니다. 개인/회사 문서 및 시스템 로그의 민감한 값은 공개 저장소에 올리지 않습니다. 확인되지 않은 항목은 통과로 표시하지 않습니다. 모든 주요 항목 합격 전에는 PR #41 Draft를 유지하고 정식 Release를 만들지 않습니다.
