"""
Pluto Job Management Client

A standalone Python client that uses the colligo Pluto SDK to create, list,
start, stop, and monitor Pluto jobs. Designed to run on a Pluto machine
with $PLUTO_AUTH_TOKEN available.

Authentication: Uses $PLUTO_AUTH_TOKEN (machine-level JWT) automatically.
gRPC Endpoint: grpcs://pluto-grpc.ff.adobe.io (prod)
"""

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any

# Pluto SDK imports (available in colligo pylibs)
sys.path.insert(0, "/mnt/localssd/colligo_home/colligo/pylibs")

from colligo.pluto.client.access_token_provider import (
    EnvAccessTokenProvider,
    StaticAccessTokenProvider,
)
from colligo.pluto.client.base_client import create_grpc_channel
from colligo.pluto.client.client_business_actions import BusinessActionsClient
from colligo.pluto.client.client_ecs import ECSClient
try:
    from colligo.pluto.client.client_job import JobClient
except ImportError:
    JobClient = None  # SDK version mismatch — JobClient not available
from colligo.pluto.client.models.job import PlutoJob
from colligo.pluto.client.protobuf_utils import pack_to_any
from colligo.pluto.proto.actions import BusinessAction, BusinessActionContext
from colligo.pluto.proto.compute import (
    AcceleratorType,
    AutoRecoveryMode,
    ExecConfig,
    ExecSpec,
    HostSpec,
    JobRunStatus,
    JobStatus,
    JobType,
    PreemptionPolicy,
    ScriptSpec,
    ScriptType,
    StartJobAction,
    StopJobAction,
    JobStatusReason,
)
from colligo.pluto.proto.ecs import (
    ComponentMapItem,
    CreateEntity,
    QueryRule,
    QueryTypes,
    UpdateEntitiesRequest,
)
from colligo.pluto.proto.ecs_kinds import ComponentType, EntityType
from colligo.pluto.proto.system import NameComponent
from colligo.pluto.proto.compute import JobComponent


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

GRPC_HOST_PROD = "grpcs://pluto-grpc.ff.adobe.io"
GRPC_HOST_STAGE = "grpcs://pluto-grpc-stage.ff.adobe.io"
AUTH_TOKEN_ENV = "PLUTO_AUTH_TOKEN"

# Steve's project info
DEFAULT_PROJECT_ID = "cb1b7672-0919-445c-9c0f-bff79b7391ac"  # Foundry-THD
DEFAULT_PROJECT_NAME = "Foundry-THD"

# GPU instance type mapping
GPU_INSTANCE_TYPES = {
    "H200": "p5en.48xlarge",
    "H100": "p5.48xlarge",
    "A100_80GB": "p4de.24xlarge",
    "A100_40GB": "p4d.24xlarge",
    "L40S": "g6e.12xlarge",
    "A10G": "g5.12xlarge",
}

# CPU instance type mapping (no GPU)
CPU_INSTANCE_TYPES = {
    "c5d": "c5d.18xlarge",
    "c6id": "c6id.24xlarge",
}

# Accelerator type mapping (proto enum values)
GPU_ACCELERATOR_TYPES = {
    "A10G": AcceleratorType.NVIDIA_A10G,
    "A100_40GB": AcceleratorType.NVIDIA_A100_40GB,
    "A100_80GB": AcceleratorType.NVIDIA_A100_80GB,
    "H100": AcceleratorType.NVIDIA_H100_80GB,
    "H200": AcceleratorType.NVIDIA_H200_141GB,
}

# Default docker image
DEFAULT_IMAGE = "docker-matrix-experiments-snapshot.ff.adobe.io/colligo/colligo-dev:v68"

