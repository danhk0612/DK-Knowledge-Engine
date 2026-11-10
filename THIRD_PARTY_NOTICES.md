# Third-party notices / 서드파티 안내

DK-Knowledge-Engine 자체 소스코드에는 저장소 루트의 MIT `LICENSE`가 적용됩니다.
함께 포함하거나 사용하는 제3자 프로그램·라이브러리·모델에는 **각자의 라이선스**가 적용됩니다.

| 구성 요소 | 사용 위치 | 라이선스 / 공식 출처 |
| --- | --- | --- |
| .NET 10 Windows/WPF | Admin 및 Client의 자체 포함 GUI | .NET Runtime/WPF MIT, 일부 Windows용 런타임 및 WPF 바이너리 .NET Library License, Windows SDK License. https://github.com/dotnet/core/blob/main/license-information-windows.md |
| Qwen3 1.7B GGUF | Client 및 Admin의 엔진 템플릿 | Apache-2.0, https://huggingface.co/ggml-org/Qwen3-1.7B-GGUF |
| llama.cpp | Client 및 Admin의 엔진 템플릿 | MIT, https://github.com/ggml-org/llama.cpp |
| CPython | 실행 파일 안의 Python 런타임 | PSF License, https://docs.python.org/3/license.html |
| PyInstaller | 실행 파일 빌드 및 번들 | GPLv2 + 예외(일부 Apache-2.0), https://pyinstaller.org/en/stable/license.html |
| pypdf | Admin Builder의 PDF 추출 | BSD-3-Clause, https://github.com/py-pdf/pypdf |
| python-docx | Admin Builder의 DOCX 추출 | MIT, https://github.com/python-openxml/python-docx |
| lxml | python-docx 의존성 | BSD 및 별도 저작권 고지, https://github.com/lxml/lxml/blob/master/LICENSES.txt |
| typing_extensions | python-docx 의존성 | PSF License, https://github.com/python/typing_extensions/blob/main/LICENSE |

- 엔진 템플릿과 Client ZIP의 `licenses/`에는 빌드가 수집한 llama.cpp, 모델, CPython, PyInstaller의 라이선스 파일이 포함됩니다.
- Admin 및 Client ZIP의 `licenses/dotnet/`에는 .NET Runtime과 WPF의 MIT 라이선스·제3자 고지 원문(.NET 10.0.14 소스 기준), 공식 Windows 라이선스 적용 범위 안내, 빌드 시 Microsoft 공식 페이지에서 저장한 .NET Library License 및 Windows SDK License 약관 HTML이 포함됩니다. 오프라인 Admin에서 생성한 Client에도 동일 파일을 복사합니다. Microsoft 고지는 제품 자체의 MIT `LICENSE`를 대체하지 않습니다.
- 관리자 ZIP의 `licenses/builder/`에는 빌드 시 설치된 pypdf, python-docx, lxml, typing_extensions의 실제 배포 라이선스 원문을 버전별로 복사합니다. 빌드 시 해당 원문이 없다면 패키지 생성이 실패합니다.
- **관리자 ZIP을 최종 외부 공개하기 전에** 실제 동봉된 PyInstaller/Python 의존 패키지 버전과 그 하위 의존성의 저작권/라이선스 문구가 빠짐없이 배포되는지 확인해야 합니다. 이 목록은 완결된 법적 실사가 아닙니다.
- 사용자 의미 검색용 GGUF를 추가로 선택하면 해당 모델이 사용자 패키지에 포함됩니다. 제작용 고성능 LLM과는 구분되며, 선택 임베딩 GGUF의 라이선스·재배포 허용/NOTICE도 배포자가 확인해야 합니다.
- 관리자가 별도의 GGUF 파일을 선택하면 기본 Qwen3 GGUF를 대체하여 사용자 ZIP에 포함할 수 있습니다. 이 모델의 라이선스, 상업적 이용과 재배포 허용 범위, NOTICE 의무는 모델 배포자가 확인해야 합니다. 임의 GGUF의 라이선스 원문을 자동으로 다운로드하거나 패키지에 삽입하지 않습니다.
- 고객 문서·사용자 작성 자료의 저작권과 재배포 권한은 문서 제공자가 별도로 관리해야 합니다. 본 프로젝트의 MIT 라이선스가 고객 문서와 제3자 모델에 적용되지는 않습니다.
