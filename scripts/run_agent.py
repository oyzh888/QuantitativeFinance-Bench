#!/usr/bin/env python3
"""
Run an Anthropic agent for a QFBench task in Novita Sandbox.

Usage:
    python3 scripts/run_agent.py <task-name>
    python3 scripts/run_agent.py <task-name> --model claude-haiku-4-5 --n 3

Output:
    jobs/<timestamp>/result.json
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from anthropic import Anthropic

# Novita SDK
os.environ.setdefault("NOVITA_API_KEY", "sk_RlPbMnAngXwHgvH6aBoQ5nWvkosTWSFVVinLMJpZ9a8")
from novita_sandbox.code_interpreter import Sandbox
from novita_sandbox.core.sandbox.filesystem.filesystem import WriteEntry


REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = REPO_ROOT / "tasks"
WORKTREES_DIR = REPO_ROOT.parent / "worktrees"
JOBS_DIR = REPO_ROOT / "jobs"

DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_TURNS = 20
DEFAULT_AGENT_TIMEOUT_S = 600
DEFAULT_COMMAND_TIMEOUT_S = 120
MAX_TOOL_OUTPUT_CHARS = 12000
ANTHROPIC_FALLBACK_KEY = (
    "sk-ant-api03-5WypbphvMx1tsVp7IO7JNdTPk5enecBgmMoffU8n6HIElaEYQARg7Ki01llsNuc2M-"
    "xx8oTH4S7ntB0eVbdavQ-n6mNLgAA"
)


def find_task_dir(task_name: str) -> Path | None:
    """Find task directory: check main repo first, then all worktrees."""
    candidate = TASKS_DIR / task_name
    if candidate.exists():
        return candidate

    if WORKTREES_DIR.exists():
        for wt in sorted(WORKTREES_DIR.iterdir()):
            candidate = wt / "tasks" / task_name
            if candidate.exists():
                return candidate

    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an Anthropic agent on a QFBench task in Novita Sandbox."
    )
    parser.add_argument("task_name", help="Task directory name under tasks/")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Anthropic model name")
    parser.add_argument("--n", type=int, default=1, help="Number of sequential runs")
    parser.add_argument(
        "--turns", type=int, default=DEFAULT_TURNS, help="Maximum agent turns"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_AGENT_TIMEOUT_S,
        help="Total agent loop timeout in seconds",
    )
    return parser.parse_args()


def build_write_entries(source_dir: Path, sandbox_root: str) -> list[WriteEntry]:
    entries: list[WriteEntry] = []
    if not source_dir.exists():
        return entries

    for path in sorted(source_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(source_dir).as_posix()
            entries.append(WriteEntry(path=f"{sandbox_root}/{rel}", data=path.read_bytes()))
    return entries


def validate_task(task_dir: Path) -> None:
    required = [
        task_dir / "instruction.md",
        task_dir / "tests" / "test.sh",
    ]
    for path in required:
        if not path.exists():
            print(f"ERROR: Missing required file: {path}")
            sys.exit(1)


def get_anthropic_client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY") or ANTHROPIC_FALLBACK_KEY
    return Anthropic(api_key=api_key)


def truncate_output(text: str, limit: int = MAX_TOOL_OUTPUT_CHARS) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]", True


def stringify_content(blocks: list[Any]) -> str:
    parts: list[str] = []
    for block in blocks:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            parts.append(block.text)
        elif block_type == "tool_use":
            parts.append(
                f"[tool_use name={block.name} id={block.id} input={json.dumps(block.input)}]"
            )
        else:
            parts.append(str(block))
    return "\n".join(parts).strip()


def run_bash_tool(
    sandbox: Sandbox,
    command: str,
    remaining_s: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    timeout_s = max(1, min(DEFAULT_COMMAND_TIMEOUT_S, int(remaining_s)))
    started = time.time()
    try:
        result = sandbox.commands.run(
            command,
            timeout=timeout_s,
            user="root",
        )
        stdout, stdout_truncated = truncate_output(result.stdout or "")
        stderr, stderr_truncated = truncate_output(result.stderr or "")
        tool_text = (
            f"exit_code: {result.exit_code}\n"
            f"stdout:\n{stdout}\n\n"
            f"stderr:\n{stderr}"
        )
        tool_payload = {
            "command": command,
            "exit_code": result.exit_code,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "duration_s": round(time.time() - started, 2),
            "timeout_s": timeout_s,
        }
        return {"type": "tool_result", "content": tool_text}, tool_payload
    except Exception as exc:
        message = f"bash_exec failed: {exc}"
        tool_payload = {
            "command": command,
            "error": str(exc),
            "duration_s": round(time.time() - started, 2),
            "timeout_s": timeout_s,
        }
        return {"type": "tool_result", "content": message, "is_error": True}, tool_payload


def agent_loop(
    client: Anthropic,
    sandbox: Sandbox,
    model: str,
    max_turns: int,
    timeout_s: int,
) -> dict[str, Any]:
    system_prompt = (
        "You are a quantitative finance programmer. Read /app/instruction.md and "
        "implement the solution. Write your solution to /app/solve.sh (bash script "
        "that runs python3 to produce outputs). You can run commands via bash. Keep "
        f"iterating until all tests pass or you've used {max_turns} turns."
    )
    tools = [
        {
            "name": "bash_exec",
            "description": "Run a bash command inside the sandbox.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute.",
                    }
                },
                "required": ["command"],
            },
        }
    ]
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                "Start by reading /app/instruction.md. Implement the task in /app. "
                "Use bash_exec whenever you need to inspect files, write files, run "
                "Python, or execute tests."
            ),
        }
    ]
    trajectory: list[dict[str, Any]] = []
    started = time.time()
    stop_reason = "max_turns"

    for turn in range(1, max_turns + 1):
        elapsed = time.time() - started
        remaining = timeout_s - elapsed
        if remaining <= 0:
            stop_reason = "timeout"
            break

        response = client.messages.create(
            model=model,
            system=system_prompt,
            max_tokens=2000,
            temperature=0,
            tools=tools,
            messages=messages,
            timeout=min(remaining + 30, timeout_s + 30),
        )

        assistant_content = []
        turn_record: dict[str, Any] = {
            "turn": turn,
            "elapsed_s": round(elapsed, 2),
            "stop_reason": response.stop_reason,
            "usage": response.usage.model_dump() if response.usage else None,
            "assistant_text": stringify_content(response.content),
            "tool_calls": [],
        }

        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block_type == "tool_use":
                assistant_content.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )

        messages.append({"role": "assistant", "content": assistant_content})
        trajectory.append(turn_record)

        tool_uses = [block for block in response.content if getattr(block, "type", None) == "tool_use"]
        if not tool_uses:
            stop_reason = response.stop_reason or "assistant_done"
            if response.stop_reason == "end_turn":
                break
            continue

        tool_results = []
        for tool_use in tool_uses:
            command = ""
            if isinstance(tool_use.input, dict):
                command = str(tool_use.input.get("command", ""))
            remaining = timeout_s - (time.time() - started)
            if not command:
                result_block = {
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": "bash_exec requires a non-empty command",
                    "is_error": True,
                }
                tool_payload = {"command": command, "error": "empty command"}
            elif remaining <= 0:
                result_block = {
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": "Agent timeout reached before executing command",
                    "is_error": True,
                }
                tool_payload = {"command": command, "error": "agent timeout"}
                stop_reason = "timeout"
            else:
                result_block, tool_payload = run_bash_tool(sandbox, command, remaining)
                result_block["tool_use_id"] = tool_use.id

            turn_record["tool_calls"].append(tool_payload)
            tool_results.append(result_block)

        messages.append({"role": "user", "content": tool_results})

        if stop_reason == "timeout":
            break

    return {
        "turns_used": len(trajectory),
        "stop_reason": stop_reason,
        "trajectory": trajectory,
        "elapsed_s": round(time.time() - started, 2),
    }


def download_artifacts(sandbox: Sandbox, target_dir: Path) -> list[str]:
    downloaded: list[str] = []
    target_dir.mkdir(exist_ok=True)
    try:
        output_files = sandbox.files.list("/app/output")
    except Exception:
        return downloaded

    for file_info in output_files:
        name = file_info.name if hasattr(file_info, "name") else str(file_info).split("/")[-1]
        sandbox_path = f"/app/output/{name}"
        try:
            content = sandbox.files.read(sandbox_path)
            (target_dir / name).write_text(content)
            downloaded.append(name)
        except Exception:
            continue
    return downloaded


def read_optional_file(sandbox: Sandbox, sandbox_path: str, local_path: Path) -> bool:
    try:
        content = sandbox.files.read(sandbox_path)
    except Exception:
        return False

    local_path.write_text(content)
    return True


def upload_task_files(sandbox: Sandbox, task_dir: Path) -> int:
    write_entries: list[WriteEntry] = []

    write_entries.extend(build_write_entries(task_dir / "environment" / "data", "/app"))
    write_entries.append(
        WriteEntry(path="/app/instruction.md", data=(task_dir / "instruction.md").read_bytes())
    )
    write_entries.extend(build_write_entries(task_dir / "tests", "/tests"))

    sandbox.files.write_files(write_entries, user="root")
    sandbox.commands.run("mkdir -p /app/output /logs/verifier /tests", user="root")
    return len(write_entries)


def verify_run(sandbox: Sandbox, run_dir: Path) -> tuple[float, dict[str, Any]]:
    verify_started = time.time()
    verify_result = sandbox.commands.run(
        "cd /app && bash /tests/test.sh",
        timeout=300,
        user="root",
    )
    (run_dir / "verifier_stdout.txt").write_text(
        f"stdout:\n{verify_result.stdout}\n\nstderr:\n{verify_result.stderr}"
    )

    reward = 0.0
    reward_error = None
    try:
        reward = float(str(sandbox.files.read("/logs/verifier/reward.txt")).strip())
    except Exception as exc:
        reward_error = str(exc)

    info = {
        "verify_exit_code": verify_result.exit_code,
        "verify_stdout": verify_result.stdout,
        "verify_stderr": verify_result.stderr,
        "verify_s": round(time.time() - verify_started, 2),
        "reward_error": reward_error,
    }
    return reward, info


def run_single(task_name: str, task_dir: Path, model: str, max_turns: int, timeout_s: int, run_index: int, total_runs: int, parent_job_dir: Path) -> dict[str, Any]:
    run_dir = parent_job_dir / f"run_{run_index:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    sandbox = Sandbox.create()

    client = get_anthropic_client()
    reward = 0.0
    verify_info: dict[str, Any] = {}
    upload_count = 0
    agent_result: dict[str, Any] = {}
    downloaded_artifacts: list[str] = []
    run_error = None

    try:
        upload_count = upload_task_files(sandbox, task_dir)
        try:
            agent_result = agent_loop(
                client=client,
                sandbox=sandbox,
                model=model,
                max_turns=max_turns,
                timeout_s=timeout_s,
            )
        except Exception as exc:
            run_error = f"agent_loop failed: {exc}"
            agent_result = {
                "turns_used": 0,
                "stop_reason": "agent_error",
                "trajectory": [],
                "elapsed_s": 0.0,
            }
        (run_dir / "trajectory.json").write_text(
            json.dumps(agent_result["trajectory"], indent=2)
        )

        reward, verify_info = verify_run(sandbox, run_dir)
        downloaded_artifacts = download_artifacts(sandbox, run_dir / "artifacts")
        read_optional_file(sandbox, "/logs/verifier/ctrf.json", run_dir / "ctrf.json")
        read_optional_file(sandbox, "/logs/verifier/reward.txt", run_dir / "reward.txt")
        read_optional_file(sandbox, "/app/output/results.json", run_dir / "agent_results.json")
    finally:
        sandbox.kill()

    total_s = round(time.time() - t0, 2)
    run_result = {
        "task": task_name,
        "reward": reward,
        "turns": agent_result.get("turns_used", 0),
        "job_id": sandbox.sandbox_id,
        "sandbox_id": sandbox.sandbox_id,
        "run_index": run_index,
        "model": model,
        "stop_reason": agent_result.get("stop_reason"),
        "agent_elapsed_s": agent_result.get("elapsed_s"),
        "total_s": total_s,
        "uploaded_files": upload_count,
        "downloaded_artifacts": downloaded_artifacts,
        "verifier_exit_code": verify_info.get("verify_exit_code"),
        "run_dir": str(run_dir),
        "error": run_error,
    }
    (run_dir / "result.json").write_text(json.dumps(run_result, indent=2))

    print(
        f"Run {run_index}/{total_runs}: reward={reward:.1f} "
        f"({run_result['turns']} turns, {total_s:.0f}s)"
    )
    return run_result


def main() -> int:
    args = parse_args()

    if args.n < 1:
        print("ERROR: --n must be >= 1")
        return 1
    if args.turns < 1:
        print("ERROR: --turns must be >= 1")
        return 1
    if args.timeout < 1:
        print("ERROR: --timeout must be >= 1")
        return 1

    task_dir = find_task_dir(args.task_name)
    if task_dir is None:
        print(f"ERROR: Task '{args.task_name}' not found in tasks/ or worktrees/")
        return 1
    validate_task(task_dir)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d__%H-%M-%S")
    job_dir = JOBS_DIR / timestamp
    job_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Agent Run: {args.task_name} ===")
    print(f"Task dir: {task_dir}")
    print(f"Job: {job_dir}")
    print(f"Model: {args.model}")

    runs = []
    for run_index in range(1, args.n + 1):
        runs.append(
            run_single(
                task_name=args.task_name,
                task_dir=task_dir,
                model=args.model,
                max_turns=args.turns,
                timeout_s=args.timeout,
                run_index=run_index,
                total_runs=args.n,
                parent_job_dir=job_dir,
            )
        )

    rewards = [run["reward"] for run in runs]
    pass_count = sum(1 for reward in rewards if reward >= 0.999999)
    pass_rate = round(pass_count / len(runs), 3)

    result = {
        "task": args.task_name,
        "agent": args.model,
        "n_runs": args.n,
        "pass_rate": pass_rate,
        "rewards": rewards,
        "runs": runs,
        "timestamp": timestamp,
        "job_dir": str(job_dir),
        "turn_limit": args.turns,
        "timeout_s": args.timeout,
    }
    result_path = job_dir / "result.json"
    result_path.write_text(json.dumps(result, indent=2))

    latest = JOBS_DIR / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(job_dir.name)

    print(f"Result: {result_path}")
    print(f"Pass rate: {pass_rate:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