# AcceleratorType enum values (from compute_types.proto)
ACCELERATOR_TYPE_MAP = {
    "H200": 14,   # NVIDIA_H200_141GB
    "H100": 7,    # NVIDIA_H100_80GB
    "A100_80GB": 5,  # NVIDIA_A100_80GB
    "A100_40GB": 4,  # NVIDIA_A100_40GB
    "L40S": 3,    # NVIDIA_L40S
    "A10G": 1,    # NVIDIA_A10G
    "B200": 15,   # NVIDIA_B200_1440GB
}


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class JobConfig:
    """Configuration for creating a new Pluto job."""
    name: str
    project_id: str = DEFAULT_PROJECT_ID
    gpu_type: str = "H200"          # H200, H100, A100_80GB, or "cpu" for CPU-only
    gpu_count: int = 4              # GPUs per pod (4 = half node H200), ignored for cpu
    cpu_type: str = "c5d"           # CPU instance type: c5d, c6id (only for gpu_type="cpu")
    cpu_cores: int = 4              # CPU cores to request (only for gpu_type="cpu")
    num_pods: int = 1               # Number of pods (replicas/ranks)
    job_type: str = "interactive"   # interactive or training
    image: str = DEFAULT_IMAGE
    preemptible: bool = False       # Use preemptible (quota-free) allocation
    limited_time_access: bool = False  # Use LTA allocation
    init_scripts: list[str] = field(default_factory=list)  # Paths to init scripts
    main_scripts: list[str] = field(default_factory=list)  # Paths to main scripts
    env_vars: dict[str, str] = field(default_factory=dict)
    description: str = ""
    auto_start: bool = False        # Start the job immediately after creation
    enable_docker: bool = False     # Enable Docker-in-Docker (privileged mode)


@dataclass
class JobInfo:
    """Information about an existing job."""
    job_id: str
    name: str
    owner: str
    project_id: str
    status: str           # DRAFT, SCHEDULED, PAUSED
    run_status: str       # NONE, PENDING, RUNNING, FAILED, etc.
    created_at: str
    tags: list[str] = field(default_factory=list)
    unique_name: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────────────────────────────────────

