<!--
SPDX-FileCopyrightText: Copyright 2026 SK TELECOM CO., LTD.
SPDX-FileCopyrightText: Copyright 2026 hemaher0

SPDX-License-Identifier: Apache-2.0
-->

# Efficient LLM Routing Challenge

**프롬프트 난이도·특성에 따라 최적 모델을 선택하는 compute-efficient routing
오픈소스 라우터 개발 챌린지**

이 과제에서는 입력 프롬프트의 내용만 보고 다음 세 평가용 모델 프로필 중 하나를
선택하는 라우터를 만듭니다.

- `ax31-light`
- `ax31`
- `axk1-think`

라우터는 모델을 직접 호출하지 않습니다. 운영자는 라우터가 선택한 모델과
미리 계산해 둔 모델별 평가 결과를 결합하여 품질과 비용을 계산합니다.
따라서 문항마다 프롬프트 내용으로 모델 하나를 한 번 선택하며, 실시간으로
모델 답변을 호출하거나 여러 답변을 비교하는 단계는 없습니다.

## 참가 순서

1. 이 저장소를 참가 팀의 GitHub 계정이나 조직으로 fork합니다.
2. 공개 Train/Dev 자료와 규칙을 확인하고 baseline에서 구현을 시작합니다.
3. `self-check`와 컨테이너 실행으로 세 등급의 선택 결과를 확인합니다.
4. 제출할 코드 커밋을 공개하고, 그 커밋에서 `linux/arm64` 이미지를 빌드해
   공개 레지스트리에 push합니다.
5. 저장소 루트에 `submission-ossp-skt.json`을 추가해 별도 커밋하고, 이
   커밋의 고정된 GitHub 스냅샷 URL을 결과보고서의 `프로젝트 등록 URL`에
   기재합니다.

로컬 clone 등 개발 방법과 브랜치 이름은 자유입니다. 다만 제출 시점부터 평가가
끝날 때까지 평가할 fork와 커밋을 별도 권한 없이 열 수 있어야 합니다.
수상팀은 수상일로부터 5년 동안 제출 저장소를 공개 상태로 유지해야 합니다.

질문과 문서·하네스 오류 신고는 이 저장소의 GitHub Issues에서 받습니다.

## 공개 Train/Dev 준비

참가자에게 Train 1,760문항과 Dev 880문항을 제공합니다. 각 문항에는 라우팅
입력과 모델별 실행 결과에서 산출한 점수 및 토큰 사용량이 포함됩니다. 일부
원천 자료는 라이선스 조건에 따라 고정된 절차로 내려받거나 재현합니다.
비공개 평가 자료의 구성과 분할 기준은 공개하지 않습니다.

재배포 가능한 프롬프트와 모델 답변 본문을 제외한 평가 결과는 `data/train/`과
`data/dev/`에 있습니다. 재배포가 불가한 AIME 원문은 타 repository로부터
Train/Dev에 필요한 고정 파일만 공개 출처에서 받아 결합합니다.
자료 생성에는 Python 3.10 이상과 uv 0.12.3이 필요합니다.

```console
uv run --locked --no-dev --group materialize \
  python tools/materialize_public_data.py
```

완성된 입력은 Git 비추적 경로인 `data/materialized/train/inputs.json`과
`data/materialized/dev/inputs.json`에 생깁니다. 입력 수와 SHA-256은
[`data/public-data.v1.json`](data/public-data.v1.json), 출처와 고지는
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)에서 확인할 수 있습니다.

## E5 제출 라우터: 학습부터 오프라인 추론까지

현재 제출 라우터는 **학습이 필요한 모델**입니다. 다만 학습 위치와 평가 위치가
다릅니다.

- 개발·재현 단계에서는 공개 Train으로 hash-regex cost head, binomial quality
  head와 E5 compatibility head를 반드시 학습합니다.
- `intfloat/multilingual-e5-small` 자체의 가중치는 fine-tune하지 않습니다. 고정된
  공개 ONNX 가중치를 prompt encoder로만 사용합니다.
- 학습이 끝나면 세 aggregate JSON과 고정 E5 ONNX model/tokenizer를 이미지에
  넣습니다.
