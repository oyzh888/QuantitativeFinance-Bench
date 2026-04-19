#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Harbor DinD Init Script
#
# Bootstraps a complete Harbor benchmark environment on a Docker-in-Docker
# cloud instance. Designed for CPU-only or GPU nodes.
#
# Prerequisites:
#   - Docker available (Docker-in-Docker mode enabled)
#   - Provider credentials (auto-detected from FB_MODEL):
#     Bedrock:  AWS_BEARER_TOKEN_BEDROCK or $SHARED_FS/.bedrock_env
#     Gemini:   GEMINI_VERTEX_TOKEN + GEMINI_VERTEX_BASE_URL (or auto via foundry_aws_gateway)
#     Azure:    AZURE_API_KEY + AZURE_API_BASE (or auto via foundry_aws_gateway)
#     Other:    OPENAI_API_KEY + OPENAI_API_BASE
#
# Environment variables:
#   FB_TASK        — task path, e.g. "tasks/american-option-fd-new" (default: all)
#   FB_TRIAL_NAME  — trial name prefix (default: fb-run)
#   FB_MODEL       — model identifier (default: bedrock sonnet 4)
#                    Examples:
#                      bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0
#                      openai/google/gemini-2.5-flash
#                      openai/google/gemini-2.5-pro
#                      azure/gpt-5
#   FB_AGENT       — agent type (default: claude-code)
#   FB_REPO_BRANCH — git branch to clone (default: ke/eval_workflow)
#   FB_REPO_URL    — repo URL (default: QuantitativeFinance-Bench)
#   SHARED_FS      — shared filesystem path for logs/credentials (default: /tmp/fb-harbor)
# ─────────────────────────────────────────────────────────────────────────────
set -e

SHARED_FS="${SHARED_FS:-/tmp/fb-harbor}"
LOGDIR="$SHARED_FS"
mkdir -p "$LOGDIR"
exec > >(tee "$LOGDIR/init-log.txt") 2>&1

echo "=== Harbor DinD Setup ==="
echo "Hostname: $(hostname)"
echo "Date: $(date -u)"
echo "CPU cores: $(nproc)"
echo "Memory: $(free -h | awk '/Mem:/{print $2}')"

# Configurable defaults (override via env vars)
FB_TASK="${FB_TASK:-}"
FB_TRIAL_NAME="${FB_TRIAL_NAME:-fb-run}"
FB_MODEL="${FB_MODEL:-bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0}"
FB_AGENT="${FB_AGENT:-claude-code}"
FB_REPO_BRANCH="${FB_REPO_BRANCH:-ke/eval_workflow}"
FB_REPO_URL="${FB_REPO_URL:-https://github.com/beckybyte/QuantitativeFinance-Bench.git}"

# ── Step 1: Bootstrap pip ──────────────────────────────────────────────────
echo ">>> Step 1: Bootstrap pip"
python3 -c "import urllib.request; urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py', '/tmp/get-pip.py')"
python3 /tmp/get-pip.py --quiet 2>&1 | tail -1
export PATH="$HOME/.local/bin:$PATH"

# ── Step 2: Docker + Compose ──────────────────────────────────────────────
echo ">>> Step 2: Verify Docker + install Compose V2 plugin"
sudo chmod 666 /var/run/docker.sock 2>/dev/null || true
docker --version || { echo "FATAL: Docker not available"; exit 1; }

# Install docker compose v2 plugin if not present
if ! docker compose version &>/dev/null; then
    COMPOSE_SRC="$SHARED_FS/docker-compose-plugin"
    if [ -f "$COMPOSE_SRC" ]; then
        sudo mkdir -p /usr/libexec/docker/cli-plugins
        sudo cp "$COMPOSE_SRC" /usr/libexec/docker/cli-plugins/docker-compose
        sudo chmod +x /usr/libexec/docker/cli-plugins/docker-compose
    else
        echo "Downloading Docker Compose V2 plugin..."
        COMPOSE_VERSION="v2.36.2"
        sudo mkdir -p /usr/libexec/docker/cli-plugins
        curl -fsSL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
            -o /usr/libexec/docker/cli-plugins/docker-compose --connect-timeout 30 --max-time 120 || {
            echo "FATAL: Cannot install Docker Compose plugin"; exit 1;
        }
        sudo chmod +x /usr/libexec/docker/cli-plugins/docker-compose
    fi
fi
docker compose version
echo "Docker + Compose OK!"

