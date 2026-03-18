# Package path for this plugin module relative to the repo root
ARG package=arcaflow_plugin_rusty_comms

# ---------------------------------------------------------------------------
# STAGE 0 -- Build rusty-comms from source
# ---------------------------------------------------------------------------
FROM docker.io/library/rust:1.82-slim-bookworm AS rust-builder

RUN apt-get update \
 && apt-get install -y --no-install-recommends git pkg-config \
 && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch main \
        https://github.com/redhat-performance/rusty-comms.git \
        /build/rusty-comms

WORKDIR /build/rusty-comms
RUN cargo build --release

# ---------------------------------------------------------------------------
# STAGE 1 -- Build Python module dependencies and run tests
# ---------------------------------------------------------------------------
FROM quay.io/arcalot/arcaflow-plugin-baseimage-python-buildbase:0.4.0 AS build
ARG package

COPY poetry.lock /app/
COPY pyproject.toml /app/

RUN python -m poetry install --without dev --no-root \
 && python -m poetry export -f requirements.txt --output requirements.txt --without-hashes

COPY ${package}/ /app/${package}
COPY tests /app/${package}/tests

ENV PYTHONPATH /app/${package}
WORKDIR /app/${package}

RUN python -m coverage run tests/test_${package}.py \
 && python -m coverage html -d /htmlcov --omit=/usr/local/*

# ---------------------------------------------------------------------------
# STAGE 2 -- Build final plugin image
# ---------------------------------------------------------------------------
FROM quay.io/arcalot/arcaflow-plugin-baseimage-python-osbase:0.4.0
ARG package

COPY --from=rust-builder /build/rusty-comms/target/release/ipc-benchmark \
     /usr/local/bin/ipc-benchmark

COPY --from=build /app/requirements.txt /app/
COPY --from=build /htmlcov /htmlcov/
COPY LICENSE /app/
COPY README.md /app/
COPY ${package}/ /app/${package}

RUN python -m pip install -r requirements.txt

WORKDIR /app/${package}

ENTRYPOINT ["python", "rusty_comms_plugin.py"]
CMD []

LABEL org.opencontainers.image.source="https://github.com/arcalot/arcaflow-plugin-rusty-comms"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.vendor="Arcalot project"
LABEL org.opencontainers.image.authors="Arcalot contributors"
LABEL org.opencontainers.image.title="Arcaflow rusty-comms IPC Benchmark Plugin"
LABEL io.github.arcalot.arcaflow.plugin.version="1"
