#!/usr/bin/env python3
"""
One-command Harbor benchmark launcher for Pluto.

Allocation strategy (designed to minimize cost):
  1. Try CPU preemptible (c6id.24xlarge, P2 quota-free)
  2. If INSUFFICIENT_RESOURCES after 60s, try CPU non-preemptible (P0)
  3. If still fails, fall back to A10G GPU preemptible (smallest GPU full-node)
  4. If all fail, report error

Usage:
    # Quick test: single task, CPU preemptible
    python3 launch.py --name fb-test --task tasks/american-option-fd-new

    # Full benchmark: all tasks
    python3 launch.py --name fb-full

    # Force GPU (skip CPU attempts)
    python3 launch.py --name fb-gpu --strategy gpu

    # Custom model
    python3 launch.py --name fb-opus --model bedrock/us.anthropic.claude-opus-4-20250514-v1:0

    # Non-preemptible only (guaranteed allocation)
    python3 launch.py --name fb-safe --strategy guaranteed

    # Check status of running job
    python3 launch.py --status <job_id>

    # Stop a running job
    python3 launch.py --stop <job_id>
"""

import argparse
import asyncio
import os
import sys
import time

# Add pylibs and local path
sys.path.insert(0, "/mnt/localssd/colligo_home/colligo/pylibs")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pluto_client import PlutoJobManager, JobConfig, DEFAULT_PROJECT_ID


# ─────────────────────────────────────────────────────────────────────────────
# Allocation strategies: ordered list of (description, JobConfig overrides)
# ─────────────────────────────────────────────────────────────────────────────

STRATEGY_DEFAULT = [
    {
        "desc": "CPU c6id preemptible (P2, quota-free)",
        "gpu_type": "cpu",
        "cpu_type": "c6id",
        "cpu_cores": 80,  # full node
        "preemptible": True,
        "limited_time_access": False,
    },
    {
        "desc": "CPU c6id non-preemptible (P0, quota-charged)",
        "gpu_type": "cpu",
        "cpu_type": "c6id",
        "cpu_cores": 80,
        "preemptible": False,
        "limited_time_access": False,
    },
    {
        "desc": "GPU A10G preemptible (P2, smallest GPU node)",
        "gpu_type": "A10G",
        "gpu_count": 4,
        "preemptible": True,
        "limited_time_access": False,
    },
]

STRATEGY_GPU = [
    {
        "desc": "GPU A10G preemptible (P2)",
        "gpu_type": "A10G",
        "gpu_count": 4,
        "preemptible": True,
        "limited_time_access": False,
    },
    {
        "desc": "GPU A10G non-preemptible (P0)",
        "gpu_type": "A10G",
        "gpu_count": 4,
        "preemptible": False,
        "limited_time_access": False,
    },
]

STRATEGY_GUARANTEED = [
    {
        "desc": "CPU c6id non-preemptible (P0)",
        "gpu_type": "cpu",
        "cpu_type": "c6id",
        "cpu_cores": 80,
        "preemptible": False,
        "limited_time_access": False,
    },
]

STRATEGIES = {
    "default": STRATEGY_DEFAULT,
    "gpu": STRATEGY_GPU,
    "guaranteed": STRATEGY_GUARANTEED,
}

# Default init script path (relative to repo root)
DEFAULT_INIT_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "init_harbor_dind.sh",
)

SHARED_FS = "/sensei-fs-3/users/zouyang/fb-harbor"


def ensure_bedrock_token():
    """Ensure Bedrock token is saved to shared FS for the init script."""
    token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "")
    if not token:
        print("WARN: AWS_BEARER_TOKEN_BEDROCK not set in environment")
        print("      The init script will try to load from shared FS")
        return

    env_file = os.path.join(SHARED_FS, ".bedrock_env")
    os.makedirs(SHARED_FS, exist_ok=True)
    with open(env_file, "w") as f:
        f.write(f"export AWS_BEARER_TOKEN_BEDROCK='{token}'\n")
    os.chmod(env_file, 0o600)
    print(f"Bedrock token saved to {env_file} (length: {len(token)})")