- 공식 평가에서는 이 파일로 inference만 수행합니다. 재학습, outcome 접근,
  model download와 다른 네트워크 접근은 하지 않습니다.

이 흐름은 [대회 규칙](docs/CHALLENGE_RULES.md)의 공개 데이터 사용 경계와
일치합니다. 공개 Train/Dev에서 계수와 학습 파일을 만들고 재배포 가능한 소형
NLP 모델을 이미지에 포함하는 것은 허용되며, 금지되는 것은 공식 평가 중의
네트워크·외부 추론 서비스·비공개 평가 정보 사용입니다.

저장소에는 위 과정을 이미 완료한 세 aggregate artifact가 포함되어 있습니다.
따라서 공개된 현재 라우터를 그대로 실행하거나 심사하는 사람은 다시 학습하지
않습니다. 반면 artifact를 처음부터 재현하거나 변경하는 개발자는 아래 학습
절차를 생략하면 안 됩니다.

제출 이미지에는 `src/ossp_router/`의 inference code만 들어갑니다. Offline CLI인
[`train_e5_binomial_router.py`](baselines/train_e5_binomial_router.py)는 content
encoding ([`e5_training_features.py`](baselines/e5_training_features.py)),
Train-only fit ([`e5_training_fit.py`](baselines/e5_training_fit.py)), 고정 artifact
평가 ([`e5_training_evaluation.py`](baselines/e5_training_evaluation.py))에만
위임하며, 이 training 모듈들은 wheel이나 제출 이미지에 포함되지 않습니다.

### 1. 공개 데이터와 고정 E5 파일 준비

공개 데이터를 위 명령으로 materialize한 다음, 네트워크가 허용된 개발 환경에서
고정 revision의 E5 파일을 한 번 내려받습니다. 다운로드 도구는 파일 크기와
SHA-256이 model spec과 모두 일치해야만 파일을 게시합니다.

```console
uv run --locked --no-dev python tools/fetch_e5_model.py \
  --spec configs/e5-model.v1.json \
  --output build/e5-model

uv run --locked --no-dev python tools/fetch_e5_model.py \
  --spec configs/e5-model.v1.json \
  --output build/e5-model \
  --check
```

대회 규칙이 네트워크를 금지하는 시점은 공식 평가 실행 중입니다. 개발자는 공개
모델을 이미지 빌드 전에 받아 고정해야 하며, 제출 커밋에서 그 이미지를 재현할
수 있어야 합니다. 최종 컨테이너는 `build/e5-model/onnx/model.onnx`와
`tokenizer.json`을 복사한 뒤 `--network none` 환경에서 실행합니다.

### 2. hash-regex cost artifact 학습

Train 1,760문항으로 feature standardization과 ridge head를 학습하고, Dev
880문항은 세 tier의 safety ratio만 보정하는 데 사용합니다. 아래 명령은 실제
공개 artifact를 만든 모든 선택값을 명시합니다.

```console
uv run --locked --no-dev --group train \
  python baselines/train_hash_regex.py \
  --input data/materialized/train/inputs.json \
  --outcomes data/train/outcomes.json \
  --validation-input data/materialized/dev/inputs.json \
  --validation-outcomes data/dev/outcomes.json \
  --artifact build/e5-training/hash-regex-public.v1.json \
  --report build/e5-training/hash-regex-report.json \
  --hash-bins 256 \
  --folds 5 \
  --alphas 0.1,1,10,100 \
  --safety-grid-size 121
```

### 3. 고정 E5 embedding 생성

이 단계는 Train과 Dev의 prompt content만 인코딩합니다. outcome은 읽지 않으며,
E5 가중치도 변경하지 않습니다. 생성되는 NPZ는 로컬 중간 파일이므로 Git이나
제출 이미지에 넣지 않습니다.

```console
uv run --locked --no-dev --group e5-runtime \
  python baselines/train_e5_binomial_router.py encode \
  --train-input data/materialized/train/inputs.json \
  --dev-input data/materialized/dev/inputs.json \
  --model-spec configs/e5-model.v1.json \
  --model-dir build/e5-model \
  --output build/e5-training/onnx-features.npz
```

