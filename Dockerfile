# Single source of truth for system dependencies; used by docker compose and .devcontainer.
# LibreDWG (dwg2dxf) is not packaged in Debian, so it is built from source.
FROM python:3.12-slim AS libredwg
ARG LIBREDWG_VERSION=0.13.3
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl xz-utils ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL "https://github.com/LibreDWG/libredwg/releases/download/${LIBREDWG_VERSION}/libredwg-${LIBREDWG_VERSION}.tar.xz" \
    | tar -xJ -C /tmp \
    && cd "/tmp/libredwg-${LIBREDWG_VERSION}" \
    && ./configure --disable-shared --enable-static --disable-bindings --disable-docs --disable-werror --prefix=/opt/libredwg \
    && make -j"$(nproc)" \
    && make install

FROM python:3.12-slim AS base
COPY --from=libredwg /opt/libredwg/bin/dwg2dxf /usr/local/bin/dwg2dxf
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

FROM base AS runtime
COPY pyproject.toml ./
COPY digital_workshop ./digital_workshop
RUN pip install --no-cache-dir .
EXPOSE 8080
CMD ["python", "-m", "digital_workshop"]
