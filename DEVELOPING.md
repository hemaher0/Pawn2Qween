<!--
SPDX-FileCopyrightText: Copyright 2026 SK TELECOM CO., LTD.
SPDX-FileCopyrightText: Copyright 2026 hemaher0

SPDX-License-Identifier: Apache-2.0
-->

# 개발 안내

## 로컬 실행

런타임은 Python 3.9 이상과 표준 라이브러리만 사용합니다. 개발 환경은
`.python-version`의 Python 3.11과 uv 0.12.3을 기준으로 합니다. 잠금 파일에
맞춰 개발 도구를 설치하고 전체 테스트를 실행합니다.

```console
uv sync --locked
uv run --locked python -m unittest discover -s tests -p 'test_*.py'
```

toy 입력으로 제출을 만들고 검사하는 명령은 다음과 같습니다.

```console
uv run --locked --no-dev python baselines/always_light.py \
  --input data/toy/inputs.json \
  --output-dir build/toy-submission

uv run --locked --no-dev python baselines/prompt_heuristic.py \
  --input data/toy/inputs.json \
  --tier fast \
  --output build/prompt-heuristic-fast.json

uv run --locked --no-dev python -m ossp_router.cli self-check \
  --input data/toy/inputs.json \
  --outcomes data/toy/outcomes.json \
  --submissions build/toy-submission \
  --report build/toy-report.json
```

materialization을 마친 공개 Train/Dev 전체의 로컬 선별 측정은 다음 명령으로
실행할 수 있습니다. 구현·등급 조합마다 5회 미만은 허용하지 않습니다. 동결된
공식 보고서를 덮어쓰지 않도록 결과는 `build/`에 기록합니다.

```console
uv run --locked --no-dev python tools/benchmark_runtime.py \
  --json-output build/runtime-benchmark.local.json \
  --markdown-output build/runtime-benchmark.local.md
```

공식 Apple Silicon·Colima 컨테이너 재측정에는 별도 측정 이미지를 사용해야
하므로 [`docs/APPLE_SILICON_MEASUREMENT.md`](docs/APPLE_SILICON_MEASUREMENT.md)의
소스 결속, 경계 테스트와 운영자 확인 절차를 그대로 따릅니다.

Docker 호환 CLI와 실행기가 있는 환경의 격리 통합 테스트는
[`docs/RUNTIME.md`](docs/RUNTIME.md)의 명령을 따릅니다.
macOS에서는 오픈소스 Colima를 실행기로 사용할 수 있으며 Docker Desktop은
필수 의존성이 아닙니다.

## 변경 원칙

- 입력, 결과, 제출, 정책의 스키마는 알 수 없는 필드를 거부합니다.
- 비용 한도는 `Decimal`로 비교하고, 한도와 정확히 같을 때만 통과합니다.
- 라우터 구현은 prompt 또는 messages 외의 과제명, 출처, 정답, 평가
  결과(outcome)를 입력으로 사용하면 안 됩니다.
- 결과 파일에는 모델 생성문, 추론 과정, 정답, 출력 해시를 추가하지 않습니다.
- 내부 Git 이력, 운영 설정, 비공개 평가 자료, 사내 경로·호스트명을 넣지
  않습니다.
- 새 의존성이나 제3자 자료는 출처·고정 버전·라이선스·고지 조건을 함께
  검토합니다.

원본 코드와 설정에는 파일 형식에 맞는 다음 SPDX 정보를 붙입니다.

```text
SPDX-FileCopyrightText: Copyright 2026 SK TELECOM CO., LTD.
SPDX-License-Identifier: Apache-2.0
```

정식 라이선스 전문과 제3자 파일의 기존 헤더는 수정하지 않습니다.

## 검증

커밋 전에는 잠금 상태, 코드 검사, 라이선스, 테스트와 배포 파일 생성을 함께
확인합니다.

```console
uv lock --check
uv run --locked ruff check .
uv run --locked reuse lint
uv run --locked python -m unittest discover -s tests -p 'test_*.py'
uv build --clear
```

저장소 공개 전에는 비밀 탐지, 로컬 링크, 심볼릭 링크, 라이선스 전문 해시,
참가자 문서와 구현의 정책 값 일치를 함께 확인합니다. 공개 전 작업 목록과
승인 기록은 공개 저장소 밖의 조직 운영 공간에서 관리합니다.

## 릴리스

일반 branch push와 `main` push는 CI만 실행하며 릴리스를 만들지 않습니다.
GitHub Release는 지원되는 버전 tag를 push할 때만 생성됩니다. 릴리스 전에
`pyproject.toml`의 `project.version`을 tag와 일치시키고, `CHANGELOG.md`의
`[Unreleased]` 내용을 tag에서 선행 `v`를 뺀 버전 제목으로 옮깁니다. 해당
제목은 정확히 하나이고 내용이 비어 있지 않아야 합니다.

- stable: `vMAJOR.MINOR.PATCH` 형식이며 GitHub의 최신 정식 릴리스가 됩니다.
- latest: `vMAJOR.MINOR.PATCH-alpha.N`, `-beta.N`, `-rc.N` 형식이며 GitHub
  prerelease로 만들고 최신 정식 릴리스 표시는 유지합니다.

latest tag의 SemVer 표기는 project version에서 PEP 440으로 바꿉니다. 예를
들어 `v2.0.0-rc.4`는 `project.version = "2.0.0rc4"`와 changelog 제목
`## [2.0.0-rc.4] - YYYY-MM-DD`를 사용합니다. stable `v1.2.3`은 project
version과 changelog 버전 모두 `1.2.3`입니다.

tag를 push하기 전에 위 검증 명령을 모두 실행합니다. release workflow도 같은
품질·Python 버전 검사를 다시 통과한 뒤 wheel과 source distribution을 해당
changelog 내용과 함께 GitHub Release에 첨부합니다. PyPI나 컨테이너
registry에는 게시하지 않습니다.
