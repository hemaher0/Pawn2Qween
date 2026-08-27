<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

# E5 model provenance and reproduction

## Upstream model

The E5 compatibility component uses the upstream FP32 ONNX export from
[`intfloat/multilingual-e5-small`](https://huggingface.co/intfloat/multilingual-e5-small).
The model repository declares the MIT license. Runtime files are pinned to the
immutable revision below; the model bytes are downloaded separately and are
not committed to this repository.

```text
model: intfloat/multilingual-e5-small
revision: fd1525a9fd15316a2d503bf26ab031a61d056e98
license: MIT
```

| Upstream path | Size | SHA-256 |
| --- | ---: | --- |
| `onnx/model.onnx` | 470,268,510 bytes | `ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665` |
| `onnx/tokenizer.json` | 17,082,730 bytes | `0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39` |

The repository does not convert, quantize, or re-export the ONNX graph. The
fetch tool streams both files from the exact revision, checks their sizes and
SHA-256 values, and publishes them to the requested local directory only after
verification succeeds.

```console
python tools/fetch_e5_model.py \
  --spec configs/e5-model.v1.json \
  --output build/e5-model
```

## Preprocessing identity

The aggregate compatibility artifact binds the model bytes to preprocessing
identity `e5-query-head-tail-mean-pool-l2-v1`:

1. tokenize canonical prompt content without special tokens;
2. retain all content through 480 tokens, otherwise retain the first 240 and
   last 240 content tokens;
3. prepend `query: ` and add the tokenizer's special tokens;
4. run the pinned ONNX model with a maximum sequence length of 512;
5. mean-pool the last hidden state over positions selected by the attention
   mask; and
6. L2-normalize the resulting 384-dimensional FP32 vector.

The encoder runs with ONNX Runtime's `CPUExecutionProvider`, sequential graph
execution, two intra-op threads, and one inter-op thread. Runtime inference
does not download files or access outcomes.

## Runtime dependencies

The tested runtime dependency set is:

- [NumPy 2.0.2](https://github.com/numpy/numpy/blob/v2.0.2/LICENSE.txt),
  BSD-3-Clause;
- [ONNX Runtime 1.28.0](https://github.com/microsoft/onnxruntime/blob/v1.28.0/LICENSE),
  MIT; and
- [tokenizers 0.22.2](https://github.com/huggingface/tokenizers/blob/v0.22.2/LICENSE),
  Apache-2.0.

PyTorch is used only for offline fitting of the two-dimensional aggregate
compatibility head. It is not imported by the runtime router.

## Submission image contents

The submission image uses the digest-pinned
`python:3.11.15-slim-bookworm` Docker Official Image. Its dependency stage
installs the locked `e5-runtime` group for `linux/arm64`; the final stage copies
that virtual environment without `uv` or Python package-management tools. The
copied environment retains installed wheel metadata and any license files
shipped in those wheels.

The final image also contains exactly the E5 execution modules needed by the
router, the bundled routing policy, and these three aggregate artifacts:

- `baselines/hash-regex-public.v1.json`;
- `baselines/binomial-logistic-quality-public.v1.json`; and
- `baselines/e5-bilinear-compatibility-public.v1.json`.

The build copies the project `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md`,
`LICENSES/`, and the pinned model specification to
`/usr/share/licenses/pawn2qween/`. The upstream model license declaration,
immutable revision, file sizes, and hashes remain recorded in
[`configs/e5-model.v1.json`](../configs/e5-model.v1.json); runtime dependency
notices are summarized in
[`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).

Run the supported image build from the repository root:

```console
IMAGE_NAME=my-router:check ./scripts/build-arm64.sh
```

The script downloads or revalidates the model cache before Docker receives the
build context. It then measures the ARM64 OCI compressed layers and merged
root filesystem against the hard image limits and runs one constrained toy
smoke. On a non-ARM64 Docker server, that smoke is compatibility screening
only. It does not replace the required native ARM64 full Train+Dev latency
check described in [`RUNTIME.md`](RUNTIME.md). The generated local report has
`submission_ready: false`; the exact pushed repository digest requires separate
official image-size evidence.

## Reproducing aggregate artifacts

First materialize content-aligned ONNX vectors. The archive is a local build
artifact and is not committed.

```console
PYTHONPATH=src:. python baselines/train_e5_binomial_router.py encode \
  --train-input data/materialized/train/inputs.json \
  --dev-input data/materialized/dev/inputs.json \
  --model-spec configs/e5-model.v1.json \
  --model-dir build/e5-model \
  --output build/e5-bilinear/onnx-features.npz
```

Then fit the Train-only binomial and rank-two compatibility artifacts on one
CUDA device. The publication command fixes the retained seed, rank, optimizer,
step count, regularization, and blend weight; it exposes no tuning flags.

```console
PYTHONPATH=src:. python baselines/train_e5_binomial_router.py fit \
  --train-input data/materialized/train/inputs.json \
  --train-outcomes data/train/outcomes.json \
  --features build/e5-bilinear/onnx-features.npz \
  --hash-artifact baselines/hash-regex-public.v1.json \
  --binomial-output baselines/binomial-logistic-quality-public.v1.json \
  --compatibility-output baselines/e5-bilinear-compatibility-public.v1.json
```

The committed artifacts contain only aggregate parameters and Train
provenance. They do not contain prompts, identifiers, per-row embeddings,
outcomes, answers, or predictions.

## Offline execution

The runtime requires the verified model directory and the three aggregate
router artifacts. It derives both quality signals from prompt content, reuses
the hash-regex cost predictions, and delegates selection to the existing
cost-aware allocator.

```console
PYTHONPATH=src:. python baselines/e5_binomial_router.py \
  --input input.json \
  --tier balanced \
  --model-dir build/e5-model \
  --output submission.json
```

No runtime network access is required.
