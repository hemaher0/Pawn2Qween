<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

# E5 저차원 모델 호환성 모듈

## 역할

이 모듈은 프롬프트의 의미와 각 후보 모델 사이의 호환성을 계산합니다. 같은
프롬프트라도 모델마다 잘 처리하는 정도가 다를 수 있으므로, 후보 모델별 예상
품질을 각각 `0`과 `1` 사이의 값으로 출력합니다.

모듈은 다음 두 부분으로 구성됩니다.

1. E5가 프롬프트를 384차원 의미 벡터로 변환합니다.
2. 저차원 bilinear 계산이 의미 벡터와 후보 모델의 조합에 맞는 품질을
   계산합니다.

## E5 의미 벡터

E5는 텍스트를 고정된 길이의 숫자 벡터로 변환하는 임베딩 모델입니다. 문장을
생성하거나 정답을 작성하지 않습니다. 텍스트의 의미를 비교하고 계산에 사용할
수 있는 숫자 표현을 만듭니다.

이 모듈은 다음 E5 모델을 고정해서 사용합니다.

- 모델: `intfloat/multilingual-e5-small`
- 리비전: `fd1525a9fd15316a2d503bf26ab031a61d056e98`
- 라이선스: MIT
- 출력 차원: 384

프롬프트 앞에는 E5의 질의 입력 형식인 `query: `를 붙입니다. E5가 출력한 각
토큰의 상태는 실제 토큰이 있는 위치만 평균하고, 마지막으로 벡터 길이가 `1`이
되도록 정규화합니다.

```text
text
    -> "query: " + text
    -> E5 token states
    -> attention-mask mean pooling
    -> L2 normalization
    -> embedding[384]
```

E5의 가중치는 이 모듈을 학습할 때 변경하지 않습니다. E5는 항상 같은 방식으로
의미 벡터를 만드는 고정된 입력 변환기이고, 뒤에 있는 호환성 계산만 학습합니다.

## 긴 프롬프트 처리

프롬프트 내용이 480토큰을 넘으면 앞부분 240토큰과 뒷부분 240토큰을 사용합니다.
앞부분은 주제와 주요 지시를, 뒷부분은 마지막 조건과 질문을 보존하기 위한
구성입니다.

```text
content_tokens <= 480
    -> use all content tokens

content_tokens > 480
    -> first 240 tokens + last 240 tokens
```

이 처리 뒤에 `query: ` 접두사와 E5 특수 토큰을 포함해 최대 512토큰으로
인코딩합니다.

## 저차원 호환성 계산

384차원 E5 벡터는 먼저 학습 데이터의 평균 벡터를 빼서 중심을 맞춥니다.

```text
centered_embedding = embedding - training_mean_embedding
```

그다음 학습된 선형 변환을 사용해 384차원 벡터를 2차원 프롬프트 벡터로
줄입니다.

```text
prompt_vector[2] = projection[2, 384] * centered_embedding[384]
```

후보 모델마다 학습된 2차원 모델 벡터와 기준값을 하나씩 가집니다. 프롬프트
벡터와 모델 벡터의 내적에 기준값을 더하면 해당 조합의 품질 logit이 됩니다.

```text
compatibility_logit[model]
    = model_bias[model]
      + dot(prompt_vector, model_vector[model])

compatibility_quality[model]
    = sigmoid(compatibility_logit[model])
```

내적이 크다는 것은 현재 프롬프트의 의미 방향과 해당 모델의 학습된 강점 방향이
잘 맞는다는 뜻입니다. 내적이 작거나 음수이면 그 조합의 예상 품질을 낮춥니다.

2차원은 프롬프트를 두 종류로 분류한다는 뜻이 아닙니다. 두 값은 사람이 정한
도메인 이름이 아니라, 학습 과정에서 모델 사이의 성능 차이를 설명하도록 만들어진
연속적인 좌표입니다.

## 학습 방법

학습 데이터에는 프롬프트와 모델별 관측 품질 `q`, 생성 횟수 `n`이 있습니다.
관측 품질은 성공 횟수와 실패 횟수로 바꾸고, 작은 관측에서 확률이 바로 `0`이나
`1`에 고정되지 않도록 양쪽에 `0.5`를 더합니다.

```text
successes = round(q * n) + 0.5
failures  = n - round(q * n) + 0.5
trials    = successes + failures
```

학습 대상은 다음 값입니다.

- 384차원을 2차원으로 줄이는 projection
- 후보 모델별 2차원 model vector
- 후보 모델별 bias

이 값들은 관측된 성공과 실패의 이항 음의 로그 가능도를 최소화하도록 함께
학습합니다. 생성 횟수가 많은 행은 더 많은 관측으로 뒷받침되므로 손실에 더 큰
무게를 가집니다. projection과 model vector에는 가중치가 지나치게 커지는 것을
억제하는 정규화를 적용하고, 모델별 bias에는 적용하지 않습니다.

## 이항 로지스틱 품질 모듈과 결합

이 모듈은 이항 로지스틱 품질 모듈과 독립적으로 학습합니다. 이항 로지스틱
모듈의 예측값이나 오차를 학습 입력으로 사용하지 않습니다.

실행할 때는 두 모듈이 계산한 품질 logit을 같은 비율로 결합합니다.

```text
combined_logit[model]
    = 0.5 * binomial_logit[model]
      + 0.5 * compatibility_logit[model]

combined_quality[model]
    = sigmoid(combined_logit[model])
```

확률을 바로 평균하지 않고 logit을 결합하므로, 두 모듈이 계산한 품질 근거를
sigmoid 적용 전의 같은 척도에서 합칩니다.

## 출력과 라우터의 경계

모듈의 출력은 프롬프트마다 계산한 후보 모델별 예상 품질입니다.

```text
{
    model_a: combined_quality_a,
    model_b: combined_quality_b,
    model_c: combined_quality_c
}
```

이 모듈은 최종 모델을 직접 선택하거나 예산을 배분하지 않습니다. 출력된 예상
품질은 별도의 비용 예측값과 함께 기존 비용 인식 allocator에 전달됩니다.
allocator가 등급별 예산 안에서 전체 입력의 모델 선택을 결정합니다.

## 학습 후 저장하는 값

학습이 끝나면 새로운 프롬프트에 같은 계산을 적용하는 데 필요한 다음 값을
저장합니다.

- E5 모델 식별자와 고정 리비전
- 접두사, 토큰 한도, 긴 프롬프트 선택 방식과 pooling 방식
- 학습 데이터에서 계산한 384차원 평균 벡터
- 384차원을 2차원으로 줄이는 projection
- 후보 모델별 2차원 model vector와 bias
- 이항 로지스틱 품질과 호환성 품질을 결합하는 비율

개별 학습 프롬프트, 개별 의미 벡터, 관측 품질과 생성 결과는 학습 결과에
저장하지 않습니다.
