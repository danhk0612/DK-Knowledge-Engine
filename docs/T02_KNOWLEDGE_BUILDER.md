# T02 — Knowledge Builder: 사용법 및 설계 결정

상태: T02 구현 및 테스트, T03 검색 모듈·T04 LLM·T05 API는 포함하지 않습니다.

## 사용 환경과 명령

제작자 PC에 Python 3.11 이상과 SQLite FTS5가 필요합니다. 사용자 PC에서의 별도 Python 및 PDF 라이브러리 설치는 T07 패키징 목표에서 제외합니다.

```powershell
python -m pip install -r requirements-builder.txt
python -m builder.knowledge_builder --source ./sources --database ./output/knowledge.db
python -m builder.knowledge_builder --source ./sources --database ./output/knowledge.db --rebuild
```

회귀 테스트(테스트 PDF 생성 라이브러리 포함):

```powershell
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
```

Builder 실행 중 네트워크 호출은 수행하지 않습니다. 의존성 파일은 제작자 환경에서 미리 다운로드할 수 있습니다.

## 입력 파일

```text
sources/
  example-program/
    manuals/
      setup.pdf
      setup.pdf.meta.json    # 선택
      guide.docx
      faq.md
      notes.txt
    rules/
      DB-1001.json          # 선택
  another-program/
    manuals/
      setup.md
```

- 첫 번째 하위 폴더가 `product_id`이며, 제품 ID를 파일 내용에서 추측하지 않습니다.
- PDF/DOCX/TXT/MD를 그대로 넣습니다. 전체 매뉴얼을 JSON으로 변환할 필요는 없습니다.
- `*.meta.json`의 선택 필드: `document_id`, `title`, `version_from`, `version_to`, `language`. 생략 시 제목은 파일명, 언어는 `ko`입니다.
- PDF 텍스트 페이지는 1부터 번호를 기록합니다. DOCX 페이지 번호는 추출하지 않으며 문단·표·절 제목을 저장합니다.
- 오류 규칙의 JSON에는 `rule_id`, `product_id`, `document_id`, `title`, `content`와 `event_id` 또는 `error_code`를 기입합니다. 선택 필드는 `screen_id`, 버전 범위, `chunk_id`입니다.

문서 메타데이터 예시 (`setup.pdf.meta.json`):

```json
{
  "document_id": "example-setup-manual",
  "title": "설정 안내서",
  "version_from": "2.0.0",
  "version_to": "2.5.0",
  "language": "ko"
}
```

규칙 예시 (`rules/DB-1001.json`):

```json
{
  "rule_id": "example-db-1001",
  "product_id": "example-program",
  "error_code": "DB-1001",
  "event_id": "connection_failed",
  "document_id": "example-setup-manual",
  "chunk_id": null,
  "title": "DB 연결 실패",
  "content": "DB 서버 상태와 접속 설정을 확인하십시오."
}
```

규칙이 참조한 문서 및 청크가 없거나 다른 제품 문서이면 등록을 중단합니다. 버전 범위 **비교와 규칙 매칭**은 T03 범위입니다.

## DB 스키마 및 갱신 계약

`schema_info`: `schema_version=1`, `tokenizer=unicode61`  
`documents`: 제품, 문서 경로·형식·제목·버전·언어·해시  
`chunks`: 문서 ID·순서·제목·본문·페이지  
`chunks_fts`: SQLite FTS5 검색 인덱스, 트리거로 청크와 동기화  
`help_rules`: 오류 및 이벤트별 사전 승인 안내문과 출처  

- `document_id`를 명시하지 않으면 **원본 루트 기준 상대경로 SHA-256 앞 24자리**로 결정합니다. 동일 경로에서 문서 내용만 변경하면 문서 ID가 유지됩니다.
- `chunk_id`는 `document_id:000001`처럼 순번으로 생성합니다. 문서 구성 변경 시 동일한 순번 ID가 다른 내용을 나타낼 수 있으므로 **외부 영구 참조로 사용하지 않습니다**.
- 문서 원본 해시와 메타데이터 해시로 변경 여부를 판정하며, 불변 문서는 재추출하지 않습니다.
- 문서 추가·변경·삭제, 청크 교체, FTS5 동기화, 규칙 유효성 검사는 SQLite 트랜잭션에서 수행합니다.
- 첫 생성과 `--rebuild`는 임시 파일에 DB를 생성한 뒤 성공할 때 대상 파일로 교체합니다. 사용자 PC의 배포 후 DB 교체·롤백은 T07에서 다룹니다.
- 다른 검색 엔진으로 옮길 때 기존 FTS DB 파일을 공통 포맷으로 간주하지 않고 **원본 문서에서 재색인**합니다.
- 스키마 버전 불일치 시 자동 변환하지 않고 중단합니다.

## 알려진 한계

- SQLite 기본 `unicode61`은 한국어 형태소 분석을 하지 않습니다. 조사·띄어쓰기·동의어 차이에 취약하며, 한국어 검색 개선은 T03에서 검증합니다. [공식 SQLite FTS5 문서](https://www.sqlite.org/fts5.html)
- `pypdf`는 OCR을 제공하지 않습니다. 전체 페이지가 스캔 이미지라 텍스트가 없으면 작업 실패, 일부 페이지만 텍스트가 없으면 경고합니다. [pypdf 추출 안내](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)
- 복잡한 PDF 표·이미지·DOCX의 머리글·바닥글·부동 개체는 추출 누락 또는 순서 왜곡이 있을 수 있습니다.
- 청크는 최대 **1,200문자**로 나눕니다. 최적의 검색 청크 크기는 T03에서 검증할 사항입니다.
- T02는 DB **생성 도구**이지 검색 API나 LLM 생성 기능이 아닙니다.

## 테스트 범위

자동 생성한 PDF·DOCX와 TXT·MD를 이용하여 원본 해시 불변, 페이지·절·표 출처, 문서 중복 방지, 추가·수정·삭제, FTS 검색 결과 반영, 규칙 참조, 재생성과 증분 갱신 정합성, 무효 PDF·규칙에 대한 기존 DB 보존, 한국어 FTS5의 토큰화 한계를 검증합니다.
