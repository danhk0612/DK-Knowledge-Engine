# DK Knowledge Engine

Windows 환경에서 **인터넷·Docker·GPU 없이 동작하는 범용 AI 도움말 엔진**을 목표로 하는 프로젝트입니다.

사용 설명서(PDF/DOCX/TXT/Markdown), FAQ, 트러블슈팅 자료를 제작자 PC에서 지식 DB로 만들고, 배포 대상 PC에서는 기존 웹·Windows 프로그램이 `127.0.0.1` HTTP API로 도움말을 요청합니다.

## 목표 구조

```text
[제작자 PC] 매뉴얼 원본 → Knowledge Builder → 배포용 지식 DB
                                             ↓
[사용자 PC] 웹/Windows 앱 → localhost API → 지식 검색 → (필요 시) 로컬 LLM
                                         └──── 근거 문서 기반 안내 ────→ 앱
```

- 초기 후보: **Qwen3 1.7B GGUF + llama.cpp + SQLite FTS5**
- 비교 후보: Qwen3.5 2B (실제 성능 검증 이후 결정)
- 명확한 오류 코드·이벤트는 LLM 호출 없이 규칙에 따라 응답
- 자연어 질문은 지식 검색 후 로컬 LLM에서 답변
- 개인화 방식은 **RAG**이며, 모델 가중치에 문서를 파인튜닝하지 않음
- 실행 환경: Windows x64 포터블, PC 상황에 맞춰 모델·스레드·컨텍스트·CPU/GPU용 실행 파일을 사용자가 선택 (하드웨어별 권장 사양 측정은 필수 조건 아님)
- 출처가 없는 경우 추측으로 해결책을 제시하지 않음

## 재사용·지식 갱신 원칙

1. 원본 문서와 메타데이터는 특정 모델·검색 엔진의 저장 형식과 독립적으로 관리합니다.
2. 문서 **추가·수정·삭제·재색인**과 전체 DB 재생성을 지원하도록 설계합니다.
3. 지식 DB 및 제품별 안내 자료는 엔진 코드와 분리하여 갱신·재배포할 수 있게 합니다.
4. 동일 엔진을 여러 웹·Windows 프로그램에서 재사용하고, `product_id`·버전을 기준으로 자료를 구분합니다.
5. LLM 실행 계층과 검색 계층에 명확한 경계를 두어 추후 구성 변경이 가능하도록 하지만 **첫 버전부터 모든 조합을 지원하지는 않습니다**.
6. 배포용 지식 패키지는 로컬에서만 동작하며, 민감한 원본·모델 대용량 파일을 Git에 무분별하게 포함하지 않습니다.

## 문서

- [T01 요구사항 및 데이터·API 계약](docs/T01_CONTRACT.md)
- [T02~T10 작업 계획 및 완료 조건](TASKS.md)
- [T02 Knowledge Builder 사용법](docs/T02_KNOWLEDGE_BUILDER.md)
- [T03 지식 검색 모듈 사용법](docs/T03_KNOWLEDGE_SEARCH.md)
- [T04 CPU용 로컬 LLM 연결](docs/T04_LOCAL_LLM.md)
- [T05 localhost HTTP API 사용법](docs/T05_LOCALHOST_API.md)
- [T06 웹·Windows 프로그램 연동 예제](docs/T06_INTEGRATIONS.md)
- [T07 Windows 포터블 ZIP 및 지식 DB 갱신](docs/T07_WINDOWS_PACKAGE.md)
- [T08 CPU 계측·모델 비교 및 고객 PC 검증 조건](docs/T08_VALIDATION.md)
- [T08 현장 기능·보안 확인 절차 (사양 측정 없음)](docs/T08_FIELD_CHECKLIST.md)
- [T09 사용자별 모델·실행 환경 선택](docs/T09_MODEL_CONFIGURATION.md)
- [T10 근거 출처·답변 정확성·로컬 보안 검증](docs/T10_VALIDATION.md)

## 현재 상태

**T01 설계 및 T02~T10 구현 PR #1~#9와 DB 갱신 복구·CI 재현성 보완 PR #11이 `main`에 병합되었습니다.** Windows 포터블 CPU 추론, localhost API·웹/WPF 연동, 사용자 설정형 모델 선택 및 인공 매뉴얼 품질·보안 14/14 검증이 자동 CI로 확인되었습니다. PR #11의 DB 교체 중단·SHA 기록 복구도 `main`에 반영된 상태입니다.

**후속 검증 보완 PR #13~#15도 `main`에 병합되었습니다.** [#13 사내 HTTPS→localhost LNA 및 Origin/CSP 브라우저 검증](https://github.com/danhk0612/DK-Knowledge-Engine/pull/13), [#14 T08 Windows PowerShell 5.1 현장 평가 판정 수정](https://github.com/danhk0612/DK-Knowledge-Engine/pull/14), [#15 T10 품질 기대값 검증 보강](https://github.com/danhk0612/DK-Knowledge-Engine/pull/15). 각 PR의 최신 자동 CI 검증은 통과했으며, **실제 고객 PC/문서의 현장 검증은 아직 별도**입니다.

**정식 고객 배포 적합성은 아직 미확정**입니다. 실제 사내 HTTPS 웹사이트 LNA 권한, 고객 문서 정답성, 완전 오프라인 현장 점검, 서명/SmartScreen 및 라이선스 적합성 검토가 필요합니다. CPU/RAM/GPU 성능 측정은 T09 결정에 따라 필수 승인 조건이 아닙니다.
