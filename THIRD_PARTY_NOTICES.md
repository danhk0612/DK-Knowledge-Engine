# Third-party notices / 서드파티 안내

DK-Knowledge-Engine 자체 소스코드에는 저장소 루트의 MIT `LICENSE`가 적용됩니다.
함께 포함하거나 사용하는 제3자 프로그램·라이브러리·모델에는 **각자의 라이선스**가 적용됩니다.

| 구성 요소 | 사용 위치 | 라이선스 / 공식 출처 |
| --- | --- | --- |
| Qwen3 1.7B GGUF | Client 및 Admin의 엔진 템플릿 | Apache-2.0, https://huggingface.co/ggml-org/Qwen3-1.7B-GGUF |
| llama.cpp | Client 및 Admin의 엔진 템플릿 | MIT, https://github.com/ggml-org/llama.cpp |
| CPython | 실행 파일 안의 Python 런타임 | PSF License, https://docs.python.org/3/license.html |
| PyInstaller | 실행 파일 빌드 및 번들 | GPLv2 + 예외(일부 Apache-2.0), https://pyinstaller.org/en/stable/license.html |
| pypdf | Admin Builder의 PDF 추출 | BSD-3-Clause, https://github.com/py-pdf/pypdf |
| python-docx | Admin Builder의 DOCX 추출 | MIT, https://github.com/python-openxml/python-docx |
| lxml | python-docx 의존성 | BSD 및 별도 저작권 고지, https://github.com/lxml/lxml/blob/master/LICENSES.txt |

- 엔진 템플릿과 Client ZIP의 `licenses/`에는 빌드가 수집한 llama.cpp, 모델, CPython, PyInstaller의 라이선스 파일이 포함됩니다.
- **관리자 ZIP을 최종 외부 공개하기 전에** 실제 동봉된 PyInstaller/Python 의존 패키지 버전과 그 하위 의존성의 저작권/라이선스 문구가 빠짐없이 배포되는지 확인해야 합니다. 이 목록은 완결된 법적 실사가 아닙니다.
- 관리자가 별도의 GGUF 파일을 선택하면 기본 Qwen3 GGUF를 대체하여 사용자 ZIP에 포함할 수 있습니다. 이 모델의 라이선스, 상업적 이용과 재배포 허용 범위, NOTICE 의무는 모델 배포자가 확인해야 합니다. 임의 GGUF의 라이선스 원문을 자동으로 다운로드하거나 패키지에 삽입하지 않습니다.
- 고객 문서·사용자 작성 자료의 저작권과 재배포 권한은 문서 제공자가 별도로 관리해야 합니다. 본 프로젝트의 MIT 라이선스가 고객 문서와 제3자 모델에 적용되지는 않습니다.
