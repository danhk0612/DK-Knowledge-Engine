# DK Knowledge Engine v0.2.0-preview.1 — 배포 후보 (아직 미공개)

Windows 10/11 x64에서 Docker·Python 설치·인터넷 접속 없이 기본 Qwen3 CPU 모델을 실행하는 **오프라인 AI 도움말 엔진**입니다. 이 문서는 향후 배포할 `v0.2.0-preview.1`의 초안이며 **릴리스·태그가 생성되었다는 의미가 아닙니다**.

## v0.1.0-preview.4 대비 주요 변경

- **제품별 Client 분리:** Client 한 패키지당 제품 한 개의 ID·버전·지식 DB로 제한. 검색·규칙·기본 DB·선택형 벡터도 다른 제품 정보와 격리합니다.
- **독립형 Admin·Client GUI:** 제품 정보·지식 DB·소스 문서·AI 모델·사용자 ZIP 제작을 별도의 관리자 WPF 화면에서 관리합니다. Client는 질문·문서 검색·출처, 로컬 API 4종 테스트, 포트 저장, 엔진 시작·중지, DB 업데이트·롤백을 제공합니다.
- **제품별 브랜드 지정:** Admin에서 사용자 프로그램명과 PNG/ICO 아이콘을 지정하면 Client EXE·창·트레이에 반영됩니다.
- **창 닫기 동작:** Client의 X 버튼은 트레이 숨김, 트레이 메뉴에서 재열기·질문·엔진 제어·DB 관리·설정·완전 종료가 가능합니다.
- **지식 DB만 업데이트:** 같은 제품의 검증된 DB를 적용하고 이전 DB로 복구할 수 있습니다. 자신이 시작한 엔진은 중지·재시작하며 별도로 실행한 엔진은 종료하지 않습니다.
- **배포 구조:** Admin은 단일 EXE를 포함한 ZIP, Client는 EXE와 자체 포함 .NET DLL을 함께 포함한 **다중 파일** ZIP입니다. Client EXE만 다른 폴더로 이동해서는 안 됩니다.

## Preview에 포함할 파일 (예정)

- `DK-Knowledge-Engine-Admin-Win-x64-v0.2.0-preview.1.zip` — 문서 제작자용 Admin·Builder·엔진 템플릿·기본 GGUF.
- `DK-Knowledge-Engine-Client-Win-x64-v0.2.0-preview.1.zip` — 최종 사용자용 Client·로컬 API·기본 모델·인공 샘플 지식 DB.
- `SHA256SUMS.txt` — 두 ZIP의 SHA-256 검증 목록.

**시험용 Client의 `knowledge.db`에는 인공 샘플 문서만 있습니다.** 실제 고객 문서와 업무 지식 DB가 포함되어 있지 않습니다. 배포자가 허가받은 설명서로 Admin에서 별도 고객 전용 Client ZIP을 생성해야 합니다.

## 기술·검증

- 기본: Qwen3 1.7B GGUF (Q4_K_M), Windows CPU llama.cpp, SQLite FTS5, 127.0.0.1 로컬 API.
- 선택 기능: 제작용 로컬 GGUF/localhost AI 서버를 이용한 검색 표현 사전 보강, 사용자용 별도 임베딩 GGUF를 이용한 의미 검색. 선택한 모델의 재배포 권한은 별도 확인해야 합니다.
- Windows CI에서 Admin/Client 실제 WPF 동작, 아이콘, 독립형 Builder의 PDF·DOCX·TXT·MD DB 제작, 패키지 무결성·DLL 변조 차단, 제품 격리, 엔진·DB 갱신/복구를 검증했습니다.
- 2026-11-11 사용자 Windows PC에서 인공 샘플을 대상으로 Admin/Client 주요 동작, 트레이, AI 질문 세 건의 `3308` 답변과 `setup.md` 출처가 확인됐습니다.
- 실제 고객 PDF·DOCX의 답변 품질, 스캔 OCR, 모든 Windows·기업 보안 정책, 제3자 라이선스 및 외부 배포 적합성은 **최종 검증 대상**입니다. 자동 검사·정답 키워드만으로 응답 사실성을 보증하지 않습니다.

## 실행·주의 사항

- Windows 10/11 x64. 설치 관리자가 없는 **포터블·미서명 Preview**입니다.
- Windows SmartScreen이나 조직 보안 정책을 임의로 우회하지 마세요.
- 추가 GGUF·OCR 구성 요소·고객 문서의 사용 및 재배포 권한은 개별 검토가 필요합니다.
- DB 업데이트 전에 Client의 제품 ID를 확인하고, 중요 데이터의 별도 백업을 유지하세요. **온라인 자동 업데이트 기능은 제공하지 않습니다.**

참고: [Admin 안내](ADMIN_QUICKSTART.md) · [Client 안내](CLIENT_QUICKSTART.md) · [v0.2.0 배포 검수표](V020_RELEASE_READINESS.md) · [기존 Draft 제작 절차](RELEASE_PROCESS.md)
