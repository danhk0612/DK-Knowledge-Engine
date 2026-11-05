# T09 — 사용자별 로컬 모델·실행 환경 선택

## 목표 및 지원 범위

제품 지원을 위한 모델은 **단일 권장 사양에 고정하지 않습니다.** 사용자가 자신의 Windows PC에 맞게 설치한 GGUF 모델·llama.cpp 실행 파일 및 추론 설정을 선택합니다. 시스템 사양 자동 측정·자동 추천·모델 다운로드·성능 등급 판정은 하지 않습니다.

T07의 기본 파일 구성과 모델은 그대로 유지합니다. 새로운 T09에서는 **포터블 폴더 안에 추가한 모델·런타임을 선택하고 API를 재시작**하면 됩니다.

지원 대상은 **llama.cpp `llama-completion.exe` 형식과 호환되는 GGUF 모델**입니다. 모델마다 요구하는 llama.cpp 버전·토큰 형식·라이선스·양자화·지원 하드웨어가 다를 수 있습니다. 다른 백엔드(Ollama 등), 임의의 GGUF, 모든 GPU 빌드를 무조건 지원한다고 보장하지 않습니다.

## 사용자 구성 파일

Windows 포터블 ZIP을 압축 해제한 뒤 `config/settings.json`을 수정합니다.

~~~json
{
  "port": 8765,
  "allowed_origins": [],
  "model": {
    "file": "models/Qwen3-1.7B-Q4_K_M.gguf",
    "runtime": "runtime/llama-completion.exe",
    "threads": 4,
    "context_size": 4096,
    "max_tokens": 192,
    "timeout_seconds": 180,
    "gpu_layers": 0,
    "prompt_mode": "qwen3"
  }
}
~~~

| 설정 | 의미 |
|---|---|
| `file` | 선택할 GGUF 파일. `models/` 하위의 상대 경로만 허용 |
| `runtime` | 선택할 llama.cpp 실행 파일. `runtime/` 하위의 .exe만 허용 |
| `threads` | CPU 추론 스레드 수(양의 정수) |
| `context_size` | 모델에 전달할 컨텍스트 크기(양의 정수) |
| `max_tokens` | 답변 생성 토큰 수 상한(양의 정수) |
| `timeout_seconds` | 각 로컬 모델 추론 대기 제한(양의 정수) |
| `gpu_layers` | GPU에 올릴 레이어 수(0 이상). **기본 제공 CPU 전용 실행 파일에서는 0 유지** |
| `prompt_mode` | `qwen3`(기존 T07 방식) 또는 `raw_chatml`(ChatML 토큰 사용 모델용) |

예를 들어 `models/other-model.gguf` 파일을 모델 제공처와 라이선스를 확인하고 직접 복사한 뒤 `file`을 해당 상대 경로로 변경할 수 있습니다. GPU 빌드나 다른 버전의 llama.cpp를 사용할 경우 `runtime/` 아래 별도 이름의 EXE 및 필요한 **실행 의존 DLL을 함께 제공**해야 합니다. 선택한 모델이 해당 런타임과 호환되지 않으면 답변 생성이 실패할 수 있습니다.

`prompt_mode=raw_chatml`은 해당 GGUF가 ChatML 메시지 토큰을 지원하고 그 형식이 적합할 때만 선택하세요. Qwen3.5와 같은 모델은 이전 T08 실험에서 **새 llama.cpp 버전** 및 ChatML 프롬프트 조합으로만 검증했으며, T07에 포함된 v0.8.0 실행 파일로 해당 모델의 호환성을 보장하지 않습니다.

모델 변경은 **API 종료 → 모델·런타임 파일 배치 → 설정 편집 → API 재시작** 순서입니다. 이미 실행 중인 프로세스의 모델을 동적으로 교체하지 않습니다. 기본 GGUF는 패키지에서 제거할 필요가 없습니다.

## 구버전 설정과 무결성 범위

