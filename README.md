<!--
SPDX-FileCopyrightText: Copyright 2026 SK TELECOM CO., LTD.
SPDX-FileCopyrightText: Copyright 2026 hemaher0

SPDX-License-Identifier: Apache-2.0
-->

# Pawn2Qween

## 개발 배경 및 목적

생성형 AI 요청은 단순 질의부터 수학·코딩·추론 문제까지 난이도와 특성이
다릅니다. 모든 요청을 고성능 모델로 처리하면 비용과 지연이 커지고, 경량
모델만 사용하면 복잡한 요청의 품질이 낮아집니다.

Pawn2Qween은 프롬프트 내용만 분석하여 `ax31-light`, `ax31`, `axk1-think` 중
적합한 모델을 선택하는 오픈소스 LLM 라우터입니다. 실제 모델을 호출하거나
복수 답변을 비교하지 않고 후보 모델의 품질과 비용을 미리 추정하여,
Fast·Balanced·Premium의 비용 한도 안에서 입력 전체의 기대 품질을
최대화합니다.

- 제출 inference: `src/ossp_router/`
- offline 학습·평가: `src/ossp_router/training/`
- 단순 비교 예제: `baselines/`

## 시스템 구성 및 아키텍처

```text
프롬프트 입력
  → prompt-only 구조·어휘 특징과 E5 의미 embedding 생성
  → 모델별 binomial 품질, E5 호환성, 비용 예측
  → 두 품질 logit을 0.5:0.5로 결합
  → tier별 비용 한도와 safety ratio를 적용한 전역 할당
  → episode_id와 model_id를 기록한 submission JSON 생성
```

- 구조 경로는 길이, 한글 비율, 코드·수학·숫자 신호와 signed unigram·bigram
  hashing으로 모델별 품질과 비용을 예측합니다.
- 의미 경로는 고정 E5 encoder의 384차원 embedding을 학습된 2차원 공간에
  투영하여 프롬프트와 후보 모델의 호환성을 계산합니다.
- 예산 경로는 문항을 따로 고르지 않고 batch 전체의 예상 비용을 함께 고려해
  각 tier의 한도 안에서 모델을 배분합니다.
- 실행 중에는 네트워크, 외부 API, 정답, 모델 응답과 평가 outcome을 사용하지
  않습니다. model·tokenizer·artifact identity를 검증하고 submission을
  원자적으로 저장합니다.

## 주요 기능

1. 한국어·영어, 코드, 수학식과 장문을 함께 반영하는 하이브리드 prompt 분석
2. 공개 Train 1,760건의 관측 품질과 generation count를 이용한 모델별
   binomial 품질 예측
3. E5 본체를 fine-tune하지 않고 rank 2 호환성 head만 학습하는 경량 의미 모델
4. 예상 품질과 token cost를 함께 사용하는 tier별 전역 예산 할당
5. 고정 revision·dependency·SHA-256으로 재현하는 offline ARM64 inference

세 aggregate JSON의 합계는 약 142KB이며, 학습이 끝난 runtime은 이 파일과
고정 E5 ONNX model만 사용합니다.

## 개발 환경

| 범위 | 환경 |
| --- | --- |
| 개발·학습 장비 | Linux x86_64, Intel Xeon Silver 4208 2개(32 threads), RAM 약 125GiB, NVIDIA GeForce RTX 2080 Ti 4개(각 11GB); 최종 호환성 fit은 GPU 1개 사용 |
| 평가 환경 | `linux/arm64`, CPU 2 cores, RAM 2GiB, GPU·network 없음, tier별 90초 |
| 언어·runtime | Python 3.11, `python:3.11.15-slim-bookworm` final image |
| 주요 library | NumPy 2.0.2, ONNX Runtime 1.28.0, tokenizers 0.22.2, PyTorch 2.8.0, scikit-learn 1.7.2, PyArrow 23.0.1 |
| 개발 도구 | uv 0.12.3, Git, GitHub, Docker, unittest, Ruff |
| 기반 모델 | `intfloat/multilingual-e5-small` fixed FP32 ONNX, MIT License |

