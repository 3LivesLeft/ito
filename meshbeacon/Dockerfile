# syntax=docker/dockerfile:1.28.0@sha256:bb22d9815c728170f72750f4e5b0d672e06176142e1d602c7e66c050100b7e5b
# MeshBeacon app image. Base image pinned by multi-arch digest (Python 3.13, Alpine 3.24).
FROM ghcr.io/home-assistant/base-python:3.13-alpine3.24@sha256:c7d34ae22a87275d46deb65bcb0511b389d7bc6eb8dccb28d44dd7cb8616e603

ARG BUILD_VERSION=0.2.0
ARG BUILD_ARCH

ENV \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_EXTRA_INDEX_URL="" \
    PIP_NO_CACHE_DIR=1 \
    MESHBEACON_DATA=/data

# Security updates for base-image packages that the pinned HA base image predates, with explicit
# minimum versions so the build fails rather than silently shipping a vulnerable version. Found by
# the CI image scan (18 Nov 2026): zlib CVE-2026-4738 (critical), krb5-libs and libexpat (high).
# Drop these lines once the HA base image includes the fixes; then refresh the base digest.
# apk's log records install times; nothing reads it, and it would make builds differ, so it goes.
RUN apk add --no-cache --upgrade \
        "zlib>=1.4-r0" \
        "krb5-libs>=1.22.3-r0" \
        "libexpat>=2.10.0-r0" \
    && rm -f /var/log/apk.log

# Reproducible builds (docs/releasing.md): when the release build sets SOURCE_DATE_EPOCH, Python
# (pip's bytecode step and compileall below) writes hash-checked .pyc files with no timestamps.
ARG SOURCE_DATE_EPOCH

# Hash-pinned, binary-only install of the unmodified Reticulum reference implementation and its
# dependencies, from PyPI only.
# An optional build secret `build_ca` lets builds run behind a TLS-intercepting proxy; it is never
# stored in the image, and the hash pins protect package integrity either way.
COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=secret,id=build_ca,required=false \
    if [ -s /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    pip install \
        --index-url https://pypi.org/simple \
        --require-hashes --no-deps --only-binary=:all: \
        -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

# MeshBeacon core, installed into site-packages so that it runs under `python3 -I`.
COPY core/meshbeacon /tmp/meshbeacon
RUN set -eu; \
    site="$(python3 -I -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"; \
    mv /tmp/meshbeacon "${site}/meshbeacon"; \
    python3 -I -m compileall -q "${site}/meshbeacon" "${site}/RNS"; \
    addgroup -S -g 9100 meshbeacon; \
    adduser -S -D -H -h /nonexistent -s /sbin/nologin -u 9100 -G meshbeacon meshbeacon

COPY LICENSE NOTICE THIRD_PARTY_NOTICES /usr/share/doc/meshbeacon/
COPY rootfs /
RUN chmod 0755 /etc/cont-init.d/10-meshbeacon /etc/services.d/meshbeacon/run /etc/services.d/meshbeacon/finish \
    /etc/services.d/discovery-relay/run /etc/services.d/discovery-relay/finish

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app" \
    io.hass.arch="aarch64|amd64" \
    org.opencontainers.image.title="MeshBeacon" \
    org.opencontainers.image.description="Decentralised connectivity for your home" \
    org.opencontainers.image.source="https://github.com/3LivesLeft/meshbeacon" \
    org.opencontainers.image.licenses="Apache-2.0 AND LicenseRef-Reticulum"
