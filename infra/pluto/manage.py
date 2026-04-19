#!/usr/bin/env python3
"""
Pluto Job Manager CLI

A command-line tool for managing Pluto jobs from a Pluto machine.
Uses $PLUTO_AUTH_TOKEN for authentication.

Usage:
    # Create a new interactive job with 4x H200 GPUs
    python manage.py create --name "lego-ie-worker-1" --gpu-type H200 --gpu-count 4

    # Create and auto-start
    python manage.py create --name "lego-ie-worker-1" --gpu-type H200 --gpu-count 4 --start

    # Create with an init script
    python manage.py create --name "lego-ie-worker-1" --gpu-type H200 --gpu-count 4 \
        --init-script /home/colligo/code/lego_v/deploy.sh --start

    # List jobs
    python manage.py list

    # Get job status
    python manage.py status <job_id>

    # Start/stop a job
    python manage.py start <job_id>
    python manage.py stop <job_id>

    # Get SSH info for a running job
    python manage.py ssh-info <job_id>

    # Wait for a job to be running
    python manage.py wait <job_id> --timeout 600

    # Create a batch of worker jobs for Lego IE
    python manage.py create-workers --count 5 --prefix "lego-ie-worker"
"""

import argparse
import asyncio
import json
import sys
import os

# Add pylibs to path for colligo SDK
sys.path.insert(0, "/mnt/localssd/colligo_home/colligo/pylibs")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pluto_client import PlutoJobManager, JobConfig, DEFAULT_PROJECT_ID


def setup_logging(verbose: bool = False):
    import logging
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def print_json(data):
    """Print data as pretty JSON."""
    if hasattr(data, "__dict__"):
        data = data.__dict__
    print(json.dumps(data, indent=2, default=str))


def print_jobs_table(jobs):
    """Print jobs in a formatted table."""
    if not jobs:
        print("No jobs found.")
        return

    # Header
    fmt = "{:<38} {:<30} {:<12} {:<22} {:<20}"
    print(fmt.format("JOB_ID", "NAME", "STATUS", "RUN_STATUS", "CREATED"))
    print("-" * 125)

    for j in jobs:
        print(fmt.format(
            j.job_id[:36] + ".." if len(j.job_id) > 38 else j.job_id,
            j.name[:28] + ".." if len(j.name) > 30 else j.name,
            j.status,
            j.run_status,
            j.created_at[:19] if j.created_at else "",
        ))


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

async def cmd_create(args):
    """Create a new job."""
    mgr = PlutoJobManager()

    config = JobConfig(
        name=args.name,
        project_id=args.project or DEFAULT_PROJECT_ID,
        gpu_type=args.gpu_type,
        gpu_count=args.gpu_count,
        cpu_type=args.cpu_type,
        cpu_cores=args.cpu_cores,
        num_pods=args.num_pods,
        job_type=args.job_type,
        image=args.image,
        preemptible=args.preemptible,
        limited_time_access=args.lta,
        init_scripts=args.init_script or [],
        main_scripts=args.main_script or [],
        description=args.description or "",
        auto_start=args.start,
        enable_docker=args.enable_docker,
    )

    job_id = await mgr.create_job(config)
    print(f"\nJob created successfully!")
    print(f"  Job ID:  {job_id}")
    print(f"  Name:    {config.name}")
    if config.gpu_type.lower() == "cpu":
        print(f"  CPU:     {config.cpu_cores} cores ({config.cpu_type})")
    else:
        print(f"  GPU:     {config.gpu_count}x {config.gpu_type}")
    print(f"  Type:    {config.job_type}")
    print(f"  UI URL:  https://ai.corp.adobe.com/jobs/{job_id}")

    if config.auto_start:
        print(f"\n  Job start requested. Waiting for RUNNING state...")
        running = await mgr.wait_for_running(job_id, timeout=600)
        if running:
            ssh_info = await mgr.get_job_ssh_info(job_id)
            print(f"\n  Job is RUNNING!")
            if ssh_info.get("pods"):
                for rank, pod in ssh_info["pods"].items():
                    print(f"    Rank {rank}: {pod}")
                    urls = ssh_info["service_urls"].get(rank, {})
                    if urls:
                        print(f"      DNS URL: {urls.get('dns', 'N/A')}")
        else:
            print(f"\n  Job did not reach RUNNING state within timeout.")