## 개발 과정

- 공개 Train 1,760건과 Dev 880건을 고정 schema로 materialize하고 출처,
  license와 SHA-256을 확인했습니다.
- 길이·언어·코드·수학 신호를 사용하는 hash router를 기준으로 만든 뒤,
  generation count를 반영하는 binomial quality model을 학습했습니다.
- 고정 E5 embedding과 후보 모델의 관계를 학습하는 rank 2 compatibility
  head를 추가하고 두 quality logit을 결합했습니다.
- Train으로 quality parameter를 학습하고, Dev로 tier별 safety ratio와 최종
  budget·quality 동작을 확인했습니다.
- 고정 ONNX model, tokenizer와 세 aggregate artifact를 ARM64 image에 포함해
  network와 GPU 없이 같은 inference를 재현하도록 구성했습니다.

## Quickstart

Python 3.11과 uv 0.12.3을 준비한 뒤 E5 runtime 환경을 설치합니다.

```console
uv sync --locked --no-dev --group e5-runtime
```

고정 revision의 ONNX model과 tokenizer를 내려받아 크기와 SHA-256을
검증합니다.

```console
uv run --locked --no-dev --group e5-runtime --no-sync \
  python tools/fetch_e5_model.py \
  --spec configs/e5-model.v1.json \
  --output build/e5-model

uv run --locked --no-dev --group e5-runtime --no-sync \
  python tools/fetch_e5_model.py \
  --spec configs/e5-model.v1.json \
  --output build/e5-model \
  --check
```

패키지에 포함된 학습 완료 artifact로 toy 입력의 세 tier를 실행합니다.

```console
for tier in fast balanced premium; do
  uv run --locked --no-dev --group e5-runtime --no-sync \
    router-run \
    --input data/toy/inputs.json \
    --tier "$tier" \
    --model-dir build/e5-model \
    --output "build/quickstart/$tier.json"
done
```

결과 형식, 문항 누락, 비용 한도와 점수를 확인합니다.

```console
uv run --locked --no-dev --group e5-runtime --no-sync \
  python -m ossp_router.cli self-check \
  --input data/toy/inputs.json \
  --outcomes data/toy/outcomes.json \
  --submissions build/quickstart \
  --report build/quickstart-report.json
```

제출 image를 빌드할 때는 다음 명령을 사용합니다.

```console
IMAGE_NAME=pawn2qween:local ./scripts/build-arm64.sh
```

image entrypoint는 공식 실행 interface와 같은 인자를 받습니다.

```console
router-run \
  --input /challenge/input/inputs.json \
  --tier balanced \
  --output /challenge/output/submission.json
```

`router-run`과 컨테이너 entrypoint는 모두
`ossp_router.e5_router.route(inputs, policy, tier, artifacts) -> Submission`
경계를 호출합니다. 다른 artifact를 시험할 때만 `--hash-artifact`,
`--binomial-artifact`, `--compatibility-artifact`를 지정합니다.

위 Quickstart가 재학습하지 않는 이유는 저장소의 세 JSON이 이미 공개 데이터로
학습된 결과이기 때문입니다. 라우터를 변경하거나 artifact를 처음부터 재현할
때는 아래 학습 절차 전체를 실행해야 합니다. E5 base weight는 fine-tune하지
않고 routing head만 학습합니다. 공식 평가에서는 이미지에 포함된 model과
artifact로 inference만 하며 네트워크를 사용하지 않습니다.

## 학습 artifact 재현

### 1. 공개 Train/Dev materialization

```console
uv run --locked --no-dev --group materialize \
  python tools/materialize_public_data.py
```

입력은 `data/materialized/train/inputs.json`과
`data/materialized/dev/inputs.json`에 생성됩니다. 고정 row count와 SHA-256은
[`data/public-data.v1.json`](data/public-data.v1.json)에 있습니다.