# ── Step 3: Install uv + Python 3.12 ─────────────────────────────────────
echo ">>> Step 3: Install uv + Python 3.12"
pip3 install uv --quiet
uv python install 3.12 2>&1 | tail -3

# ── Step 4: Clone benchmark repo ─────────────────────────────────────────
echo ">>> Step 4: Clone benchmark repo"
WORKDIR="${WORKDIR:-/tmp}"
cd "$WORKDIR"
rm -rf finance-bench
git clone -b "$FB_REPO_BRANCH" "$FB_REPO_URL" finance-bench 2>&1 | tail -3
cd finance-bench

# ── Step 5: Setup venv + install harbor ───────────────────────────────────
echo ">>> Step 5: Setup venv + install Harbor"
uv venv --python 3.12 --seed .venv
source .venv/bin/activate
uv pip install "harbor @ git+https://github.com/harbor-framework/harbor" litellm pytest 2>&1 | tail -10
echo "Harbor: $(harbor --version 2>&1 || echo 'NOT FOUND')"

# ── Step 6: Build sandbox image + patch compose ──────────────────────────
echo ">>> Step 6: Build sandbox Docker image"
docker build -t finance-bench-sandbox:latest -f docker/sandbox.Dockerfile . 2>&1 | tail -10

# Patch Harbor's docker-compose-base.yaml: add network_mode: host (required in k8s DinD)
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

# Patch Harbor's docker.py: add timeout to docker compose cp operations only.
# Without this, docker compose cp can hang indefinitely in DinD environments.
# We add timeout_sec=300 to upload_file, upload_dir, download_file, download_dir.
# IMPORTANT: do NOT add timeout to the general exec() method — agent needs unlimited time.
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
    print(f"Patched docker.py: added timeout_sec=300 to {count} docker compose cp commands")
else:
    print("docker.py: no cp patterns matched, skipping")
PYPATCH
fi

# ── Step 7: Load credentials + run benchmark ─────────────────────────────
echo ">>> Step 7: Run benchmark"

TRIALS="$LOGDIR/trials"
mkdir -p "$TRIALS"

# Build harbor command
HARBOR_CMD=(.venv/bin/harbor trials start)

# Task selection: specific task or all tasks
if [ -n "$FB_TASK" ]; then
    HARBOR_CMD+=(-p "$FB_TASK")
else
    HARBOR_CMD+=(-p tasks/)
fi

HARBOR_CMD+=(-a "$FB_AGENT")
HARBOR_CMD+=(-m "$FB_MODEL")

