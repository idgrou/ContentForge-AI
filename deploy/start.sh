#!/bin/sh
# Container entrypoint for servers whose Docker manager cannot build images (e.g. Hostinger VPS).
# Runs on a stock python image: installs system packages once per container, then installs or
# updates ContentForge from GitHub on every start (restart the project to update).
set -e
REPO="${CONTENTFORGE_REPO:-https://github.com/idgrou/ContentForge-AI.git}"
REF="${CONTENTFORGE_REF:-claude/great-brown-ftpn5m}"
DENO_VERSION="${DENO_VERSION:-2.9.6}"

if [ ! -f /opt/.system-ready ]; then
  echo "[start] installing system packages"
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends ffmpeg fonts-dejavu-core libglib2.0-0 git curl unzip ca-certificates >/dev/null
  curl -fsSL "https://dl.deno.land/release/v${DENO_VERSION}/deno-x86_64-unknown-linux-gnu.zip" -o /tmp/deno.zip
  unzip -oq /tmp/deno.zip -d /usr/local/bin && rm /tmp/deno.zip
  rm -rf /var/lib/apt/lists/*
  echo "[start] installing Python dependencies"
  pip install -q --no-cache-dir "contentforge-ai[web,transcribe,facetrack,youtube] @ git+${REPO}@${REF}"
  touch /opt/.system-ready
else
  echo "[start] updating ContentForge from ${REF}"
  pip install -q --no-cache-dir --no-deps --force-reinstall "contentforge-ai @ git+${REPO}@${REF}"
fi

mkdir -p /data && cd /data
exec uvicorn contentforge.web:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 75
