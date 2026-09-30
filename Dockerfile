# A small evalkit image: the wheel installed on Alpine Python, run as a non-root user.
#
#   docker run --rm ghcr.io/superintelligenceco/evalkit run evals.yaml
#   docker run --rm -v "$PWD:/work" -u "$(id -u):$(id -g)" ghcr.io/superintelligenceco/evalkit run evals.yaml
#
# /work holds the starter suite from `evalkit init`, so the first command runs offline. Mount your
# own directory on /work to run your suites.

FROM python:3.12-alpine@sha256:4c47124a8391cb7a9f571164147d154777cf012a4ece5f86097130d7a4478111 AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels .

FROM python:3.12-alpine@sha256:4c47124a8391cb7a9f571164147d154777cf012a4ece5f86097130d7a4478111
LABEL org.opencontainers.image.title="evalkit" \
      org.opencontainers.image.description="Evals as code for LLM apps and agents" \
      org.opencontainers.image.source="https://github.com/superintelligenceco/evalkit" \
      org.opencontainers.image.licenses="Apache-2.0"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN --mount=type=bind,from=build,source=/wheels,target=/wheels \
    pip install --no-cache-dir /wheels/*.whl \
    && adduser -D -u 10001 evalkit \
    && mkdir /work \
    && cd /work \
    && evalkit init \
    && chown -R evalkit:evalkit /work
USER 10001
WORKDIR /work
ENTRYPOINT ["evalkit"]
CMD ["--help"]
