#!/usr/bin/env python3
"""
Launch parallel Harbor benchmark experiments on Pluto.

Creates Pluto DinD CPU jobs with different model+task combos.
Each job runs init_harbor_dind.sh inside a Docker-in-Docker container.

Usage:
    python3 launch_experiments.py                    # Launch pre-defined experiment batch
    python3 launch_experiments.py --dry-run          # Show what would be launched
    python3 launch_experiments.py --status           # Check status of running experiments

Requires: pluto_client.py, foundry_aws_gateway (for Gemini/Azure tokens)
"""

import asyncio
import json
import os
import sys
import time

# Add pluto client to path
sys.path.insert(0, "/mnt/localssd/colligo_home/colligo/pylibs")
sys.path.insert(0, "/mnt/localssd/colligo_home/code/pluto_job_manage")

from pluto_client import PlutoJobManager, JobConfig

SHARED_FS = "/sensei-fs-3/users/zouyang/fb-harbor"

# ─── Experiment definitions ───────────────────────────────────────────────

EXPERIMENTS = [
    # (trial_name, model, agent, task, description)
    # ── Claude models via Bedrock (proven pipeline) ──
    ("fb-s4-bollinger",   "bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0",   "claude-code", "tasks/bollinger-backtest-aapl",  "Sonnet 4 × bollinger (new task)"),
    ("fb-s4-kelly",       "bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0",   "claude-code", "tasks/kelly-var-sizing",         "Sonnet 4 × kelly (medium)"),
    ("fb-s45-hull",       "bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0", "claude-code", "tasks/hull-white-swaption",      "Sonnet 4.5 × hull-white (hard)"),
    ("fb-h45-bollinger",  "bedrock/us.anthropic.claude-haiku-4-5-20250929-v1:0",  "claude-code", "tasks/bollinger-backtest-aapl",  "Haiku 4.5 × bollinger (compare)"),
    # ── GPT-5 via Azure OpenAI (new provider!) ──
    ("fb-gpt5-sma",       "azure/gpt-5",                                          "codex",       "tasks/sma-crossover-spy",        "GPT-5 × sma (easy baseline)"),
    ("fb-gpt5-momentum",  "azure/gpt-5",                                          "codex",       "tasks/momentum-backtest",        "GPT-5 × momentum (easy)"),
]


def generate_init_script(trial_name: str, model: str, agent: str, task: str) -> str:
    """Generate the init script for a Pluto job.

    This script runs on the Pluto pod (not inside Harbor sandbox).
    It generates auth tokens, then calls the main init_harbor_dind.sh.
    """
    return f'''#!/bin/bash
set -e
SHARED_FS="{SHARED_FS}"
LOGDIR="$SHARED_FS/trials/{trial_name}"
mkdir -p "$LOGDIR"
exec > >(tee "$LOGDIR/pluto-init-log.txt") 2>&1

echo "=== Pluto Init: {trial_name} ==="
echo "Model: {model}"
echo "Agent: {agent}"
echo "Task: {task}"
echo "Date: $(date -u)"

# ── Generate auth tokens ──
export PATH="$HOME/.local/bin:$PATH"

case "{model}" in
    openai/google/gemini-*)
        echo ">>> Generating Gemini credentials..."
        eval "$(python3 $SHARED_FS/scripts/foundry_auth.py gemini 2>/dev/null)"
        if [ -z "$GEMINI_VERTEX_TOKEN" ]; then
            echo "FATAL: Failed to get Gemini token"
            exit 1
        fi
        echo "Gemini token OK (length: ${{#GEMINI_VERTEX_TOKEN}})"
        ;;
    azure/gpt-*)
        echo ">>> Generating Azure credentials..."
        eval "$(python3 $SHARED_FS/scripts/foundry_auth.py azure 2>/dev/null)"
        if [ -z "$AZURE_API_KEY" ]; then
            echo "FATAL: Failed to get Azure token"
            exit 1
        fi
        echo "Azure token OK (endpoint: $AZURE_API_BASE)"
        ;;
esac

# ── Run the main Harbor init script ──
export FB_TASK="{task}"
export FB_TRIAL_NAME="{trial_name}"
export FB_MODEL="{model}"
export FB_AGENT="{agent}"
export SHARED_FS="$SHARED_FS"

bash "$SHARED_FS/init_harbor_dind.sh"

echo "=== Pluto job complete: {trial_name} ==="
'''


