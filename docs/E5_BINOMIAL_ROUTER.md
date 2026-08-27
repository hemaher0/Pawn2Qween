<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

# E5-binomial router

## 역할과 범위

이 라우터는 프롬프트마다 후보 모델의 quality와 cost를 예측하고, 선택한 tier의
budget 안에서 사용할 모델을 결정합니다. 후보 모델은 다음 세 가지입니다.

- `ax31-light`
- `ax31`
- `axk1-think`

quality prediction에는 hash-regex feature를 입력으로 학습한 binomial logistic
모듈과 pinned E5 embedding을 입력으로 학습한 model compatibility 모듈을 함께
사용합니다. cost는 hash-regex feature를 사용하는 별도의 linear head로
예측합니다. quality와 cost prediction이 끝나면 budget-aware allocator가 전체
프롬프트의 모델 선택을 한꺼번에 결정합니다.

runtime에서는 정답, 모델의 실제 generation이나 관측 quality를 읽지 않습니다.
필요한 prediction은 입력 프롬프트와 사전에 학습한 aggregate artifact만으로
계산합니다.

## 전체 runtime flow

하나의 프롬프트에서 두 종류의 representation을 만듭니다. hash-regex feature는
binomial logistic quality와 cost prediction에 사용하고, pinned E5 encoder가
만든 embedding은 model compatibility prediction에 사용합니다.

```text
prompt
  ├─ hash-regex feature → binomial quality ─┐
  ├─ E5 embedding → model compatibility ───┤→ combined quality
  └─ hash-regex feature → predicted cost ──┘
                              ↓
                    budget-aware allocator
                              ↓
                         model decision
```

각 구성요소의 계산이 끝나면 다음 순서로 최종 선택을 만듭니다.

1. 후보 모델별 binomial logistic quality를 계산합니다.
2. 후보 모델별 E5 compatibility logit을 계산합니다.
3. 두 값을 logit space에서 결합해 후보 모델별 predicted quality를 만듭니다.
4. 후보 모델별 predicted cost를 계산합니다.
5. tier별 budget과 safety ratio를 적용해 전체 프롬프트의 모델을 배분합니다.
6. 선택 결과를 protocol 형식으로 검증한 뒤 submission 파일로 저장합니다.

## quality prediction 결합

[Binomial logistic quality module](BINOMIAL_LOGISTIC_QUALITY.md)은 프롬프트의
길이, code·math·numeric signal과 signed word hashing 값을 사용해 후보 모델별
quality를 예측합니다.

[E5 low-rank model compatibility module](E5_BILINEAR_COMPATIBILITY.md)은
프롬프트를 384차원 embedding으로 바꾼 다음, 학습된 2차원 latent space에서
프롬프트와 후보 모델의 compatibility logit을 계산합니다.

두 모듈은 서로 독립적으로 값을 계산합니다. runtime에서는 binomial logistic
quality를 logit으로 바꾸고, compatibility logit과 같은 비율로 결합합니다.

```text
combined_logit[model]
    = 0.5 * binomial_logit[model]
      + 0.5 * compatibility_logit[model]

combined_quality[model]
    = sigmoid(combined_logit[model])
```

blend weight `0.5`는 E5 compatibility artifact에 저장되며, runtime code도 이
값이 정확히 `0.5`인지 확인합니다. 결합 결과는 `0`과 `1` 사이의 후보 모델별
predicted quality입니다.

## cost prediction과 budget allocation

cost prediction은 quality prediction과 분리되어 있습니다. hash-regex feature를
standardize한 뒤 후보 모델별 linear head로 log-cost를 예측하고, `exp`를 적용해
predicted cost로 바꿉니다. 계산된 cost는 모델 순서에 맞게 다음 관계를
유지하도록 보정합니다.

```text
cost[ax31-light] < cost[ax31] < cost[axk1-think]
```

allocator는 먼저 모든 프롬프트를 `ax31-light`로 처리할 때의 predicted cost
합계를 기준으로 삼습니다. 선택한 tier의 budget multiplier에 artifact의 tier별
safety ratio를 곱해 allocation에 사용할 budget cap을 계산합니다.

```text
effective_ratio = max(1, tier_budget_multiplier * tier_safety_ratio)
budget_cap       = all_light_predicted_cost * effective_ratio
```

각 후보 모델의 selection value는 predicted quality에서 cost penalty를 뺀
값입니다.

```text
selection_value[model]
    = predicted_quality[model]
      - penalty * predicted_cost[model] / all_light_predicted_cost
```

allocator는 각 프롬프트에서 selection value가 가장 큰 모델을 고릅니다. 전체
predicted cost가 budget cap을 넘으면 `penalty`를 높이고, cap 안으로 들어올
때까지 binary search를 수행합니다. 탐색 뒤에도 cap을 만족하는 allocation을
만들 수 없으면 모든 프롬프트에 `ax31-light`를 선택합니다.

