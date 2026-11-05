# DK Knowledge Engine — T01 요구사항·데이터·API 계약 v1.1

- 상태: **기준 문서(설계 단계)**. 실제 기능 구현 및 성능 검증 전.
- 기준 저장소: `danhk0612/DK-Knowledge-Engine`
- 이력: v1.0의 기능 범위를 유지하고, **지식 갱신·독립성·다중 프로그램 재사용·교체 가능한 경계**를 보강.
- 범위 제한: 이번 단계는 문서화만 수행. 임의의 확장 기능, 엔진 교체 구현, 모델 다운로드·배포는 진행하지 않음.

## 1. 목표

1. 제작자 PC에서 PDF/DOCX/TXT/Markdown 사용 설명서와 트러블슈팅 문서를 추출·색인하여 배포 가능한 지식 DB를 생성한다.
2. 사용자 PC는 **외부 접속 없이**, **Docker 없이**, **GPU 없이도** 준비된 지식 DB와 소형 GGUF LLM을 로컬에서 실행할 수 있어야 한다.
3. 기존 웹/Windows 프로그램은 `127.0.0.1` HTTP/JSON API로 자연어 질문 또는 제품 상태/오류를 전달한다.
4. 정확한 오류/이벤트 매칭은 승인된 도움말을 직접 반환하고, 일반 질문에 한하여 검색 결과를 근거로 LLM을 호출한다.
5. 지식 자료는 추후 추가·수정·삭제·재색인이 가능해야 하고, 서로 다른 제품 및 프로그램에서 재사용 가능해야 한다.
6. 모델·검색 엔진의 교체를 위해 경계를 분리하되, **초기 구현 대상은 단일 조합**으로 한정한다.

### 1.1 초기 기술 기준

| 항목 | 기준 |
|---|---|
| OS | Windows 10/11 x64 |
| 네트워크 | 배포·실행 중 외부 인터넷 불필요, `127.0.0.1` 사용 가능 |
| 컨테이너 | Docker 불사용 |
| 기본 모델 후보 | Qwen3 1.7B 양자화 GGUF, 아티팩트/라이선스/해시 후속 확정 |
| 비교 모델 | Qwen3.5 2B, 평가만 계획 |
| LLM 추론 | llama.cpp |
| 검색 | SQLite FTS5 우선; 한국어 정확도 평가 필수 |
| 임베딩·벡터 검색 | 최초 구현 필수 아님; 필요성 검증 후 별도 결정 |
| 하드웨어 | GPU 없는 8GB RAM 목표, 16GB 권장; 최소 성능 실측 필요 |
| API | 로컬 HTTP/JSON, 제품·버전·근거 출처 포함 |
| 지식 갱신 | 제작자 PC에서 DB 생성/갱신, 사용자 PC에는 데이터 패키지 전달 |

### 1.2 범위 제외

모델 가중치 파인튜닝, 클라우드/API 의존성, Docker 서비스, 자동 프로그램 수리, 제작자용 GUI, 외부 사용자 계정 서비스, 모든 모델/DB 조합의 즉시 지원은 초기 범위에서 제외한다.

## 2. 구성 요소 및 책임 경계

| 구성 | 역할 | 배포 여부 |
|---|---|---|
| Source Knowledge | 원본 자료와 제품·버전 메타데이터의 기준 저장소 | 정책에 따라 선택 |
| Knowledge Builder | 문서 추출·변경 감지·색인 DB 생성·검증 | 제작자 PC 전용 |
| Knowledge DB | 문서·청크·도움말 규칙·FTS 색인 | 사용자 PC에 배포 |
| Search Backend | 지식 DB 조회·필터·검색 결과 반환 | 사용자 PC |
| LLM Runtime Adapter | 질문과 검색 근거를 로컬 추론 엔진에 전달 | 사용자 PC |
| AI Help Engine | API, 호출 분기, 답변·출처 구성 | 사용자 PC |
| Integration Client | 기존 웹/Windows 앱에서 API 호출 및 표시 | 대상 앱에 연결 |

**RAG는 지식 DB 그 자체가 아니라 검색 → 근거 구성 → LLM 전달 흐름이다.** 모델 파일만 옮겨서는 등록한 지식이 따라가지 않으므로 지식 패키지를 별도로 제공해야 한다.

초기 Search Backend는 SQLite FTS5, LLM Runtime Adapter는 llama.cpp 한 종류만 구현한다. 경계 분리는 향후 변경 시 코드 영향 범위를 줄이려는 것으로, 플러그인 시스템이나 범용 추상화 프레임워크 구축을 요구하지 않는다.