async def launch_batch(experiments, dry_run=False):
    """Launch a batch of experiments on Pluto."""
    if not dry_run:
        mgr = PlutoJobManager()

    job_ids = []
    for trial_name, model, agent, task, desc in experiments:
        script_content = generate_init_script(trial_name, model, agent, task)

        if dry_run:
            print(f"\n{'='*60}")
            print(f"Trial: {trial_name}")
            print(f"Model: {model}")
            print(f"Agent: {agent}")
            print(f"Task:  {task}")
            print(f"Desc:  {desc}")
            print(f"{'='*60}")
            continue

        # Write script to shared FS
        script_path = f"{SHARED_FS}/scripts/init_{trial_name}.sh"
        with open(script_path, 'w') as f:
            f.write(script_content)
        os.chmod(script_path, 0o755)

        config = JobConfig(
            name=f"fb-bench-{trial_name}",
            gpu_type="cpu",
            cpu_type="c6id",
            cpu_cores=96,
            num_pods=1,
            job_type="interactive",
            preemptible=True,
            enable_docker=True,
            init_scripts=[script_path],
            description=f"Finance-bench: {desc}",
            auto_start=True,
        )

        try:
            job_id = await mgr.create_job(config)
            print(f"✓ {trial_name}: job_id={job_id}")
            job_ids.append((trial_name, job_id))
        except Exception as e:
            print(f"✗ {trial_name}: FAILED - {e}")
            job_ids.append((trial_name, None))

    return job_ids


async def check_status():
    """Check status of recent experiments."""
    mgr = PlutoJobManager()
    jobs = await mgr.list_my_jobs()

    # Filter for fb-bench jobs
    bench_jobs = [j for j in jobs if j.name.startswith('fb-bench-')]
    if not bench_jobs:
        # Show recent jobs
        bench_jobs = sorted(jobs, key=lambda j: j.created_at, reverse=True)[:10]

    print(f"\n{'Job Name':<40} {'Status':<12} {'Run Status':<12} {'Created'}")
    print("-" * 95)
    for j in bench_jobs:
        print(f"{j.name or j.job_id[:20]:<40} {j.status:<12} {j.run_status:<12} {j.created_at}")

    # Check for trial results on shared FS
    print(f"\n{'='*60}")
    print("Trial results on shared FS:")
    print(f"{'='*60}")
    trials_dir = f"{SHARED_FS}/trials"
    if os.path.exists(trials_dir):
        for trial in sorted(os.listdir(trials_dir)):
            trial_path = os.path.join(trials_dir, trial)
            if not os.path.isdir(trial_path):
                continue
            # Check for result.json
            result_path = os.path.join(trial_path, "result.json")
            log_path = os.path.join(trial_path, "pluto-init-log.txt")

            status = "?"
            reward = "?"
            if os.path.exists(result_path):
                try:
                    r = json.load(open(result_path))
                    vr = r.get("verifier_result", {})
                    rewards = vr.get("rewards", {})
                    reward = rewards.get("reward", rewards) if isinstance(rewards, dict) else rewards
                    ar = r.get("agent_result", {})
                    tokens_in = ar.get("n_input_tokens", "?")
                    tokens_out = ar.get("n_output_tokens", "?")
                    status = "DONE"
                except:
                    status = "RESULT_ERROR"
            elif os.path.exists(log_path):
                log = open(log_path).read()
                if "Init script complete" in log:
                    status = "DONE (no result)"
                elif "FATAL" in log:
                    status = "FATAL"
                else:
                    status = "RUNNING"
            else:
                status = "PENDING"

            extra = ""
            if status == "DONE" and tokens_in != "?":
                extra = f" tokens={tokens_in}/{tokens_out}"
            print(f"  {trial:<40} status={status:<20} reward={reward}{extra}")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Launch benchmark experiments on Pluto")
    parser.add_argument("--dry-run", action="store_true", help="Show experiments without launching")
    parser.add_argument("--status", action="store_true", help="Check experiment status")
    parser.add_argument("--experiments", type=str, help="JSON list of experiment indices to run (e.g. '[0,1,2]')")
    args = parser.parse_args()

    if args.status:
        await check_status()
        return

    # Select experiments
    exps = EXPERIMENTS
    if args.experiments:
        indices = json.loads(args.experiments)
        exps = [EXPERIMENTS[i] for i in indices]

    print(f"Launching {len(exps)} experiments...")
    for i, (name, model, agent, task, desc) in enumerate(exps):
        print(f"  [{i}] {name}: {agent} + {model} × {task}")
    print()

    job_ids = await launch_batch(exps, dry_run=args.dry_run)

    if not args.dry_run and job_ids:
        print(f"\n{'='*60}")
        print("Launched jobs:")
        for name, jid in job_ids:
            print(f"  {name}: {jid or 'FAILED'}")
        print(f"\nMonitor with: python3 {__file__} --status")


if __name__ == "__main__":
    asyncio.run(main())
