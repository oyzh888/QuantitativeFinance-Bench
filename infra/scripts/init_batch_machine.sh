#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Per-Machine Init Script for Batch Harbor Runs
#
# This script:
# 1. Sets up the Harbor environment (pip, docker, harbor, venv)
# 2. Generates auth credentials
# 3. Runs batch_runner.sh to execute assigned tasks in parallel
#
# Environment (set by the per-experiment wrapper):
#   BATCH_TASKS     — space-separated task names
#   FB_MODEL        — model identifier
#   FB_AGENT        — agent type
#   FB_TRIAL_PREFIX — trial name prefix
#   MAX_PARALLEL    — concurrent tasks per machine
#   MACHINE_ID      — identifier for this machine (1, 2, 3...)
# ─────────────────────────────────────────────────────────────────────────────
set -e

SHARED_FS="/sensei-fs-3/users/zouyang/fb-harbor"
LOGDIR="$SHARED_FS/machine-logs/machine-${MACHINE_ID:-0}"
mkdir -p "$LOGDIR"
exec > >(tee "$LOGDIR/init.log") 2>&1

echo "=== Machine ${MACHINE_ID:-0} Init ==="
echo "Hostname: $(hostname)"
echo "Date: $(date -u)"
echo "Tasks: $BATCH_TASKS"
echo "Model: $FB_MODEL"

# ── Step 1: Bootstrap pip ──
echo ">>> Step 1: Bootstrap pip"
python3 -c "import urllib.request; urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py', '/tmp/get-pip.py')"
python3 /tmp/get-pip.py --quiet 2>&1 | tail -1
export PATH="$HOME/.local/bin:$PATH"

# ── Step 2: Docker + Compose ──
echo ">>> Step 2: Verify Docker"
sudo chmod 666 /var/run/docker.sock 2>/dev/null || true
docker --version || { echo "FATAL: Docker not available"; exit 1; }

if ! docker compose version &>/dev/null; then
    COMPOSE_SRC="$SHARED_FS/docker-compose-plugin"
    if [ -f "$COMPOSE_SRC" ]; then
        sudo mkdir -p /usr/libexec/docker/cli-plugins
        sudo cp "$COMPOSE_SRC" /usr/libexec/docker/cli-plugins/docker-compose
        sudo chmod +x /usr/libexec/docker/cli-plugins/docker-compose
    else
        COMPOSE_VERSION="v2.36.2"
        sudo mkdir -p /usr/libexec/docker/cli-plugins
        curl -fsSL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
            -o /usr/libexec/docker/cli-plugins/docker-compose --connect-timeout 30 --max-time 120
        sudo chmod +x /usr/libexec/docker/cli-plugins/docker-compose
    fi
fi
docker compose version

# ── Step 3: Install uv + Python 3.12 ──
echo ">>> Step 3: Install uv + Python 3.12"
pip3 install uv --quiet
uv python install 3.12 2>&1 | tail -3

# ── Step 4: Clone repo ──
echo ">>> Step 4: Clone repo"
WORKDIR="/tmp"
cd "$WORKDIR"
rm -rf finance-bench
git clone -b ke/eval_workflow https://github.com/beckybyte/QuantitativeFinance-Bench.git finance-bench 2>&1 | tail -3
cd finance-bench

# ── Step 5: Setup venv ──
echo ">>> Step 5: Setup venv + Harbor"
uv venv --python 3.12 --seed .venv
source .venv/bin/activate
uv pip install "harbor @ git+https://github.com/harbor-framework/harbor" litellm pytest 2>&1 | tail -10

# ── Step 6: Build sandbox + patch ──
echo ">>> Step 6: Build sandbox Docker image"
SANDBOX_TAR="$SHARED_FS/finance-bench-sandbox.tar"
if [ -f "$SANDBOX_TAR" ]; then
    echo "Loading sandbox image from cache: $SANDBOX_TAR"
    docker load < "$SANDBOX_TAR" 2>&1 | tail -3
else
    for attempt in 1 2 3; do
        if docker build -t finance-bench-sandbox:latest -f docker/sandbox.Dockerfile . 2>&1 | tail -10; then
            docker save finance-bench-sandbox:latest > "$SANDBOX_TAR" 2>/dev/null && echo "Saved image cache" || true
            break
        fi
        echo "Build attempt $attempt failed, retrying in 30s..."; sleep 30
    done
fi

COMPOSE_BASE=".venv/lib/python3.12/site-packages/harbor/environments/docker/docker-compose-base.yaml"
if [ -f "$COMPOSE_BASE" ] && ! grep -q "network_mode" "$COMPOSE_BASE"; then
    python3 -c "