async def cmd_list(args):
    """List jobs."""
    mgr = PlutoJobManager()
    jobs = await mgr.list_my_jobs(project_id=args.project or DEFAULT_PROJECT_ID)

    if args.status:
        jobs = [j for j in jobs if j.run_status.lower() == args.status.lower()
                or j.status.lower() == args.status.lower()]

    if args.json:
        print_json([j.__dict__ for j in jobs])
    else:
        print_jobs_table(jobs)
        print(f"\nTotal: {len(jobs)} jobs")


async def cmd_status(args):
    """Get job status."""
    mgr = PlutoJobManager()
    info = await mgr.get_job(args.job_id)
    if args.json:
        print_json(info)
    else:
        print(f"Job: {info.name}")
        print(f"  ID:         {info.job_id}")
        print(f"  Owner:      {info.owner}")
        print(f"  Status:     {info.status}")
        print(f"  Run Status: {info.run_status}")
        print(f"  Created:    {info.created_at}")
        print(f"  UI URL:     https://ai.corp.adobe.com/jobs/{info.job_id}")


async def cmd_start(args):
    """Start a job."""
    mgr = PlutoJobManager()
    await mgr.start_job(args.job_id)
    print(f"Start requested for job {args.job_id}")

    if args.wait:
        print("Waiting for job to reach RUNNING state...")
        running = await mgr.wait_for_running(args.job_id, timeout=args.timeout)
        if running:
            print("Job is now RUNNING!")
        else:
            print("Job did not reach RUNNING state within timeout.")


async def cmd_stop(args):
    """Stop a job."""
    mgr = PlutoJobManager()
    await mgr.stop_job(args.job_id)
    print(f"Stop requested for job {args.job_id}")


async def cmd_restart(args):
    """Restart a job."""
    mgr = PlutoJobManager()
    await mgr.restart_job(args.job_id)
    print(f"Restart requested for job {args.job_id}")


async def cmd_ssh_info(args):
    """Get SSH connection info."""
    mgr = PlutoJobManager()
    info = await mgr.get_job_ssh_info(args.job_id)
    if args.json:
        print_json(info)
    else:
        if info.get("error"):
            print(f"Error: {info['error']}")
            return

        print(f"SSH Connection Info for job {args.job_id}:")
        print(f"  SSH Proxy: {info['ssh_proxy']}")
        print()
        for rank, pod in info.get("pods", {}).items():
            print(f"  Rank {rank}: {pod}")
            urls = info["service_urls"].get(rank, {})
            print(f"    DNS URL:  {urls.get('dns', 'N/A')}")
            print(f"    Internal: {urls.get('internal', 'N/A')}")
            print(f"    SSH:      {info['ssh_commands'].get(rank, 'N/A')}")
            print()


async def cmd_wait(args):
    """Wait for a job to reach RUNNING status."""
    mgr = PlutoJobManager()
    running = await mgr.wait_for_running(args.job_id, timeout=args.timeout)
    if running:
        print(f"Job {args.job_id} is now RUNNING!")
        sys.exit(0)
    else:
        print(f"Job {args.job_id} did not reach RUNNING state within {args.timeout}s.")
        sys.exit(1)


