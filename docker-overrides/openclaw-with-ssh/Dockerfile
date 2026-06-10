FROM ghcr.io/openclaw/openclaw:2026.6.5
USER root
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends openssh-client git jq ripgrep ca-certificates unzip curl \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL https://github.com/cli/cli/releases/download/v2.23.0/gh_2.23.0_linux_amd64.tar.gz \
    | tar xz -C /tmp \
 && mv /tmp/gh_2.23.0_linux_amd64/bin/gh /usr/local/bin/gh \
 && rm -rf /tmp/gh_2.23.0_linux_amd64 \
 && ln -sfn /home/node/.openclaw/ssh /home/node/.ssh \
 && printf '%s\n' '#!/bin/sh' 'exec ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new mauro@host.docker.internal "$@"' > /usr/local/bin/host-sh \
 && chmod 0755 /usr/local/bin/host-sh
COPY host-wrap /usr/local/bin/host-wrap
COPY repo-gitlog /usr/local/bin/repo-gitlog
RUN chmod 0755 /usr/local/bin/host-wrap /usr/local/bin/repo-gitlog \
 && printf '%s\n' '#!/bin/sh' 'exec host-wrap docker "$@"' > /usr/local/bin/docker \
 && printf '%s\n' '#!/bin/sh' 'exec host-wrap systemctl "$@"' > /usr/local/bin/systemctl \
 && printf '%s\n' '#!/bin/sh' 'exec host-wrap journalctl "$@"' > /usr/local/bin/journalctl \
 && printf '%s\n' '#!/bin/sh' 'exec host-wrap ss "$@"' > /usr/local/bin/ss \
 && printf '%s\n' '#!/bin/sh' 'exec host-wrap hostname "$@"' > /usr/local/bin/hostname \
 && printf '%s\n' '#!/bin/sh' 'exec host-wrap uptime "$@"' > /usr/local/bin/uptime \
 && printf '%s\n' '#!/bin/sh' 'exec host-wrap df "$@"' > /usr/local/bin/df \
 && printf '%s\n' '#!/bin/sh' 'exec host-wrap free "$@"' > /usr/local/bin/free \
 && printf '%s\n' '#!/bin/sh' 'exec host-sh "hostname; uptime; df -h /; free -h; docker ps -a --format '\''table {{.ID}}\t{{.Image}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}'\''"' > /usr/local/bin/host-status \
 && chmod 0755 /usr/local/bin/docker /usr/local/bin/systemctl /usr/local/bin/journalctl /usr/local/bin/ss /usr/local/bin/hostname /usr/local/bin/uptime /usr/local/bin/df /usr/local/bin/free /usr/local/bin/host-status
RUN git config --system user.name "OpenClaw Mauro" \
 && git config --system user.email "me@maurocastro.cl"
USER node
ENV PATH="/home/node/.bun/bin:${PATH}"
