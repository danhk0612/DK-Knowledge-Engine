# 2026-11-12 작업 종료 / 다음 작업 인수인계

> 이 문서는 **진행 상태 및 재시작 절차만** 기록합니다. 고객 매뉴얼 원본, 실행 파일 또는 새 기능을 추가하지 않습니다.

## 확정된 원칙

**범용 제작 → 범용 모델 선택 → 범용 사용**이 기본 구조입니다. 특정 고객 매뉴얼, 제품명, GGUF 모델을 위한 하드코딩을 피하고, 관리자 DB 제작용 모델/사용자 실행 모델/선택적 임베딩 모델은 분리 가능해야 합니다.

## 기준 브랜치 및 테스트

- Repo: `danhk0612/DK-Knowledge-Engine`
- 검증 브랜치: `fix/grounded-retrieval-20261112`
- Draft PR: https://github.com/danhk0612/DK-Knowledge-Engine/pull/42
- 현재 검증 HEAD: `3643569ee55962ef74076d53ef43c987743d9d99`
- `main`은 본 PR을 아직 병합하지 않았음.
- HEAD에 대한 GitHub Actions 결과: **T02 / T04 / T09 / T12 / T21 모두 성공**
  - T02: Windows/Ubuntu 각각 121개 단위 테스트
  - T04: 실제 CPU Qwen3 GGUF 추론
  - T09: 기본/선택 모델과 런타임·raw_chatml·실패 시나리오의 Windows 포터블 검사
  - T12: Admin/Client 독립 ZIP·Windows 패키징·경량 DB 복사·선택적 임베딩 분리
  - T21: Windows 한국어 임베딩 GGUF
- T12 Actions: https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/43173235002
- T12 검증용 아티팩트: `DK-Knowledge-Engine-Admin-Win-x64-T13`, `DK-Knowledge-Engine-Client-Win-x64-T12`. GitHub 자동 보관 만료일 **2026-11-19**. 이 아티팩트는 **Release가 아님**.

## 이번 작업에서 해결 및 검증된 범위

1. 질문 불필요 단어와 한국어 동사 어미 정규화, 본문 중심의 검색 순위.
2. 문서의 다른 페이지에 나뉜 **비교 질문의 양쪽 근거** 우선 검색.
3. 권한표 O/X의 단순 행-열 긍정/부정 반전 검출, 근거 없는 숫자·출처 번호 거절.
4. Qwen3가 올바른 답에 거절 문장을 덧붙이던 문제: 완료 문구를 직접 인용하지 않는 자연어 프롬프트로 수정 후 실제 CPU/Windows 포터블 재검증 성공.
5. 실제 매뉴얼의 `재 기동`과 질문의 `재기동해야` 간 띄어쓰기 차이를 범용 인접 단어 검색으로 보완. 다른 제품과 무관한 부분 문자열은 제외.
6. 고객 PDF를 올리지 않은 합성 PDF/매뉴얼의 추출→검색→답변 검증 회귀 테스트 추가.

**미완료:** 실제 고객 PDF 전체를 현재 빌더로 DB 생성한 다음, 동일 Client/모델에서 질문별 검색 근거·답변을 검증한 **수용 테스트**. 원본 PDF의 실행 가능한 바이트를 이 작업 환경에 가져오지 못했으므로 성공으로 기록하지 않습니다.

## 다음 번에 사용자 PC에서 할 일 (재부팅 후 새 PowerShell 창)

필요한 프로그램: 기존에 사용하던 `gh`(GitHub CLI), GitHub 인증, 충분한 다운로드/압축 해제 공간. 개발 빌드나 Docker 설치는 불필요합니다. **새 테스트 전용 폴더**를 사용하고 운영 중인 기존 Admin/Client 폴더는 덮어쓰지 않습니다.