async def cmd_create_workers(args):
    """Create multiple worker jobs for Lego IE batch deployment."""
    mgr = PlutoJobManager()

    print(f"Creating {args.count} worker jobs...")
    print(f"  Prefix:    {args.prefix}")
    print(f"  GPU:       {args.gpu_count}x {args.gpu_type}")
    print(f"  Project:   {args.project or DEFAULT_PROJECT_ID}")
    print()

    created_jobs = []
    for i in range(1, args.count + 1):
        name = f"{args.prefix}-{i}"
        config = JobConfig(
            name=name,
            project_id=args.project or DEFAULT_PROJECT_ID,
            gpu_type=args.gpu_type,
            gpu_count=args.gpu_count,
            job_type="interactive",
            image=args.image,
            preemptible=args.preemptible,
            limited_time_access=args.lta,
            init_scripts=args.init_script or [],
            description=f"Lego IE worker {i} for batch generation",
            auto_start=args.start,
        )
        try:
            job_id = await mgr.create_job(config)
            created_jobs.append({"name": name, "job_id": job_id})
            print(f"  [{i}/{args.count}] Created: {name} -> {job_id}")
        except Exception as e:
            print(f"  [{i}/{args.count}] FAILED: {name} -> {e}")

    print(f"\n{len(created_jobs)}/{args.count} jobs created successfully.")

    if created_jobs and args.start:
        print("\nWaiting for all jobs to reach RUNNING state...")
        for job in created_jobs:
            running = await mgr.wait_for_running(job["job_id"], timeout=args.timeout)
            status = "RUNNING" if running else "NOT RUNNING"
            print(f"  {job['name']}: {status}")

    # Output summary
    if args.json:
        print_json(created_jobs)


# ─────────────────────────────────────────────────────────────────────────────
# CLI Parser
# ─────────────────────────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        description="Pluto Job Manager - Create and manage Pluto GPU jobs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── create ──
    p_create = subparsers.add_parser("create", help="Create a new job")
    p_create.add_argument("--name", required=True, help="Job name (unique within project)")
    p_create.add_argument("--project", help=f"Project ID (default: {DEFAULT_PROJECT_ID})")
    p_create.add_argument("--gpu-type", default="H200",
                          choices=["H200", "H100", "A100_80GB", "A100_40GB", "L40S", "A10G", "cpu"],
                          help="GPU type, or 'cpu' for CPU-only (default: H200)")
    p_create.add_argument("--gpu-count", type=int, default=4, help="GPUs per pod (default: 4)")
    p_create.add_argument("--cpu-type", default="c5d", choices=["c5d", "c6id"],
                          help="CPU instance type for --gpu-type cpu (default: c5d)")
    p_create.add_argument("--cpu-cores", type=int, default=4,
                          help="CPU cores for --gpu-type cpu (default: 4)")
    p_create.add_argument("--num-pods", type=int, default=1, help="Number of pods/ranks (default: 1)")
    p_create.add_argument("--job-type", default="interactive",
                          choices=["interactive", "training"], help="Job type (default: interactive)")
    p_create.add_argument("--image", default="docker-matrix-experiments-snapshot.ff.adobe.io/colligo/colligo-dev:v68",
                          help="Docker image URL")
    p_create.add_argument("--preemptible", action="store_true", help="Use preemptible allocation (quota-free)")
    p_create.add_argument("--lta", action="store_true", help="Use limited time access allocation")
    p_create.add_argument("--init-script", action="append", help="Path to init script (can repeat)")
    p_create.add_argument("--main-script", action="append", help="Path to main script (can repeat)")
    p_create.add_argument("--description", help="Job description")
    p_create.add_argument("--enable-docker", action="store_true", help="Enable Docker-in-Docker (privileged)")
    p_create.add_argument("--start", action="store_true", help="Start the job after creation")
    p_create.set_defaults(func=cmd_create)

    # ── list ──
    p_list = subparsers.add_parser("list", help="List jobs in project")
    p_list.add_argument("--project", help=f"Project ID (default: {DEFAULT_PROJECT_ID})")
    p_list.add_argument("--status", help="Filter by status (RUNNING, STOPPED, etc.)")
    p_list.add_argument("--json", action="store_true", help="Output as JSON")
    p_list.set_defaults(func=cmd_list)

    # ── status ──
    p_status = subparsers.add_parser("status", help="Get job status")
    p_status.add_argument("job_id", help="Job ID")
    p_status.add_argument("--json", action="store_true", help="Output as JSON")
    p_status.set_defaults(func=cmd_status)

    # ── start ──
    p_start = subparsers.add_parser("start", help="Start a job")
    p_start.add_argument("job_id", help="Job ID")
    p_start.add_argument("--wait", action="store_true", help="Wait for job to start")
    p_start.add_argument("--timeout", type=int, default=600, help="Wait timeout in seconds (default: 600)")
    p_start.set_defaults(func=cmd_start)

    # ── stop ──
    p_stop = subparsers.add_parser("stop", help="Stop a job")
    p_stop.add_argument("job_id", help="Job ID")
    p_stop.set_defaults(func=cmd_stop)

    # ── restart ──
    p_restart = subparsers.add_parser("restart", help="Restart a job")
    p_restart.add_argument("job_id", help="Job ID")
    p_restart.set_defaults(func=cmd_restart)

    # ── ssh-info ──
    p_ssh = subparsers.add_parser("ssh-info", help="Get SSH connection info for a running job")
    p_ssh.add_argument("job_id", help="Job ID")
    p_ssh.add_argument("--json", action="store_true", help="Output as JSON")
    p_ssh.set_defaults(func=cmd_ssh_info)

    # ── wait ──
    p_wait = subparsers.add_parser("wait", help="Wait for a job to reach RUNNING status")
    p_wait.add_argument("job_id", help="Job ID")
    p_wait.add_argument("--timeout", type=int, default=600, help="Timeout in seconds (default: 600)")
    p_wait.set_defaults(func=cmd_wait)

    # ── create-workers ──
    p_workers = subparsers.add_parser("create-workers",
                                       help="Create multiple worker jobs for batch deployment")
    p_workers.add_argument("--count", type=int, required=True, help="Number of workers to create")
    p_workers.add_argument("--prefix", default="lego-ie-worker", help="Job name prefix (default: lego-ie-worker)")
    p_workers.add_argument("--project", help=f"Project ID (default: {DEFAULT_PROJECT_ID})")
    p_workers.add_argument("--gpu-type", default="H200",
                           choices=["H200", "H100", "A100_80GB", "A100_40GB", "L40S", "A10G"])
    p_workers.add_argument("--gpu-count", type=int, default=4)
    p_workers.add_argument("--image", default="docker-matrix-experiments-snapshot.ff.adobe.io/colligo/colligo-dev:v68")
    p_workers.add_argument("--preemptible", action="store_true")
    p_workers.add_argument("--lta", action="store_true")
    p_workers.add_argument("--init-script", action="append")
    p_workers.add_argument("--start", action="store_true", help="Start all jobs after creation")
    p_workers.add_argument("--timeout", type=int, default=600)
    p_workers.add_argument("--json", action="store_true")
    p_workers.set_defaults(func=cmd_create_workers)

    # ── resources ──
    p_res = subparsers.add_parser("resources", help="Check cluster resources and project quota")
    p_res.add_argument("--json", action="store_true", help="Output as JSON")
    p_res.set_defaults(func=cmd_resources)

    return parser


