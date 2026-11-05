# T10 — 근거 정확성·HTTP 경계·배포 검증

**범위:** 모델·RAG 검색·API·Windows 포터블 패키지는 수정하지 않고 **검증 도구와 샘플 데이터만** 추가합니다. 실제 고객 매뉴얼은 제공되지 않았으므로 자동 CI는 저작권 문제가 없는 인공 자료로 수행하며, **고객 배포 적합 판정은 아직 완료되지 않았습니다.**

## 1. 검증 도구

- `tests/t10_fixture.py`: T02 Builder로 서로 다른 제품 및 지원 버전의 테스트 DB 생성.
- `tests/t10_cases_sample.json`: 기대 검색 결과·승인 오류 규칙·정답 단어·오답 금지 단어·출처 및 증거 텍스트를 선언.
- `tests/t10_eval.py`: **이미 실행 중인 localhost API**에 요청하고 실제 DB 검색 결과와 답변의 인용 출처를 대조. 고객 질문과 생성 답변 원문을 보고서에 저장하지 않음.
- `tests/t10_run_portable.py`: Windows에서 T09 포터블 ZIP을 기동하고 기존 Verify-AIHelp.ps1로 패키지 무결성·라이선스 고지 파일 존재 여부를 확인한 후 위 평가를 실행.
- `tests/test_t10_quality_eval.py`: 고정된 인공 생성기와 실제 HTTP API를 이용해 정답/오답·인용 위조·자료 격리·보고서 비식별화 판정 자체를 회귀 테스트.
- `.github/workflows/t10-validation.yml`: Windows·Ubuntu 단위 테스트와 실제 T09 Qwen3 포터블 ZIP 통합 검증.

이번 변경에서는 사용자 PC의 RAM/CPU/GPU/응답 시간·메모리를 측정하거나 사양별 통과 여부를 판정하지 않습니다. **T09 모델/실행 파일 선택 정책을 유지합니다.**

## 2. 자동 채점 범위

### 실제 지식 DB와 출처 대조

| 테스트 | 자동 판정 |
|---|---|
| 검색 | 요청한 제품·버전에 해당하는 출처 포함, 금지 출처 없음 |
| 승인 오류 이벤트 | 예상 `rule_id`, 표시할 포트·문구 및 지식 출처 대조 |
| 근거 있는 AI 답변 | `grounded=true`, 정답 단어 포함·오답 단어 미포함 |
| 인용 근거의 진위 | 표시된 `document_id`·`chunk_id`·`source_path`·페이지가 **동일 질문의 실제 FTS 검색 결과**와 일치해야 함 |
| 근거 내용 | 기대 텍스트가 인용된 검색 청크 안에 있어야 함 |
| 다른 제품/버전 | 해당되지 않는 출처가 반환되면 실패 |
| 근거 없는 질문 | `grounded=false`, 출처 배열이 비어야 함 |

샘플 사례는 두 제품의 서로 다른 데이터베이스 포트(3308/9999), 이전 버전 포트(3310), 승인 오류 코드 및 존재하지 않는 제품과 지원 외 버전을 포함합니다.

**주의:** 정답 단어가 있다는 이유만으로 자연어 답변 전체가 참임을 증명할 수는 없습니다. 모델이 “3308을 사용하지 마세요”라고 답해도 키워드 검사를 통과할 수 있습니다. `grounded=true`는 실제 문서를 검색했다는 뜻일 뿐 모델 답변이 사실이라는 보증이 아닙니다. 자동 평가를 통과한 경우에도 실제 고객 질문·답변·인용 원문에 대한 담당자 판정이 필요합니다.

### HTTP 경계

- 허용하지 않은 브라우저 `Origin`에서의 POST 거부.
- 위조된 `Host` 요청 거부.
- 올바른 루프백 Host에서 `/health` 조회 허용.
- 허용하지 않은 Origin의 OPTIONS 사전 요청 거부.
- 차단된 요청에는 `Access-Control-Allow-Origin`이 반환되지 않아야 함.

위 테스트는 **API의 자체 접근 제한**만 검증합니다. 인터넷 접속을 물리적으로 끊은 상태의 실행, 실제 기업 웹사이트의 Chrome/Edge Local Network Access 승인, 로컬 악성 프로그램 접근 제어, Windows SmartScreen 정책까지 입증하지는 않습니다.

## 3. 개발자 환경에서 재현

### 샘플 자료로 실행

1. T09 Windows 포터블 ZIP을 임의 경로에 풉니다.
2. 개발 PC에 `requirements-builder.txt`의 Python 패키지를 설치하고 다음 명령으로 인공 지식 DB를 생성합니다.

~~~powershell
python tests/t10_fixture.py --output ".\t10-sample.db"
~~~

3. 포터블 API를 종료한 다음 해당 ZIP의 `Update-Knowledge.ps1`로 DB 파일을 안전하게 교체합니다. 새 DB의 독립 SHA-256 값을 인자로 전달해야 합니다.

~~~powershell
$hash = (Get-FileHash ".\t10-sample.db" -Algorithm SHA256).Hash.ToLowerInvariant()
& "D:\DK-Knowledge-Engine-Win-x64\Update-Knowledge.ps1" -SourceDb ".\t10-sample.db" -ExpectedSha256 $hash
~~~

