#!/bin/sh
# Build the TEST-ONLY stand-in base image (see Dockerfile.localbase). Usage:
#   tests/container/build_localbase.sh <workdir> <platform: linux/amd64|linux/arm64>
set -eu
work="$1"; platform="${2:-linux/amd64}"
v=3.2.3.2
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$work"
cd "$work"
for f in noarch x86_64 aarch64; do
    [ -f "s6-overlay-$f.tar.xz" ] || curl -fsSL -o "s6-overlay-$f.tar.xz" \
        "https://github.com/just-containers/s6-overlay/releases/download/v$v/s6-overlay-$f.tar.xz"
    curl -fsSL -o "s6-overlay-$f.tar.xz.sha256" \
        "https://github.com/just-containers/s6-overlay/releases/download/v$v/s6-overlay-$f.tar.xz.sha256"
    sha256sum -c "s6-overlay-$f.tar.xz.sha256"
done
for pair in amd64:x86_64 arm64:aarch64; do
    d="rootfs-${pair%%:*}"; rm -rf "$d"; mkdir -p "$d"
    tar -C "$d" -Jxpf s6-overlay-noarch.tar.xz
    tar -C "$d" -Jxpf "s6-overlay-${pair##*:}.tar.xz"
done
cp "$here/Dockerfile.localbase" .
docker buildx build --load --platform "$platform" -t meshbeacon-localbase:test -f Dockerfile.localbase .
