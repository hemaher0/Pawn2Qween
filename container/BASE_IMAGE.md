<!--
SPDX-FileCopyrightText: Copyright 2026 SK TELECOM CO., LTD.
SPDX-License-Identifier: Apache-2.0
-->

# 기반 이미지 기록

E5-binomial 제출 컨테이너는 Docker Official Image인 다음 기반 이미지를
의존성 빌드 단계와 최종 실행 단계에 동일하게 사용합니다.

```text
python:3.11.15-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3
```

- 다중 플랫폼 인덱스 다이제스트:
  `sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3`
- `linux/arm64` 매니페스트 다이제스트:
  `sha256:ecb0ac954790dd64a0d518d699b9c61a91780c42b0d877c802dbaffd04db66f9`
- 공식 선택 플랫폼: `linux/arm64`
- [Docker Official Images의 Python 항목](https://github.com/docker-library/official-images/blob/master/library/python)
- [고정한 빌드 조리법](https://github.com/docker-library/python/blob/4d216ad3beb5b697c4049071c82fc375acb8abad/3.11/slim-bookworm/Dockerfile)

공식 이미지 항목은 이 태그가 여러 플랫폼을 지원하고 조리법이
`docker-library/python`의 커밋
`4d216ad3beb5b697c4049071c82fc375acb8abad`, 디렉터리
`3.11/slim-bookworm`에서 왔음을 기록합니다. Debian glibc 기반 이미지를
사용하므로 `linux/arm64`용 ONNX Runtime wheel을 별도 C 라이브러리 변환 없이
실행할 수 있습니다.

빌드 단계는 잠금 파일의 `e5-runtime` 그룹에서 NumPy 2.0.2, ONNX Runtime
1.28.0, tokenizers 0.22.2와 그 전이 의존성을 설치합니다. 최종 단계에는 이
실행 환경만 복사하고 `pip`, `setuptools`, `wheel`과 `uv`는 남기지 않습니다.
모델·토크나이저 출처와 해시, 런타임 패키지 라이선스는
[`../docs/E5_MODEL_PROVENANCE.md`](../docs/E5_MODEL_PROVENANCE.md)와
[`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)에 기록합니다.

이 저장소의 Apache-2.0 라이선스는 기반 이미지 안의 Python, Debian과 개별
패키지를 재라이선스하지 않습니다. 이미지를 배포할 때는 이미지 안의 Python과
Debian 패키지 메타데이터, 설치된 Python wheel의 라이선스·저작권 고지를
그대로 보존하고 별도로 검사해야 합니다. 최종 이미지는 프로젝트 `LICENSE`,
`NOTICE`, `LICENSES/`도 `/usr/share/licenses/pawn2qween/`에 보존합니다.

다이제스트 고정은 자동 보안 갱신을 막으므로 공개 이미지 배포 전에는 해당
다이제스트의 운영체제·Python 패키지 취약점과 소프트웨어 자재 명세서(SBOM)를
다시 검사해야 합니다. 보안 갱신으로 기반 이미지 다이제스트를 바꾸는 경우
새 이미지의 출처·라이선스·취약점·재현 빌드를 함께 검증합니다. 이 변경은
v1 JSON 형식이나 평가 정책 ID를 바꾸지 않지만 제출 이미지 다이제스트는
새로 기록해야 합니다.

공식 실행기가 제한 출력 볼륨에서 결과를 꺼낼 때만 사용하는 운영자 도우미는
별도의 Docker Official Image
`python:3.14.6-alpine3.23@sha256:b165067c5afc37fa5608a3c05609cc3d51aafd808a30fbfd822ee594fef55ad4`로
고정합니다. 이 이미지는 참가자 라우터 이미지의 기반이나 제출 요건이 아닙니다.