### 4. Train-only quality artifact 학습

publication fit은 Python 3.11, Linux x86_64와 NVIDIA CUDA 장치 하나를
요구합니다. `e5-train`은 `e5-runtime`을 포함하고 PyTorch 2.8.0 및
scikit-learn 1.7.2를 별도로 설치합니다. 이 의존성은 wheel이나 제출 이미지에
포함되지 않습니다.

```console
uv run --locked --no-dev --group e5-train \
  python baselines/train_e5_binomial_router.py fit \
  --train-input data/materialized/train/inputs.json \
  --train-outcomes data/train/outcomes.json \
  --features build/e5-training/onnx-features.npz \
  --hash-artifact build/e5-training/hash-regex-public.v1.json \
  --binomial-output build/e5-training/binomial-logistic-quality-public.v1.json \
  --compatibility-output build/e5-training/e5-bilinear-compatibility-public.v1.json
```

### 5. 학습과 평가를 분리해 실행

`fit`이 만든 artifact를 고정한 다음 별도 `evaluate` 명령을 실행합니다. 이
명령은 grouped Train OOF와 held-out Dev를 비교하며, Dev 선택을 hash로 고정한
뒤에만 Dev outcome을 읽습니다. 모든 tier가 예산을 통과하고 사전 정의한 성능
gate를 통과하지 않으면 exit code `2`로 실패합니다.

```console
uv run --locked --no-dev --group e5-train \
  python baselines/train_e5_binomial_router.py evaluate \
  --train-input data/materialized/train/inputs.json \
  --train-outcomes data/train/outcomes.json \
  --dev-input data/materialized/dev/inputs.json \
  --dev-outcomes data/dev/outcomes.json \
  --features build/e5-training/onnx-features.npz \
  --hash-artifact build/e5-training/hash-regex-public.v1.json \
  --binomial-artifact build/e5-training/binomial-logistic-quality-public.v1.json \
  --compatibility-artifact build/e5-training/e5-bilinear-compatibility-public.v1.json \
  --report build/e5-training/evaluation-report.json
```

평가가 성공한 artifact만 runtime resource로 게시합니다.

```console
install -m 0644 build/e5-training/hash-regex-public.v1.json \
  src/ossp_router/resources/hash-regex-public.v1.json
install -m 0644 build/e5-training/binomial-logistic-quality-public.v1.json \
  src/ossp_router/resources/binomial-logistic-quality-public.v1.json
install -m 0644 build/e5-training/e5-bilinear-compatibility-public.v1.json \
  src/ossp_router/resources/e5-bilinear-compatibility-public.v1.json
```

동일한 고정 소프트웨어·가속기 환경에서 공식 artifact를 재현할 때의 목표는 세
파일의 byte-for-byte 일치입니다. 다른 CUDA 장치나 수치 라이브러리에서 diff가
생겼다고 자동으로 게시하면 안 됩니다. 기존 artifact와 evaluation report를
함께 검수하고, 새 학습 결과를 의도한 경우에만 별도 기능 커밋으로 게시합니다.

### 6. 학습 완료 artifact로 inference

`router-run`과 컨테이너 entrypoint는 모두 안정된
`ossp_router.e5_router.route(inputs, policy, tier, artifacts)` 경계만
호출합니다. 기본값은 패키지에 포함된 세 artifact와 `build/e5-model`입니다.

```console
for tier in fast balanced premium; do
  uv run --locked --no-dev --group e5-runtime \
    router-run \
    --input data/materialized/dev/inputs.json \
    --tier "$tier" \
    --model-dir build/e5-model \
    --output "build/e5-submission/dev/$tier.json"
done

uv run --locked --no-dev python -m ossp_router.cli self-check \
  --input data/materialized/dev/inputs.json \
  --outcomes data/dev/outcomes.json \
  --submissions build/e5-submission/dev \
  --report build/e5-submission/dev-report.json
```

다른 artifact를 시험할 때만 `--hash-artifact`, `--binomial-artifact`,
`--compatibility-artifact`를 지정합니다. `--policy`를 생략하면 package의 동결
v1 policy를 사용합니다.