### 2. hash quality·cost artifact 학습

```console
uv run --locked --no-dev --group train \
  router-train hash \
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

Train으로 feature normalization과 ridge head를 학습하고 Dev로 tier별 safety
ratio만 보정합니다.

### 3. 고정 E5 embedding 생성

```console
uv run --locked --no-dev --group e5-runtime \
  router-train encode \
  --train-input data/materialized/train/inputs.json \
  --dev-input data/materialized/dev/inputs.json \
  --model-spec configs/e5-model.v1.json \
  --model-dir build/e5-model \
  --output build/e5-training/onnx-features.npz
```

NPZ에는 Train/Dev prompt content의 embedding과 정렬 digest만 저장하며, outcome은
읽지 않습니다. 이 파일은 학습 중간 산출물이므로 Git과 제출 이미지에 넣지
않습니다.

### 4. Train-only quality artifact 학습

이 단계는 Python 3.11, Linux x86_64와 NVIDIA CUDA device 하나를 사용합니다.

```console
uv run --locked --no-dev --group e5-train \
  router-train fit \
  --train-input data/materialized/train/inputs.json \
  --train-outcomes data/train/outcomes.json \
  --features build/e5-training/onnx-features.npz \
  --hash-artifact build/e5-training/hash-regex-public.v1.json \
  --binomial-output build/e5-training/binomial-logistic-quality-public.v1.json \
  --compatibility-output build/e5-training/e5-bilinear-compatibility-public.v1.json
```

### 5. 고정 artifact 평가

`fit`과 분리된 `evaluate`가 grouped Train OOF와 held-out Dev를 검사합니다.
예산 또는 성능 gate가 실패하면 exit code `2`를 반환합니다.

```console
uv run --locked --no-dev --group e5-train \
  router-train evaluate \
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

평가가 성공한 세 artifact만 runtime resource로 게시합니다.

```console
install -m 0644 build/e5-training/hash-regex-public.v1.json \
  src/ossp_router/resources/hash-regex-public.v1.json
install -m 0644 build/e5-training/binomial-logistic-quality-public.v1.json \
  src/ossp_router/resources/binomial-logistic-quality-public.v1.json
install -m 0644 build/e5-training/e5-bilinear-compatibility-public.v1.json \
  src/ossp_router/resources/e5-bilinear-compatibility-public.v1.json
```

## 고정 hyperparameter

| 구성요소 | 값 |
| --- | --- |
| Hash feature | dense 14개 + FNV-1a 64-bit signed word unigram/bigram 256 bins |
| Hash ridge | deterministic OOF 5-fold; alpha 후보 `0.1, 1, 10, 100`; 목적함수 `score MSE + 0.05 × log-cost MSE`; 공개 artifact 선택값 `100` |
| Hash safety | tier별 `1 / budget_multiplier`부터 `1`까지 121점; Fast `0.9483333333333334`, Balanced `0.9166666666666667`, Premium `0.925` |
| Binomial target | 행·모델별 generation count; success/failure Jeffreys pseudocount 각각 `0.5` |
| Binomial optimizer | Newton method; inverse regularization `0.01`; 최대 2,000회; tolerance `1e-10`; backtracking 최대 60회, factor `0.5` |
| Binomial normalization | 표준편차 floor `1e-12`; 그 이하는 scale `1` |
| E5 model | `intfloat/multilingual-e5-small`; revision `fd1525a9fd15316a2d503bf26ab031a61d056e98`; FP32 ONNX; weight fine-tuning 없음 |
| E5 preprocessing | prefix `query: `; content 480 tokens; 초과 시 head 240 + tail 240; 최대 512; mean pooling 후 L2 normalization; 384 dimensions |
| E5 batch | 최대 64 rows, padded token 합계 최대 4,096 |
| Compatibility model | latent rank `2`; full-fit seed `20260927`; grouped OOF 4-fold seed `20260827 + fold_index`; initialization `Normal(0, 0.05)` |
| Compatibility optimizer | deterministic AdamW; 1,200 steps; learning rate `0.03`; projection/model vector weight decay `0.05`; bias decay `0` |
| Quality blend | binomial logit `0.5` + compatibility logit `0.5`; probability clip epsilon `1e-5` |
| Cost prediction | predicted log-cost clamp `[-50, 50]`; model cost monotonicity epsilon `1e-12` |
| Allocator | penalty bound `1`에서 `2^60`까지 배가; binary search 80회; Premium AX31 fill safety `0.65` |
| ONNX runtime | `CPUExecutionProvider`; sequential execution; intra-op 2 threads; inter-op 1 thread; graph optimization all |