f='$COMPOSE_BASE'
txt=open(f).read()
txt=txt.replace('services:\n  main:\n', 'services:\n  main:\n    network_mode: host\n')
open(f,'w').write(txt)
print('Patched compose: network_mode: host')
"
fi

# Patch docker.py cp timeouts
DOCKER_PY=".venv/lib/python3.12/site-packages/harbor/environments/docker/docker.py"
if [ -f "$DOCKER_PY" ] && ! grep -q "timeout_sec=300" "$DOCKER_PY"; then
    python3 << 'PYPATCH'
f = ".venv/lib/python3.12/site-packages/harbor/environments/docker/docker.py"
txt = open(f).read()
count = 0
for old, new in [
    ('''        await self._run_docker_compose_command(
            [
                "cp",
                str(source_path),
                f"main:{target_path}",
            ],
            check=True,
        )''',
     '''        await self._run_docker_compose_command(
            [
                "cp",
                str(source_path),
                f"main:{target_path}",
            ],
            check=True,
            timeout_sec=300,
        )'''),
    ('''        await self._run_docker_compose_command(
            [
                "cp",
                f"{source_dir}/.",
                f"main:{target_dir}",
            ],
            check=True,
        )''',
     '''        await self._run_docker_compose_command(
            [
                "cp",
                f"{source_dir}/.",
                f"main:{target_dir}",
            ],
            check=True,
            timeout_sec=300,
        )'''),
    ('''        await self._run_docker_compose_command(
            [
                "cp",
                f"main:{source_path}",
                str(target_path),
            ],
            check=True,
        )''',
     '''        await self._run_docker_compose_command(
            [
                "cp",
                f"main:{source_path}",
                str(target_path),
            ],
            check=True,
            timeout_sec=300,
        )'''),
    ('''        await self._run_docker_compose_command(
            [
                "cp",
                f"main:{source_dir}/.",
                str(target_dir),
            ],
            check=True,
        )''',
     '''        await self._run_docker_compose_command(
            [
                "cp",
                f"main:{source_dir}/.",
                str(target_dir),
            ],
            check=True,
            timeout_sec=300,
        )'''),
]:
    if old in txt:
        txt = txt.replace(old, new)
        count += 1
if count > 0:
    open(f, 'w').write(txt)
    print(f"Patched docker.py: added timeout_sec=300 to {count} cp commands")
PYPATCH
fi

# ── Step 7: Generate credentials ──
echo ">>> Step 7: Generate credentials"
pip3 install foundry-aws-gateway --quiet 2>/dev/null || true

case "$FB_MODEL" in
    openai/google/gemini-*)
        eval "$(python3 $SHARED_FS/scripts/foundry_auth.py gemini 2>/dev/null)" || true
        if [ -z "$GEMINI_VERTEX_TOKEN" ]; then
            echo "FATAL: Cannot get Gemini token"; exit 1
        fi
        export OPENAI_API_KEY="$GEMINI_VERTEX_TOKEN"
        export OPENAI_API_BASE="$GEMINI_VERTEX_BASE_URL"
        echo "Gemini OK (token len: ${#GEMINI_VERTEX_TOKEN})"
        ;;
    azure/gpt-*)
        eval "$(python3 $SHARED_FS/scripts/foundry_auth.py azure 2>/dev/null)" || true
        if [ -z "$AZURE_API_KEY" ]; then
            echo "FATAL: Cannot get Azure token"; exit 1
        fi
        export OPENAI_API_KEY="$AZURE_API_KEY"
        export OPENAI_API_BASE="${AZURE_API_BASE}/openai"
        echo "Azure OK (endpoint: $AZURE_API_BASE)"
        ;;
    bedrock/*|us.anthropic.*)
        # Bedrock token from Pluto env
        if [ -f "$SHARED_FS/.bedrock_env" ]; then
            source "$SHARED_FS/.bedrock_env"
        fi
        export CLAUDE_CODE_USE_BEDROCK=1
        export AWS_REGION=us-west-2
        export CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING=1
        echo "Bedrock OK (token len: ${#AWS_BEARER_TOKEN_BEDROCK})"
        ;;
esac

# ── Step 8: Run batch ──
echo ">>> Step 8: Run batch tasks"
export SHARED_FS WORKDIR="/tmp/finance-bench"
export FB_MODEL FB_AGENT FB_TRIAL_PREFIX MAX_PARALLEL BATCH_TASKS

bash "$SHARED_FS/scripts/batch_runner.sh"

echo "=== Machine ${MACHINE_ID:-0} complete at $(date -u) ==="
