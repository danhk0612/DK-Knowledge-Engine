[CmdletBinding()]
param(
    [long]$RunId = 42964843944,
    [string]$OutputDir = '.\DK-Knowledge-Engine-v020-FieldQA'
)
$ErrorActionPreference = 'Stop'
$repository = 'danhk0612/DK-Knowledge-Engine'

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw 'GitHub CLI (gh)가 필요합니다. gh 설치 및 로그인을 확인하세요.'
}
$destination = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $destination) {
    throw "이미 존재하는 폴더는 덮어쓰지 않습니다: $destination"
}
$runJson = & gh run view $RunId -R $repository --json headSha,conclusion,status
if ($LASTEXITCODE -ne 0) { throw 'GitHub Actions 실행 정보 조회 실패' }
$run = ($runJson | Out-String | ConvertFrom-Json)
if ($run.status -ne 'completed' -or $run.conclusion -ne 'success') {
    throw "성공한 T12 실행만 다운로드할 수 있습니다. run=$RunId status=$($run.status) conclusion=$($run.conclusion)"
}
$artifacts = Join-Path $destination 'downloads'
$adminDownload = Join-Path $artifacts 'admin'
$clientDownload = Join-Path $artifacts 'client'
New-Item -ItemType Directory -Path $adminDownload,$clientDownload -Force | Out-Null
& gh run download $RunId -R $repository -n 'DK-Knowledge-Engine-Admin-Win-x64-T13' -D $adminDownload
if ($LASTEXITCODE -ne 0) { throw 'Admin 아티팩트 다운로드 실패' }
& gh run download $RunId -R $repository -n 'DK-Knowledge-Engine-Client-Win-x64-T12' -D $clientDownload
if ($LASTEXITCODE -ne 0) { throw 'Client 아티팩트 다운로드 실패' }

$adminZip = Join-Path $adminDownload 'DK-Knowledge-Engine-Admin-Win-x64.zip'
$clientZip = Join-Path $clientDownload 'DK-Knowledge-Engine-Client-Win-x64.zip'
foreach ($file in @($adminZip,$clientZip)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "예상 ZIP이 없습니다: $file"
    }
}
$adminFolder = Join-Path $destination 'Admin'
$clientFolder = Join-Path $destination 'Client'
Expand-Archive -LiteralPath $adminZip -DestinationPath $adminFolder
Expand-Archive -LiteralPath $clientZip -DestinationPath $clientFolder
$admin = Join-Path $adminFolder 'DK-Knowledge-Engine-Admin'
$client = Join-Path $clientFolder 'DK-Knowledge-Engine-Client'
foreach ($file in @(
    (Join-Path $admin 'DK-Knowledge-Admin.exe'),
    (Join-Path $admin 'engine-template\Verify-AIHelp.ps1'),
    (Join-Path $client 'DK-Knowledge-Client.exe'),
    (Join-Path $client 'Verify-AIHelp.ps1'),
    (Join-Path $client 'coreclr.dll'),
    (Join-Path $client 'DK-Knowledge-Client.runtimeconfig.json')
)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "압축 해제된 필수 파일이 없습니다: $file"
    }
}
& powershell.exe -NoProfile -File (Join-Path $admin 'engine-template\Verify-AIHelp.ps1') -Root (Join-Path $admin 'engine-template')
if ($LASTEXITCODE -ne 0) { throw 'Admin에 포함된 엔진 무결성 검증 실패' }
& powershell.exe -NoProfile -File (Join-Path $client 'Verify-AIHelp.ps1') -Root $client
if ($LASTEXITCODE -ne 0) { throw 'Client 패키지 무결성 검증 실패' }

$info = Get-Content -LiteralPath (Join-Path $client 'package-info.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($info.product_id -ne 'example-program' -or
    $info.product_version -ne '2.0.0' -or
    $info.app_name -ne 'Example Help Client') {
    throw '예제 Client의 제품 ID·버전·앱 이름이 예상과 다릅니다.'
}
$os = Get-CimInstance Win32_OperatingSystem
$report = @"
# DK-Knowledge-Engine v0.2.0 Windows 테스트 결과

- 날짜: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
- Windows: $($os.Caption) / $($os.Version)
- T12 run ID: $RunId
- Git commit: $($run.headSha)
- Admin: $admin
- Client: $client
- 테스트 전 패키지 무결성: Admin 엔진·Client 모두 통과
- 예제 Client: $($info.product_id) / $($info.product_version) / $($info.app_name)

## 직접 확인할 항목 (통과한 뒤 [x]로 변경)

- [ ] Admin EXE 실행, 제품·문서·DB 화면 정상 표시
- [ ] Admin에서 샘플 PDF/DOCX/TXT/MD 추가·지식 DB 재생성
- [ ] Admin에서 Client 프로그램명·아이콘 지정 후 ZIP 제작
- [ ] Client EXE 실행, 아이콘·프로그램명·제품명 확인
- [ ] Client 엔진 시작, AI 질문·문서 검색과 출처 확인
- [ ] Client API 도구 4종 요청·응답 확인
- [ ] Client X 클릭 시 트레이로 숨김 및 아이콘 표시
- [ ] 트레이 더블클릭 창 복구
- [ ] 트레이 우클릭 메뉴: 질문·엔진 시작/중지·DB 관리·설정 이동
- [ ] 트레이 메뉴 종료 후 본인 Client와 본인 엔진만 종료
- [ ] 실제 문서의 답변 정확성·출처·근거 부족 응답 확인
- [ ] 조직 정책·보안 경고 검토 (정책 우회 없이)

## 오류·특이사항

- 증상:
- 재현 순서:
- 관련 파일/메시지(민감정보 제거):
- 판정: 미완료
"@
$reportPath = Join-Path $destination 'FIELD_QA_RESULT.md'
[IO.File]::WriteAllText($reportPath,$report,(New-Object System.Text.UTF8Encoding($false)))
Write-Output "FIELD_QA_PREPARE_OK commit=$($run.headSha)"
Write-Output "Admin EXE: $(Join-Path $admin 'DK-Knowledge-Admin.exe')"
Write-Output "Client EXE: $(Join-Path $client 'DK-Knowledge-Client.exe')"
Write-Output "Test report: $reportPath"
