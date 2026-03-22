#!/usr/bin/env python3
"""
Run oracle solution for a QFBench task in Novita Sandbox.

Usage:
    python3 scripts/run_oracle.py <task-name>
    python3 scripts/run_oracle.py kalman-pairs-trading

Output:
    jobs/<timestamp>/result.json
    jobs/<timestamp>/oracle_stdout.txt
"""
import os
import sys
import json
import time
import glob
from datetime import datetime, timezone
from pathlib import Path

# Novita SDK
os.environ.setdefault("NOVITA_API_KEY", "sk_RlPbMnAngXwHgvH6aBoQ5nWvkosTWSFVVinLMJpZ9a8")
from novita_sandbox.code_interpreter import Sandbox
from novita_sandbox.core.sandbox.filesystem.filesystem import WriteEntry

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = REPO_ROOT / "tasks"
JOBS_DIR  = REPO_ROOT / "jobs"


def run_oracle(task_name: str) -> dict:
    task_dir = TASKS_DIR / task_name
    if not task_dir.exists():
        print(f"ERROR: Task directory not found: {task_dir}")
        sys.exit(1)

    # Validate required files
    solve_sh     = task_dir / "solution" / "solve.sh"
    test_sh      = task_dir / "tests" / "test.sh"
    test_py      = task_dir / "tests" / "test_outputs.py"
    data_dir     = task_dir / "environment" / "data"

    for f in [solve_sh, test_sh, test_py]:
        if not f.exists():
            print(f"ERROR: Missing required file: {f}")
            sys.exit(1)

    # Create job directory
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d__%H-%M-%S")
    job_dir = JOBS_DIR / timestamp
    job_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Oracle Run: {task_name} ===")
    print(f"Job: {job_dir}")

    t0 = time.time()

    # 1. Create sandbox
    print("  [1/5] Creating sandbox...")
    sandbox = Sandbox.create()
    t_create = time.time() - t0
    print(f"        sandbox_id={sandbox.sandbox_id} ({t_create:.1f}s)")

    try:
        # 2. Upload files
        print("  [2/5] Uploading files...")
        t1 = time.time()

        write_entries = []

        # Upload data files
        if data_dir.exists():
            for data_file in sorted(data_dir.iterdir()):
                if data_file.is_file():
                    sandbox_path = f"/app/{data_file.name}"
                    write_entries.append(
                        WriteEntry(path=sandbox_path, data=data_file.read_bytes())
                    )
                    print(f"        → /app/{data_file.name}")

        # Upload solve.sh
        write_entries.append(
            WriteEntry(path="/app/solve.sh", data=solve_sh.read_bytes())
        )

        # Upload test files
        write_entries.append(
            WriteEntry(path="/tests/test.sh", data=test_sh.read_bytes())
        )
        write_entries.append(
            WriteEntry(path="/tests/test_outputs.py", data=test_py.read_bytes())
        )

        sandbox.files.write_files(write_entries, user="root")

        # Create required directories
        sandbox.commands.run("mkdir -p /app/output /logs/verifier", user="root")

        t_upload = time.time() - t1
        print(f"        {len(write_entries)} files uploaded ({t_upload:.1f}s)")

        # 3. Run oracle
        print("  [3/5] Running oracle (solve.sh)...")
        t2 = time.time()
        oracle_result = sandbox.commands.run(
            "cd /app && bash /app/solve.sh",
            timeout=300,
            user="root"
        )
        t_oracle = time.time() - t2
        print(f"        exit_code={oracle_result.exit_code} ({t_oracle:.1f}s)")

        # Save oracle stdout
        (job_dir / "oracle_stdout.txt").write_text(
            f"stdout:\n{oracle_result.stdout}\n\nstderr:\n{oracle_result.stderr}"
        )

        if oracle_result.exit_code != 0:
            print(f"        ⚠️ Oracle failed! stderr: {oracle_result.stderr[:500]}")

        # 4. Run verifier
        print("  [4/5] Running verifier (test.sh)...")
        t3 = time.time()
        verify_result = sandbox.commands.run(
            "cd /app && bash /tests/test.sh",
            timeout=300,
            user="root"
        )
        t_verify = time.time() - t3
        print(f"        exit_code={verify_result.exit_code} ({t_verify:.1f}s)")

        # Save verifier output
        (job_dir / "verifier_stdout.txt").write_text(
            f"stdout:\n{verify_result.stdout}\n\nstderr:\n{verify_result.stderr}"
        )

        # 5. Read reward
        print("  [5/5] Reading reward...")
        try:
            reward_txt = sandbox.files.read("/logs/verifier/reward.txt")
            reward = float(reward_txt.strip())
        except Exception as e:
            print(f"        ⚠️ Could not read reward: {e}")
            reward = 0.0

        # Also try to read results.json from the agent's output
        try:
            agent_results = sandbox.files.read("/app/output/results.json")
            (job_dir / "agent_results.json").write_text(agent_results)
        except Exception:
            pass

        # Try to read CTRF test report
        try:
            ctrf = sandbox.files.read("/logs/verifier/ctrf.json")
            (job_dir / "ctrf.json").write_text(ctrf)
            ctrf_data = json.loads(ctrf)
            tests = ctrf_data.get("results", {}).get("tests", [])
            passed = sum(1 for t in tests if t.get("status") == "passed")
            failed = sum(1 for t in tests if t.get("status") == "failed")
            print(f"        Tests: {passed} passed / {failed} failed")
        except Exception:
            pass

    finally:
        sandbox.kill()

    t_total = time.time() - t0

    # Write result
    result = {
        "task": task_name,
        "agent": "oracle",
        "reward": reward,
        "timestamp": timestamp,
        "sandbox_id": sandbox.sandbox_id,
        "timing": {
            "create_s": round(t_create, 1),
            "upload_s": round(t_upload, 1),
            "oracle_s": round(t_oracle, 1),
            "verify_s": round(t_verify, 1),
            "total_s":  round(t_total, 1),
        },
        "oracle_exit_code": oracle_result.exit_code,
        "verifier_exit_code": verify_result.exit_code,
    }

    result_path = job_dir / "result.json"
    result_path.write_text(json.dumps(result, indent=2))

    # Summary
    emoji = "✅" if reward == 1.0 else "❌"
    print(f"\n{'='*60}")
    print(f"  Task:    {task_name}")
    print(f"  Reward:  {reward} {emoji}")
    print(f"  Time:    {t_total:.1f}s")
    print(f"  Result:  {result_path}")
    print(f"{'='*60}")

    # Symlink latest
    latest = JOBS_DIR / "latest"
    if latest.is_symlink():
        latest.unlink()
    latest.symlink_to(job_dir.name)

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/run_oracle.py <task-name>")
        print(f"Available tasks: {sorted(d.name for d in TASKS_DIR.iterdir() if d.is_dir())}")
        sys.exit(1)

    task = sys.argv[1]
    result = run_oracle(task)
    sys.exit(0 if result["reward"] == 1.0 else 1)
