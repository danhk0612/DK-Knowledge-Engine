# DK Knowledge Engine — 사용자 빠른 시작

**Windows x64용 로컬 AI 도움말 프로그램**입니다. ZIP을 풀어 실행하며, 기본 CPU 패키지는 Docker·Python·별도 모델 다운로드가 필요하지 않습니다.

## 시작하기

1. 제작자에게 받은 `DK-Knowledge-Engine-Client-Win-x64*.zip`을 다운로드해 원하는 폴더에 압축 해제합니다.
2. `DK-Knowledge-Engine-Client/DK-Knowledge-Client.exe`를 실행합니다. **EXE만 다른 폴더로 옮기지 마세요.** 같은 폴더의 DLL, `*.deps.json`, `*.runtimeconfig.json`은 실행에 필요한 자체 포함 .NET 파일입니다. ZIP 폴더 전체를 유지해야 하며 별도 .NET 설치는 필요하지 않습니다.
3. 프로그램에서 로컬 엔진을 시작한 뒤 **문서 검색** 또는 **AI 질문**을 사용합니다. 제품 ID와 버전은 관리자 패키지 제작 시 고정되어 있어 사용자가 입력하지 않습니다.
4. 답변에 표시되는 출처를 함께 확인하세요. 답변은 제공된 지식 DB에 포함된 자료 범위에 제한됩니다.

기본 통신은 이 PC의 `127.0.0.1:8765`를 사용합니다. 충돌하면 **설정** 화면에서 엔진을 중지한 후 포트를 변경할 수 있습니다. 통신은 127.0.0.1에만 바인딩됩니다. 설정 파일은 `config/settings.json`이며, 오프라인 기본 패키지는 CPU 추론을 사용합니다.

## 포함 / 미포함

포함: Client GUI EXE와 .NET 자체 포함 실행 DLL, 로컬 API 엔진, llama.cpp 실행 파일, Qwen3 1.7B GGUF 모델, 설정, 지식 DB, 검증·DB 갱신 스크립트, 라이선스 고지.

미포함: 제작자용 관리자 EXE, 문서 등록/색인 도구, 원본 PDF/DOCX/TXT/MD, 설치 관리자, 자동 온라인 업데이트.

## API 테스트, 트레이, DB 갱신

**API 도구** 화면에서 `GET /health`, `POST /search`, `POST /chat`, `POST /event`를 선택하고 요청 JSON을 수정해 호출하거나 복사할 수 있습니다. 제품 ID와 버전, API 포트는 자동 채워집니다.

창의 **X 버튼을 누르면 트레이에 유지**됩니다. 트레이를 더블클릭하면 창이 열리며, 우클릭 메뉴에서 질문하기·엔진 시작/중지·지식 DB 관리·설정·완전 종료를 이용할 수 있습니다.

이 프로그램이 시작한 엔진은 DB 적용·롤백 전에 자동 중지하며 성공하면 다시 실행합니다. 별도로 실행한 엔진은 종료하지 않습니다. 동일한 제품 ID가 아닌 DB 업데이트는 거부됩니다.

## 검증 및 DB 갱신

작업 폴더에서 PowerShell을 실행하여 패키지 무결성을 확인할 수 있습니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Verify-AIHelp.ps1
```

제작자가 **동일한 제품 ID의** 검증된 새 `knowledge.db`를 배포했다면 실행 중인 엔진을 종료한 후 다음을 수행합니다. 다른 제품의 지식 DB는 적용할 수 없습니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Update-Knowledge.ps1 -SourceDb "D:\updates\knowledge.db" -ExpectedSha256 "64자리_SHA256"
```

이전 DB로 복귀하려면 엔진 종료 후 `-Rollback`을 사용합니다. 자세한 내용은 저장소의 `docs/T07_WINDOWS_PACKAGE.md`를 참고하세요. 패키지 전체 ZIP을 덮어쓸 때는 **기존 사용자 설정·DB 백업을 별도로 보관**하세요.

## 주의 사항

관리자가 다른 모델을 선택하면 해당 GGUF는 패키지의 `models/`에 포함되며 `config/settings.json`에 선택 파일 경로가 설정됩니다. 사용자가 모델을 직접 추가·변경하는 방법은 [T09 모델 설정](T09_MODEL_CONFIGURATION.md)을 참고하세요.

이 프로그램은 생성형 AI 답변을 제공하므로 틀린 답변이 나올 수 있습니다. 원본 설명서·공식 기술 지원 문서를 우선하세요. 서명되지 않은 포터블 EXE에 대한 Windows SmartScreen 또는 조직 정책은 별도의 검토 대상입니다. 공식 배포의 SHA-256 체크섬과 다운로드 출처를 먼저 확인하세요.
