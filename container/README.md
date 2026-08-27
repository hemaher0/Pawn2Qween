<!--
SPDX-FileCopyrightText: Copyright 2026 SK TELECOM CO., LTD.
SPDX-License-Identifier: Apache-2.0
-->

# Baseline 컨테이너

[`Dockerfile`](Dockerfile)은 E5-binomial 라우터를 표준 `router-run`
인터페이스로 실행합니다. 최종 이미지에는 E5·binomial 실행 코드, 세 aggregate
JSON artifact, 고정한 E5 ONNX 모델과 tokenizer, NumPy·ONNX Runtime·tokenizers
실행 의존성이 들어 있습니다. PyTorch와 오프라인 학습 코드는 실행에 필요하지
않습니다.

라우터 실행 입력 JSON의 컨테이너 내부 경로는
`/challenge/input/inputs.json`, 선택 결과 JSON의 경로는
`/challenge/output/submission.json`, 임시 경로는 `/tmp`입니다. 모델 파일은
저장소에 커밋하지 않습니다. [`../scripts/build-arm64.sh`](../scripts/build-arm64.sh)가
고정 리비전에서 `build/e5-model`로 내려받아 크기와 SHA-256을 검증한 다음
이미지에 포함합니다. 정확한 출처와 파일 해시는
[`../docs/E5_MODEL_PROVENANCE.md`](../docs/E5_MODEL_PROVENANCE.md)에 있습니다.

구체적인 인자, 파일 권한, 제한 시간 초과와 비정상 종료, 출력 검증,
CPU, RAM, 프로세스·스레드 수의 최종 한도는
[`../docs/RUNTIME.md`](../docs/RUNTIME.md)에 정의합니다. 운영자 측 기술 장애,
최대 3회 실행, 첫 유효 결과와 전체 실격 사유는
[`../docs/ENFORCEMENT.md`](../docs/ENFORCEMENT.md)에 정의합니다.

컨테이너는 네트워크 없이, 비특권 UID/GID `65532:65532`, 읽기 전용 파일 시스템에서
실행하도록 설계했습니다. 참가자에게는 시도별 4 MiB 제한 출력 볼륨과
256 MiB `/tmp`만 쓰기 가능하며 GPU나 별도 device를 전달하지 않습니다.
공유 메모리는 제공하지 않고 이미지의 모든 `VOLUME` 선언은 실행 전에
거부합니다. 기반 이미지 출처와 다이제스트는
[`BASE_IMAGE.md`](BASE_IMAGE.md)에 기록합니다.

출력 회수, Docker 자원 정리와 장애 복구 방식은
[`../docs/OPERATIONS.md`](../docs/OPERATIONS.md)에 정의합니다.

## 빌드와 사전 검사

```console
IMAGE_NAME=my-router:check ./scripts/build-arm64.sh
```

이 명령은 `linux/arm64` 이미지를 빌드하면서 OCI layout과 로컬 적재 이미지의
config digest를 결합해 검사합니다. OCI 압축 계층 합계 1 GiB, 병합 rootfs
겉보기 크기 2 GiB 한도를 측정하고, Balanced toy 입력 한 번을 CPU 2개,
메모리 2 GiB, 추가 스왑 없음, 프로세스·스레드 32개, 90초 제한과 공식 격리
옵션으로 실행합니다. 보고서는 `build/e5-image-preflight.json`에 생성됩니다.
이 보고서는 `submission_ready: false`인 build-local screening 기록입니다. 임시
OCI exporter 결과를 검사하므로, 레지스트리에 올린 최종 repository digest의
공식 이미지 크기 증거를 대신하지 않습니다. 최종 제출 artifact는
[`../docs/OPERATIONS.md`](../docs/OPERATIONS.md)의 절차로 다시 측정해야 합니다.

이 사전 검사는 패키징·이미지 크기·제한 조건에서의 실제 E5 호출을 빠르게
확인하는 smoke test입니다. Docker 서버가 `linux/arm64`가 아니면 QEMU를 통한
실행 시간은 호환성 증거일 뿐이며, 공식 90초 성능을 입증하지 않습니다.

제출 전에는 materialization을 마친 공개 Train 1,760문항과 Dev 880문항을
네이티브 `linux/arm64` Docker 서버에서 세 등급 모두 실행해야 합니다. 다음
strict 모드는 네이티브 서버나 전체 입력이 없으면 성공하지 않습니다.

```console
OSSP_REQUIRE_NATIVE_RUNTIME=1 \
  IMAGE_NAME=my-router:check \
  ./scripts/build-arm64.sh
```

통합 테스트는 `OSSP_RUN_CONTAINER_TESTS=1`로 켤 수 있습니다. 기존 공개
baseline 측정 결과와 동결한 최종 자원 한도는
[`../docs/runtime-benchmark.md`](../docs/runtime-benchmark.md)에 있습니다.
측정과 한도 동결 절차는
[`../docs/APPLE_SILICON_MEASUREMENT.md`](../docs/APPLE_SILICON_MEASUREMENT.md)를
따릅니다.

참가자가 자신의 최종 이미지를 같은 공개 Train/Dev와 자원 제한으로 확인하는
명령은 [`../docs/RUNTIME.md`](../docs/RUNTIME.md#로컬-검증)에 안내합니다.
