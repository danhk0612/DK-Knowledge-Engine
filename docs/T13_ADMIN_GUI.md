# T13 — 관리자 문서 관리 및 독립 실행 패키지

## 두 프로그램은 물리적으로 분리

- Admin `DK-Knowledge-Admin.exe`는 제작자 전용입니다. 문서 등록·교체·삭제, DB 재생성, API 시험 및 Client 전용 ZIP 제작을 담당합니다.
- Client는 `DK-Knowledge-Client.exe`, 엔진·런타임·GGUF·지식 DB·설정·검증/갱신 스크립트만 포함합니다. 원본 PDF/DOCX/TXT/MD, 관리자 실행 파일, 독립 Builder, Python 및 SDK는 **포함하지 않습니다**.
- 분리된 GUI들은 기존 localhost API와 DB 스키마를 그대로 사용합니다.

## 관리자 문서 조작 (T14 개편)

1. **원본 문서 폴더**에는 원하는 위치의 Windows 폴더를 지정합니다. 폴더 최상위의 `사용설명서.pdf` 또는 임의 하위 폴더의 PDF/DOCX/TXT/MD 모두 목록에 나타납니다. `product_id/manuals` 형태로 옮길 필요는 없습니다.
2. **일반 폴더 문서 제품 ID**는 제품별 폴더 구조가 없는 문서에 적용합니다. 예: `manual-test`. 기존 `<product_id>/manuals/...`와 `<product_id>/rules/...` 구조는 제품별 구분 및 규칙과 함께 그대로 유지합니다.
3. **문서 추가**는 외부에 있는 파일 하나를 **선택한 원본 폴더 최상위**에 복사합니다. 동일 파일명이 있으면 덮어쓰지 않으며 기존 문서를 선택하여 **교체**해야 합니다.
4. **선택 문서 교체/삭제**는 문서가 처음부터 원본 폴더에 있었든 문서 추가로 등록했든 동일하게 작동합니다. 교체는 같은 확장자의 파일만 받으며 `.meta.json`은 유지합니다. 삭제 시 확인을 받고 해당 문서와 연결된 `.meta.json`을 삭제합니다.
5. 파일을 복사하거나 삭제한 사실만으로는 DB가 변경되지 않습니다. **지식 DB 재생성**을 클릭하면 원본 폴더 내의 모든 지원 문서를 다시 색인합니다. 그 후 사용자 패키지를 별도로 제작합니다.

폴더의 실제 경로·파일 이름에는 제품별 디렉터리명, 영문 이름 또는 특정 드라이브 제한이 없습니다. 다만 관리 명령은 선택한 원본 폴더 **안의 문서**에만 적용하며, 상위 폴더 이탈·심볼릭 링크는 허용하지 않습니다. DB 출력은 별도 저장 경로를 사용합니다.

개발 소스에서 직접 실행하는 GUI는 Python 후보(`<repo>/.venv/Scripts/python.exe`, `<repo>/venv/Scripts/python.exe`, PATH의 `python`, Windows `py -3`)를 순서대로 확인합니다. `pypdf`와 `python-docx`가 포함된 인터프리터를 찾으면 실제 실행 파일 경로를 자동 입력하며, 없으면 안내만 표시합니다. 패키지는 자동 설치하지 않습니다. **독립형 Admin ZIP에서는 Python·Git·.NET SDK 입력란 자체가 숨겨지고 내장 Builder를 사용**합니다.

## 독립형 관리자 패키지

Windows x64 관리자용 ZIP 생성 명령(빌드 PC에서만 Python 3.11, PyInstaller, .NET 10 SDK 필요):

```powershell
.\distribution\Build-Admin-Package.ps1 `
  -EnginePackage "D:\Base\DK-Knowledge-Engine-Win-x64" `
  -OutputDir "D:\New-Admin-Output"
```

출력:

```text
DK-Knowledge-Engine-Admin/
├── DK-Knowledge-Admin.exe
├── tools/
│   ├── builder/DK-Knowledge-Builder.exe (+ 내장 Python 의존 DLL)
│   └── Build-Client-Package.ps1
├── client/DK-Knowledge-Client.exe
├── engine-template/   (검증된 T07 엔진/모델/샘플 DB)
└── workspace/
    └── sources/       (관리자 PC의 문서 저장소)
```

독립형 관리자 GUI 실행 시 기본 원본 폴더·DB 경로·엔진 템플릿이 자동 지정되고 개발용 저장소/Python 입력란은 숨겨집니다. Builder는 PyInstaller로 동결한 별도 EXE이며, Client EXE도 이미 자체 포함 빌드되어 있습니다. 따라서 **관리자 패키지를 실행하는 제작자 PC에는 Git, Python, .NET SDK가 필요하지 않습니다.** 최초 ZIP 생성 빌드는 CI/개발 환경에서 수행합니다.

독립형 Admin의 사용자 패키지 제작은 기존 `Build-Client-Package.ps1`에 `-ClientExe`를 제공하여 .NET SDK 없이 GUI를 복사합니다. 기존 개발자 모드(로컬 소스 프로젝트를 `dotnet publish` 하는 동작)는 유지합니다.

Admin 패키지에는 배포 테스트용 엔진 템플릿이 들어갑니다. 실제 문서가 포함된 지식 DB를 관리자 GUI에서 생성한 뒤 Client 전용 ZIP에 사용합니다. 사용자에게 전달되는 ZIP에서 Admin과 Builder가 빠졌는지 검증합니다.

## 검증 및 미완료

- Windows .NET 10 관리자/사용자 WPF 컴파일, 콘솔 문서 CRUD 회귀, 독립 Admin ZIP 생성.
- Admin ZIP을 새 폴더에 압축 해제한 후 Python/.NET SDK가 PATH에 없는 환경에서 동봉 Builder로 MD/TXT/PDF/DOCX 색인, 동봉 Client EXE와 지식 DB를 조합한 사용자 전용 ZIP 생성 및 무결성 검사.
- 샘플 DB·모델을 사용하는 GitHub Actions 검증 결과와 **실제 제작자 PC의 WPF 버튼 클릭 검증**을 구분합니다.
- 시험 ZIP이며 정식 Release, 서명, 자동 업데이트는 아직 없습니다.

## T13 CI 검증 기록 (2026-11-09)

- [Windows 독립형 Admin·Client 빌드 및 통합 검증](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/42547416394): 전체 작업 성공.
- Admin/Client WPF 빌드, C# 문서 추가·교체·삭제·경로 보호 스모크 통과.
- 독립형 Admin ZIP 생성 및 새로운 폴더에 압축 해제; Python/.NET SDK 미포함 PATH에서 동봉 Builder로 PDF·DOCX·TXT·MD 각 1개씩 총 4개 색인(4청크), 사용자 전용 Client ZIP 생성 및 `PACKAGE_VERIFY_OK` 확인.
- T02 Windows/Ubuntu, T07 CPU 포터블, T09 로컬 모델 설정 회귀도 성공.
- 사용한 문서는 합성 테스트 자료이며, 실제 제작자 PC에서 GUI 문서 교체·삭제 버튼 조작 및 원본문서 적용은 아직 직접 확인하지 않았습니다.