async def try_allocation(
    mgr: PlutoJobManager,
    name: str,
    project_id: str,
    alloc: dict,
    init_script: str,
    env_vars: dict,
    wait_timeout: int = 120,
) -> str | None:
    """
    Try to create and start a job with the given allocation.
    Returns job_id if successful, None if resources unavailable.
    """
    desc = alloc["desc"]
    print(f"\n{'='*60}")
    print(f"Trying: {desc}")
    print(f"{'='*60}")

    config = JobConfig(
        name=name,
        project_id=project_id,
        gpu_type=alloc["gpu_type"],
        gpu_count=alloc.get("gpu_count", 4),
        cpu_type=alloc.get("cpu_type", "c6id"),
        cpu_cores=alloc.get("cpu_cores", 80),
        preemptible=alloc.get("preemptible", False),
        limited_time_access=alloc.get("limited_time_access", False),
        enable_docker=True,
        init_scripts=[init_script],
        description=f"Harbor benchmark: {desc}",
        auto_start=False,
        env_vars=env_vars,
    )

    try:
        job_id = await mgr.create_job(config)
        print(f"Created job: {job_id}")
        print(f"UI: https://ai.corp.adobe.com/jobs/{job_id}")
    except Exception as e:
        print(f"Failed to create job: {e}")
        return None

    # Start and wait
    try:
        await mgr.start_job(job_id)
        print(f"Start requested, waiting up to {wait_timeout}s...")
    except Exception as e:
        print(f"Failed to start job: {e}")
        return None

    start_time = time.time()
    while time.time() - start_time < wait_timeout:
        info = await mgr.get_job(job_id)
        status = info.run_status

        if status == "RUNNING":
            print(f"Job is RUNNING!")
            return job_id

        if status in ("FAILED", "STOPPED", "SUCCEEDED"):
            print(f"Job reached terminal state: {status}")
            # Clean up
            try:
                await mgr.stop_job(job_id)
            except Exception:
                pass
            return None

        if status == "INSUFFICIENT_RESOURCES":
            elapsed = time.time() - start_time
            if elapsed > 60:
                print(f"INSUFFICIENT_RESOURCES for {elapsed:.0f}s, giving up on this allocation")
                try:
                    await mgr.stop_job(job_id)
                except Exception:
                    pass
                return None
            # Still waiting, might free up
            print(f"  {status} ({elapsed:.0f}s elapsed, will retry for 60s)")

        else:
            print(f"  Status: {status} ({time.time() - start_time:.0f}s)")

        await asyncio.sleep(10)

    print(f"Timeout after {wait_timeout}s")
    try:
        await mgr.stop_job(job_id)
    except Exception:
        pass
    return None


async def launch(args):
    """Main launch logic with allocation fallback."""
    mgr = PlutoJobManager()

    # Ensure credentials are available
    ensure_bedrock_token()

    # Build env vars to pass to the pod
    env_vars = {}
    if args.task:
        env_vars["FB_TASK"] = args.task
    if args.trial_name:
        env_vars["FB_TRIAL_NAME"] = args.trial_name
    else:
        env_vars["FB_TRIAL_NAME"] = args.name
    if args.model:
        env_vars["FB_MODEL"] = args.model
    if args.agent:
        env_vars["FB_AGENT"] = args.agent

    # Get allocation strategy
    strategy = STRATEGIES.get(args.strategy, STRATEGY_DEFAULT)
    init_script = args.init_script or DEFAULT_INIT_SCRIPT

    if not os.path.exists(init_script):
        print(f"ERROR: Init script not found: {init_script}")
        sys.exit(1)

    print(f"Launch: {args.name}")
    print(f"Strategy: {args.strategy} ({len(strategy)} allocation tiers)")
    print(f"Init script: {init_script}")
    if args.task:
        print(f"Task: {args.task}")
    else:
        print(f"Task: ALL")
    print(f"Model: {env_vars.get('FB_MODEL', 'default')}")

    # Try each allocation tier
    for i, alloc in enumerate(strategy):
        job_id = await try_allocation(
            mgr=mgr,
            name=f"{args.name}" if i == 0 else f"{args.name}-t{i+1}",
            project_id=args.project,
            alloc=alloc,
            init_script=init_script,
            env_vars=env_vars,
            wait_timeout=args.wait_timeout,
        )

        if job_id:
            print(f"\n{'='*60}")
            print(f"SUCCESS: Job running with {alloc['desc']}")
            print(f"{'='*60}")
            print(f"  Job ID:  {job_id}")
            print(f"  UI:      https://ai.corp.adobe.com/jobs/{job_id}")
            print(f"  Logs:    tail -f {SHARED_FS}/init-log.txt")
            print(f"  Results: {SHARED_FS}/trials/")
            print(f"\n  To stop: python3 launch.py --stop {job_id}")
            return

    print(f"\nFAILED: All {len(strategy)} allocation tiers exhausted.")
    print("Try again later or check resources: python3 manage.py resources")
    sys.exit(1)


