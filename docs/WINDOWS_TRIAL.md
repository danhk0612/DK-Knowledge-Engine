# Windows 시험용 패키지 — Git 수신 및 실기 검증

> **시험용, 정식 Release가 아닙니다.** 이 절차의 ZIP에는 GitHub Actions가 만든 **인공 샘플 매뉴얼 DB**와 Windows x64 CPU 모델(Qwen3 1.7B)이 포함됩니다. 실제 고객 자료나 계정 정보는 포함하지 않습니다. 회사 PC 시험은 담당자의 허가를 받아 진행하십시오.

## 1. Git 저장소와 실행 ZIP은 별도입니다

- Git: 제작자 소스, PowerShell 검증 도구, Windows/C#·웹 연동 예제, 문서만 체크아웃합니다. Git만 내려받아도 GGUF/EXE가 자동 생성되지는 않습니다.
- 실행 ZIP: [Windows trial package and field smoke](../.github/workflows/test-windows-trial.yml)에서 검증된 **`DK-Knowledge-Engine-Win-x64-demo-T07` 아티팩트**입니다. GitHub Actions 보관 기간은 **7일**입니다. 이미 만료됐으면 워크플로를 재실행합니다.
- ZIP 제작 때만 GitHub Actions 빌더가 인터넷에서 고정 GGUF·llama.cpp를 내려받습니다. 시험용 PC에서는 별도의 Python·Docker·GPU나 모델 다운로드가 필요하지 않습니다.

## 2. Windows 개발 PC에서 Git으로 소스 받기

PowerShell에서 다음을 실행합니다. Git과 GitHub CLI(`gh`)가 설치·로그인되어 있어야 하며, 소스 디렉터리에 기존 수정사항이 있다면 `git pull --ff-only` 전에 확인하십시오.

```powershell
git clone https://github.com/danhk0612/DK-Knowledge-Engine.git
Set-Location .\DK-Knowledge-Engine
git switch main
git pull --ff-only
git rev-parse HEAD
gh auth status
```

`git rev-parse HEAD`가 시험에 사용한 소스 버전입니다. **ZIP을 만든 Actions 실행의 커밋 SHA와 같아야만** 같은 소스 버전을 시험한 것입니다.

## 3. 검증된 Windows 시험용 ZIP 받기