이 과정은 runtime 전용
[`routing_allocator.select_models`](../src/ossp_router/routing_allocator.py)에
구현되어 있습니다.

## premium tier의 AX31 추가 allocation

`premium` tier에는 첫 번째 allocation이 끝난 뒤 남은 conservative budget을
사용하는 추가 단계가 있습니다. 이 단계는 앞에서 선택한 `ax31`과
`axk1-think`를 그대로 유지하고, 아직 `ax31-light`인 프롬프트만 검토합니다.

각 프롬프트에서 `ax31`로 바꿀 때의 predicted quality gain과 predicted cost
increase를 계산합니다.

```text
quality_gain = quality[ax31] - quality[ax31-light]
cost_increase = cost[ax31] - cost[ax31-light]

upgrade_value
    = quality_gain
      - penalty * cost_increase / all_light_predicted_cost
```

`premium` 전용 safety ratio는 `0.65`입니다. 현재 선택의 predicted cost를
낮추지는 않으며, 다음 두 값 중 큰 값을 추가 allocation의 budget cap으로
사용합니다.

```text
premium_fill_cap
    = max(
        current_predicted_cost,
        all_light_predicted_cost * max(1, premium_budget_multiplier * 0.65)
      )
```

`upgrade_value`가 양수인 선택만 `ax31`로 바꾸며, 추가 선택의 전체 predicted
cost가 이 budget cap 안에 들도록 `penalty`를 binary search합니다. 이 단계는
기존 선택을 낮은 모델로 변경하지 않습니다. 안전한 추가 allocation을 만들 수
없으면 첫 번째 allocation 결과를 그대로 사용합니다.

이 추가 단계는 runtime 전용
[`routing_allocator.fill_ax31_upgrades`](../src/ossp_router/routing_allocator.py)에
구현되어 있습니다.

## 구성요소와 input validation

라우터는 inference를 시작하기 전에 함께 사용하는 구성요소가 같은 protocol과
학습 구성을 나타내는지 확인합니다.

- hash-regex artifact의 policy ID와 policy digest가 현재 policy와 일치해야
  합니다.
- binomial logistic 모듈의 모델 순서가 protocol의 모델 순서와 일치해야
  합니다.
- binomial logistic 모듈의 feature 이름과 순서가 hash-regex feature와
  일치해야 합니다.
- E5 compatibility 모듈의 모델 순서가 protocol과 일치해야 합니다.
- E5 encoder의 model, revision, preprocessing identity와 파일 hash가
  compatibility artifact에 기록된 값과 일치해야 합니다.
- encoder가 반환한 embedding 수가 입력 프롬프트 수와 일치해야 합니다.

ONNX model과 tokenizer는 파일 크기와 SHA-256 hash를 모두 확인한 뒤
불러옵니다. 입력, artifact나 model 파일이 validation을 통과하지 못하면 라우터는
선택 결과를 만들지 않고 error code `2`로 종료합니다. 검증된 submission은
atomic write하므로 작성 도중의 불완전한 파일을 남기지 않습니다.

## runtime에 필요한 파일

기본 runtime에는 다음 파일이 필요합니다.

- `src/ossp_router/resources/hash-regex-public.v1.json`: hash-regex feature standardization,
  cost head와 tier별 safety ratio
- `src/ossp_router/resources/binomial-logistic-quality-public.v1.json`: 후보 모델별 binomial
  logistic quality parameter
- `src/ossp_router/resources/e5-bilinear-compatibility-public.v1.json`: E5 preprocessing
  identity, low-rank compatibility parameter와 blend weight
- `build/e5-model/onnx/model.onnx`: pinned E5 ONNX model
- `build/e5-model/onnx/tokenizer.json`: pinned E5 tokenizer

세 JSON artifact에는 전체 학습 데이터에서 계산한 aggregate parameter와
provenance만 들어 있습니다. 개별 프롬프트, 개별 embedding, 정답이나 모델
generation은 저장하지 않습니다.

E5 model 파일들은 저장소에 포함하지 않으며, pinned revision에서 별도로 받아
hash를 검증합니다. 출처, license, 파일 hash와 reproduction 방법은
[E5 model provenance 문서](E5_MODEL_PROVENANCE.md)에 설명되어 있습니다. 파일을
준비한 뒤의 router runtime에는 network 연결이 필요하지 않습니다.

## 실행 방법

다음 명령은 기본 artifact와 `build/e5-model`의 E5 파일을 사용해 `balanced`
tier의 submission을 만듭니다.

```console
uv run --locked --no-dev --group e5-runtime router-run \
  --input input.json \
  --tier balanced \
  --model-dir build/e5-model \
  --output submission.json
```

다른 policy나 artifact를 사용할 때는 `--policy`, `--hash-artifact`,
`--binomial-artifact`, `--compatibility-artifact` 옵션으로 경로를 지정할 수
있습니다. 지정한 파일에도 앞에서 설명한 구성요소 validation이 동일하게
적용됩니다.