## 3. 지식 데이터 계약

### 3.1 Document

| 필드 | 타입 | 필수 | 의미 |
|---|---|---|---|
| `document_id` | string | Y | 문서 식별자 |
| `product_id` | string | Y | 대상 프로그램 식별자 |
| `title` | string | Y | 문서 제목 |
| `source_path` | string | Y | 제작자 원본 기준 상대 경로 |
| `source_type` | enum | Y | pdf/docx/txt/md |
| `version_from` | string/null | N | 적용 시작 제품 버전 |
| `version_to` | string/null | N | 적용 종료 제품 버전 |
| `language` | string | N | 예: ko |
| `source_hash` | string | Y | 원본 파일 SHA-256 |

### 3.2 Chunk

| 필드 | 타입 | 필수 | 의미 |
|---|---|---|---|
| `chunk_id` | string | Y | 청크 식별자 |
| `document_id` | string | Y | 소속 문서 |
| `section_title` | string/null | N | 절 제목 |
| `content` | string | Y | 원문에서 추출한 검색 본문 |
| `page_from`, `page_to` | int/null | N | 원본 페이지(1부터 시작) |
| `sequence` | int | Y | 문서 내 순서 |

### 3.3 Help Rule

| 필드 | 타입 | 필수 | 의미 |
|---|---|---|---|
| `rule_id` | string | Y | 규칙 ID |
| `product_id` | string | Y | 대상 프로그램 |
| `event_id` | string/null | N | 상태 이벤트 코드 |
| `error_code` | string/null | N | 오류 코드 |
| `screen_id` | string/null | N | 화면/기능 코드 |
| `version_from`, `version_to` | string/null | N | 적용 버전 범위 |
| `document_id` | string | Y | 근거 문서 |
| `chunk_id` | string/null | N | 근거 청크 |
| `title` | string | Y | 표시 제목 |
| `content` | string | Y | 사전 승인된 안내문 |

`event_id` 또는 `error_code` 중 최소 하나가 필요하다. 충돌하는 규칙을 임의로 한 건 선택하면 안 된다. 문자열 사전순의 제품 버전 비교를 금지하며, 버전 파싱/포함 규칙은 후속 작업에서 확정한다.

### 3.4 원본 자료 예시

`sources/example-program/troubleshooting/DB-1001.md`:

```markdown
# DB-1001: 데이터베이스 연결 실패

## 증상
DB 접속 실패 메시지가 표시됩니다.

## 확인
1. 서버 실행 상태 확인
2. 주소 및 포트 확인
```

`sources/example-program/rules/DB-1001.json` (정확한 자동 매칭이 필요할 때만):

```json
{
  "rule_id": "example-db-1001",
  "product_id": "example-program",
  "error_code": "DB-1001",
  "event_id": "connection_failed",
  "screen_id": "database_settings",
  "version_from": "2.0.0",
  "version_to": "2.5.0",
  "document_id": "example-db-troubleshooting",
  "chunk_id": null,
  "title": "데이터베이스 연결 실패",
  "content": "DB 서버 상태, 주소 및 포트를 확인하십시오."
}
```

일반 PDF/DOCX 자료 전체를 JSON으로 다시 작성할 필요는 없다.

## 4. 지식 갱신·이식성 계약 (v1.1 추가)

1. **원본 독립성:** 제품별 원본 파일, 메타데이터, 오류 규칙은 인덱스/LLM 런타임과 별도 보관한다. 검색 DB를 폐기해도 원본으로 다시 구축할 수 있어야 한다.
2. **추가:** 새 문서 등록 시 식별자와 출처를 함께 기록한다. 기존에 존재하는 문서/규칙을 의도치 않게 덮어쓰지 않는다.
3. **수정:** 원본 `source_hash` 변경을 감지하고 해당 문서 청크·FTS 인덱스를 갱신한다. 불변인 파일을 불필요하게 재처리하지 않는 방식은 T02에서 검증한다.
4. **삭제:** 원본 문서 삭제 또는 명시적 제거 시 관련 청크/색인과 규칙 참조를 일관되게 처리한다. 존재하지 않는 문서를 근거로 답변하지 않는다.
5. **재생성:** 지식 DB가 없어도 원본 자료에서 전체 DB를 재생성할 수 있어야 한다. 증분 갱신과 전체 재생성의 결과를 비교 검증한다.
6. **배포:** 사용자 PC에 전체 지식 DB 교체 패키지를 전달하는 것을 초기 방식으로 가정한다. 변경분만 배포하는 델타 업데이트는 후속 평가 대상으로 둔다.
7. **데이터 이동:** 특정 검색 엔진의 내부 DB 파일을 공용 교환 규격으로 간주하지 않는다. 다른 검색 백엔드로 변경할 때 원본·메타데이터에서 재색인한다.
8. **참조 안정성:** 갱신 후에도 `document_id`, `chunk_id`, `rule_id`와 출처가 일관된지 검증한다. 동일 문서의 식별자 보존/재발급 세부 정책은 T02에서 결정한다.
9. **호환성:** 지식 DB와 엔진의 포맷 버전을 식별할 수 있어야 한다. 호환성 없는 지식 패키지를 임의로 열지 않도록 검증 계약을 마련한다. 구체적인 스키마 버전 필드는 T02에서 확정한다.
10. **지식 소유권:** 배포용 DB에 포함된 문서 내용도 사용자 PC에서 추출될 수 있으므로, 배포 가능한 자료만 포함한다.