# ── Provider-specific credential setup ──
# Detect provider from model string and configure accordingly
case "$FB_MODEL" in
    openai/google/gemini-*)
        # Gemini via Vertex AI OpenAI-compatible endpoint
        # Requires: GEMINI_VERTEX_TOKEN and GEMINI_VERTEX_BASE_URL
        #   Option A: Set them in environment before running this script
        #   Option B: Use foundry_auth.py to auto-generate (needs foundry_aws_gateway)
        if [ -z "$GEMINI_VERTEX_TOKEN" ] && command -v python3 &>/dev/null; then
            echo "Auto-generating Gemini credentials via foundry_aws_gateway..."
            if pip3 show foundry-aws-gateway &>/dev/null 2>&1; then
                eval "$(python3 "$(dirname "$0")/scripts/foundry_auth.py" gemini 2>/dev/null)"
            elif [ -f "$SHARED_FS/.gemini_env" ]; then
                source "$SHARED_FS/.gemini_env"
            fi
        fi
        if [ -z "$GEMINI_VERTEX_TOKEN" ]; then
            echo "FATAL: Gemini model requires GEMINI_VERTEX_TOKEN"; exit 1
        fi
        echo "Gemini auth OK (token length: ${#GEMINI_VERTEX_TOKEN})"
        # litellm uses OPENAI_API_KEY and OPENAI_API_BASE for openai/ models
        HARBOR_CMD+=(--ae "OPENAI_API_KEY=$GEMINI_VERTEX_TOKEN")
        HARBOR_CMD+=(--ae "OPENAI_API_BASE=$GEMINI_VERTEX_BASE_URL")
        ;;

    azure/gpt-*)
        # Azure OpenAI (GPT-5) via foundry_aws_gateway
        if [ -z "$AZURE_API_KEY" ] && command -v python3 &>/dev/null; then
            echo "Auto-generating Azure OpenAI credentials via foundry_aws_gateway..."
            if pip3 show foundry-aws-gateway &>/dev/null 2>&1; then
                eval "$(python3 "$(dirname "$0")/scripts/foundry_auth.py" azure 2>/dev/null)"
            elif [ -f "$SHARED_FS/.azure_env" ]; then
                source "$SHARED_FS/.azure_env"
            fi
        fi
        if [ -z "$AZURE_API_KEY" ]; then
            echo "FATAL: Azure model requires AZURE_API_KEY"; exit 1
        fi
        echo "Azure auth OK (endpoint: $AZURE_API_BASE)"
        HARBOR_CMD+=(--ae "AZURE_API_KEY=$AZURE_API_KEY")
        HARBOR_CMD+=(--ae "AZURE_API_BASE=$AZURE_API_BASE")
        HARBOR_CMD+=(--ae "AZURE_API_VERSION=${AZURE_API_VERSION:-2025-04-01-preview}")
        # Codex agent uses OPENAI_API_KEY/OPENAI_BASE_URL; map Azure creds
        HARBOR_CMD+=(--ae "OPENAI_API_KEY=$AZURE_API_KEY")
        HARBOR_CMD+=(--ae "OPENAI_BASE_URL=${AZURE_API_BASE}/openai")
        ;;

    bedrock/*|us.anthropic.*)
        # AWS Bedrock (Claude models)
        export CLAUDE_CODE_USE_BEDROCK=1
        export AWS_REGION=us-west-2
        export CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING=1

        # Load Bedrock credentials from shared FS (if available)
        if [ -f "$SHARED_FS/.bedrock_env" ]; then
            source "$SHARED_FS/.bedrock_env"
            echo "Loaded Bedrock token from shared FS (length: ${#AWS_BEARER_TOKEN_BEDROCK})"
        else
            echo "WARN: No .bedrock_env found, using ambient credentials"
        fi

        HARBOR_CMD+=(--ae "AWS_BEARER_TOKEN_BEDROCK=$AWS_BEARER_TOKEN_BEDROCK")
        HARBOR_CMD+=(--ae "CLAUDE_CODE_USE_BEDROCK=1")
        HARBOR_CMD+=(--ae "AWS_REGION=us-west-2")
        HARBOR_CMD+=(--ae "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING=1")
        HARBOR_CMD+=(--ae "DISABLE_PROMPT_CACHING=1")
        # Disable extended thinking (Bedrock multi-turn serialization bug)
        HARBOR_CMD+=(--agent-kwarg max_thinking_tokens=0)
        ;;

    *)
        # Generic: pass through any OPENAI_API_KEY / OPENAI_API_BASE from env
        if [ -n "$OPENAI_API_KEY" ]; then
            HARBOR_CMD+=(--ae "OPENAI_API_KEY=$OPENAI_API_KEY")
        fi
        if [ -n "$OPENAI_API_BASE" ]; then
            HARBOR_CMD+=(--ae "OPENAI_API_BASE=$OPENAI_API_BASE")
        fi
        echo "Using generic model: $FB_MODEL"
        ;;
esac

HARBOR_CMD+=(--trial-name "$FB_TRIAL_NAME")
HARBOR_CMD+=(--trials-dir "$TRIALS")

# Log the command but mask credentials
HARBOR_CMD_DISPLAY="${HARBOR_CMD[*]}"
for _secret in "$AWS_BEARER_TOKEN_BEDROCK" "$GEMINI_VERTEX_TOKEN" "$AZURE_API_KEY" "$OPENAI_API_KEY"; do
    [ -n "$_secret" ] && HARBOR_CMD_DISPLAY="${HARBOR_CMD_DISPLAY//$_secret/***REDACTED***}"
done
echo "Running: $HARBOR_CMD_DISPLAY"
"${HARBOR_CMD[@]}" 2>&1

echo ""
echo "=== Done ==="
echo "Results:"
find "$TRIALS" -name "result.json" -exec echo {} \; -exec python3 -c "
import json, sys
r = json.load(open(sys.argv[1]))
print(f'  reward: {r.get(\"verifier_result\",{}).get(\"reward\",\"N/A\")}')
print(f'  agent_exit: {r.get(\"agent_result\",{}).get(\"exit_code\",\"N/A\")}')
print(f'  tokens_in: {r.get(\"agent_result\",{}).get(\"total_input_tokens\",\"N/A\")}')
print(f'  tokens_out: {r.get(\"agent_result\",{}).get(\"total_output_tokens\",\"N/A\")}')
" {} \; 2>/dev/null || echo "  (no result.json found yet)"
echo "Init script complete at $(date -u)"