### 고정 hyperparameter와 runtime 상수

아래 값은 현재 공개 artifact와 선택 결과에 영향을 주는 고정값입니다. `fit`은
이 값을 CLI tuning flag로 노출하지 않습니다.

| 구성요소 | 고정값 |
| --- | --- |
| Hash feature | dense 14개, FNV-1a 64-bit signed word unigram/bigram 256 bins |
| Hash ridge 선택 | 5-fold deterministic OOF; alpha 후보 `0.1, 1, 10, 100`; 목적함수 `score MSE + 0.05 × log-cost MSE`; 선택 alpha `100` |
| Hash safety 보정 | tier별 `1 / budget_multiplier`부터 `1`까지 121점; 최종 Fast `0.9483333333333334`, Balanced `0.9166666666666667`, Premium `0.925` |
| Binomial target | 모델·행별 generation count; success/failure 각각 Jeffreys pseudocount `0.5` |
| Binomial optimizer | Newton method; inverse regularization `0.01`(L2 strength `100`); 최대 2,000회; tolerance `1e-10`; backtracking 최대 60회, step factor `0.5` |
| Binomial normalization | feature standard deviation floor `1e-12`; 그 이하는 scale `1` |
| E5 upstream | `intfloat/multilingual-e5-small`, revision `fd1525a9fd15316a2d503bf26ab031a61d056e98`, FP32 ONNX, 가중치 fine-tuning 없음 |
| E5 preprocessing | prefix `query: `; content 480 tokens; 초과 시 head 240 + tail 240; 전체 최대 512; mean pooling 후 L2 normalization; embedding 384차원 |
| E5 encoding batch | 최대 64 rows, padded token 합계 최대 4,096 |
| Compatibility fit | latent rank `2`; full-fit seed `20260927`; grouped OOF 4-fold seed `20260827 + fold_index`; projection/model vector 초기화 `Normal(0, 0.05)` |
| Compatibility optimizer | deterministic AdamW; 1,200 steps; learning rate `0.03`; projection/model vector weight decay `0.05`; bias weight decay `0` |
| Quality 결합 | binomial logit `0.5` + compatibility logit `0.5`; probability clip epsilon `1e-5` |
| Cost runtime | predicted log-cost clamp `[-50, 50]`; 모델 cost 단조성 epsilon `1e-12` |
| Allocator | penalty upper bound를 `1`에서 `2^60`까지 배가; binary search 80회; Premium AX31 fill safety `0.65` |
| ONNX CPU runtime | `CPUExecutionProvider`; sequential execution; intra-op 2 threads; inter-op 1 thread; ORT graph optimization all; `OPENBLAS_NUM_THREADS=2`, `OMP_NUM_THREADS=2` |

### Python과 dependency/test 범위

| 범위 | Python | dependency group | 검증 범위 |
| --- | --- | --- | --- |
| protocol, scorer, 기본 CLI | 3.9와 3.11 | 없음 | CI full discovery |
| 공개 데이터 materialization | 3.10 이상 | `materialize` | materializer tests |
| hash-regex 학습 | 3.9 이상 | `train` | NumPy training tests |
| E5 inference 및 제출 이미지 | 3.11 | `e5-runtime` | CPU ONNX/runtime/packaging tests |
| E5 publication fit와 evaluation | 3.11, Linux x86_64 + CUDA | `e5-train` | deterministic CPU unit tests와 별도 CUDA publication run |

Python 3.9 지원은 core protocol과 NumPy hash-regex 경로에만 해당합니다. 최종
E5 라우터와 `linux/arm64` 제출 컨테이너는 Python 3.11로 동결합니다.

## 라우터 실행 입력

입력 JSON에는 정수 `schema_version: 1`, `challenge_id`, 데이터 구분을
나타내는 `split`, `episodes`가 들어 있습니다. 각 문항은 최대 128자인
불투명한 `episode_id`와 다음 둘 중 하나만 포함합니다.

- 비어 있지 않은 `prompt`
- `system`, `user`, `assistant` 역할과 `content`로 구성된 비어 있지 않은
  `messages`