[시험용 빌드 Actions 목록](https://github.com/danhk0612/DK-Knowledge-Engine/actions/workflows/test-windows-trial.yml)에서 **성공한 main 실행의 run 번호**를 확인합니다.

```powershell
# 최신 목록을 확인하고 성공한 main run 번호로 아래 값을 직접 바꾸세요.
gh run list -R danhk0612/DK-Knowledge-Engine --workflow test-windows-trial.yml --branch main --limit 10
$runId = 12345678901

# 다른 커밋에서 빌드된 ZIP을 실수로 검사하지 않도록 확인합니다.
$sourceSha = (git rev-parse HEAD).Trim()
$runSha = (gh run view $runId -R danhk0612/DK-Knowledge-Engine --json headSha --jq '.headSha').Trim()
if ($sourceSha -ne $runSha) { throw "Git HEAD와 Actions 빌드 커밋이 다릅니다." }

gh run download $runId -R danhk0612/DK-Knowledge-Engine -n DK-Knowledge-Engine-Win-x64-demo-T07 -D .\trial-artifact
Expand-Archive -LiteralPath .\trial-artifact\DK-Knowledge-Engine-Win-x64.zip -DestinationPath .\trial-extracted
$package = (Resolve-Path -LiteralPath .\trial-extracted\DK-Knowledge-Engine-Win-x64).Path
```

성공 실행이 없거나 아티팩트가 만료됐다면 `gh workflow run test-windows-trial.yml --ref main -R danhk0612/DK-Knowledge-Engine`으로 직접 새 실행을 요청할 수 있습니다. 목록을 다시 조회하여 새 run 번호를 사용합니다. 실행 페이지에는 **ZIP SHA-256**도 기록되므로 로컬의 `(Get-FileHash .\trial-artifact\DK-Knowledge-Engine-Win-x64.zip -Algorithm SHA256).Hash`와 비교할 수 있습니다. **기존 `trial-artifact`·`trial-extracted` 경로가 있으면 새 경로를 선택**하고, 남의 시험 결과 위에 덮어쓰지 마십시오.

## 4. 로컬 Windows 기능 검사 (자동 구동·종료)

엔진을 수동 실행하기 **전에**, 프로젝트 루트에서 PowerShell 5.1로 다음을 실행합니다. 자체적으로 시험용 API를 시작·종료하며, 포트 8765에 다른 서버가 이미 있으면 실패하도록 설계되어 있습니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$package\Verify-AIHelp.ps1" -Root $package
if ($LASTEXITCODE -ne 0) { throw "포터블 ZIP 무결성 검증 실패" }

$report = Join-Path (Get-Location) ("trial-report-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tests\t08_field_check.ps1 -PackageRoot $package -CasesPath .\tests\t08_field_cases_sample.json -OutputDir $report -RunsPerChat 2
if ($LASTEXITCODE -ne 0) { throw "Windows 현장 기능 검증 실패" }
Get-Content -LiteralPath (Join-Path $report 'field-validation.json') -Raw -Encoding UTF8
```

**예상 결과:** `PACKAGE_VERIFY_OK`, `T08_FIELD_CHECK_OK passed=7 of 7`. 검색, 승인된 오류 이벤트, 실제 CPU LLM 답변 2회, 제품·버전 격리, 근거 없는 질문을 확인합니다. 실패는 그대로 기록하고 검증 기준을 임의로 낮추지 마십시오.

`field-validation.json`에는 출처 상대 경로와 PC 환경 정보가 포함될 수 있습니다. **실제 고객 DB로 시험했다면 결과를 공개 GitHub에 업로드하지 마십시오.**

## 5. 수동 API 확인

위 자동 시험이 종료된 뒤, **첫 번째 PowerShell 창에서** 아래를 실행해 엔진을 켭니다.

```powershell
& (Join-Path $package 'Start-AIHelp.cmd')
```

**두 번째 PowerShell 창에서** 접속을 확인합니다.

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8765/health -Method Get

$payload = @{ product_id = 'example-program'; version = '2.1.0'; query = '연결 오류' } | ConvertTo-Json -Compress
Invoke-RestMethod -Uri http://127.0.0.1:8765/search -Method Post -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($payload))
```

`/health`의 `status`는 `ready`, `/search`의 결과에는 샘플 매뉴얼 출처가 보여야 합니다. 엔진 종료는 첫 번째 창에서 **Ctrl+C**를 사용합니다. `config/settings.json`의 `allowed_origins`는 기본 빈 배열이므로 임의의 사내 도메인에 CORS를 개방하지 않습니다.

## 6. 네트워크 차단 PC와 고객 자료 시험

ZIP을 별도 PC로 복사한 다음 위의 **무결성 검사·실행**을 반복할 수 있습니다. 물리적으로 Wi-Fi·유선 연결이 차단됐는지 운영자가 직접 기록해야 하며, Windows Defender·SmartScreen·사내 보안 정책을 우회하지 않습니다.

사내 HTTPS 브라우저→localhost 접근 권한은 [T06 LNA 현장 검증 지침](T06_LNA_FIELD_VALIDATION.md), 고객 매뉴얼 정답·출처는 [T10 검증 지침](T10_VALIDATION.md)에 따라 **승인받은 시험 PC의 비공개 자료로** 별도 평가합니다. 시험 ZIP은 인공 데이터만 포함하므로 실제 제품 설명서의 정확성·법적 재배포 적합성을 입증하지 않습니다.

**주의:** ZIP의 `manifest.json`은 아직 전자서명이 없습니다. 샘플용 GitHub Actions 아티팩트를 정식 고객용 설치 프로그램이나 서명된 Release로 배포하지 마십시오.