```powershell
$repo = 'danhk0612/DK-Knowledge-Engine'
$runId = 43173235002
$expectedSha = '3643569ee55962ef74076d53ef43c987743d9d99'
$qaRoot = Join-Path $env:USERPROFILE 'Downloads\DK-KE-QA-20261112'

gh auth status
$actualSha = (gh run view $runId -R $repo --json headSha --jq '.headSha').Trim()
if ($actualSha -ne $expectedSha) { throw '시험 아티팩트의 커밋 SHA가 다릅니다.' }

New-Item -ItemType Directory -Path (Join-Path $qaRoot 'admin-artifact') -Force | Out-Null
gh run download $runId -R $repo -n 'DK-Knowledge-Engine-Admin-Win-x64-T13' -D (Join-Path $qaRoot 'admin-artifact')
if ($LASTEXITCODE -ne 0) { throw 'Admin 시험용 아티팩트 다운로드 실패 또는 만료' }

$zip = Join-Path $qaRoot 'admin-artifact\DK-Knowledge-Engine-Admin-Win-x64.zip'
Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $qaRoot 'admin-extracted')
$admin = Join-Path $qaRoot 'admin-extracted\DK-Knowledge-Engine-Admin\DK-Knowledge-Admin.exe'
if (-not (Test-Path -LiteralPath $admin)) { throw '압축 해제한 Admin 실행 파일을 찾지 못했습니다.' }
Start-Process -FilePath $admin
```

**명령은 재부팅 후 한 번에 실행하는 것을 가정**합니다. 같은 `admin-extracted`에 재압축 해제하지 마세요. 아티팩트가 만료되면 새 실행을 요청하고, **새 성공 run ID와 headSha**를 다시 확인해야 합니다:

```powershell
$repo = 'danhk0612/DK-Knowledge-Engine'
gh workflow run t12-windows-guis.yml -R $repo --ref fix/grounded-retrieval-20261112
gh run list -R $repo --workflow t12-windows-guis.yml --branch fix/grounded-retrieval-20261112 --limit 5
```

시험용 Admin의 **문서 · 지식 DB** 화면에서 원본 PDF를 **문서 추가**로 비공개 로컬에 등록하고, 가능하면 PDF 레이아웃 보존 추출을 켠 뒤 DB를 생성합니다. 사용자를 위한 시험용 Client ZIP을 만들어 로컬로 실행합니다. 프로그램은 원본 PDF를 Client에 넣지 않습니다.

## 실제 PDF 수용 테스트 항목 (담당자가 원문으로 판단)

| 질문 예시 | 기대 근거/판정 | 확인 내용 |
| --- | --- | --- |
| 회로시험과 시뮬레이션의 차이는? | 매뉴얼 PDF 39~40쪽 | 실제 수신기 출력 여부 차이. 양쪽 페이지 모두 검색되는지 |
| 시뮬레이션에서 연동 심볼 목록을 클릭하면? | 40쪽 | 클릭한 심볼의 연동 심볼로 이동 |
| 기록 조회 보고서를 어떤 형식으로 받나? | 51쪽 | XLS/PDF |
| 일반사용자가 회로시험을 실행할 수 있나? | 56쪽 | **불가(X)**. 행과 열을 교차 검증 |
| 프로그램을 재기동해야 하는 상황은? | 67쪽 | 구역명/키 상태/수신기 동기화/글자 입력 관련 상황 |
| 최소 GPU VRAM 용량은? | 이 매뉴얼 범위에 근거 없음 | 다른 사양을 추측하지 않고 근거 부족 표시 |

각 질문마다 **검색 원문·출처 페이지 → 모델 답변 → 정오 판정**을 따로 확인합니다. `grounded=true`만으로 정답 처리하지 않습니다. DB 제작 직후 `knowledge.quality.json`의 PDF 추출량 및 경고도 확인합니다. 고객 PDF·DB·질문 원문·평가 로그를 공개 GitHub 또는 일반 CI에 업로드하지 않습니다.

## 다음 개발 시작 시

1. PR #42와 HEAD 및 5개 Actions 검증 상태를 다시 확인.
2. 실제 PDF 수용 테스트에서 발견한 원문 추출 / 검색 / 답변 단계별 실패만 수정하고 해당 단계의 회귀 테스트 추가.
3. 동일 사용자 모델뿐 아니라 다른 선택 GGUF에서 범용 동작이 유지되는지 필요 범위만 검증.
4. **사용자 수용 검증·승인 전** `main` 병합 및 새 Preview Release 제작 금지.

오늘 종료 시점에는 **사용자가 지금 당장 해야 할 작업은 없습니다.** 다음 작업 때 위 명령을 실행하거나 동일한 PDF를 시험용 Admin GUI에 등록해 결과를 전달하면 됩니다.