4. 포터블 API를 실행한 후 다음 명령으로 평가합니다. 이 평가 CLI 자체는 **개발자용 Python 도구**이며 고객에게 배포한 엔진에 Python 설치를 요구하지 않습니다.

~~~powershell
python tests/t10_eval.py --database "D:\DK-Knowledge-Engine-Win-x64\knowledge\knowledge.db" --cases ".\tests\t10_cases_sample.json" --port 8765 --output ".\t10-results\quality.json"
~~~

기존 데이터는 T07의 갱신/롤백 절차를 준수하여 백업 후 교체하십시오. 인공 샘플 DB로 고객 데이터베이스를 덮어쓰지 않도록 **별도의 시험용 압축 해제 폴더**에서 실행하는 것이 원칙입니다.

### 실제 고객 매뉴얼 검증

- 고객이 배포할 권리가 있는 문서를 개발/운영 PC에서 T02 Builder로 색인합니다.
- 질문별로 제품 ID, 적용 버전, 실제 매뉴얼 출처, 필수 답변, 잘못된 안내 예시와 근거 확인 텍스트를 검토자가 **별도의 비공개 JSON 사례 파일**에 작성합니다.
- 비공개 PC에서 API를 시작해 `t10_eval.py`를 실행합니다. 공개 GitHub Actions에는 고객 매뉴얼·질문·답변 원문을 올리지 않습니다.
- JSON에는 질문/답변 텍스트와 출처 경로를 저장하지 않습니다. 다만 원본 사례 파일과 DB 자체는 민감할 수 있으므로 로컬에 보관합니다.
- 실패 사례는 별도 승인된 로컬 과정에서 질문·답변·매뉴얼 근거를 비교하여 사람이 판정하고, 정답 기준을 임의로 낮추지 않습니다.

## 4. 배포/오프라인 경계 및 잔여 점검

CI는 기존 T09 Windows ZIP에서 사용된 `Verify-AIHelp.ps1`, 지식 DB 전체 교체, 모델 추론, 루프백 HTTP 경계를 확인합니다. 실행 환경의 PATH를 시스템 디렉터리로 제한하고 HTTP(S) 프록시를 무효 주소로 설정하지만, **물리적으로 인터넷 연결이 끊겼음을 증명하지는 못합니다.**

라이선스 텍스트 4종(기본 Qwen3, llama.cpp, CPython, PyInstaller)이 포함됐는지 검사하지만 재배포권·NOTICE·실행 파일 서명·제3자 DLL 전체를 법적으로 승인하지는 않습니다. 사용자가 T09에서 추가하는 모델/런타임 파일은 기본 패키지 불변 해시 목록에 자동 등록되지 않습니다.

**정식 고객 배포 승인 보류 항목:** 실제 고객 문서와 다수 질문에 대한 담당자 정답성·환각 검토, 물리적 네트워크 차단 상황 검증(필요시), 사내 HTTPS 브라우저 권한, SmartScreen/코드 서명·라이선스 고지 확인. 하드웨어별 성능 측정은 필수 조건이 아닙니다.

## 5. CI 증거

[T10 GitHub Actions](../.github/workflows/t10-validation.yml)는 **동일 Actions 실행에서 T07→T09를 재빌드·실제 모델 검증한 ZIP**을 받아 인공 DB로 교체한 뒤 실모델 질문 및 차단된 Origin/Host를 검증합니다. 만료된 과거 실행 번호/아티팩트에 의존하지 않습니다. 실제 고객 데이터는 사용하지 않습니다. CI 리포트는 7일 보관되는 JSON 아티팩트이며, 통과 사례 ID와 실패 원인 코드만 포함합니다. 테스트 결과가 통과하기 전에는 검증 성공으로 표기하지 않습니다.

## 6. 실제 T10 CI 확인 결과 (2026-11-05)

- [GitHub Actions run 41958831101](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41958831101) **성공**.
- 평가 도구의 Windows·Ubuntu 단위 테스트 각 **5개 통과**. 인용 위조, 잘못된 제품의 출처, 답변과 문서의 모순이 실제 실패로 처리됨을 검증했습니다.
- 기존 [T09 검증 포터블 ZIP](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41955872865)의 고객 자료 없는 인공 DB를 T07 지식 갱신 스크립트로 교체했으며, 기존 SHA-256/SQLite 검증에 통과했습니다.
- 실제 Qwen3 모델 답변을 포함한 **14개 품질·HTTP 보안 게이트 모두 통과(14/14)**. 두 제품의 3308/9999 포트, 구버전 격리, 승인 오류 코드, 문서·청크 인용 일치, 무근거 응답, 위조 Host·미허용 Origin/OPTIONS 차단을 확인했습니다.
- Actions 아티팩트 `T10-synthetic-quality-and-http-boundaries`에는 원시 질문·답변·출처 경로가 없으며 테스트 ID·통과 여부·실패 코드·검증 범위만 포함됩니다(7일 보존, 2026-11-12 만료 예정).
- 테스트에서 외부 HTTP 프록시 무효 및 제한된 PATH를 사용했지만 **물리적으로 네트워크를 차단한 것이 아니며**, 브라우저 사내 정책, 서명/SmartScreen, 라이선스 적합성 최종 판정 및 실제 고객 문서 수동 평가는 여전히 미검증입니다.

따라서 **T10 자동 검증 체계는 통과했지만, 고객 배포 적합성 최종 승인으로 해석하지 않습니다.**
