# T08 — 통합 검증 및 소형 모델 비교

## 현재 상태

**T08 자동 검증 완료(실기 검증 대기).** T07을 변경하지 않고 기존 Windows x64 포터블 ZIP을 그대로 검사합니다. 실제 Windows 10/11 고객 PC에서 측정하지 않았으므로 **최종 완료가 아닌 부분 검증**으로 기록합니다.

## 1. Windows CPU/메모리 계측

대상: [T07 통과한 포터블 ZIP](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41787427470)의 Actions 아티팩트 `DK-Knowledge-Engine-Win-x64-demo-T07`.

- 동일 ZIP을 Windows GitHub Actions 머신에 압축 해제합니다. **설치된 Python이 아니라 ZIP 내 `DK-Knowledge-API.exe`**를 실행합니다.
- 기존 T07 테스트와 같이 프로세스의 PATH를 Windows 시스템 디렉터리로 제한하고 외부 HTTP 프록시를 사용 불가한 주소로 설정합니다. 이것은 **실제 네트워크 차단 검증을 대체하지 않습니다**.
- API health, 검색, 이벤트 및 제품·버전 격리, 검색 근거가 없을 때의 응답을 검사합니다.
- 한국어 오류·포트 질문을 CPU로 3회 생성하여 요청 시간·일치율·출처를 측정합니다. **같은 모델을 매번 새 프로세스로 로드하는 현재 T04 구현**의 비용을 포함합니다.
- `psutil`로 실행 파일과 자식 llama.cpp 프로세스의 RSS를 50ms 간격으로 샘플링합니다. **RSS의 단순 합계는 공유 메모리를 중복 합산할 수 있으므로 실제 물리 RAM 사용량의 상한도 아닙니다**. 예제 사용자 PC의 하드웨어 정보가 아니라 GitHub Hosted Windows 환경에서의 계측치입니다.
- 측정 원문 결과: `T08-windows-portable-metrics` Actions JSON 아티팩트.

`tests/t08_windows_benchmark.py`는 8GB RAM 실제 PC가 아니면 `8gb_target_machine=false`를 기록합니다. 절대 8GB PC 권장 사양을 이 결과만으로 확정하지 않습니다.

### 아티팩트 유효 기간

현재 CI는 이미 검증된 **T07 run 41787427470** 아티팩트를 재사용하며, 2026-11-11 이후 만료될 수 있습니다. 해당 아티팩트가 만료되면 T07 CI에서 ZIP을 새로 검증·생성한 후 워크플로의 소스 run ID를 갱신해야 합니다. 검증하지 않은 바이너리나 다른 커밋의 ZIP으로 자동 대체하지 않습니다.

## 2. 동일 런타임 CPU 모델 비교

T07의 배포 런타임은 **llama.cpp v0.8.0 + Qwen3 1.7B**로 유지합니다. Qwen3.5는 별도 실험에서 **두 모델 모두 동일한 llama.cpp v0.9.0**을 이용해 비교합니다. 그러므로 두 모델의 **동일 환경 내 상대 비교**는 가능하지만, 모델별 실행 수치를 T07 v0.8.0 Windows 배포 수치와 직접 동일시하면 안 됩니다.

| 항목 | Qwen3 1.7B | Qwen3.5 2B |
|---|---|---|
| GGUF 소스 | `ggml-org/Qwen3-1.7B-GGUF` | `gguf/Qwen3.5-2B-GGUF` |
| 양자화 | Q4_K_M | Q4_K_M |
| 검증 방식 | 정확한 SHA-256 파일 | 정확한 SHA-256 파일 |
| 실행 엔진 | 동일 llama.cpp v0.9.0 CPU | 동일 llama.cpp v0.9.0 CPU |
| 옵션 | 4 threads, 2048 context, 192 tokens, temp 0, GPU layers 0 | 동일 |
| 시험 내용 | 동일 한국어 매뉴얼 5개 질문 | 동일 |

모델과 런타임의 다운로드는 **CI 빌드/검증 PC에서만** 수행합니다. 사용자 PC에 인터넷 접속 기능을 추가하지 않습니다. Qwen3.5 GGUF의 SHA-256은 `9a3d0aa6c920f096441139b6a254542da855223fdad06855ea00c6c087fd713d`입니다.

5개 사례는 DB 포트 구분, API 포트, 오류 코드 분기, 도움말 단축키, 업데이트 전 사전 절차입니다. 평가기는 정답 키워드가 포함되면서 명백히 잘못된 키워드는 없는지 기계적으로 검사합니다. **한정된 키워드 검사는 정답률의 완전한 정의가 아니며, 5개 사례만으로 모델 선택을 확정하지 않습니다.** 모델별 전체 출력·종료 코드·지연 시간·프로세스 RSS를 `T08-llm-comparison-evidence` JSON으로 보존합니다.

## 3. 실제 고객 PC에서 추가 검증 필요

1. Windows 10과 Windows 11 x64, **GPU 없는 실제 8GB RAM PC**에서 모델 로딩/피크 메모리/3~10회 연속 질의와 다른 업무 프로그램 동시 실행 성능 측정.
2. 네트워크 어댑터 비활성화 또는 케이블 분리 상태에서 설치·시작·검색·AI 답변·DB 갱신 테스트.
3. 실제 고객 매뉴얼을 이용한 검색 재현율·질문별 근거 품질·환각/거절 정책. 제품·버전 여러 조합.
4. 실제 사내 HTTPS 웹페이지에서 Chrome/Edge Local Network Access 권한·조직 정책과 CORS 허용 동작 확인.
5. 서명되지 않은 EXE/ZIP의 SmartScreen·백신·조직 보안 정책 및 제3자 DLL/모델 라이선스·NOTICE의 재배포 점검.

