# T12 — 두 개의 독립 Windows GUI (초기 구현)

## 분리 원칙

- **DK-Knowledge-Admin.exe** — 제작자용. 원본 PDF/DOCX/TXT/MD를 기존 Python Builder에 전달해 DB를 만들고, 로컬 API에서 AI 답변을 시험하고, Client 전용 패키지를 생성한다.
- **DK-Knowledge-Client.exe** — 사용자용. 사용자의 로컬 엔진을 실행·종료하고, 검색·질문·출처 표시, 전달받은 DB 적용·롤백·검증을 수행한다.
- 실제 사용자 배포 ZIP에는 **Client EXE, AI 엔진, GGUF, llama.cpp, 지식 DB, 구성 및 검증·갱신 스크립트**만 포함된다. Admin EXE·Builder·원본 매뉴얼·Python 색인 환경은 제외한다.
- WPF/.NET 10. 기존 T05 localhost JSON API와 Builder·DB 형식을 변경하지 않는다. 새 원격 서비스·Docker·인터넷은 필요하지 않다.
- 공유 소스는 두 GUI의 API 계약 파일 `apps/Shared/LocalApiClient.cs` 하나이다. 사용자 배포에는 빌드된 Client만 들어가므로 관리자 기능은 숨겨진 것이 아니라 **포함되지 않는다**.

## 개발 PC에서 실행

Windows 10/11 + .NET 10 SDK 사용:

```powershell
dotnet run --project apps/Admin/DKKnowledgeAdmin.csproj
dotnet run --project apps/Client/DKKnowledgeClient.csproj
```

Admin에서 Builder를 사용하려면 **제작자 PC에 Python 및 `requirements-builder.txt` 의존성**이 준비되어야 한다. Admin 소스 저장소 루트를 지정하고 원본 문서 루트(예: `sources/product-id/manuals/help.pdf`)와 출력 DB 경로를 지정한다. DB 생성은 이미 구현된 `python -m builder.knowledge_builder --source ... --database ... --rebuild`를 실행한다. 원본 수정/추가/삭제는 파일 시스템에서 수행하고 DB 재생성한다.

Client GUI는 단독으로 엔진 바이너리를 제공하지 않는다. 아래 방식으로 기존 포터블 엔진과 함께 배포해야 한다.

## 관리자에서 Client 전용 패키지 생성

기존 검증된 엔진 압축 해제 폴더와 관리자가 만든 `knowledge.db`를 준비한다. 관리자는 GUI의 "사용자 패키지 제작" 탭에서 다음을 수행하거나 PowerShell로 직접 호출한다.

```powershell
.\distribution\Build-Client-Package.ps1 `
  -EnginePackage "D:\Base\DK-Knowledge-Engine-Win-x64" `
  -KnowledgeDb "D:\Data\knowledge.db" `
  -OutputDir "D:\Output\DK-Client-New"
```

- 출력 폴더는 기존에 없어야 한다. 기존 패키지와 지식 DB 원본을 덮어쓰지 않는다.
- 서명된 프로그램·정식 Release가 아닌 **테스트 패키지**를 만든다. .NET SDK가 필요하지만 Client PC에는 Python/.NET SDK/인터넷이 필요하지 않도록 GUI를 자체 포함 EXE로 게시한다.
- 기존 패키지의 `Verify-AIHelp.ps1`을 검사하고, 검증된 `Update-Knowledge.ps1`로 DB를 적용한 후 Client EXE의 SHA-256을 manifest에 추가한다. 최종 검증 후 ZIP을 생성한다.
- 관리자 실행 파일과 Builder는 복사하지 않으며, Actions에서도 사용자 전용 ZIP의 존재·무결성과 관리자 파일 부재를 점검한다.

## 범위와 남은 실기 검증

이번 T12는 두 프로그램의 **최초 동작 버전**이다. WPF GUI 빌드, 별도 게시, 패키징 무결성은 CI에서 검증하지만 실제 Windows PC에서 버튼 클릭·DB 업데이트·사내 브라우저와의 병행·제품 지원용 UI 사용성은 별도로 확인해야 한다.

- Admin Builder는 제작자 PC의 Python에 의존한다. 별도 제작자용 Python 번들링은 아직 하지 않았다.
- Client 패키지는 포터블 ZIP이며 설치 관리자 및 자동 업데이트가 없다.
- 엔진 제어는 Client가 시작한 프로세스만 종료한다. 기존에 다른 방식으로 실행된 엔진을 임의 종료하지 않는다.
- `raw_chatml` 기본 설정 안정화는 별도의 T11 변경에서 다룬다.
- 배포 모델·원본 매뉴얼의 라이선스와 Windows SmartScreen/서명 정책은 정식 고객 배포 전에 확인해야 한다.
