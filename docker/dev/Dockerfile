# Dev container for `splk loop`: everything the roadmap loop needs to build,
# vet, deploy and test the apps against the Splunk container in
# docker/compose.yaml. Build from the repo root:
#
#   docker build -f docker/dev/Dockerfile -t splunk-apps-dev .
#
# The repository itself is not baked in: the entrypoint clones it into the
# /work volume on first start, so the loop's commits and branches survive
# image rebuilds.

FROM python:3.13-slim-bookworm

# Exact Claude Code version, so a rebuild never changes the loop's behaviour
# silently. Bump deliberately (the same version as the desktop install).
ARG CLAUDE_CODE_VERSION=2.1.325
ARG LOOP_UID=1000

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

# git and gh for the supervisor; libmagic for AppInspect; tini so signals
# (docker stop) reach the loop and it saves its state.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl git gnupg less libmagic1 procps tini \
 && install -d -m 0755 /etc/apt/keyrings \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
 && chmod 0644 /etc/apt/keyrings/githubcli-archive-keyring.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends gh \
 && rm -rf /var/lib/apt/lists/*

# splk's dependencies, from pyproject.toml's [dev] extra. splk itself is
# installed editable from the cloned repo at start-up, so tool changes merged
# to main apply without a rebuild.
COPY pyproject.toml /tmp/pyproject.toml
RUN python - <<'EOF' > /tmp/requirements.txt
import tomllib
project = tomllib.load(open("/tmp/pyproject.toml", "rb"))["project"]
print("\n".join(project["dependencies"] + project["optional-dependencies"]["dev"]))
EOF
RUN pip install -r /tmp/requirements.txt \
 && python -m playwright install --with-deps chromium \
 && rm /tmp/requirements.txt /tmp/pyproject.toml

# The loop runs as an unprivileged user, never root. /stage is shared with
# the Splunk container (splunkd installs packages from it); a named volume
# copies this directory's owner on first use, so the loop user can write it.
RUN useradd --create-home --uid "${LOOP_UID}" --shell /bin/bash loop \
 && install -d -o loop -g loop /work /stage

USER loop
ENV PATH=/home/loop/.local/bin:${PATH}

# Native installer, pinned to the version above.
RUN curl -fsSL https://claude.ai/install.sh | bash -s "${CLAUDE_CODE_VERSION}" \
 && claude --version

# Root-owned: it runs as root at every start, so the loop user must not be
# able to change it. It drops to `loop` itself (see the script).
USER root
COPY --chmod=0755 docker/dev/entrypoint.sh /usr/local/bin/loop-entrypoint
WORKDIR /work

# -g: signal the whole process group, so `docker stop` reaches the running
# `splk loop` and its step, not only the entrypoint shell.
ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/usr/local/bin/loop-entrypoint"]
CMD ["loop"]
