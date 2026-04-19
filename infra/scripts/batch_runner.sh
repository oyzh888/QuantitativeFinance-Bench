#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Batch Harbor Runner — Run N tasks in parallel on one DinD machine
#
# This script is meant to run AFTER init_harbor_dind.sh has set up the
# environment (pip, docker, harbor, venv). It launches multiple harbor tasks
# concurrently, each in its own docker sandbox.
#
# Usage: Called by the per-machine init scripts after setup is complete.
#        Or SSH into a DinD machine and run manually.
#
# Environment:
#   BATCH_TASKS     — space-separated task names (e.g. "bollinger-backtest-aapl momentum-backtest")
#   FB_MODEL        — model identifier
#   FB_AGENT        — agent type (default: claude-code)
#   FB_TRIAL_PREFIX — trial name prefix (default: fb-batch)
#   MAX_PARALLEL    — max concurrent tasks (default: 5)
#   SHARED_FS       — shared filesystem path
# ─────────────────────────────────────────────────────────────────────────────
set -e

SHARED_FS="${SHARED_FS:-/sensei-fs-3/users/zouyang/fb-harbor}"
WORKDIR="${WORKDIR:-/tmp/finance-bench}"
FB_MODEL="${FB_MODEL:-bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0}"
FB_AGENT="${FB_AGENT:-claude-code}"
FB_TRIAL_PREFIX="${FB_TRIAL_PREFIX:-fb-batch}"
MAX_PARALLEL="${MAX_PARALLEL:-5}"
TRIALS_DIR="$SHARED_FS/trials"

# All 17 tasks
ALL_TASKS=(
    american-option-fd-new
    barrier-garch-var
    bollinger-backtest-aapl
    cta-basel-capital
    fama-french-factor-model-new
    hull-white-swaption
    kelly-var-sizing
    mc-greek-surface-1
    mc-greeks-surface
    momentum-backtest
    regime-cta-vol-target
    regime-riskparity-cvar
    sentiment-factor-alpha
    sma-crossover-spy
    stochvol-implied-surface-new
    structured-note-risk
)

# Use BATCH_TASKS if set, else ALL_TASKS
if [ -n "$BATCH_TASKS" ]; then
    IFS=' ' read -ra TASKS <<< "$BATCH_TASKS"
else
    TASKS=("${ALL_TASKS[@]}")
fi

echo "=== Batch Runner ==="
echo "Model: $FB_MODEL"
echo "Agent: $FB_AGENT"
echo "Tasks: ${#TASKS[@]}"
echo "Max parallel: $MAX_PARALLEL"
echo "Trials dir: $TRIALS_DIR"
echo ""

mkdir -p "$TRIALS_DIR"

cd "$WORKDIR"
source .venv/bin/activate

# Build base harbor args (credentials)
HARBOR_BASE_ARGS=()
HARBOR_BASE_ARGS+=(-a "$FB_AGENT")
HARBOR_BASE_ARGS+=(-m "$FB_MODEL")

