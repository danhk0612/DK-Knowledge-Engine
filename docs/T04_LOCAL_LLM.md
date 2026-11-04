# T04 — Qwen3 1.7B + llama.cpp 로컬 LLM 연결

## 목표 및 범위

T03 `search_documents()`의 근거 청크를 llama.cpp `llama-completion`에 전달하는 **제작/검증 단계의 최소 CPU 추론 계층**입니다. 이 작업에는 별도의 로컬 API 서버, 인터페이스, Docker, 파인튜닝, 자동 다운로드, 모델 배포 파일이 없습니다.

T03의 `match_event()`는 별도 경로로 남아 있어 오류·이벤트 정확 매칭 시 LLM을 사용하지 않습니다.

## 모델 및 런타임 출처

| 항목 | 기준 |
|---|---|
| 모델 저장소 | https://huggingface.co/ggml-org/Qwen3-1.7B-GGUF |
| 모델 파일 | `Qwen3-1.7B-Q4_K_M.gguf` (약 1.28GB) |
| 모델 표시 커밋 | `daeb8e2` (Hugging Face 표시 축약) |
| 모델 SHA-256 | `d2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5` |
| 원본 및 GGUF 배포 라이선스 | Apache-2.0 (원본 모델 및 제공 모델 카드에 표시) |
| 런타임 | https://github.com/ggml-org/llama.cpp (MIT), 릴리스 `v0.8.0` CPU 빌드 평가 |
| 런타임 해시 | CI에서 정확한 커밋 SHA 기록. Windows 배포 바이너리의 파일 해시는 **T07에서 별도 확인** |

모델 GGUF는 공개 GitHub 저장소에 포함하지 않습니다. 사용자에게 모델 파일을 전달할 경우 라이선스·NOTICE 의무를 검토합니다. 실제 파일 SHA-256 검증 없이 원본 인증이 완료됐다고 표시하지 않습니다.

## 로컬 사용 예

Python 3.11 이상(제작 PC), T02/T03 코드, 로컬 `llama-completion` 실행 파일 및 GGUF 파일 준비 후:

```python
from llm.local_llm import LlamaCli, answer_from_knowledge

local_llm = LlamaCli(
    executable=r"C:\ai-runtime\llama-completion.exe",
    model=r"C:\ai-runtime\Qwen3-1.7B-Q4_K_M.gguf",
    threads=4,
    ctx_size=4096,
    max_tokens=192,
)
result = answer_from_knowledge(
    r"C:\knowledge\knowledge.db",
    product_id="my-product",
    version="2.1.0",
    question="DB 연결 오류를 어떻게 해결하나요?",
    generator=local_llm,
)
print(result)
```

모델은 질문 때마다 CLI 프로세스로 로드하므로 첫 응답과 동시 요청 처리 성능이 제한적입니다. 향후 T05의 API 서버 프로세스 생명주기/동시성 정책은 별도 결정입니다. `llama-completion`는 CPU 전용 `-ngl 0`으로 실행하고 GPU는 필요 없습니다.

출력 구조: `answer`(한국어 답변), `grounded`(검색 근거가 있고 지정된 모름 문구가 아닌가), `sources`(T03 출처), 성공 호출 시 `elapsed_seconds`(모델 호출 소요). 근거가 없으면 모델 호출 없이 `grounded=false`, `sources=[]`를 반환합니다.

**`grounded=true`는 답변의 사실성 보증이 아닙니다.** 근거가 검색됐다는 의미에 가까우며, 소형 모델은 잘못된 주장을 생성할 수 있습니다. 프로그램 자동 수리 명령으로 실행하지 않습니다.

## 검증

```powershell
python -m unittest discover -s tests -v
```

공식 Qwen3 GGUF 및 llama.cpp로 CPU를 실사용한 검증은 `.github/workflows/t04-cpu-smoke.yml`을 통해 실행합니다. 테스트는 매뉴얼에만 존재하는 `3308`을 답변에 포함하는지 확인합니다. 모델이 없으면 이 검증을 했다고 보고하지 않습니다.

## 알려진 한계

- `unicode61` 기반 T03 검색의 한국어 형태소 분석 미지원이 그대로 적용됩니다.
- 모델은 근거 문서 내용을 명령이 아닌 데이터로 취급하도록 프롬프트를 구성하지만, 프롬프트 인젝션 및 환각이 완전히 방지되는 것은 아닙니다.
- 추론 결과 품질/속도는 실제 CPU·운영체제·컨텍스트 길이에 따라 달라집니다. 8GB RAM 최소 사양은 T08에서 검증해야 합니다.
- 초기에 Qwen3 1.7B Q4_K_M 단일 모델만 검증합니다. 모델 변경·Qwen3.5 2B 비교는 T08 범위입니다.

실모델 출력 검증은 명령줄 안내 배너·프롬프트 재출력을 답변으로 오인하지 않도록 확인해야 합니다.
