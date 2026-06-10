#!/bin/sh
set -e
CANON="/home/node/.openclaw/workspace/projects/hl_miko"
GIT_CRED_SRC="/home/node/.openclaw-secrets/github_hl_miko_credentials"
GIT_CRED_USE="/home/node/.openclaw/.git-credentials-hl_miko"

mkdir -p /home/node/workspace /home/node/repos
if [ -d "/home/node/workspace/hl_miko" ] && [ ! -L "/home/node/workspace/hl_miko" ]; then
  rm -rf /home/node/workspace/hl_miko
fi
ln -sfn "$CANON" /home/node/workspace/hl_miko
ln -sfn "$CANON" /home/node/repos/hl_miko

if [ -f "$GIT_CRED_SRC" ] && [ -d "$CANON/.git" ]; then
  cp "$GIT_CRED_SRC" "$GIT_CRED_USE"
  chmod 600 "$GIT_CRED_USE"
  git -C "$CANON" config --local credential.helper "store --file=$GIT_CRED_USE"
  git -C "$CANON" config --local user.name "OpenClaw Mauro"
  git -C "$CANON" config --local user.email "me@maurocastro.cl"
fi

. /opt/openclaw-scripts/ensure-bun.sh

exec tini -s -- "$@"