case "$FB_MODEL" in
    openai/google/gemini-*)
        HARBOR_BASE_ARGS+=(--ae "OPENAI_API_KEY=$OPENAI_API_KEY")
        HARBOR_BASE_ARGS+=(--ae "OPENAI_API_BASE=$OPENAI_API_BASE")
        ;;
    azure/gpt-*)
        HARBOR_BASE_ARGS+=(--ae "AZURE_API_KEY=$AZURE_API_KEY")
        HARBOR_BASE_ARGS+=(--ae "AZURE_API_BASE=$AZURE_API_BASE")
        HARBOR_BASE_ARGS+=(--ae "AZURE_API_VERSION=${AZURE_API_VERSION:-2025-04-01-preview}")
        HARBOR_BASE_ARGS+=(--ae "OPENAI_API_KEY=$AZURE_API_KEY")
        HARBOR_BASE_ARGS+=(--ae "OPENAI_BASE_URL=${AZURE_API_BASE}/openai")
        ;;
    bedrock/*|us.anthropic.*)
        HARBOR_BASE_ARGS+=(--ae "AWS_BEARER_TOKEN_BEDROCK=$AWS_BEARER_TOKEN_BEDROCK")
        HARBOR_BASE_ARGS+=(--ae "CLAUDE_CODE_USE_BEDROCK=1")
        HARBOR_BASE_ARGS+=(--ae "AWS_REGION=us-west-2")
        HARBOR_BASE_ARGS+=(--ae "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING=1")
        HARBOR_BASE_ARGS+=(--ae "DISABLE_PROMPT_CACHING=1")
        HARBOR_BASE_ARGS+=(--agent-kwarg max_thinking_tokens=0)
        ;;
    *)
        [ -n "$OPENAI_API_KEY" ] && HARBOR_BASE_ARGS+=(--ae "OPENAI_API_KEY=$OPENAI_API_KEY")
        [ -n "$OPENAI_API_BASE" ] && HARBOR_BASE_ARGS+=(--ae "OPENAI_API_BASE=$OPENAI_API_BASE")
        ;;
esac

# Function to run one task
run_task() {
    local task_name="$1"
    local trial_name="${FB_TRIAL_PREFIX}-${task_name}"
    local log_file="$TRIALS_DIR/${trial_name}.log"

    echo "[$(date +%H:%M:%S)] START: $task_name → $trial_name"

    .venv/bin/harbor trials start \
        -p "tasks/${task_name}" \
        "${HARBOR_BASE_ARGS[@]}" \
        --trial-name "$trial_name" \
        --trials-dir "$TRIALS_DIR" \
        > "$log_file" 2>&1

    local exit_code=$?

    # Extract result
    local result_file="$TRIALS_DIR/$trial_name/result.json"
    if [ -f "$result_file" ]; then
        local reward=$(python3 -c "
import json
d=json.load(open('$result_file'))
def find(d, key, depth=0):
    if depth > 5: return None
    if isinstance(d, dict):
        if key in d: return d[key]
        for v in d.values():
            r = find(v, key, depth+1)
            if r is not None: return r
    return None
print(find(d, 'reward') or '?')
" 2>/dev/null)
        echo "[$(date +%H:%M:%S)] DONE:  $task_name → reward=$reward (exit=$exit_code)"
    else
        echo "[$(date +%H:%M:%S)] DONE:  $task_name → NO RESULT (exit=$exit_code)"
    fi

    return $exit_code
}

# Run tasks with parallel limit
running=0
pids=()
task_names=()

for task in "${TASKS[@]}"; do
    # Check if already done
    trial_name="${FB_TRIAL_PREFIX}-${task}"
    if [ -f "$TRIALS_DIR/$trial_name/result.json" ]; then
        echo "SKIP: $task (already has result)"
        continue
    fi

    # Wait if at max parallel
    while [ $running -ge $MAX_PARALLEL ]; do
        wait -n 2>/dev/null || true
        running=$((running - 1))
    done

    run_task "$task" &
    pids+=($!)
    task_names+=("$task")
    running=$((running + 1))
done

# Wait for all remaining
echo ""
echo "Waiting for ${#pids[@]} remaining tasks..."
for pid in "${pids[@]}"; do
    wait "$pid" 2>/dev/null || true
done

# Summary
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "BATCH RESULTS SUMMARY"
echo "═══════════════════════════════════════════════════════════════"
printf "%-35s %-10s %12s %12s\n" "TRIAL" "REWARD" "IN_TOKENS" "OUT_TOKENS"
echo "─────────────────────────────────────────────────────────────"
for dir in "$TRIALS_DIR"/${FB_TRIAL_PREFIX}-*/; do
    [ -d "$dir" ] || continue
    name=$(basename "$dir")
    result="$dir/result.json"
    if [ -f "$result" ]; then
        python3 -c "
import json
d=json.load(open('$result'))
def find(d, key, depth=0):
    if depth > 5: return None
    if isinstance(d, dict):
        if key in d: return d[key]
        for v in d.values():
            r = find(v, key, depth+1)
            if r is not None: return r
    return None
reward = find(d, 'reward')
inp = find(d, 'n_input_tokens') or '?'
out = find(d, 'n_output_tokens') or '?'
print(f'$name {reward} {inp} {out}')
" 2>/dev/null | while read name reward inp out; do
            printf "%-35s %-10s %12s %12s\n" "$name" "$reward" "$inp" "$out"
        done
    else
        printf "%-35s %-10s\n" "$name" "NO_RESULT"
    fi
done

echo ""
echo "=== Batch complete at $(date -u) ==="