공식 평가에서 벤치마크 이름, 데이터 출처, 정답, 모델 답변과 문항별 모델
평가 결과는 라우터 실행 입력으로 제공하지 않습니다. `challenge_id`, `split`,
`episode_id`는 실행 검증과 선택 결과의 문항 연결에만 사용하며 모델 선택에는
사용할 수 없습니다. 해시, 정규식, n-gram, 임베딩처럼 프롬프트 내용에서 직접
계산한 정보는 모델 선택에 사용할 수 있습니다.

공개 Train/Dev에서는 프롬프트와 별도 평가 결과를 연결하고 공개 비용 정책을
적용해 모델별 비용을 계산할 수 있습니다. 이 정보는 학습·검증과 등급별 정책
최적화에 사용할 수 있습니다. 공식 평가 실행 때는 문항별 실제 비용이
제공되지 않으므로, 필요한 경우 공개 정책과 프롬프트 특징으로 비용을
추정할 수 있습니다.

## 라우터 선택 결과

라우터는 `fast`, `balanced`, `premium` 세 등급에 대해 각각 제출 JSON을
만듭니다. 모든 입력 문항마다 `episode_id`와 `model_id`를 정확히 한 번
기록해야 합니다.

| 등급 | 최대 비용 비율 | 최종 점수 가중치 |
| --- | ---: | ---: |
| Fast | 1.25 | 0.4 |
| Balanced | 2.0 | 0.3 |
| Premium | 4.0 | 0.3 |

비용 비율은 같은 입력 전체를 `ax31-light`로 선택했을 때의 비용을 1로 둔
상대값입니다. 한도를 넘은 등급의 점수는 0입니다.

## 왜 이런 평가 방식인가요?

실제 서비스에서는 앞으로 들어올 요청의 분포를 완벽하게 알 수 없으며, 모델
서빙에도 동시성·대기열·메모리 같은 용량 한계가 있습니다. 이 과제는 공개
Train/Dev로 정책을 개발하되 별도 입력에서도 일반화하고, 정해진 비용 안에서
품질을 높이는 상황을 모사합니다. 예산을 넘긴 정책은 대기열 증가, 응답 시간
목표 위반이나 서빙 실패를 일으킬 수 있는 운영 불가능한 구성으로 보아 해당
등급을 0점 처리합니다.

## Quickstart: baseline에서 시작하기

별도 패키지를 설치하지 않고 toy 자료에서 baseline과 채점 흐름을 확인할 수
있습니다. 먼저 모든 문항에 경량 모델을 선택하는 세 등급 결과를 만듭니다.

```console
uv run --locked --no-dev python baselines/always_light.py \
  --input data/toy/inputs.json \
  --output-dir build/toy-submission

uv run --locked --no-dev python -m ossp_router.cli self-check \
  --input data/toy/inputs.json \
  --outcomes data/toy/outcomes.json \
  --submissions build/toy-submission \
  --report build/toy-report.json
```

첫 번째 명령은 세 등급의 선택 결과를 만들고, 두 번째 명령은 파일 형식, 문항
누락 여부, 비용 한도와 점수를 검사합니다. 다음으로 프롬프트 길이, 언어,
코드·수학 기호만 사용하는 baseline을 세 등급에 실행해 볼 수 있습니다.

```console
for tier in fast balanced premium; do
  uv run --locked --no-dev python baselines/prompt_heuristic.py \
    --input data/toy/inputs.json \
    --tier "$tier" \
    --output "build/prompt-heuristic/$tier.json"
done

uv run --locked --no-dev python -m ossp_router.cli self-check \
  --input data/toy/inputs.json \
  --outcomes data/toy/outcomes.json \
  --submissions build/prompt-heuristic \
  --report build/prompt-heuristic-report.json
```

[`src/ossp_router/heuristic.py`](src/ossp_router/heuristic.py)의 특징 추출과
`select_model`을 바꾸는 것이 가장 짧은 구현 경로입니다. 등급·문항 ID·입력
순서가 아니라 프롬프트 내용만 모델 선택 함수에 전달하십시오. 더 강한 특징
baseline과 공개 Train/Dev로 학습하는 예제는
[baseline 안내](baselines/README.md)에 있습니다.