async def check_status(job_id: str):
    """Check and display job status."""
    mgr = PlutoJobManager()
    info = await mgr.get_job(job_id)
    print(f"Job: {info.name}")
    print(f"  ID:         {info.job_id}")
    print(f"  Status:     {info.status}")
    print(f"  Run Status: {info.run_status}")
    print(f"  UI:         https://ai.corp.adobe.com/jobs/{info.job_id}")

    # Check log
    log_file = os.path.join(SHARED_FS, "init-log.txt")
    if os.path.exists(log_file):
        print(f"\n  Latest log:")
        with open(log_file) as f:
            lines = f.readlines()
            for line in lines[-5:]:
                print(f"    {line.rstrip()}")


async def stop_job(job_id: str):
    """Stop a running job."""
    mgr = PlutoJobManager()
    await mgr.stop_job(job_id)
    print(f"Stop requested for job {job_id}")


def main():
    parser = argparse.ArgumentParser(
        description="One-command Harbor benchmark launcher for Pluto",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Allocation strategies:
  default     Try CPU preemptible -> CPU guaranteed -> GPU preemptible
  gpu         Try GPU preemptible -> GPU guaranteed
  guaranteed  CPU non-preemptible only (uses project quota)

Examples:
  python3 launch.py --name fb-test --task tasks/american-option-fd-new
  python3 launch.py --name fb-full
  python3 launch.py --name fb-gpu --strategy gpu
  python3 launch.py --stop <job_id>
        """,
    )

    # Mode selection
    parser.add_argument("--status", metavar="JOB_ID", help="Check job status")
    parser.add_argument("--stop", metavar="JOB_ID", help="Stop a running job")

    # Launch options
    parser.add_argument("--name", default="fb-harbor", help="Job name (default: fb-harbor)")
    parser.add_argument("--project", default=DEFAULT_PROJECT_ID, help="Pluto project ID")
    parser.add_argument("--strategy", default="default",
                        choices=list(STRATEGIES.keys()),
                        help="Allocation strategy (default: default)")
    parser.add_argument("--task", help="Specific task path (default: all tasks)")
    parser.add_argument("--trial-name", help="Trial name prefix")
    parser.add_argument("--model", help="Model identifier (e.g. bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0)")
    parser.add_argument("--agent", default="claude-code", help="Agent type (default: claude-code)")
    parser.add_argument("--init-script", help=f"Init script path (default: {DEFAULT_INIT_SCRIPT})")
    parser.add_argument("--wait-timeout", type=int, default=180,
                        help="Seconds to wait for each allocation tier (default: 180)")

    args = parser.parse_args()

    if args.status:
        asyncio.run(check_status(args.status))
    elif args.stop:
        asyncio.run(stop_job(args.stop))
    else:
        asyncio.run(launch(args))


if __name__ == "__main__":
    main()
