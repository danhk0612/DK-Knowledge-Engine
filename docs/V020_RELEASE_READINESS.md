# DK-Knowledge-Engine v0.2.0 — Preview 배포 검수표 (미승인)

본 문서는 **배포 준비 기록**입니다. 버전 `v0.2.0-preview.1`은 예정된 시험용 태그이며, 현재 GitHub Release로 생성·공개하지 않았습니다.

## 1. 코드·CI·실기 상태

| 항목 | 근거 | 상태 |
| --- | --- | --- |
| 제품 ID 격리 | PR #40, 제품별 DB·규칙·검색·모델 격리 회귀 테스트 | 구현·자동 검증 |
| 독립형 Admin·Client, 아이콘·WPF GUI·트레이 | PR #41, Windows T12 | 구현·자동 검증 |
| Windows 10/11 x64 오프라인 CPU 패키지 | T07·T12 | Windows CI 통과 |
| PDF·DOCX·TXT·MD → 독립형 Builder DB·Client ZIP 생성 | T12 독립 Admin 작업 | 자동 검증 통과 |
| **PDF·DOCX·TXT·MD 실제 Client 검색 및 출처 확인** | `tests/v020_multiformat_search_smoke.ps1` / T12 | **이번 변경 CI 최종 결과 확인 필요** |
| 제품별 DB 업데이트·롤백 및 검색 내용 변경 | `tests/v020_client_engine_gui_smoke.ps1` | Windows CI 통과 |
| 사용자 Windows 실기 | 2026-11-11 사용자 직접 확인: Admin·Client 주요 기능, 트레이, 질문 3건 | **예제 DB 범위 통과** |
| 질문 정확도·출처 | 세 질문에서 `3308`, `setup.md` 표시 사용자 확인 | **예제 DB 범위 통과** |
| 실제 고객 PDF·DOCX에서의 답변 정확도/환각률 | 승인된 실제 문서 및 질문·정답 자료 미제공 | **미확인** |
| SmartScreen·기업 보안/정책·실제 배포 PC 호환성 | 환경별 검사 필요 | **미확인** |
| 서드파티 라이선스 적합성 최종 승인 | 고지 파일 CI 확인, 선택 모델·번들 의존성 별도 확인 | **미완료** |

**마지막으로 전부 통과가 확인된 기준선:** PR #41 커밋 `8271b582`에서 T02/T07/T09/T12 성공.
- T12: https://github.com/danhk0612/DK-Knowledge-Engine/actions/runs/42969057942
- 수동 테스트 패키지: 성공한 T12 실행 `42964843944`의 인공 DB Client / Admin, 사용자 Windows PC 검증 완료
- 테스트 가이드: [Windows 현장 QA](V020_WINDOWS_FIELD_QA.md)
- 기존 추가 품질 평가: [T10 검증](T10_VALIDATION.md)에서 인공 DB를 사용한 14개 테스트 통과(2026-11-05). **새 v0.2.0 고객 DB의 평가가 아님**

## 2. 고객 문서 품질 게이트 — 실제 자료가 확보되면 수행

실제 문서가 제공되지 않았으므로 **개인/고객 PDF·DOCX를 임의로 생성해 검증한 것으로 간주하지 않습니다.** 배포자가 재배포 권한을 확보한 대표 문서로 다음 절차를 별도의 비공개 Windows 작업 폴더에서 수행합니다.

1. Admin에서 실제 PDF·DOCX·TXT·MD를 등록해 제품 ID와 적용 버전을 지정하고 지식 DB를 재생성합니다. 스캔 PDF는 OCR 준비 여부와 추출 결과를 확인합니다.
2. Client 패키지에 다른 제품 문서·원본문서·Builder가 들어가지 않았는지 무결성과 압축 내용으로 확인합니다.
3. **정답을 미리 아는 질문**과 **문서에 정답이 없는 질문**을 나누어 검사합니다. 출처 경로·페이지·버전, 정확한 수치와 단위, 잘못된 내용의 차단, 근거 없는 답변의 표시를 기록합니다.
4. 필요하면 `tests/t10_eval.py`와 [T10 사례 형식](../tests/t10_cases_sample.json)으로 비공개 평가를 수행합니다. 자동 단어 검사만으로 자연어 답변의 의미적 정답을 보증할 수 없으므로 검토자가 원문과 대조합니다.
5. 원본 고객 설명서·질문·답변 전문·고객명은 공개 GitHub 이슈/PR/CI 아티팩트에 올리지 않습니다. 통과율과 민감정보를 제거한 결과만 기록합니다.

**이 게이트는 현재 미완료이며 실제 고객 배포 승인에 필요합니다.** 합성 샘플만으로 공용 Preview의 기본 구조를 검토하는 작업과 분리합니다.

## 3. 배포 파일·법적 검수

- Admin ZIP: 독립형 `DK-Knowledge-Admin.exe`, 동봉 Builder, Client 템플릿, 엔진·Qwen 기본 모델, README, MIT LICENSE, `THIRD_PARTY_NOTICES.md`, `licenses/` 확인.
- Client ZIP: 제품 한 개의 DB, `DK-Knowledge-Client.exe` 및 .NET 종속 DLL, llama.cpp·GGUF, 무결성 매니페스트, 사용 설명서·법적 고지를 확인. Admin/Builder/원본 문서 금지.
- CI가 생성한 **인공 샘플 지식 DB만 Release 후보에 포함**하는지 확인. 실제 고객 문서·규칙·계정·개인정보가 들어 있으면 배포 중단.
- 라이선스: 기본 Qwen·llama.cpp·Python·PyInstaller·.NET/WPF·pypdf·python-docx·lxml·typing_extensions 고지 및 모든 실제 번들 의존성을 별도 검수. **추가 GGUF는 별도 재배포 허가를 받아야 함**.
- 실행 파일은 **미서명 포터블 ZIP**. SmartScreen·회사 정책을 임의로 우회하지 않으며, 서명/배포 정책 확인 전 대외 제공 금지.
- ZIP 두 개와 `SHA256SUMS.txt`가 동일한 성공 CI 커밋에서 나왔는지 대조.

## 4. PR 병합과 Preview 준비 순서 (미실행)

1. [PR #40](https://github.com/danhk0612/DK-Knowledge-Engine/pull/40) → `main` 기준으로 변경 내용·CI·리뷰 확인 후 병합 승인.
2. [PR #41](https://github.com/danhk0612/DK-Knowledge-Engine/pull/41) → PR #40 기반 변경 사항이므로 **#40 병합 후 #41의 base를 `main`으로 변경**하고 최종 diff·CI·리뷰 재확인 후 병합 승인.
3. `main`의 **최종 HEAD와 정확히 같은 SHA**에서 T12 Windows 통합 CI가 성공해야 함.
4. `docs/RELEASE_NOTES_v0.2.0-preview.1.md` 검토. 기존 `v0.1.0-preview.*` Draft·태그를 재사용하거나 덮어쓰지 않음.
5. 최종 승인 이후에만 `release-draft.yml`을 `main`에서 `version=v0.2.0-preview.1`, `source_run_id=<성공한 main T12 ID>`로 실행. 초안 생성 후 아티팩트·SHA-256·라이선스·고지·개인정보를 추가 검수.
6. **Release 공개는 초안 검토 후 별도 승인**. CI 통과·사용자 예제 테스트만으로 자동 공개하지 않음.

**현재 PR #40·#41은 Draft이고, main 병합·Release 초안 생성·공개를 수행하지 않았습니다.**
