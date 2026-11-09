# DK Knowledge Engine — 사용자 빠른 시작

**Windows x64용 로컬 AI 도움말 프로그램**입니다. ZIP을 풀어 실행하며, 기본 CPU 패키지는 Docker·Python·별도 모델 다운로드가 필요하지 않습니다.

## 시작하기

1. 제작자에게 받은 `DK-Knowledge-Engine-Client-Win-x64*.zip`을 다운로드해 원하는 폴더에 압축 해제합니다.
2. `DK-Knowledge-Engine-Client/DK-Knowledge-Client.exe`를 실행합니다.
3. 프로그램에서 로컬 엔진을 시작한 뒤 **문서 검색** 또는 **AI 질문**을 사용합니다.
4. 답변에 표시되는 출처를 함께 확인하세요. 답변은 제공된 지식 DB에 포함된 자료 범위에 제한됩니다.

기본 통신은 이 PC의 `127.0.0.1:8765`를 사용합니다. 다른 프로그램에서 이미 해당 포트를 사용 중이라면 충돌할 수 있습니다. 설정은 `config/settings.json`에 있으며, 오프라인 기본 패키지는 CPU 추론을 사용합니다.

## 포함 / 미포함

포함: Client GUI, 로컬 API 엔진, llama.cpp 실행 파일, Qwen3 1.7B GGUF 모델, 설정, 지식 DB, 검증·DB 갱신 스크립트, 라이선스 고지.

미포함: 제작자용 관리자 EXE, 문서 등록/색인 도구, 원본 PDF/DOCX/TXT/MD, 설치 관리자, 자동 온라인 업데이트.

## 검증 및 DB 갱신

작업 폴더에서 PowerShell을 실행하여 패키지 무결성을 확인할 수 있습니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Verify-AIHelp.ps1
```

제작자가 검증된 새 `knowledge.db`를 배포했다면 실행 중인 엔진을 종료한 후 다음을 수행합니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Update-Knowledge.ps1 -SourceDb "D:\updates\knowledge.db" -ExpectedSha256 "64자리_SHA256"
```

이전 DB로 복귀하려면 엔진 종료 후 `-Rollback`을 사용합니다. 자세한 내용은 저장소의 `docs/T07_WINDOWS_PACKAGE.md`를 참고하세요. 패키지 전체 ZIP을 덮어쓸 때는 **기존 사용자 설정·DB 백업을 별도로 보관**하세요.

## 주의 사항

이 프로그램은 생성형 AI 답변을 제공하므로 틀린 답변이 나올 수 있습니다. 원본 설명서·공식 기술 지원 문서를 우선하세요. 서명되지 않은 포터블 EXE에 대한 Windows SmartScreen 또는 조직 정책은 별도의 검토 대상입니다. 공식 배포의 SHA-256 체크섬과 다운로드 출처를 먼저 확인하세요.