### 4.1 여러 제품에서 재사용

- 모든 API 요청에서 `product_id`를 전달한다. 다른 제품 문서를 섞지 않는다.
- 제품 버전이 있는 경우 버전별로 적용 가능한 문서/규칙만 선택한다.
- 웹 앱과 Windows 앱은 공통 API를 사용하지만 서로 다른 PC에 설치되어 있다면 해당 PC별 실행 엔진과 데이터가 필요하다.
- 다른 제품에 재사용할 때는 엔진 코드를 복제하지 않고 **제품별 지식 원본과 배포 DB를 구분**한다.
- 다중 제품 동시 설치 시 지식 DB를 한 파일로 묶을지 제품별로 나눌지는 후속 배포 단계에서 결정한다.

### 4.2 교체 가능한 조합의 경계

- 검색 계층은 `search(product_id, version, query)` 개념을, LLM 계층은 `generate(question, evidence)` 개념을 유지한다.
- API 소비자는 특정 모델 파일명, llama.cpp 내부 프로토콜, FTS 인덱스 컬럼에 직접 의존하지 않도록 한다.
- LLM 교체에는 모델 파일·프롬프트·런타임 검증이 필요할 수 있다. **기존 FTS 지식 DB가 모델 가중치에 종속되는 것은 아니다.**
- 임베딩 검색 도입 시 별도 임베딩 생성·색인이 필요하며, FTS 인덱스만으로 벡터 검색이 구현되지는 않는다.
- 대체 검색/추론 엔진용 어댑터 구현은 초기 개발 범위에 포함하지 않는다.

## 5. HTTP API 계약 초안

Base URL: `http://127.0.0.1:<port>`; 포트 결정은 T05. 요청/응답 JSON UTF-8.

### GET /health

```json
{"status":"ready","engine_version":"0.1.0","knowledge_version":"2026-11-04"}
```

`ready`는 지식 검색 사용 가능 상태이며, LLM 로딩 여부 표시는 후속 검토한다.

### POST /search

요청:

```json
{"product_id":"example-program","version":"2.1.0","query":"데이터베이스 연결 실패"}
```

응답:

```json
{"results":[{"document_id":"example-db-troubleshooting","chunk_id":"example-db-001","title":"DB-1001: 데이터베이스 연결 실패","excerpt":"DB 서버 동작 여부를 확인합니다.","source_path":"manuals/database.pdf","page_from":12}]}
```

### POST /chat

요청:

```json
{"product_id":"example-program","version":"2.1.0","question":"데이터베이스가 연결되지 않는데 어디부터 확인하나요?"}
```

응답:

```json
{"answer":"먼저 DB 서버가 실행 중인지 확인한 다음 연결 주소와 포트를 점검하십시오.","grounded":true,"sources":[{"document_id":"example-db-troubleshooting","chunk_id":"example-db-001","source_path":"manuals/database.pdf","page_from":12}]}
```

근거가 없으면 `grounded=false`, `sources=[]`로 표시하고 추측성 해결책을 작성하지 않는다. `grounded=true`는 정답 보증이 아니라 인용 근거 존재를 의미한다.

### POST /event

요청:

```json
{"product_id":"example-program","version":"2.1.0","event_id":"connection_failed","error_code":"DB-1001","screen_id":"database_settings"}
```

응답:

```json
{"matched":true,"rule_id":"example-db-1001","title":"데이터베이스 연결 실패","content":"DB 서버 상태, 연결 주소 및 포트를 확인하십시오.","source":{"document_id":"example-db-troubleshooting","chunk_id":null}}
```

