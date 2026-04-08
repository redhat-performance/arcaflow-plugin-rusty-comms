# Package path for this plugin module relative to the repo root
ARG package=arcaflow_plugin_rusty_comms

# ---------------------------------------------------------------------------
# STAGE 0 -- Build rusty-comms from source
#
# Uses CentOS Stream 9 to match the arcalot runtime base image, ensuring
# the compiled binary links against the same glibc version (2.34) that
# will be available at runtime.
# ---------------------------------------------------------------------------
FROM quay.io/centos/centos:stream9 AS rust-builder

RUN dnf install -y --setopt=install_weak_deps=False \
        gcc git make pkgconf-pkg-config \
 && dnf clean all

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain 1.82.0
ENV PATH="/root/.cargo/bin:${PATH}"

# Fetch the latest commit ref for main; ADD always checks the URL
# at build time and invalidates the layer cache when it changes.
ADD https://api.github.com/repos/redhat-performance/rusty-comms/git/refs/heads/main \
    /tmp/rusty-comms-ref.json
RUN git clone --depth 1 --branch main \
        https://github.com/redhat-performance/rusty-comms.git \
        /build/rusty-comms

WORKDIR /build/rusty-comms
RUN cargo build --release

# ---------------------------------------------------------------------------
# STAGE 1 -- Build Python module dependencies and run tests
# ---------------------------------------------------------------------------
FROM quay.io/arcalot/arcaflow-plugin-baseimage-python-buildbase:0.5.0 AS build
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
FROM quay.io/arcalot/arcaflow-plugin-baseimage-python-osbase:0.5.0
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