정책 파일은 패키지에 포함된 동결 v1을 기본으로 사용하며, 별도 파일을
검사할 때만 `--policy`를 지정합니다.

저장소 루트에 기술 제출 정보 파일을 작성한 뒤에는 다음 명령으로 여섯 필드,
코드 커밋 SHA, 이미지 다이제스트와 라이선스 값을 확인합니다.

```console
uv run --locked --no-dev python tools/validate_technical_submission.py
```

최종 이미지의 실행 시간과 자원 제한은 공개 Train/Dev 전체로 미리 확인할 수
있습니다. 제공하는 빌드 스크립트는 고정 E5 ONNX 모델과 tokenizer를 내려받아
검증하고 `linux/arm64` E5-binomial 이미지를 만든 뒤, 이미지 크기와 제한된
toy smoke를 먼저 검사합니다.

```console
IMAGE_NAME=my-router:check ./scripts/build-arm64.sh

uv run --locked --no-dev python tools/check_runtime.py \
  --image my-router:check \
  --report build/runtime-check-report.json
```

이 검사는 위 materialization으로 만든 공개 Train 1,760문항과 Dev 880문항만
사용합니다. 공개 모델별 outcome과 최종 평가 자료는 컨테이너에 전달하지
않습니다. QEMU를 사용하는 비네이티브 호스트의 smoke와 전체 검사 시간은
호환성 참고값이며 90초 통과 증거가 아닙니다. 제출 전에는 네이티브
`linux/arm64` 서버에서 다음 strict 빌드를 실행해 세 등급의 전체 Train+Dev
검사를 완료하십시오.

```console
OSSP_REQUIRE_NATIVE_RUNTIME=1 \
  IMAGE_NAME=my-router:check \
  ./scripts/build-arm64.sh
```

## 문서

이 챌린지를 이해하는 데 가장 중요한 네 문서는 다음과 같습니다.

- [과제 규칙](docs/CHALLENGE_RULES.md)
- [제출 안내](docs/SUBMISSION.md)
- [컨테이너 실행 규격](docs/RUNTIME.md)
- [데이터 카드](docs/DATA_CARD.md)

점수와 예외 처리가 필요할 때 참고해 주세요.

- [점수 계산](docs/SCORING.md)
- [실행 오류와 규칙 집행](docs/ENFORCEMENT.md)
- [데이터 라이선스](DATA_LICENSES.md)

공개 운영 절차와 자원 측정 근거는 [전체 문서 안내](docs/README.md)에 별도로
모았습니다. 라우터 구현에 필요한 필수 문서는 아닙니다.

출품작 제출 마감은 2026년 8월 27일 18:00(대한민국 표준시)이며,
[공식 대회 접수 사이트](https://osscontest.kr/)의 출품작 제출 절차를 따릅니다.
공식 결과보고서 원본 파일과 PDF를 업로드하며, 결과보고서의 `프로젝트 등록
URL`로 공개 저장소를 제출합니다. 마감 전에는 결과보고서를 복수로 제출하거나
자유롭게 다시 업로드할 수 있으며 마지막으로 접수된 파일을 심사합니다.

`submission-ossp-skt.json`은 사이트에 별도로 업로드하지 않고 제출 저장소
루트에 반드시 커밋합니다. 파일 형식과 최종 커밋 순서는
[제출 안내](docs/SUBMISSION.md)에 기록합니다.

## 제공 내용

이 저장소에는 공개 Train/Dev 자료, 네 가지 baseline, 형식·점수 검증 도구,
참가자용 컨테이너 예제와 공개 평가 하네스가 들어 있습니다. 공식 플랫폼은
`linux/arm64`이며 최종 자원 한도는
[컨테이너 실행 규격](docs/RUNTIME.md)에 동결했습니다.

## 라이선스

프로젝트가 직접 작성한 코드와 문서는 [Apache License 2.0](LICENSE)으로
제공합니다. 이 라이선스는 제3자 벤치마크 자료를 재라이선스하지 않습니다.
자료별 조건은 [DATA_LICENSES.md](DATA_LICENSES.md)에 따로 기록합니다.
