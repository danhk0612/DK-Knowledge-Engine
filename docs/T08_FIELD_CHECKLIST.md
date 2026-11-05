# T08 — Windows 10/11 8GB PC 실기 검증 지침

**상태: 실행 도구 작성 / 실사용 고객 PC 검증 미실시.** CI 환경에서 이 도구가 성공하더라도 실제 8GB/무GPU 고객 PC 적합 판정이 아닙니다.

## 준비와 사용

- T07 검증을 통과한 Windows x64 포터블 ZIP을 실제 PC에 압축 해제.
- 저장소의 tests/t08_field_check.ps1 및 현장 매뉴얼에 대응하는 사례 JSON 파일 준비. 샘플: tests/t08_field_cases_sample.json.
- Windows PowerShell 5.1 및 기본 .NET/CIM만 사용. 대상 PC에서 Python, Docker, 인터넷 불필요.
- 기존 API가 해당 포트를 점유했다면 먼저 정상 종료. 도구는 다른 실행 중 프로세스를 강제로 종료하지 않음.
- 고객 매뉴얼은 T02 Builder로 별도 생성한 지식 DB를 사용. T07 샘플 DB 결과는 고객 매뉴얼 정확도 증거가 아님.

### 실행 (각 실행은 서로 다른 새 출력 폴더 사용)

~~~powershell
cd C:\DK-Knowledge-Engine
powershell.exe -NoProfile -File .\tests\t08_field_check.ps1 `
  -PackageRoot "D:\Portable\DK-Knowledge-Engine-Win-x64" `
  -CasesPath ".\tests\t08_field_cases_sample.json" `
  -OutputDir "D:\T08-Evidence\PC-A01" `
  -RunsPerChat 3
~~~

이 스크립트는 기존 Verify-AIHelp.ps1로 해시/DB를 검사한 뒤, 포터블 EXE를 실행해 localhost health·search·event·chat을 요청합니다. 검색과 이벤트는 1회, chat은 지정 횟수(1~10회) 반복합니다. 냉시작 시간과 HTTP 시간, 메모리 사용 표본을 기록한 뒤 자신이 시작한 API만 종료합니다.

- 테스트 사례 kind: search (query, expect_results), event (event_id/error_code, expect_matched, expected_rule_id), chat (question, expected_any, forbidden_any), chat_no_evidence (question).
- 공통으로 id, product_id가 필요하며 version, expected_source를 선택적으로 지정합니다.
- 사례 ID별 결과와 응답 시간, 출처 상대 경로만 저장합니다. 답변 원문, 매뉴얼 본문, 질문 텍스트는 JSON 보고서에 저장하지 않습니다.
- 결과 디렉터리는 존재하지 않아야 합니다. 실패 시에도 실행 로그가 남을 수 있습니다. 실제 고객 자료 상대 경로가 포함될 수 있으므로 공개 Actions나 이슈에 결과를 업로드하지 마십시오.

### 보고서의 의미

field-validation.json에는 Windows 버전/총 RAM/CPU/그래픽 장치/물리 NIC 상태, 7~9GiB 범위 여부, API 시작 시간, 사례별 응답 시간과 출처, 실행 상태, 별도 PowerShell Job에서 약 100ms마다 표본 추출한 API 및 llama-completion 프로세스 합산 Working Set의 최대치가 있습니다.

**RSS 표본의 한계:** 공유 메모리 중복, 약 100ms 샘플의 누락, 동일한 프로세스명을 쓰는 다른 앱 혼합 가능성이 있습니다. 시스템 전체 피크 물리 메모리 사용량이 아닙니다. chat 키워드 일치는 부정문·문맥 오류를 잡지 못하므로 실제 답변과 매뉴얼 원문에 대한 담당자의 수동 검토가 필요합니다.

## 물리적 오프라인 검증 (수동)

1. 모델·문서 DB·스크립트를 먼저 로컬 디스크에 옮긴 뒤 Ethernet 케이블과 Wi-Fi 연결을 제거합니다. 테더링, VPN, 가상 NIC 등 다른 경로도 현장 담당자가 확인합니다.
2. 운영자가 실질적인 분리를 직접 확인한 경우에만 실행 시 -OfflineOperatorAttested를 추가합니다. 이 스위치는 **운영자 확인 기록**이며 스크립트가 통신 불가능을 독립 검증했다는 뜻이 아닙니다.
3. 모델 로딩, 질문 응답, 검색·오류 규칙, DB 갱신·롤백을 실행합니다. DB 갱신은 기존 T07 Update-Knowledge.ps1을 별도로 실행해 확인합니다. 스크립트는 네트워크 어댑터를 **자동으로 끄지 않습니다**.

## 사내 HTTPS 웹사이트 / SmartScreen (수동)

- Chrome·Edge에서 사내 HTTPS 페이지를 열고 T07 config/settings.json에 정확한 웹 Origin을 등록 후 API를 재실행합니다.
- 사용자 권한의 Local Network Access/loopback-network 프롬프트·승인/거부와, CORS 오류를 각각 기록합니다. 브라우저 버전 및 기업 정책을 같이 기록합니다. localhost→localhost 개발 페이지 통과는 이 테스트를 대체하지 못합니다.
- 정식 Windows 10/11에서 다운로드 ZIP의 SmartScreen·Defender·조직 보안 정책 차단/경고를 기록합니다. 정책을 임의 우회하지 말고 IT 관리자에게 확인합니다.
- 배포 예정 모델·llama.cpp·DLL·라이선스·NOTICE와 서명 필요 여부를 실제 배포 조건에서 재검토합니다.

## 현장 최종 승인 기준

| 검증 | 상태 |
|---|---|
| GitHub Windows 16GB 포터블 성능/메모리 | 통과 |
| GitHub 동일 llama.cpp CPU 모델 비교 5문항 | 통과 (제한된 탐색 실험) |
| Windows 10/11 PowerShell 현장 스크립트 자체 | CI 검증 대상 |
| GPU 없는 실제 Windows 10/11 8GB PC | 미검증 |
| 실제 물리적 네트워크 단절 | 미검증 |
| 고객 문서 정답/검색 근거 담당자 검토 | 미검증 |
| 사내 HTTPS 브라우저 권한·SmartScreen·재배포 | 미검증 |

**이 조건을 실제 현장에서 검증하기 전에는 T08 최종 완료 및 고객 배포 적합 판정을 보류합니다.**