async def cmd_resources(args):
    """Check cluster resources, project quota, and initiative capacity."""
    sys.path.insert(0, "/mnt/localssd/colligo_home/colligo/pylibs")

    from pluto_client import PlutoJobManager, GRPC_HOST_PROD, AUTH_TOKEN_ENV, DEFAULT_PROJECT_ID
    from colligo.pluto.client.access_token_provider import StaticAccessTokenProvider
    from colligo.pluto.client.base_client import create_grpc_channel
    from colligo.pluto.client.client_ecs import ECSClient
    from colligo.pluto.client.entity_defs import ComponentModels
    from colligo.pluto.client.models.project import PlutoProject
    from colligo.pluto.proto.ecs_kinds import ComponentType

    PROJECT_ID = DEFAULT_PROJECT_ID
    INITIATIVE_ID = "d54f60e2-523d-4314-a8dc-885f091183f6"
    CLUSTER_ID = os.environ.get("PLUTO_CLUSTER_ID", "50b0a95a-84be-443d-93c2-861ab6505e2b")

    # Second project/initiative
    PROJECT_ID_2 = "00828886-cc30-45a7-8ee2-cad6ffdd22c3"
    INITIATIVE_ID_2 = "4a0322d6-2dda-4870-a7db-6f91cc0980ae"

    GPU_NAMES = {
        "p5en.48xlarge": "H200 (141GB)",
        "p5.48xlarge": "H100 (80GB)",
        "p4de.24xlarge": "A100-80GB",
        "p4d.24xlarge": "A100-40GB",
        "p6-b200.48xlarge": "B200 (180GB)",
        "g6e.12xlarge": "L40S",
        "g5.12xlarge": "A10G",
    }

    token = os.environ.get(AUTH_TOKEN_ENV, "")
    tp = StaticAccessTokenProvider(token)
    ch = create_grpc_channel(GRPC_HOST_PROD, access_token_provider=tp, name="res-check", version="1.0")
    client = ECSClient(ch)
    await client.ping()

    # ── Cluster capacity ──
    cluster_entity = await client.get_entity(
        entity_id=CLUSTER_ID,
        component_types=[ComponentType.CAPACITY_USAGE_COMPONENT],
    )
    cluster_cap = ComponentModels.capacity_usage.get(cluster_entity)

    if cluster_cap and cluster_cap.cluster_usage and cluster_cap.cluster_usage.counters:
        print("=" * 90)
        print("CLUSTER CAPACITY (colligo-laser02-prod-uw2)")
        print("=" * 90)
        fmt = "{:<22} {:<14} {:>6} {:>8} {:>8} {:>8} {:>6} {:>6}"
        print(fmt.format("INSTANCE", "GPU", "NODES", "TOTAL", "USED", "FREE", "UTIL", "CORD"))
        print("-" * 90)
        for inst_type, counters in sorted(cluster_cap.cluster_usage.counters.items()):
            if "cpu-spli" in inst_type:
                continue
            s = counters.schedulable_node_counters
            c = counters.cordoned_node_counters
            free = s.total_xpus - s.used_xpus - s.reserved_xpus
            util = (s.used_xpus / s.total_xpus * 100) if s.total_xpus > 0 else 0
            gpu_name = GPU_NAMES.get(inst_type, "")
            print(fmt.format(inst_type, gpu_name, s.total_nodes, s.total_xpus, s.used_xpus, free, f"{util:.0f}%", c.total_nodes))

    # ── Initiative quota ──
    init_entity = await client.get_entity(
        entity_id=INITIATIVE_ID,
        component_types=[ComponentType.CAPACITY_USAGE_COMPONENT],
    )
    init_cap = ComponentModels.capacity_usage.get(init_entity)

    if init_cap and init_cap.quota_usage and init_cap.quota_usage.xpu_counters:
        print()
        print("=" * 90)
        print("INITIATIVE QUOTA (GAI-415 Foundry)")
        print("=" * 90)
        fmt = "{:<22} {:<14} {:>8} {:>8} {:>8} {:>8}"
        print(fmt.format("INSTANCE", "GPU", "ALLOC", "USED", "AVAIL", "PREEMPT"))
        print("-" * 90)
        for inst_type, c in sorted(init_cap.quota_usage.xpu_counters.items()):
            gpu_name = GPU_NAMES.get(inst_type, "")
            avail_str = str(c.quota_allocation_balance_xpus)
            if c.quota_allocation_balance_xpus < 0:
                avail_str = f"{c.quota_allocation_balance_xpus} (!)"
            print(fmt.format(inst_type, gpu_name, c.quota_allocated_xpus, c.quota_used_xpus, avail_str, c.preemptible_used_xpus))

    # ── Project quota ──
    proj_entity = await client.get_entity(
        entity_id=PROJECT_ID,
        component_types=[ComponentType.CAPACITY_USAGE_COMPONENT, ComponentType.PROJECT_COMPONENT],
    )
    proj = PlutoProject(proj_entity)
    proj_cap = ComponentModels.capacity_usage.get(proj_entity)

    if proj_cap and proj_cap.quota_usage and proj_cap.quota_usage.xpu_counters:
        print()
        print("=" * 90)
        print(f"PROJECT QUOTA (Foundry-THD) [{PROJECT_ID}]")
        print("=" * 90)
        fmt = "{:<22} {:<14} {:>8} {:>8} {:>8} {:>8}"
        print(fmt.format("INSTANCE", "GPU", "ALLOC", "USED", "AVAIL", "PREEMPT"))
        print("-" * 90)
        for inst_type, c in sorted(proj_cap.quota_usage.xpu_counters.items()):
            gpu_name = GPU_NAMES.get(inst_type, "")
            avail_str = str(c.quota_allocation_balance_xpus)
            if c.quota_allocation_balance_xpus < 0:
                avail_str = f"{c.quota_allocation_balance_xpus} (!)"
            print(fmt.format(inst_type, gpu_name, c.quota_allocated_xpus, c.quota_used_xpus, avail_str, c.preemptible_used_xpus))

    # ── Initiative 2: GAI-416 Platform Optimization ──
    init2_entity = await client.get_entity(
        entity_id=INITIATIVE_ID_2,
        component_types=[ComponentType.CAPACITY_USAGE_COMPONENT],
    )
    init2_cap = ComponentModels.capacity_usage.get(init2_entity)

    if init2_cap and init2_cap.quota_usage and init2_cap.quota_usage.xpu_counters:
        print()
        print("=" * 90)
        print("INITIATIVE QUOTA (GAI-416 Platform Optimization)")
        print("=" * 90)
        fmt = "{:<22} {:<14} {:>8} {:>8} {:>8} {:>8}"
        print(fmt.format("INSTANCE", "GPU", "ALLOC", "USED", "AVAIL", "PREEMPT"))
        print("-" * 90)
        for inst_type, c in sorted(init2_cap.quota_usage.xpu_counters.items()):
            gpu_name = GPU_NAMES.get(inst_type, "")
            avail_str = str(c.quota_allocation_balance_xpus)
            if c.quota_allocation_balance_xpus < 0:
                avail_str = f"{c.quota_allocation_balance_xpus} (!)"
            print(fmt.format(inst_type, gpu_name, c.quota_allocated_xpus, c.quota_used_xpus, avail_str, c.preemptible_used_xpus))

    # ── Project 2: xPU Efficiency ──
    proj2_entity = await client.get_entity(
        entity_id=PROJECT_ID_2,
        component_types=[ComponentType.CAPACITY_USAGE_COMPONENT],
    )
    proj2_cap = ComponentModels.capacity_usage.get(proj2_entity)

    if proj2_cap and proj2_cap.quota_usage and proj2_cap.quota_usage.xpu_counters:
        print()
        print("=" * 90)
        print(f"PROJECT QUOTA (xPU Efficiency) [{PROJECT_ID_2}]")
        print("=" * 90)
        fmt = "{:<22} {:<14} {:>8} {:>8} {:>8} {:>8}"
        print(fmt.format("INSTANCE", "GPU", "ALLOC", "USED", "AVAIL", "PREEMPT"))
        print("-" * 90)
        for inst_type, c in sorted(proj2_cap.quota_usage.xpu_counters.items()):
            gpu_name = GPU_NAMES.get(inst_type, "")
            avail_str = str(c.quota_allocation_balance_xpus)
            if c.quota_allocation_balance_xpus < 0:
                avail_str = f"{c.quota_allocation_balance_xpus} (!)"
            print(fmt.format(inst_type, gpu_name, c.quota_allocated_xpus, c.quota_used_xpus, avail_str, c.preemptible_used_xpus))

    # ── Summary / Recommendations ──
    print()
    print("=" * 90)
    print("RECOMMENDATION")
    print("=" * 90)
    if cluster_cap and cluster_cap.cluster_usage:
        for name, inst in [("H200", "p5en.48xlarge"), ("H100", "p5.48xlarge"), ("A100", "p4de.24xlarge"), ("B200", "p6-b200.48xlarge")]:
            if inst in cluster_cap.cluster_usage.counters:
                s = cluster_cap.cluster_usage.counters[inst].schedulable_node_counters
                free = s.total_xpus - s.used_xpus - s.reserved_xpus
                can4 = "YES" if free >= 4 else "NO"
                can8 = "YES" if free >= 8 else "NO"
                print(f"  {name:6}: {free:>4} GPUs free  |  4-GPU job: {can4}  |  8-GPU job: {can8}")


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    setup_logging(args.verbose)
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