## Dependency와 Python 범위

| 경로 | Python | dependency group |
| --- | --- | --- |
| core protocol, scorer, 기본 CLI | 3.9와 3.11 | 없음 |
| 공개 데이터 materialization | 3.10 이상 | `materialize` |
| hash artifact 학습 | 3.9 이상 | `train` |
| E5 encoding·inference | 3.11 | `e5-runtime` |
| E5 fit·evaluation | 3.11, Linux x86_64 + CUDA | `e5-train` |

`e5-runtime`에는 NumPy, ONNX Runtime과 tokenizers만 들어가며, `e5-train`의
scikit-learn과 PyTorch는 제출 이미지에 포함되지 않습니다.

## 기대 효과 및 활용 분야

Pawn2Qween은 실제 생성 모델을 여러 번 호출하지 않고 prompt만으로 routing을
결정합니다. 단순 요청에는 가벼운 모델을 사용하고 복잡한 요청에는 필요한
성능의 모델을 배분하여, 제한된 비용 안에서 전체 서비스 품질을 유지하는 데
사용할 수 있습니다.

- 여러 LLM을 운영하는 AI gateway와 대규모 생성형 AI platform
- 고객 상담, 문서 질의응답과 검색 서비스
- coding·수학·교육처럼 요청 난이도 차이가 큰 서비스
- 입력을 외부 routing 서비스로 보내기 어려운 on-premises 환경
- 요금제나 service level에 따른 Fast·Balanced·Premium model 배분

후보 모델 정의, 품질·비용 예측과 budget policy를 분리했으므로 다른 모델
조합과 서비스별 비용 정책으로 확장할 수 있습니다.

## 한계와 로드맵

현재 학습 자료는 공개 Train 1,760건이고 후보 모델은 세 종류로 고정되어 있어,
비공개 평가나 새로운 서비스 domain에서는 분포 차이가 생길 수 있습니다.
480 token을 넘는 입력은 앞 240개와 뒤 240개 token을 사용하므로 장문의 중간
정보가 손실될 수 있습니다. 또한 약 465MiB의 FP32 E5 ONNX model을 CPU에서
실행하므로 규칙 기반 router보다 image 크기와 초기 실행 비용이 큽니다.

향후에는 domain별 학습 자료와 후보 모델을 확대하고, 장문 표현과 더 작은
encoder 또는 quantization을 검증하여 같은 runtime 한도에서 정확도와 효율을
개선할 수 있습니다.

## 문서

- [대회 규칙](docs/CHALLENGE_RULES.md)
- [제출 안내](docs/SUBMISSION.md)
- [컨테이너 실행 규격](docs/RUNTIME.md)
- [데이터 카드](docs/DATA_CARD.md)
- [점수 계산](docs/SCORING.md)
- [E5 provenance](docs/E5_MODEL_PROVENANCE.md)
- [데이터 라이선스](DATA_LICENSES.md)

## 라이선스

프로젝트가 직접 작성한 코드와 문서는 [Apache License 2.0](LICENSE)으로
제공합니다. 제3자 자료의 조건은 [DATA_LICENSES.md](DATA_LICENSES.md)와
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)를 따릅니다.
