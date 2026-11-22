# syntax=docker/dockerfile:1.28.0@sha256:bb22d9815c728170f72750f4e5b0d672e06176142e1d602c7e66c050100b7e5b
# MeshBeacon app image. Base image pinned by multi-arch digest (Python 3.13, Alpine 3.24).
FROM ghcr.io/home-assistant/base-python:3.13-alpine3.24@sha256:c7d34ae22a87275d46deb65bcb0511b389d7bc6eb8dccb28d44dd7cb8616e603
# One image for everyone (M4, D-M4-8): the Reticulum gateway and the optional LXMF messaging engine,
# which runs, as its own user and s6 service, only when the user switches messaging on (off by
# default). Nothing of it runs, and no messaging data is created, while it is off.
# v0.6 (ADR 0027): Nomad Network pages the same way: the unmodified Nomad Network daemon and ito's
# pages service, as their own user and s6 service, only when the user switches pages on.

ARG BUILD_VERSION=0.6.1
ARG BUILD_ARCH

ENV \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_EXTRA_INDEX_URL="" \
    PIP_NO_CACHE_DIR=1 \
    MESHBEACON_DATA=/data \
    S6_CMD_WAIT_FOR_SERVICES=0
# S6_CMD_WAIT_FOR_SERVICES=0 (ADR 0018): Reticulum and its prepare step are services that stay down
# until the core starts them, so s6-overlay must not wait for every service to be up (it would
# wait for ever: the base image sets no time limit). It only gates a container CMD; there is none.

# Security updates for base-image packages that the pinned HA base image predates, with explicit
# minimum versions so the build fails rather than silently shipping a vulnerable version. Found by
# the CI image scan (18 Nov 2026): zlib CVE-2026-4738 (critical), krb5-libs and libexpat (high);
# 21 Nov 2026: libxml2 CVE-2026-86144 (high, fixed in 2.13.9-r3; part of the base image).
# Drop these lines once the HA base image includes the fixes; then refresh the base digest.
# apk's log records install times; nothing reads it, and it would make builds differ, so it goes.
# The base image's tempio (a Go template tool for app scripts) is removed: MeshBeacon never uses it,
# and its Go runtime carried a high-severity finding with a fix (GO-2026-5972, release scan, M1.2).
RUN apk add --no-cache --upgrade \
        "zlib>=1.4-r0" \
        "krb5-libs>=1.22.3-r0" \
        "libexpat>=2.10.0-r0" \
        "libxml2>=2.13.9-r3" \
    && rm -f /var/log/apk.log /usr/bin/tempio \
    && ! command -v tempio

# Reproducible builds (docs/releasing.md): when the release build sets SOURCE_DATE_EPOCH, Python
# (pip's bytecode step and compileall below) writes hash-checked .pyc files with no timestamps.
ARG SOURCE_DATE_EPOCH

# Hash-pinned, binary-only install of the unmodified Reticulum and LXMF reference implementations
# and their dependencies, from PyPI only.
# An optional build secret `build_ca` lets builds run behind a TLS-intercepting proxy; it is never
# stored in the image, and the hash pins protect package integrity either way.
COPY requirements.txt requirements-messaging.txt requirements-pages.txt /tmp/
RUN --mount=type=secret,id=build_ca,required=false \
    if [ -s /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    pip install \
        --index-url https://pypi.org/simple \
        --require-hashes --no-deps --only-binary=:all: \
        -r /tmp/requirements.txt -r /tmp/requirements-messaging.txt -r /tmp/requirements-pages.txt \
    && rm -f /tmp/requirements.txt /tmp/requirements-messaging.txt /tmp/requirements-pages.txt

# MeshBeacon core and its messaging engine, installed into site-packages so that they run under
# `python3 -I`. Users (ADR 0018): the core 9100, Reticulum 9101, the messaging engine 9102; the
# group mb-msg (9111) holds only the core and the engine (its socket and settings folder); the
# group mb-rpc (9112) only Reticulum and the engine (the shared instance's RPC key, ADR 0023).
# v0.6 (ADR 0027): the pages service and its Nomad Network daemon 9103 (mb-nomad, also in mb-rpc);
# the group mb-page (9113) holds only the core and mb-nomad (published pages, the service's socket).
COPY --exclude=**/__pycache__ core/meshbeacon /tmp/meshbeacon
RUN set -eu; \
    site="$(python3 -I -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"; \
    mv /tmp/meshbeacon "${site}/meshbeacon"; \
    python3 -I -m compileall -q "${site}/meshbeacon" "${site}/RNS" "${site}/LXMF" "${site}/nomadnet"; \
    addgroup -S -g 9100 meshbeacon; \
    adduser -S -D -H -h /nonexistent -s /sbin/nologin -u 9100 -G meshbeacon meshbeacon; \
    addgroup -S -g 9101 mb-rns; \
    adduser -S -D -H -h /nonexistent -s /sbin/nologin -u 9101 -G mb-rns mb-rns; \
    addgroup -S -g 9110 mb-options; \
    addgroup meshbeacon mb-options; \
    addgroup mb-rns mb-options; \
    addgroup -S -g 9102 mb-lxmf; \
    adduser -S -D -H -h /nonexistent -s /sbin/nologin -u 9102 -G mb-lxmf mb-lxmf; \
    addgroup -S -g 9111 mb-msg; \
    addgroup meshbeacon mb-msg; \
    addgroup mb-lxmf mb-msg; \
    addgroup -S -g 9112 mb-rpc; \
    addgroup mb-rns mb-rpc; \
    addgroup mb-lxmf mb-rpc; \
    addgroup -S -g 9103 mb-nomad; \
    adduser -S -D -H -h /nonexistent -s /sbin/nologin -u 9103 -G mb-nomad mb-nomad; \
    addgroup -S -g 9113 mb-page; \
    addgroup meshbeacon mb-page; \
    addgroup mb-nomad mb-page; \
    addgroup mb-nomad mb-rpc

COPY frontend /usr/share/meshbeacon/frontend
COPY LICENSE NOTICE THIRD_PARTY_NOTICES /usr/share/doc/meshbeacon/
COPY rootfs /
RUN chmod 0755 /etc/cont-init.d/10-meshbeacon /etc/services.d/meshbeacon/run /etc/services.d/meshbeacon/finish \
    /etc/services.d/discovery-relay/run /etc/services.d/discovery-relay/finish \
    /etc/services.d/reticulum/run /etc/services.d/reticulum/finish \
    /etc/services.d/rns-prepare/run /etc/services.d/rns-prepare/finish \
    /etc/cont-init.d/20-messaging /etc/services.d/messaging/run /etc/services.d/messaging/finish \
    /etc/cont-init.d/30-pages /etc/services.d/pages/run /etc/services.d/pages/finish

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app" \
    io.hass.arch="aarch64|amd64" \
    org.opencontainers.image.title="ito" \
    org.opencontainers.image.description="Private, decentralised connectivity for your home, powered by Reticulum" \
    org.opencontainers.image.source="https://github.com/3LivesLeft/ito" \
    org.opencontainers.image.licenses="Apache-2.0 AND LicenseRef-Reticulum AND GPL-3.0-only"