일치 규칙이 없으면 `matched=false`를 반환한다. 이 경로는 기본적으로 LLM을 호출하지 않는다. 현 API 4개 외에 지식 관리 API를 임의로 추가하지 않는다. 초기 DB 갱신은 제작자 도구가 담당한다.

## 6. 로컬 보안 및 신뢰성

- 리스너는 `127.0.0.1`에만 바인딩하며 `0.0.0.0`을 사용하지 않는다.
- localhost 자체가 인증 수단은 아니다. 웹 연동의 Origin/CORS, 로컬 접근 토큰 여부 및 브라우저별 정책을 T05~T06에서 검증한다.
- 비밀값, 연결 문자열, 사용자 개인정보를 질문/이벤트에 무분별하게 전달하거나 기록하지 않는다.
- 원본 문서 안에 포함된 지시문이 시스템 규칙을 덮어쓰지 않도록 문서를 비신뢰 데이터로 처리한다.
- 제품 버전 해석 실패나 규칙 충돌 시 성공으로 간주하거나 임의의 안내문을 선택하지 않는다.
- 지식 DB 갱신/교체 중 일부만 변경된 DB가 사용자에게 노출되지 않도록 무결성 확인 및 안전한 교체 방법을 T02/T07에서 검증한다.

## 7. 검증 완료 조건

### T01 문서 완료

- 요구사항·제외 범위·초기 조합이 구분됨.
- 문서·청크·오류/이벤트 규칙의 데이터 필드 정의됨.
- 네 가지 API의 요청·응답과 출처가 정의됨.
- 문서 추가·수정·삭제·전체 재색인의 목표 동작과 자료 독립성이 명시됨.
- 다중 제품 사용, 모델/검색 백엔드 교체 경계가 명시됨.
- 구현 전 확인할 미결정 사항이 구분됨.

### 후속 구현 검증

- PDF/DOCX/TXT/MD 변환·출처 추적 및 미추출 페이지 알림.
- 추가·수정·삭제·전체 재색인 후 검색 DB의 정합성.
- 제품별/버전별 규칙 격리 및 오류 코드 정확 매칭.
- 한국어 띄어쓰기·동의어 검색 품질.
- 근거가 없는 질문에 대한 비근거 답변 억제.
- Windows 사용자별 모델·추론 실행 환경 선택을 지원하며, 특정 RAM/CPU/GPU의 응답 속도·메모리 실측은 필수 승인 조건에서 제외한다(T09 결정).
- 인터넷 차단·Docker 미설치 상태의 처음 설치 및 첫 실행.
- 웹 브라우저와 Windows 앱에서 localhost 호출 검증.
- 배포 모델·런타임 라이선스/해시 검증 및 갱신 가능한 DB 파일 포맷 검증.

## 8. 미확정 사항 — 근거 없이 결정하지 않음

1. `product_id` 명명 규칙과 제품 간 데이터 분리 단위.
2. 제품 버전 파싱·경계 포함 규칙 및 규칙 충돌 처리.
3. 정확한 GGUF 파일명/양자화/출처·라이선스·SHA-256.
4. Builder 언어 및 PDF/DOCX 추출 라이브러리.
5. 한국어 FTS5 토큰화·랭킹·청크 분할과 재색인 동작.
6. 수정된 문서의 ID 유지 정책과 스키마/패키지 버전 관리 규격.
7. HTTP 포트·Origin/CORS/토큰 정책.
8. 모델 실행/종료 및 동시 요청 정책.
9. 전체 DB 교체를 위한 설치·무결성·롤백 방식.
10. 원문 PDF를 사용자 패키지에 함께 포함할지 여부.

## 9. Task 연계

- **T02:** Knowledge Builder 및 추가·수정·삭제·재색인 구현/검증.
- **T03:** SQLite FTS5 기반 검색, 정확 매칭, 제품·버전 필터.
- **T04:** llama.cpp + Qwen3 1.7B 및 근거 기반 답변.
- **T05:** 로컬 API 네 개 및 접근 제어 검증.
- **T06:** 웹/Windows 연동 예제.
- **T07:** 독립형 오프라인 패키징·지식 DB 갱신.
- **T08:** 통합·성능·모델 비교 및 실제 오프라인 검증.

**본 문서에서 승인한 것은 요구사항과 개발 방향이며, 후속 구현의 상세 기술 선택을 검증 없이 확정한 것은 아니다.**
