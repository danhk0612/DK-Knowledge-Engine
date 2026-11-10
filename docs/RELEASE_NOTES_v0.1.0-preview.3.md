# DK Knowledge Engine v0.1.0-preview.3

Windows 10/11 x64를 위한 **오프라인 문서 검색 및 로컬 AI 도움말 프로그램의 세 번째 사전 배포 후보**입니다. 설치 관리자가 없는 포터블 ZIP으로 제공되며, **디지털 서명이 없는 Preview**입니다.

## preview.2 대비 수정 사항

- 기본 Qwen3 1.7B의 답변에서 단독 `</think>` 종료 태그가 노출되는 문제를 수정했습니다.
- AI가 설치 확인 코드 등 원문에 명시된 값을 누락하고 문서 위치만 안내하는 사례를 줄이도록 한국어 응답 프롬프트를 개선했습니다.
- `manual-test/manuals/dk-test.md`의 합성 문서로 질문 `설치 확인 코드`에 `DKTEST-3308`이 답변에 포함되고 출처가 표시되는 것을 실제 CPU Qwen3와 Windows GUI에서 확인했습니다.
- 기존 Admin/Client 분리, 모델·DB 형식 및 기능은 유지합니다. 새 모델, 스키마 또는 런타임 업그레이드는 없습니다.

## 포함 파일

- `DK-Knowledge-Engine-Admin-Win-x64-v0.1.0-preview.3.zip` — 제작자용. 원본문서 관리, 지식 DB 제작, 별도 사용자 ZIP 생성 기능과 Builder·기본 모델·엔진 템플릿을 포함합니다.
- `DK-Knowledge-Engine-Client-Win-x64-v0.1.0-preview.3.zip` — 사용자용. 기본 Qwen3 1.7B CPU 모델, localhost API, 문서 검색, 출처 표시, 지식 DB 갱신 기능을 포함합니다.
- `SHA256SUMS.txt` — 위 두 ZIP의 파일 무결성 확인용 SHA-256입니다.

**주의:** 이 Preview의 사용자 ZIP에 포함된 `knowledge.db`는 CI가 생성한 **합성 샘플 문서 DB**입니다. 실제 고객 문서 또는 업무용 지식 DB가 들어 있지 않습니다. 사용자에게 실제 설명서를 제공하려면 관리자에서 승인된 원본문서로 새 DB와 사용자 ZIP을 제작하세요.

## 관리자(Admin) 기능

- PDF/DOCX/TXT/MD를 임의의 원본 폴더에서 관리하고, 문서를 추가하면 관리 폴더에 복사하며 기존 문서 교체·삭제를 지원합니다.
- 원본문서·지식 DB·엔진·출력 위치의 기본 경로를 자동 입력하고, 폴더별 Windows 탐색기 열기 버튼을 제공합니다.
- DB 재생성 시 선택적 PDF 레이아웃 보존, 스캔 PDF용 오프라인 OCR, 문서별 추출 품질 보고서를 지원합니다. OCR을 사용하려면 **제작 PC에 Tesseract·Poppler를 별도로 설치**해야 합니다.
- **선택 기능:** 제작 전용 고성능 로컬 GGUF 또는 localhost 모델 서버로 검색용 질문·용어를 사전 생성할 수 있습니다. 이 제작 모델은 Client로 전달하지 않습니다.
- **선택 기능:** 경량 임베딩 GGUF로 원본문서의 벡터를 제작 PC에서 생성하고, 호환되는 같은 모델을 사용자 ZIP에 별도 포함할 수 있습니다.
- 사용자 AI 답변용 GGUF는 제작/임베딩 모델과 독립적으로 지정할 수 있습니다. 기본값은 Qwen3입니다.

## 사용자(Client) 기능 및 경량화

- 별도 Python·Docker·.NET SDK·인터넷 연결 없이 로컬 CPU에서 기본 모델을 실행할 수 있습니다.
- SQLite FTS5 검색, 한국어 복합어 공백 보정, 제작자가 미리 생성한 검색 표현 색인과 원본문서 출처 표시를 지원합니다.
- 문서 근거를 활용한 단계별 답변을 제공하며, 근거가 없으면 추측 답변을 제한하도록 설정되어 있습니다. **AI 답변의 사실성을 보장하는 것은 아닙니다.**
- 기본 사용자 ZIP에는 의미 검색용 GGUF/실행 파일을 포함하지 않습니다. 관리자가 벡터 DB를 제작했더라도 **기본 Client용 DB 사본에서는 사용하지 않는 임베딩 벡터를 제거·압축**합니다.
- 관리자가 의미 검색을 선택해 별도 사용자 ZIP을 제작하면, 같은 임베딩 모델의 SHA-256 일치·색인 완성도를 검사한 뒤 필요 모델을 추가합니다. 일반 키워드 검색에서 근거가 없을 때만 쿼리 임베딩을 수행합니다.

## 검증과 제한

- 수정 PR [#37](https://github.com/danhk0612/DK-Knowledge-Engine/pull/37)에서 실제 Qwen CPU 테스트, Windows·Ubuntu 회귀, Windows Admin/Client 통합 패키지 CI가 통과했습니다. 이 결과는 합성 문서 기반이며 광범위한 실제 고객 문서 정답률을 보장하지 않습니다.
- 이전 `preview.2`는 별도 미공개 Draft로 유지하며 이 버전은 신규 빌드·신규 해시로 배포합니다.


- Windows GUI·기본 CPU Qwen3·독립형 Admin/Client 패키징·PDF/DOCX/TXT/MD 합성 문서 색인·기본/의미 검색 패키지 분리를 GitHub Actions에서 검증했습니다.
- 별도의 실제 모델 시험에서 **TwinSunsLLC multilingual-e5-small Q8_0 (384차원)** 모델과 `llama.cpp v0.8.0` Windows CPU 실행을 확인했습니다. **이 임베딩 GGUF는 기본 Client ZIP에 포함되지 않습니다.** [검증 모델 안내](https://github.com/danhk0612/DK-Knowledge-Engine/blob/main/docs/T19_OPTIONAL_SEMANTIC_SEARCH.md)
- 실제 고객 PDF의 정답률·OCR 품질, 대규모 문서 성능, 모든 Windows PC의 작동, 실제 배포 환경의 SmartScreen·조직 정책·내부망 브라우저 제약은 별도 현장 검증 대상입니다.
- ZIP은 설치 프로그램이 아니며 자동 온라인 업데이트를 제공하지 않습니다. 선택한 추가 GGUF의 라이선스와 재배포 권한은 배포자가 확인해야 합니다.
- 비서명 Preview이므로 공식 Release의 SHA-256과 다운로드 출처를 확인하고, 보안 경고를 무조건 우회하지 마세요.
- Builder 의존성의 고지 원문을 추가로 포함했으나, **전체 .NET/Python 번들 및 기타 제3자 라이선스에 대한 최종 법적 검수 완료를 의미하지는 않습니다.**

사용법: [관리자 안내](https://github.com/danhk0612/DK-Knowledge-Engine/blob/main/docs/ADMIN_QUICKSTART.md) · [사용자 안내](https://github.com/danhk0612/DK-Knowledge-Engine/blob/main/docs/CLIENT_QUICKSTART.md) · [배포 검수 절차](https://github.com/danhk0612/DK-Knowledge-Engine/blob/main/docs/RELEASE_PROCESS.md)
