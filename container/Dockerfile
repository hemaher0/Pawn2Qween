# SPDX-FileCopyrightText: Copyright 2026 SK TELECOM CO., LTD.
# SPDX-License-Identifier: Apache-2.0

FROM python:3.11.15-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3 AS dependencies

ENV UV_PROJECT_ENVIRONMENT=/opt/e5-runtime

WORKDIR /build

RUN python3 -m pip install --no-cache-dir uv==0.12.3

COPY pyproject.toml uv.lock /build/

RUN uv sync \
    --locked \
    --no-dev \
    --group e5-runtime \
    --no-install-project \
    --compile-bytecode

COPY configs/e5-model.v1.json /build/configs/e5-model.v1.json
COPY tools/fetch_e5_model.py /build/tools/fetch_e5_model.py
COPY build/e5-model /build/e5-model

RUN python3 /build/tools/fetch_e5_model.py \
    --spec /build/configs/e5-model.v1.json \
    --output /build/e5-model \
    --check

FROM python:3.11.15-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3

# Remove package-management tools that are not needed during inference.
RUN python3 -m pip uninstall --yes pip setuptools wheel

ARG SOURCE_MANIFEST_SHA256=unbound
ARG SOURCE_COMMIT_SHA=unbound
ARG SOURCE_REPOSITORY_URL=unbound

LABEL io.sktelecom.ossp.source-manifest-sha256="${SOURCE_MANIFEST_SHA256}" \
    org.opencontainers.image.revision="${SOURCE_COMMIT_SHA}" \
    org.opencontainers.image.source="${SOURCE_REPOSITORY_URL}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    OPENBLAS_NUM_THREADS=2 \
    OMP_NUM_THREADS=2 \
    PATH=/opt/e5-runtime/bin:$PATH \
    PYTHONPATH=/opt/router \
    PYTHONUNBUFFERED=1 \
    TMPDIR=/tmp

COPY --from=dependencies --chown=65532:65532 /opt/e5-runtime /opt/e5-runtime
COPY --from=dependencies --chown=65532:65532 /build/e5-model /opt/router/build/e5-model
COPY --chown=65532:65532 src/ossp_router /opt/router/ossp_router
COPY --chown=65532:65532 container/entrypoint.py /opt/router/entrypoint.py
COPY LICENSE NOTICE THIRD_PARTY_NOTICES.md /usr/share/licenses/pawn2qween/
COPY LICENSES /usr/share/licenses/pawn2qween/LICENSES/
COPY configs/e5-model.v1.json /usr/share/licenses/pawn2qween/configs/e5-model.v1.json

WORKDIR /opt/router

USER 65532:65532

ENTRYPOINT ["/opt/e5-runtime/bin/python", "/opt/router/entrypoint.py"]