- 기존 T07의 `{"port":8765,"allowed_origins":[]}` 설정도 그대로 지원합니다. `model` 객체가 없으면 원래의 Qwen3 1.7B, CPU 4스레드, 4096 컨텍스트 등을 사용합니다.
- 설정에서 폴더 상위로 이동하는 `../` 경로, 다른 폴더의 파일, 유효하지 않은 수치, 존재하지 않는 모델·실행 파일은 **시작 전에 거부**합니다. 별도 외부 드라이브 절대 경로는 이번 버전에서 지원하지 않습니다. `models/`, `runtime/`에 복사 후 사용하세요.
- **기본 배포 모델·런타임은 기존 manifest.json SHA-256으로 검증합니다.** 사용자가 추가한 임의의 모델·실행 파일은 원래 패키지 manifest에 자동 등록되거나 서명·신뢰성 검증되지 않습니다. 관리자 또는 모델 제공처의 SHA-256, 라이선스·출처를 직접 확인해야 합니다.
- 웹 JavaScript/C# 호출 방법과 `/health`, `/search`, `/chat`, `/event` 응답 계약은 변경하지 않습니다.
- 기존 DB와 지식 갱신·롤백 스크립트는 변경하지 않습니다. 모델 선택과 문서 데이터는 서로 독립적입니다.

## 하드웨어 정책 변경

T08의 기존 측정 수치는 **과거 시험 자료로 보존**하지만 RAM 8GB, CPU 코어 수 또는 특정 GPU가 제품의 필수 승인 기준이 되지 않습니다. 성능이 필요한 사용자가 자신의 환경에 맞춰 경량 GGUF, 스레드 수, 컨텍스트 크기, CPU 전용/GPU 호환 실행 파일을 선택합니다. **사양 자동 탐지·권장 모델 자동 선택은 구현하지 않습니다.**

실제 고객 매뉴얼의 답변 타당성, 물리적 오프라인 동작 및 브라우저·보안 정책 확인은 사양과 별도의 검증 영역입니다.

## 검증

- `tests/test_model_selection.py`: 구설정 호환, 대체 모델·실행 파일 선택, 경로 탈출 거부, 파라미터 검증, 기존 Qwen 및 raw ChatML 호출 형태.
- `.github/workflows/t09-model-configuration.yml`: 검증된 T07 모델/CPU 런타임으로 **현재 T09 코드를 다시 PyInstaller 빌드**하고 포터블 ZIP을 생성·압축 해제하여 실제 기본 모델 및 선택한 모델 별칭·다른 이름의 실행 파일·추론 설정을 테스트합니다.
- 모델 별칭은 **같은 Qwen3 GGUF 데이터에 다른 파일명을 부여한 것**입니다. 다양한 GGUF 모델 아키텍처나 GPU 드라이버·CUDA 호환성을 테스트했다는 의미가 아닙니다. 추가 모델을 직접 검증할 때는 모델 제공처·실행 파일 버전·실제 Q/A 결과를 기록해야 합니다.
- 정상 통과한 샘플 ZIP 아티팩트는 7일 보존하며 정식 Release/tag는 만들지 않습니다.

## T09 Windows 통합 검증 기록 (2026-11-05)

- [Windows 포터블 ZIP 재빌드 및 모델 선택 CI 41955872865](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41955872865) **성공**. 새로운 PyInstaller 실행 파일을 포함한 포터블 ZIP을 생성해, 기본 Qwen3 1.7B 실모델 답변, 같은 Qwen3 데이터의 다른 이름 GGUF 선택, 다른 이름의 llama.cpp EXE 선택, 스레드/컨텍스트/토큰 설정, `raw_chatml` 답변, 누락 모델 거부를 확인했습니다.
- 같은 CI에서 T09 선택 설정 단위 테스트 7개 통과. 기존 [Windows/Ubuntu 회귀 각각 69개 성공](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41955872746).
- **다른 GGUF 아키텍처나 GPU 런타임의 실제 호환성을 검증한 것은 아닙니다.** 추가된 파일은 원래 manifest의 고정 해시 검증 대상이 아니므로 출처와 해시·라이선스를 사용자가 별도로 확인해야 합니다.
- 샘플 ZIP 아티팩트 `DK-Knowledge-Engine-Win-x64-configurable-T09`는 Actions 실행의 Artifacts에 있으며 7일 보관, 정식 Release 아님.
- 사양/성능 측정은 중단하고 현장 기능 검증에서도 제거했습니다. [Windows PowerShell 기능 검증 7/7](https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/41956675584).

### 최신 CI 아티팩트 의존성

T09의 재빌드는 이전 Actions 실행 ID를 다운로드하지 않고 **동일 워크플로 안에서 T07 CPU ZIP을 먼저 생성·검증**한 다음 그 모델·런타임을 사용합니다. T10에서도 같은 실행 안에서 T09 패키지를 재빌드합니다. 결과물은 여전히 7일짜리 테스트 아티팩트이며 정식 Release가 아닙니다.
