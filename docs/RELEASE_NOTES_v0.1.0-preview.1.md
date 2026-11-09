# DK Knowledge Engine v0.1.0-preview.1

Windows x64에서 실행하는 **오프라인 AI 도움말 엔진의 첫 사전 배포판**입니다. 별도 설치 관리자 없이 압축 해제 후 실행합니다.

## 파일 선택

- `DK-Knowledge-Engine-Admin-Win-x64-v0.1.0-preview.1.zip` — 제작자 전용. 문서 등록·교체·삭제, 지식 DB 재생성, Client 패키지 제작.
- `DK-Knowledge-Engine-Client-Win-x64-v0.1.0-preview.1.zip` — 최종 사용자 전용. 로컬 CPU AI 답변·문서 검색·출처 표시. **이 파일의 지식 DB는 인공 샘플 문서로 만들어졌습니다.** 실제 고객 자료를 배포하려면 제작자가 Admin에서 새 Client ZIP을 생성해야 합니다.
- `SHA256SUMS.txt` — ZIP 두 개의 SHA-256 체크섬.

## 주요 기능

- PDF/DOCX/TXT/MD를 기존 폴더 구조와 관계없이 지식 DB로 색인
- 문서 추가 시 관리자 원본 폴더로 자동 복사, 기존 문서의 교체·삭제
- 원본 문서·DB·엔진·출력 경로의 기본값 자동 지정 및 Windows 탐색기 바로 열기
- 같은 사용자 패키지 출력 폴더 재사용(생성 파일 교체, 그 외 파일 유지)
- 자체 포함 Client/Admin WPF GUI, 로컬 검색 API, Qwen3 1.7B CPU 추론
- Client ZIP에 관리자 실행 파일·원본문서·색인 도구를 포함하지 않음

## 한계 및 주의

- **preview / 비서명 ZIP**: Windows Defender SmartScreen 및 일부 조직의 실행 제한이 발생할 수 있습니다. 보안 경고를 무조건 우회하지 마세요.
- Windows 10/11 x64 일반 사용자 환경의 광범위한 호환성, 실제 고객 문서의 정답성, 브라우저 사내 HTTPS→localhost 연동은 별도 현장 검증 대상입니다.
- 기본 GGUF는 Qwen3 1.7B Q4_K_M, CPU용 llama.cpp 기반입니다. 사용자 PC에 GPU가 없어도 동작하도록 구성했으나 성능은 하드웨어에 따라 달라집니다.
- ZIP은 **설치 프로그램이 아니며 자동 업데이트가 없습니다.**
- 모델·Python 라이브러리 등 제3자 소프트웨어는 각 라이선스를 따릅니다. 외부 공개 전 포함된 모든 라이선스/NOTICE 확인이 필요합니다.

사용법: [관리자 안내](docs/ADMIN_QUICKSTART.md) · [사용자 안내](docs/CLIENT_QUICKSTART.md) · [배포 검증/제한](docs/RELEASE_PROCESS.md)
