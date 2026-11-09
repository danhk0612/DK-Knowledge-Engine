# DK Knowledge Engine

**인터넷 연결이나 Docker 없이 Windows PC에서 사용하는 AI 도움말 엔진**입니다. PDF·DOCX·TXT·Markdown 설명서를 로컬 지식 DB로 만들고, 사용자는 로컬 AI에게 질문하거나 문서를 검색할 수 있습니다.

두 개의 프로그램을 구분합니다.

| 프로그램 | 누구를 위한 프로그램인가요? | 주요 기능 |
| --- | --- | --- |
| **Admin** — DK-Knowledge-Admin.exe | 문서 제작자·관리자 | 원본문서 추가/교체/삭제, DB 재생성, 사용자용 ZIP 제작 |
| **Client** — DK-Knowledge-Client.exe | 최종 사용자 | 로컬 엔진 시작/종료, AI 질문·검색, 출처 확인, DB 갱신·복구 |

## 다운로드 및 설치

- **배포용 ZIP을 사용하세요.** 개발 소스를 `git clone`하는 것만으로는 GGUF 모델과 실행 엔진이 설치되지 않습니다.
- 배포판: [GitHub Releases](https://github.com/danhk0612/DK-Knowledge-Engine/releases) — 첫 버전은 `v0.1.0-preview.1`로 준비 중입니다. Release가 게시되기 전에는 GitHub Actions의 시험용 아티팩트를 사용합니다.
- 운영체제: **Windows 10/11 x64**. 프로그램은 설치 관리자가 없는 **포터블 ZIP**입니다.
- 기본 구성: **Qwen3 1.7B GGUF (Q4_K_M) + llama.cpp CPU + SQLite FTS5**, 자체 포함 Windows GUI. 최종 사용자 PC에서는 기본 모델을 별도로 내려받거나 Python·Docker·.NET SDK를 설치할 필요가 없습니다.
- **미서명 실행 파일**입니다. SmartScreen·조직 보안 정책과 실제 고객 환경의 호환성은 별도 확인 대상입니다. 보안 정책을 임의로 우회하지 마세요.

### 관리자 첫 실행

1. Admin ZIP을 별도 폴더에 압축 해제하고 `DK-Knowledge-Admin.exe`를 실행합니다.
2. 원본 문서 폴더에 PDF/DOCX/TXT/MD를 복사하거나 프로그램에서 **문서 추가**를 클릭합니다.
3. **지식 DB 재생성**을 실행합니다.
4. **사용자 패키지 제작** 탭에서 별도 Client ZIP을 생성합니다.

기본 작업 위치는 `%LOCALAPPDATA%\DK-Knowledge-Engine\`이며, 문서·DB·출력 경로는 자동 입력됩니다. 경로 옆 버튼으로 탐색기를 바로 열 수 있습니다. 자세한 사용법은 [관리자 안내](docs/ADMIN_QUICKSTART.md)를 참조하세요.

### 사용자 첫 실행

1. Client ZIP을 압축 해제하고 `DK-Knowledge-Client.exe`를 실행합니다.
2. 로컬 엔진을 시작합니다.
3. AI에게 질문하거나 지식 DB를 검색합니다. 답변에 제시된 **출처 문서**를 함께 확인합니다.

[사용자 안내](docs/CLIENT_QUICKSTART.md)

**중요:** CI 시험용 ZIP의 지식 DB에는 인공 샘플 문서만 포함됩니다. 실제 제품의 도움말을 배포하려면 Admin에서 고객별 지식 DB를 만들어 새 Client ZIP을 생성해야 합니다. 원본 설명서 파일 자체는 Client ZIP에 포함되지 않습니다.

## 어떻게 동작하나요?

```text
관리자 PC: PDF/DOCX/TXT/MD → Builder → knowledge.db → Client ZIP 제작
사용자 PC: Client GUI → localhost(127.0.0.1) API → SQLite 검색 → 로컬 LLM → 출처 표시
```

- 여러 제품 자료는 `product_id`로 구분하고, 필요하면 버전을 지정합니다.
- 명확한 오류 코드·이벤트는 사전 정의된 규칙으로 처리하고, 자연어 질문은 검색 결과를 근거로 AI 답변을 생성합니다.
- `knowledge.db`를 업데이트하거나 롤백할 수 있습니다. 고객 문서를 모델에 추가 학습시키는 방식이 아닙니다.
- 기본 패키지는 GPU 가속을 필요로 하지 않습니다. 다른 모델·GPU 런타임을 사용하려면 별도 호환성 확인이 필요합니다.

## 개발 및 세부 문서

- [설계와 API 계약](docs/T01_CONTRACT.md)
- [Knowledge Builder](docs/T02_KNOWLEDGE_BUILDER.md)
- [로컬 검색](docs/T03_KNOWLEDGE_SEARCH.md) / [모델 실행](docs/T04_LOCAL_LLM.md)
- [localhost API](docs/T05_LOCALHOST_API.md) / [웹·Windows 연동](docs/T06_INTEGRATIONS.md)
- [Windows 포터블 및 DB 갱신](docs/T07_WINDOWS_PACKAGE.md)
- [모델 선택](docs/T09_MODEL_CONFIGURATION.md)
- [관리자 통합 문서 관리](docs/T13_ADMIN_GUI.md)
- [Windows 시험용 패키지 확인](docs/WINDOWS_TRIAL.md)
- [사전 배포판 기록](docs/RELEASE_NOTES_v0.1.0-preview.1.md) / [Release 제작](docs/RELEASE_PROCESS.md)
- [구현 단계 및 검증 기록](TASKS.md)

### 개발 소스 실행

```powershell
git clone https://github.com/danhk0612/DK-Knowledge-Engine.git
cd DK-Knowledge-Engine
dotnet run --project apps/Admin/DKKnowledgeAdmin.csproj
```

개발용 실행에는 .NET 10 SDK가 필요하며, Builder를 직접 구동하려면 Python과 `requirements-builder.txt` 의존성도 필요합니다. **배포용 Admin ZIP은 Builder가 포함되어 있으므로 개발 도구가 필요하지 않습니다.**

## 라이선스와 제한

DK-Knowledge-Engine 자체 코드는 [MIT License](LICENSE)입니다. 포함되는 모델·추론 엔진·Python 의존성에는 각자의 라이선스가 적용되며 [서드파티 안내](THIRD_PARTY_NOTICES.md)에서 확인할 수 있습니다.

이 프로젝트는 AI 답변의 정확성, 특정 고객 PC·내부망 보안 정책, 모든 Windows 환경과의 호환성을 보장하지 않습니다. 서명되지 않은 첫 배포판은 **preview**로 표시하며, 외부 공개 전 라이선스·보안·실고객 문서에 대한 검토가 필요합니다.
