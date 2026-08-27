<!--
SPDX-FileCopyrightText: Copyright 2026 SK TELECOM CO., LTD.
SPDX-License-Identifier: Apache-2.0
-->

# Comparison baselines

이 디렉터리에는 공식 E5 라우터와 비교하기 위한 작은 예제만 둡니다.
학습 코드, 학습 artifact와 제출 runtime은 모두 `src/ossp_router/`에서
관리합니다.

- `always_light.py`: 모든 문항에 `ax31-light`를 선택합니다.
- `prompt_heuristic.py`: 프롬프트 길이와 코드·수학 표식으로 모델을 선택합니다.
- `feature_budget.py`: prompt-only 특징 점수와 등급별 비용 예산을 함께
  사용합니다.

toy 입력에서 각 예제를 실행하려면 다음 명령을 사용합니다.

```console
uv run --locked --no-dev python baselines/always_light.py \
  --input data/toy/inputs.json \
  --output-dir build/baselines/always-light

for tier in fast balanced premium; do
  uv run --locked --no-dev python baselines/prompt_heuristic.py \
    --input data/toy/inputs.json \
    --tier "$tier" \
    --output "build/baselines/prompt-heuristic/$tier.json"

  uv run --locked --no-dev python baselines/feature_budget.py \
    --input data/toy/inputs.json \
    --tier "$tier" \
    --output "build/baselines/feature-budget/$tier.json"
done
```

공식 E5 라우터의 학습과 실행 방법은 [프로젝트 README](../README.md)의
Quickstart를 따릅니다.
