# 첫 사전 배포판 제작 절차

현재 검수 대상 버전: `v0.1.0-preview.4` (기존 `preview.1`·`preview.2`·`preview.3`는 각각 미공개 Draft로 유지). Windows x64, **사전 배포 / unsigned**.

## 1. 배포 전 필수 확인

1. `main`의 T12 Windows GUI 통합 워크플로가 **성공**했는지 확인합니다. 관리자/사용자 통합 ZIP 두 파일이 같은 실행 결과에 존재해야 합니다. 빌드 ZIP의 DB는 인공 샘플만 사용합니다.
2. 관리자의 문서 폴더 추가/교체/삭제 및 Client 검색/출처 검증 결과를 확인합니다. CI 성공이 실제 Windows 모든 환경의 동작을 보장하지 않습니다.
3. 바이너리 서명 부재/SmartScreen, 모델 라이선스, PyInstaller 번들에 포함된 라이브러리/하위 의존성의 고지 의무를 확인합니다. 관리자 ZIP의 `licenses/builder/`에 pypdf, python-docx, lxml, typing_extensions 원문이 실제 포함됐는지 확인합니다. `THIRD_PARTY_NOTICES.md`는 확인 목록이지 완전한 법적 검토를 의미하지 않습니다.
4. Release에 비공개 원본문서, 고객 이름, 계정 정보, 내부 DB가 섞이지 않았는지 확인합니다. Client ZIP의 지식 DB는 인공 샘플이며 고객용 정식 DB가 아닙니다.

## 2. GitHub Actions에서 초안 Release 만들기

배포를 준비한 `main`에서 T12 CI가 성공하면 해당 Run ID를 확인합니다.

```powershell
$repo = "danhk0612/DK-Knowledge-Engine"
gh run list -R $repo --workflow t12-windows-guis.yml --branch main --limit 10
# 성공한 Run ID로 변경
$runId = "12345678901"
gh workflow run release-draft.yml -R $repo --ref main -f source_run_id=$runId -f version=v0.1.0-preview.4
```

`release-draft.yml`은 선택한 실행이 **성공했고 main의 현재 커밋과 SHA가 일치**하는지 확인한 뒤, Admin·Client ZIP을 수령하고 `SHA256SUMS.txt`를 생성하여 **비공개 Draft Pre-release**를 작성합니다. 기존 릴리스가 있다면 덮어쓰지 않습니다. **Draft 생성 자체가 공개 배포는 아닙니다.**

결과 확인:
```powershell
gh release view v0.1.0-preview.4 -R danhk0612/DK-Knowledge-Engine
```

## 3. 공개 전 검수와 게시

Draft의 ZIP 두 개, SHA256SUMS, README, 라이선스/고지 내용을 검수합니다. 특히 관리자 ZIP에는 원본 고객 자료를 포함하지 않아야 하며, 사용자 ZIP은 테스트용 DB로만 배포됩니다.

공개를 승인했으면 GitHub Release 페이지에서 **Publish release**를 사용하거나 다음 명령으로 공개합니다.

```powershell
gh release edit v0.1.0-preview.4 -R danhk0612/DK-Knowledge-Engine --draft=false --prerelease
```

게시 전에는 버전과 서명 정책을 다시 검토합니다. **Stable/latest 릴리스로 표현하지 않습니다.**

## 4. 후속 배포

- 수정 릴리스는 새 태그(예: `v0.1.0-preview.5`)로 생성합니다. 기존 태그와 배포 ZIP을 덮어쓰지 않습니다.
- 실제 고객에게 전달할 Client는 관리자 GUI에서 **고객별 지식 DB로 새 ZIP을 생성**합니다.
- SHA256SUMS는 공개 Release의 파일과 대조합니다. 신뢰할 수 없는 위치에서 다운로드한 파일을 실행하지 마세요.
