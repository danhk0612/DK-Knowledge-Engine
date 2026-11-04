# T07 — Windows x64 오프라인 포터블 배포

## 범위와 현재 구현

- 초기 배포 방식은 별도 설치 관리자 없는 **Windows x64 ZIP**입니다.
- 제작자 PC에서 Python 3.11, PyInstaller, CMake/MSVC와 인터넷을 이용해 **한 번 패키지를 제작**합니다.
- 사용자 PC는 ZIP 압축 해제 후 `Start-AIHelp.cmd`를 실행하며 **Python, Docker, 인터넷, GPU가 필요하지 않도록 설계**했습니다.
- LLM 조합은 T04에서 검증한 **Qwen3 1.7B Q4_K_M GGUF + llama.cpp v0.8.0 CPU**로 고정합니다.
- 검색 DB는 T02/T03의 `schema_version=1` SQLite 파일을 사용합니다.
- 이번 T07은 **기존 T05 API의 포터블 배포**만 담당하며, 웹·WPF 프로그램 수정이나 추가 API를 구현하지 않습니다.

## 배포 폴더

```text
DK-Knowledge-Engine-Win-x64/
├─ Start-AIHelp.cmd
├─ Verify-AIHelp.ps1
├─ Update-Knowledge.ps1
├─ manifest.json
├─ config/
│  └─ settings.json
├─ engine/
│  ├─ DK-Knowledge-API.exe
│  └─ _internal/              (PyInstaller 포함 런타임)
├─ runtime/
│  ├─ llama-completion.exe
│  └─ *.dll                   (Windows CPU 실행 의존성)
├─ models/
│  └─ Qwen3-1.7B-Q4_K_M.gguf
├─ knowledge/
│  ├─ knowledge.db
│  └─ knowledge.sha256
└─ licenses/
   ├─ llama.cpp-LICENSE
   ├─ Qwen3-Apache-2.0-LICENSE
   ├─ CPython-LICENSE
   └─ PyInstaller-COPYING.txt
```

### 사용자 PC에서 시작·검사

1. ZIP을 임의의 폴더에 압축 해제합니다. 같은 PC에서 웹·Windows 앱과 함께 실행할 수 있습니다.
2. PowerShell에서 파일 무결성을 검사합니다: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Verify-AIHelp.ps1`.
3. `Start-AIHelp.cmd`를 실행합니다. 기존 T05와 동일한 `127.0.0.1:8765` HTTP API가 시작됩니다.
4. 종료할 때는 해당 콘솔에서 Ctrl+C를 사용합니다. Windows 서비스 자동 등록은 하지 않습니다.

`config/settings.json`의 `port` 또는 `allowed_origins`를 변경할 수 있습니다. 이 설정은 수정 가능한 파일이므로 배포 바이너리의 고정 해시 검증 범위에서 제외됩니다. 웹 연동 시에는 신뢰하는 사이트의 정확한 Origin만 허용하세요. **같은 PC의 임의 로컬 프로세스까지 인증하는 기능은 없습니다.**

## 제작자 PC에서 빌드

패키징 입력은 T02 Builder로 생성한 DB, 공식 GGUF 모델 파일, Windows에서 빌드된 `llama-completion.exe` 및 의존 DLL, 필수 라이선스 사본입니다.

기본 빌드 도구:

```powershell
python -m pip install -r requirements-builder.txt
python -m pip install pyinstaller==6.22.3
```

프로젝트 루트에서 `distribution/Build-Portable.ps1`을 실행하며 `-KnowledgeDb`, `-LlamaBinDir`, `-ModelFile`, `-LlamaLicense`, `-ModelLicense`, `-PythonLicense`, `-PyInstallerLicense`, `-OutputDir`를 지정합니다.

- 모델 SHA-256은 `d2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5`여야 하며 다르면 패키징을 중단합니다.
- 실행 엔진은 PyInstaller의 **onedir** 방식으로 만들며, 사용자 PC에 개발용 의존성은 전달하지 않습니다.
- llama.cpp 런타임은 CPU 전용 빌드가 기준입니다. Windows CPU의 명령어 집합 호환성은 실제 배포 PC에서 검증해야 합니다.
- `manifest.json`은 엔진·DLL·모델·라이선스·실행 스크립트의 파일별 SHA-256과 런타임 출처 커밋을 기록합니다.
- 원본 고객 문서나 사내 DB·계정 정보·모델 대용량 파일은 Git 저장소에 직접 업로드하지 않습니다.

[빌드·검증 GitHub Actions](../.github/workflows/t07-portable-windows.yml)는 공식 모델과 CPU 런타임을 **CI 빌드 과정에서만 다운로드**한 후, 가상 Windows 환경의 새 폴더에 압축을 풀고 독립 실행을 확인합니다. 자동 생성한 **샘플 매뉴얼 DB**를 넣은 시험용 ZIP이며 고객 자료가 포함된 정식 배포판이 아닙니다. CI 아티팩트는 7일 보관하도록 설정했습니다.

## 지식 DB 전체 교체 및 롤백

지식 데이터 갱신은 **제작자 PC에서 새로운 knowledge.db를 생성한 뒤 사용자 PC로 전달**하는 방식입니다. 사용자 PC에서 PDF를 재색인하지 않습니다.

1. 엔진 콘솔을 종료합니다.
2. 제작자가 전달한 새 DB와 **독립적으로 확인된 SHA-256** 값을 준비합니다.
3. 배포 폴더에서 다음을 실행합니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Update-Knowledge.ps1 -SourceDb "D:\updates\knowledge.db" -ExpectedSha256 "64자리_SHA256"
```

