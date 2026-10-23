# uv comes in as a stage because Dependabot only updates FROM lines, not
# COPY --from=<image>.
FROM ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 AS uv

FROM python:3.14.8-slim-trixie@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170

ARG SOURCE_REVISION=""

LABEL org.opencontainers.image.source="https://github.com/cmiic/media-screener-api" \
    org.opencontainers.image.licenses="AGPL-3.0-or-later" \
    org.opencontainers.image.revision="$SOURCE_REVISION"

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
ENV PATH="/app/.venv/bin:$PATH" \
    MODEL_PATH="/models/640m.onnx" \
    SOURCE_REVISION="$SOURCE_REVISION" \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install dependencies for opencv and curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-build --no-dev \
    && find /app/.venv -type f -name '*.onnx' -delete \
    && rm -rf /root/.cache/uv

COPY LICENSES /app/LICENSES
COPY scripts/collect_python_licenses.py /app/scripts/collect_python_licenses.py
RUN /app/.venv/bin/python /app/scripts/collect_python_licenses.py

COPY app.py .
COPY LICENSE /app/LICENSE
COPY model.env /app/model.env
COPY --chmod=755 scripts/container-entrypoint.sh /app/scripts/container-entrypoint.sh

# Set by the release workflow from the git tag (without its leading "v"); local
# and CI builds keep "dev". Declared after the dependency and license layers so
# a new version does not invalidate their cache.
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
LABEL org.opencontainers.image.version="${APP_VERSION}"

EXPOSE 8080

HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=12 \
    CMD curl -fsS http://localhost:8080/health || exit 1

ENTRYPOINT ["/app/scripts/container-entrypoint.sh"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
