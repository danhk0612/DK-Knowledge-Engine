# v0.2.0 — 실제 매뉴얼 Client 재검증 준비

**목표:** 기존 작성용 `knowledge.db`를 변경하거나 다시 색인하지 않고, CI 성공 커밋의 개선된 오프라인 엔진과 독립형 Client로 재패키징해 실제 문서 질문을 재검증합니다. **실제 질문·답변·고객 자료는 공개 GitHub에 추가하지 않습니다.**

## 1. 시험용 Admin 및 Client 준비 (Windows PowerShell 5.1)

개발 저장소의 `feature/v020-batched-admin-client` 브랜치에서 실행합니다.

`tests/Prepare-Windows-RAG-Recheck.ps1`는 GitHub CLI(`gh`)로 지정한 **T12 success** 실행의 Admin ZIP만 다운로드합니다. 다운받은 ZIP과 실제 Client는 사용자 PC에서만 처리하며 GitHub CI로 사용자 DB를 전송하지 않습니다.

명령 예시 (제품 ID·제품명·DB 경로는 **로컬 테스트 데이터**에 맞게 변경):

~~~powershell
git pull --ff-only origin feature/v020-batched-admin-client

powershell.exe -NoProfile -File .\tests\Prepare-Windows-RAG-Recheck.ps1 `
  -RunId 43144191154 `
  -ExpectedCommit '0997d318e602d9038feddb22ae6b098458171b22' `
  -KnowledgeDb (Join-Path $env:LOCALAPPDATA 'DK-Knowledge-Engine\knowledge.db') `
  -ProductId 'example-product' `
  -ProductName 'Example Product' `
  -ProductVersion '1.0.0' `
  -AppName 'Example Help QA'
~~~

**주의:** 위 `example-product`는 예시일 뿐입니다. 실제 패키지의 제품 ID가 DB의 제품 ID와 다르면 작업은 실패해야 합니다. 필요하면 `-IconFile 'C:\path\app.ico'`를 추가하여 사용자 ICO도 검증할 수 있습니다. 기본 제공 아이콘으로 실행하려면 이 인자를 생략합니다.

스크립트는 다음을 수행합니다.

1. Actions 실행의 성공 상태와 **정확한 HEAD SHA**를 확인합니다.
2. Admin 아티팩트 한 개를 별도 폴더에 다운로드하고 압축을 풉니다.
3. 동봉 엔진의 `Verify-AIHelp.ps1` 및 **선택한 DB의 제품 ID**를 검증합니다.
4. 개선된 엔진·기존 DB·Client EXE로 새 Client ZIP을 생성하고 패키지 무결성을 검사합니다.
5. 기존 작성용 DB의 SHA-256이 변경되지 않았음을 확인합니다.
6. `RECHECK_RESULT.md`를 로컬에 작성합니다. **AI 모델을 실행하거나 질문에 자동으로 합격 판정을 내리지 않습니다.**

출력 기본 폴더: `DK-Knowledge-Engine-v020-RAG-Recheck\` (저장소의 `.gitignore`에 등록됨). 기존 폴더가 있으면 덮어쓰지 않고 중단합니다. 외부 경로를 `-OutputDir`로 지정한 경우는 별도로 관리합니다.

## 2. 실제 매뉴얼 검색·답변 점검

1. 구버전 Client는 트레이 우클릭 메뉴의 **완전 종료**를 통해 닫습니다. 로컬 엔진이 중복 실행되지 않아야 합니다.
2. 다음 새 EXE를 실행합니다.
   `.\DK-Knowledge-Engine-v020-RAG-Recheck\generated\DK-Knowledge-Engine-Client\DK-Knowledge-Client.exe`
3. 새 Client의 엔진을 시작하고, **기존과 동일한 질문 및 부정 사례**로 테스트합니다.
4. 각 질문에서 (a) 검색 출처 페이지, (b) 원문에 실제 있는 근거, (c) AI의 결론, (d) 사실을 뒤집거나 생략한 부분을 **모두 따로** 확인합니다.
5. 내용이 없는 질문은 `근거 부족`이어야 합니다. 복수 페이지 비교는 **각 페이지의 설명이 모두 검색되는지** 확인합니다.
6. 결과는 **로컬** `RECHECK_RESULT.md`에 기록합니다. 전체 PDF·DB·질문/답변 원문을 공개 Issue/PR에 업로드하지 않습니다.

정답 키워드가 포함되어도 “하지 않는다/할 수 없다” 같은 부정 표현을 반대로 해석했다면 **실패**입니다. 자동 회귀·샘플 검색 통과는 실제 사용자의 질문 품질 통과와 구분합니다.

## 3. 재검증 후

실제 Windows 질문에서 문제를 재현하면 질문 ID, 검색 결과 페이지, 잘못된 답변 문장과 **필요한 최소한의 비식별 맥락**만 공유합니다. 개선 코드는 기존 버전의 Admin EXE, Client EXE 내부에 자동으로 반영되지 않습니다. 정확한 CI 아티팩트 SHA에서 새 Client 패키지를 만들어 시험해야 합니다.

이 단계가 통과해도 PR 병합과 Preview/정식 Release에는 별도 승인이 필요합니다.