class PlutoJobManager:
    """High-level Pluto job management client."""

    def __init__(
        self,
        grpc_host: str = GRPC_HOST_PROD,
        token: str | None = None,
    ):
        self.grpc_host = grpc_host
        self._token = token or os.environ.get(AUTH_TOKEN_ENV, "")
        if not self._token:
            raise RuntimeError(
                f"No auth token. Set ${AUTH_TOKEN_ENV} or pass token= parameter."
            )
        self._channel = None
        self._ecs_client: ECSClient | None = None
        self._job_client: JobClient | None = None
        self._ba_client: BusinessActionsClient | None = None

    async def _ensure_clients(self):
        """Lazily initialize gRPC clients."""
        if self._ecs_client is not None:
            return

        token_provider = StaticAccessTokenProvider(self._token)
        self._channel = create_grpc_channel(
            self.grpc_host,
            access_token_provider=token_provider,
            name="pluto-job-manage",
            version="1.0.0",
        )
        self._ecs_client = ECSClient(self._channel)
        self._job_client = JobClient(self._channel) if JobClient is not None else None
        self._ba_client = BusinessActionsClient(self._channel)

        # Test connection
        await self._ecs_client.ping()
        logger.info("Connected to Pluto gRPC at %s", self.grpc_host)

    # ─────────────────────────────────────────────────────────────────────
    # Job Creation
    # ─────────────────────────────────────────────────────────────────────

    async def create_job(self, config: JobConfig) -> str:
        """
        Create a new Pluto job.

        Returns the job_id of the created job.
        """
        await self._ensure_clients()

        # Build HostSpec — CPU-only or GPU
        if config.gpu_type.lower() == "cpu":
            cpu_instance = CPU_INSTANCE_TYPES.get(config.cpu_type)
            if not cpu_instance:
                raise ValueError(
                    f"Unknown CPU type: {config.cpu_type}. "
                    f"Valid types: {list(CPU_INSTANCE_TYPES.keys())}"
                )
            host_spec = HostSpec(
                cloud_instance_name=cpu_instance,
                cpu_cores=config.cpu_cores,
            )
        else:
            gpu_instance = GPU_INSTANCE_TYPES.get(config.gpu_type)
            if not gpu_instance:
                raise ValueError(
                    f"Unknown GPU type: {config.gpu_type}. "
                    f"Valid types: {list(GPU_INSTANCE_TYPES.keys())}"
                )
            accel_type = GPU_ACCELERATOR_TYPES.get(config.gpu_type, AcceleratorType.NONE)
            host_spec = HostSpec(
                cloud_instance_name=gpu_instance,
                accelerator_type=accel_type,
                accelerator_count=config.gpu_count,
                use_single_node_group=True,
            )

        # Determine preemption policy
        if config.preemptible:
            preemption_policy = PreemptionPolicy.PREEMPTABLE
        elif config.limited_time_access:
            preemption_policy = PreemptionPolicy.LIMITED_TIME_ACCESS
        else:
            preemption_policy = PreemptionPolicy.NON_PREEMPTABLE

        # Determine job type
        if config.job_type == "training":
            job_type = JobType.JOB_TYPE_TRAINING
        else:
            job_type = JobType.JOB_TYPE_INTERACTIVE_SESSION

        # Build ExecSpec
        exec_spec = ExecSpec(
            image_url=config.image,
            host_spec=host_spec,
            scripts=[],  # scripts uploaded separately
            num_ranks=config.num_pods,
            auto_snapshot=True,
            preemption_policy=preemption_policy,
            auto_recovery_mode=AutoRecoveryMode.AUTO_RECOVERY_MODE_DISABLED,
            exec_config=ExecConfig(
                keep_failed_pods_running=False,
                verbose=False,
            ),
            env=config.env_vars,
            enable_docker=config.enable_docker,
        )

        # Build JobComponent
        job_component = JobComponent(
            job_type=job_type,
            exec_spec=exec_spec,
        )

        # Build components list
        components = [
            ComponentMapItem(
                component_type=ComponentType.NAME_COMPONENT,
                component_data=pack_to_any(
                    NameComponent(
                        name=config.name,
                        description=config.description,
                    )
                ),
            ),
            ComponentMapItem(
                component_type=ComponentType.JOB_COMPONENT,
                component_data=pack_to_any(job_component),
            ),
        ]

        # Create the job entity
        response = await self._ecs_client.update_entities(
            UpdateEntitiesRequest(
                create_entities=[
                    CreateEntity(
                        type=EntityType.ENTITY_TYPE_JOB,
                        parent_id=config.project_id,
                        components=components,
                    ),
                ]
            )
        )

        if response.errors:
            error_msgs = [str(e) for e in response.errors]
            raise RuntimeError(f"Failed to create job: {error_msgs}")

        job_id = response.created_entities[0].id
        logger.info("Job created: %s (id=%s)", config.name, job_id)

        # Track the job locally
        self._save_tracked_job(job_id)

        # Upload scripts if provided
        if config.init_scripts or config.main_scripts:
            await self._upload_scripts(job_id, config.init_scripts, config.main_scripts)

        # Auto-start if requested
        if config.auto_start:
            await self.start_job(job_id)

        return job_id

    async def _upload_scripts(
        self,
        job_id: str,
        init_scripts: list[str],
        main_scripts: list[str],
    ):
        """Upload init and main scripts to a job."""
        import uuid

        script_specs = []
        for idx, path in enumerate(init_scripts):
            content = _read_file(path)
            script_specs.append(
                ScriptSpec(
                    id=str(uuid.uuid4()),
                    name=f"Init Script {idx + 1}",
                    type=ScriptType.INIT,
                    shell_code=content,
                )
            )
        for idx, path in enumerate(main_scripts):
            content = _read_file(path)
            script_specs.append(
                ScriptSpec(
                    id=str(uuid.uuid4()),
                    name=f"Main Script {idx + 1}",
                    type=ScriptType.MAIN,
                    shell_code=content,
                )
            )

        if script_specs:
            from colligo.pluto.proto.compute import UploadJobScriptsAction
            await self._run_actions(
                job_id,
                [BusinessAction(upload_job_scripts=UploadJobScriptsAction(script_specs=script_specs))],
            )
            logger.info("Uploaded %d scripts to job %s", len(script_specs), job_id)

    # ─────────────────────────────────────────────────────────────────────
    # Job Actions
    # ─────────────────────────────────────────────────────────────────────

    async def start_job(self, job_id: str, env_vars: dict[str, str] | None = None):
        """Start a job."""
        await self._ensure_clients()
        await self._run_actions(
            job_id,
            [BusinessAction(start_job=StartJobAction(env_vars=env_vars or {}))],
        )
        logger.info("Job %s start requested", job_id)

    async def stop_job(self, job_id: str):
        """Stop a running job."""
        await self._ensure_clients()
        await self._run_actions(
            job_id,
            [BusinessAction(stop_job=StopJobAction(
                reason=JobStatusReason.JOB_STATUS_REASON_USER_INITIATED
            ))],
        )
        logger.info("Job %s stop requested", job_id)

    async def restart_job(self, job_id: str):
        """Restart a job."""
        await self._ensure_clients()
        from colligo.pluto.proto.compute import RestartJobAction
        await self._run_actions(
            job_id,
            [BusinessAction(restart_job=RestartJobAction())],
        )
        logger.info("Job %s restart requested", job_id)

    # ─────────────────────────────────────────────────────────────────────
    # Job Queries
    # ─────────────────────────────────────────────────────────────────────

    async def get_job(self, job_id: str) -> JobInfo:
        """Get detailed info about a single job."""
        await self._ensure_clients()
        entity = await self._ecs_client.get_entity(
            entity_id=job_id,
            component_types=[
                ComponentType.JOB_STATUS_COMPONENT,
                ComponentType.JOB_RUN_COMPUTED_STATE_COMPONENT,
            ],
        )
        if not entity:
            raise ValueError(f"Job not found: {job_id}")
        return _entity_to_job_info(entity)

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Get the status of a job (simplified)."""
        info = await self.get_job(job_id)
        return {
            "job_id": info.job_id,
            "name": info.name,
            "status": info.status,
            "run_status": info.run_status,
        }

    async def list_my_jobs(self, project_id: str = DEFAULT_PROJECT_ID) -> list[JobInfo]:
        """
        List jobs in the project.

        NOTE: SearchAllEntities is not available with machine-level tokens.
        This method tries search first, falls back to getting known jobs
        from the tracked jobs file.
        """
        await self._ensure_clients()

        # First try SearchAllEntities (works with user tokens / newer SDK)
        try:
            from colligo.pluto.ecs import search_all_entities_collected
            rule = QueryRule(types=QueryTypes(types=[EntityType.ENTITY_TYPE_JOB]))
            response = await search_all_entities_collected(
                self._ecs_client,
                rule=rule,
                component_types=[
                    ComponentType.JOB_STATUS_COMPONENT,
                    ComponentType.JOB_RUN_COMPUTED_STATE_COMPONENT,
                ],
            )
            jobs = []
            for entity in response.entities:
                info = _entity_to_job_info(entity)
                if project_id and info.project_id != project_id:
                    continue
                jobs.append(info)
            return jobs
        except Exception:
            pass  # Fall through to tracked jobs

        # Fallback: get status of tracked jobs (from local tracking file)
        tracked = self._load_tracked_jobs()
        if not tracked:
            logger.warning(
                "SearchAllEntities not available with machine token, "
                "and no tracked jobs found. Create jobs first, or provide job IDs directly."
            )
            return []

        jobs = []
        for job_id in tracked:
            try:
                info = await self.get_job(job_id)
                if project_id and info.project_id != project_id:
                    continue
                jobs.append(info)
            except Exception as e:
                logger.debug("Failed to get job %s: %s", job_id, e)
        return jobs

    def _load_tracked_jobs(self) -> list[str]:
        """Load tracked job IDs from the local tracking file."""
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tracked_jobs.json")
        if not os.path.exists(path):
            return []
        with open(path, "r") as f:
            data = json.load(f)
        return list(data.get("job_ids", []))

    def _save_tracked_job(self, job_id: str):
        """Save a job ID to the local tracking file."""
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tracked_jobs.json")
        data = {"job_ids": []}
        if os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
        if job_id not in data["job_ids"]:
            data["job_ids"].append(job_id)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    async def wait_for_running(self, job_id: str, timeout: int = 600, poll_interval: int = 10) -> bool:
        """
        Wait until job reaches RUNNING status.
        Returns True if running, False on timeout.
        """
        import time
        start = time.time()
        while time.time() - start < timeout:
            info = await self.get_job(job_id)
            if info.run_status == "RUNNING":
                logger.info("Job %s is now RUNNING", job_id)
                return True
            if info.run_status in ("FAILED", "STOPPED", "SUCCEEDED"):
                logger.warning("Job %s reached terminal state: %s", job_id, info.run_status)
                return False
            logger.info(
                "Job %s status: %s / %s (waiting...)",
                job_id, info.status, info.run_status,
            )
            await asyncio.sleep(poll_interval)
        logger.warning("Timeout waiting for job %s to start", job_id)
        return False

    # ─────────────────────────────────────────────────────────────────────
    # SSH & Connectivity
    # ─────────────────────────────────────────────────────────────────────

    async def get_job_pods(self, job_id: str) -> dict[int, str]:
        """Get pod name mapping (rank -> pod_name) for a running job."""
        await self._ensure_clients()
        entity = await self._ecs_client.get_entity(
            entity_id=job_id,
            component_types=[
                ComponentType.JOB_STATUS_COMPONENT,
                ComponentType.CLUSTER_RUN_RESPONSE_COMPONENT,
                ComponentType.JOB_RUN_COMPUTED_STATE_COMPONENT,
                ComponentType.CLUSTER_RUN_REQUEST_COMPONENT,
            ],
        )
        if not entity:
            raise ValueError(f"Job not found: {job_id}")

        pluto_job = PlutoJob(entity)
        if not pluto_job.cluster_run_response or not pluto_job.cluster_run_response.ranks:
            return {}

        # Build ID -> rank mapping from request
        id_to_rank = {}
        if pluto_job.cluster_run_request:
            for req in pluto_job.cluster_run_request.ranks:
                if hasattr(req, "rank"):
                    id_to_rank[req.id] = req.rank

        # Map ranks to pod names from response
        rank_mapping = {}
        for rank in pluto_job.cluster_run_response.ranks:
            if rank.id in id_to_rank:
                pod_name = rank.dns_name_prefix if rank.dns_name_prefix else rank.deployment_name
                if pod_name:
                    rank_mapping[id_to_rank[rank.id]] = pod_name

        return rank_mapping

    async def get_job_ssh_info(self, job_id: str) -> dict[str, Any]:
        """
        Get SSH connection info for a running job.
        Returns pod names, SSH domains, and example commands.
        """
        pods = await self.get_job_pods(job_id)
        if not pods:
            return {"error": "No pods found (job may not be running)"}

        ssh_domain = "ssh.or2.colligo.dev"  # Default for prod uw2
        result = {
            "pods": pods,
            "ssh_proxy": ssh_domain,
            "ssh_commands": {},
            "service_urls": {},
        }
        for rank, pod_name in pods.items():
            result["ssh_commands"][rank] = (
                f"ssh -o ProxyCommand='openssl s_client -quiet -connect {ssh_domain}:22 "
                f"-servername {pod_name}' colligo@{pod_name}"
            )
            result["service_urls"][rank] = {
                "dns": f"https://{pod_name}-8767.or2.colligo.dev",
                "internal": f"http://{pod_name}:8767",
            }

        return result

    # ─────────────────────────────────────────────────────────────────────
    # Internal Helpers
    # ─────────────────────────────────────────────────────────────────────

    async def _run_actions(self, entity_id: str, actions: list[BusinessAction]):
        """Execute business actions on an entity."""
        contexts = [
            BusinessActionContext(entity_id=entity_id, business_action=action)
            for action in actions
        ]
        await self._ba_client.run_business_actions(contexts)


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def _read_file(path: str) -> str:
    """Read a file and return its contents."""
    with open(path, "r") as f:
        return f.read()


# Job status enum name mappings
_JOB_STATUS_NAMES = {0: "DRAFT", 1: "SCHEDULED", 2: "PAUSED"}
_JOB_RUN_STATUS_NAMES = {
    0: "NONE", 1: "PENDING", 2: "INSUFFICIENT_RESOURCES",
    3: "STARTING", 4: "RUNNING_UNSTABLE", 5: "FAILED",
    6: "RUNNING", 7: "SUCCEEDED", 8: "STOPPING", 9: "STOPPED",
}


def _entity_to_job_info(entity) -> JobInfo:
    """Convert an ECS entity to a JobInfo using the PlutoJob model."""
    from datetime import datetime, timezone

    try:
        pluto_job = PlutoJob(entity)
        status_val = pluto_job.status
        run_status_val = 0  # default
        if pluto_job.current_run is not None:
            run_status_val = pluto_job.current_run.status
        elif pluto_job.last_run is not None:
            run_status_val = pluto_job.last_run.status
    except Exception:
        # Fallback: extract from raw entity
        status_val = 0
        run_status_val = 0

    created_str = ""
    if entity.created_at and entity.created_at.seconds:
        created_str = datetime.fromtimestamp(
            entity.created_at.seconds, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S UTC")

    return JobInfo(
        job_id=entity.id,
        name=entity.data.name if hasattr(entity.data, "name") else "",
        owner=entity.data.owner if hasattr(entity.data, "owner") else "",
        project_id=entity.data.parent_id if hasattr(entity.data, "parent_id") else "",
        status=_JOB_STATUS_NAMES.get(status_val, f"UNKNOWN({status_val})"),
        run_status=_JOB_RUN_STATUS_NAMES.get(run_status_val, f"UNKNOWN({run_status_val})"),
        created_at=created_str,
        tags=list(entity.data.tags) if hasattr(entity.data, "tags") else [],
        unique_name=entity.data.unique_name if hasattr(entity.data, "unique_name") else "",
    )