**이 항목이 확인되지 않으면 T08은 부분 검증 상태이며 최종 생산 배포 적합 판정은 보류**합니다.

## CI 실행 및 재현

[GitHub Actions `T08 CPU evidence and model comparison`](../.github/workflows/t08-benchmarks.yml)에서 동일 SHA 모델과 출처·명령을 고정하여 재현할 수 있도록 했습니다.

- `tests/t08_windows_benchmark.py --zip <검증된 T07 ZIP> --output t08-results`
- `tests/t08_model_comparison.py --llama-completion <v0.9.0 바이너리> --qwen3 <GGUF> --qwen35 <GGUF> --llama-revision <commit> --output t08-results`

두 실험의 계측 환경은 다르며, 결과를 비교할 때는 OS/호스트 RAM/CPU/실행 엔진 버전 차이를 반드시 포함해야 합니다.

## 4. 2026-11-05 GitHub Actions 실측 기록

기존 배포 프로그램을 고친 결과가 아니라 **이미 T07에서 검증한 Windows x64 ZIP**을 그대로 측정한 결과입니다.

### Windows 호스팅 CPU 계측

| 지표 | [첫 실행 41950331007](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41950331007) | [재실행 41951563077](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41951563077) |
|---|---:|---:|
| 호스팅 RAM | 16,378.7 MiB | 16,378.7 MiB |
| CPU | 4 논리/2 물리 코어 | 동일 유형 러너 |
| 한국어 포트 답변 | 3/3 | 3/3 |
| AI HTTP 호출 중앙값 | 12.298초 | 10.240초 |
| AI HTTP 호출 최대 | 12.332초 | 10.474초 |
| API + 자식 모델 프로세스 합산 RSS 피크 | 2253.1 MiB | 2253.2 MiB |
| 검색/이벤트/제품·버전 격리 | 모두 통과 | 모두 통과 |

첫 실행의 `/health` 0.023초, 검색 0.016초, 오류 규칙 0.018초는 LLM과 비교하기 위한 참고값입니다. **CI 러너는 Windows 10/11 8GB 고객 PC가 아닙니다.** RSS는 공유 페이지가 중복 집계될 수 있는 50ms 샘플 합계이며 RAM 사용량의 절대값은 아닙니다.

### 동일 llama.cpp v0.9.0 Linux CPU 모델 비교

| 지표 | Qwen3 1.7B Q4_K_M | Qwen3.5 2B Q4_K_M |
|---|---:|---:|
| 한국어 매뉴얼 5문항 | 5/5 | 5/5 |
| [첫 실험 41950996925](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41950996925) 중앙값 | 2.574초 | 2.339초 |
| [수정 채점 CI 41951563077](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41951563077) 중앙값 | 4.424초 | 4.224초 |
| 수정 채점 CI 프로세스 RSS 피크 | 2163.2 MiB | 1963.7 MiB |

- 첫 시도에서 Qwen3.5의 엄격한 Jinja 템플릿이 `No user query found in messages`로 실패하여, 이후 두 모델에 **동일한 명시적 ChatML 메시지·`-no-cnv`**를 전달했습니다. 배포용 T07의 프롬프트/런타임 설정은 수정하지 않았습니다.
- 최초 채점은 E-205의 정답인 **“불필요한 파일을 정리해야 합니다”**를 `저장`과 `파일` 두 단어가 동시에 없다는 이유로 오답 처리했습니다. 원문 응답을 확인한 후 허용 가능한 표현을 명시했고, **최신 CI에서 두 모델 모두 5/5**로 판정됐습니다. 이는 사후 채점 규칙 수정임을 기록하며 정답률의 일반화는 금지합니다.
- 모델 Qwen3.5 GGUF는 `gguf/Qwen3.5-2B-GGUF`의 고정 SHA-256 파일로, 공식 Qwen 가중치를 제3자가 양자화한 배포본입니다. 실제 상용 재배포 시 원본 모델 카드·라이선스·GGUF 배포자의 출처 확인이 추가로 필요합니다.
- 서로 다른 CI 실행에서 두 모델의 시간 차이는 수 초 수준으로 달라졌습니다. 이번 결과만으로 **Qwen3.5의 실사용 속도 우위 또는 메모리 우위를 확정할 수 없습니다**. 품질·속도·배포 검증이 충분한 기존 **Qwen3 1.7B + llama.cpp v0.8.0 구성 유지**를 권고합니다.

### 품질 판정 및 잔여 조건

**자동화된 개발/CI 검증 범위 내에서는 통과했지만, 고객 PC 배포 적합 판정은 미완료입니다.** 실제 8GB RAM 무GPU Windows 10/11 기기, 물리적 네트워크 차단, 현장 제품별 매뉴얼·오류의 다수 사례, Chrome/Edge LNA 권한, 보안 정책/SmartScreen, 제3자 재배포 검증은 계속 필요합니다.

원시 데이터는 두 실행의 `T08-windows-portable-metrics`, `T08-llm-comparison-evidence` Actions 아티팩트에 JSON으로 보관됩니다(7일 보존). 대용량 모델 자체는 저장소에 커밋하지 않았습니다.