4. `Verify-AIHelp.ps1`로 검증하고 엔진을 다시 실행합니다.
5. 이전 DB로 복구하려면 서버를 종료하고 다음을 실행합니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Update-Knowledge.ps1 -Rollback
```

업데이트 도구는 변경 전 원본 DB를 `knowledge.previous.db`에 보관하고, 새 DB를 **같은 볼륨 임시 파일**에서 해시·SQLite 무결성·스키마 확인 후 `File.Replace`로 교체합니다. 잘못된 해시·손상된 DB·스키마 불일치는 기존 DB에 영향을 주지 않으며, 서버가 실행 중일 때 교체하지 않도록 검사합니다. 이전 DB 복구 역시 무결성 검사를 거칩니다. **델타 업데이트·자동 온라인 갱신은 없습니다.**

`manifest.json`은 불변 엔진·모델 파일에만 적용되고, 교체 가능한 지식 DB는 `knowledge/knowledge.sha256`로 별도 관리합니다. 수정 가능한 `settings.json`은 서명하거나 강제 검증하지 않으므로 신뢰할 수 있는 관리자가 수정해야 합니다.

## 검증 기준과 한계

- Windows GitHub Actions에서 ZIP 압축 해제 → 포함된 EXE 단독 실행 → API `/health`, `/search`, `/event`, 실제 CPU `/chat` 테스트.
- 사용자 PC의 시스템 Python을 `PATH`에서 제거하고 외부 프록시를 무효 주소로 지정하여 실행합니다. 이것은 **실제 네트워크가 물리적으로 차단된 PC에서의 검증과 동일하지 않습니다**.
- 같은 ZIP의 DB 교체, 새 지식 검색, 기존 항목 삭제 반영, 롤백 복구, 잘못된 해시의 업데이트 거부, 조작된 바이너리/스크립트 해시 거부를 자동 검증합니다.
- 빌드 환경의 Windows Server 2025만으로 Windows 10/11 사용자 PC 전 기종의 호환성, 8GB RAM 성능, 서명되지 않은 EXE의 SmartScreen 정책까지 보장할 수 없습니다. 이 항목은 T08 실기 테스트가 필요합니다.
- ZIP은 포터블 패키지이므로 Windows 서비스 설치/업데이트 서비스 또는 Windows 설치 프로그램(MSI/EXE)을 제공하지 않습니다.
- 모델과 llama.cpp는 각각 공식 배포 출처·라이선스를 포함합니다. 최종 상용 재배포 전에는 실제 포함된 3자 DLL·소스·NOTICE를 추가 점검해야 합니다.
