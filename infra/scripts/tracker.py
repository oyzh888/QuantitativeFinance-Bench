#!/usr/bin/env python3
"""
Finance-Bench Experiment Tracker

Manages the global experiment plan, result collection, and TRACKER.md generation.

Commands:
    init        Generate experiment plan (models × tasks × rounds)
    claim       Claim experiments for a runner
    submit      Submit results from Harbor trials directory
    refresh     Regenerate TRACKER.md from current state
    status      Show summary statistics

Data flow:
    1. `init` creates experiments.jsonl (the master plan)
    2. Runners `claim` experiments → status changes to "running"
    3. After Harbor completes, `submit` extracts results → results/*.jsonl
    4. `refresh` regenerates TRACKER.md from experiments.jsonl + results/

All state lives in experiments.jsonl (one line per experiment).
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ─── Configuration ───────────────────────────────────────────────────────────

INFRA_DIR = Path(__file__).resolve().parent.parent  # infra/
EXPERIMENTS_FILE = INFRA_DIR / "experiments.jsonl"
RESULTS_DIR = INFRA_DIR / "results"
TRACKER_MD = INFRA_DIR / "TRACKER.md"

# All 16 tasks
ALL_TASKS = [
    "american-option-fd-new",
    "barrier-garch-var",
    "bollinger-backtest-aapl",
    "cta-basel-capital",
    "fama-french-factor-model-new",
    "hull-white-swaption",
    "kelly-var-sizing",
    "mc-greek-surface-1",
    "mc-greeks-surface",
    "momentum-backtest",
    "regime-cta-vol-target",
    "regime-riskparity-cvar",
    "sentiment-factor-alpha",
    "sma-crossover-spy",
    "stochvol-implied-surface-new",
    "structured-note-risk",
]

# Default model set for experiments (subset of benchmark.py MODEL_REGISTRY)
# Format: (short_name, full_model_id, agent_type)
DEFAULT_MODELS = [
    # Claude Code agentic
    ("cc-sonnet-4", "bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0", "claude-code"),
    ("cc-opus-4", "bedrock/us.anthropic.claude-opus-4-20250514-v1:0", "claude-code"),
    ("cc-sonnet-4-6", "anthropic/claude-sonnet-4-6", "claude-code"),
    ("cc-opus-4-6", "anthropic/claude-opus-4-6", "claude-code"),
    ("cc-haiku-4-5", "anthropic/claude-haiku-4-5-20251001", "claude-code"),
    # Codex CLI agentic
    ("codex-gpt-5", "openai/gpt-5", "codex-cli"),
    ("codex-gpt-5.4", "openai/gpt-5.4", "codex-cli"),
    # Finance-Zero (single API call)
    ("fz-sonnet-4-6", "anthropic/claude-sonnet-4-6", "finance-zero"),
    ("fz-gpt-5", "openai/gpt-5", "finance-zero"),
    ("fz-gemini-2.5-pro", "gemini/gemini-2.5-pro", "finance-zero"),
    ("fz-deepseek-v3", "openrouter/deepseek/deepseek-chat-v3-0324", "finance-zero"),
    ("fz-deepseek-r1", "openrouter/deepseek/deepseek-r1", "finance-zero"),
]

DEFAULT_ROUNDS = 3

# ─── Helpers ─────────────────────────────────────────────────────────────────

def load_experiments() -> list[dict]:
    """Load all experiments from experiments.jsonl."""
    if not EXPERIMENTS_FILE.exists():
        return []
    experiments = []
    for line in EXPERIMENTS_FILE.read_text().strip().split("\n"):
        if line.strip():
            experiments.append(json.loads(line))
    return experiments


def save_experiments(experiments: list[dict]):
    """Save all experiments to experiments.jsonl."""
    with open(EXPERIMENTS_FILE, "w") as f:
        for exp in experiments:
            f.write(json.dumps(exp, ensure_ascii=False) + "\n")


def load_results() -> list[dict]:
    """Load all results from results/*.jsonl."""
    results = []
    if not RESULTS_DIR.exists():
        return results
    for path in sorted(RESULTS_DIR.glob("*.jsonl")):
        for line in path.read_text().strip().split("\n"):
            if line.strip():
                results.append(json.loads(line))
    return results


def make_experiment_id(model_short: str, task: str, round_num: int) -> str:
    """Generate deterministic experiment ID."""
    return f"{model_short}_{task}_r{round_num}"


# ─── Commands ────────────────────────────────────────────────────────────────

def cmd_init(args):
    """Generate the full experiment plan."""
    if EXPERIMENTS_FILE.exists() and not args.force:
        print(f"ERROR: {EXPERIMENTS_FILE} already exists. Use --force to overwrite.")
        sys.exit(1)

    models = DEFAULT_MODELS
    tasks = ALL_TASKS
    rounds = args.rounds or DEFAULT_ROUNDS

    experiments = []
    for model_short, model_id, agent in models:
        for task in tasks:
            for r in range(1, rounds + 1):
                exp_id = make_experiment_id(model_short, task, r)
                experiments.append({
                    "experiment_id": exp_id,
                    "model_short": model_short,
                    "model": model_id,
                    "agent": agent,
                    "task": task,
                    "round": r,
                    "status": "pending",      # pending → claimed → done / error
                    "claimed_by": None,
                    "claimed_at": None,
                    "completed_at": None,
                    "run_id": None,
                })

    save_experiments(experiments)
    total = len(experiments)
    print(f"Created {total} experiments ({len(models)} models × {len(tasks)} tasks × {rounds} rounds)")
    print(f"Written to: {EXPERIMENTS_FILE}")

    # Auto-refresh tracker
    _refresh_tracker(experiments, load_results())


def cmd_claim(args):
    """Claim a batch of experiments for a runner."""
    experiments = load_experiments()
    if not experiments:
        print("ERROR: No experiments found. Run `tracker.py init` first.")
        sys.exit(1)

    runner = args.runner
    count = args.count
    model_filter = args.model
    task_filter = args.task

    claimed = []
    for exp in experiments:
        if len(claimed) >= count:
            break
        if exp["status"] != "pending":
            continue
        if model_filter and exp["model_short"] != model_filter:
            continue
        if task_filter and exp["task"] != task_filter:
            continue

        exp["status"] = "claimed"
        exp["claimed_by"] = runner
        exp["claimed_at"] = datetime.now(timezone.utc).isoformat()
        exp["run_id"] = str(uuid.uuid4())
        claimed.append(exp)

    if not claimed:
        print("No matching pending experiments found.")
        return

    save_experiments(experiments)
    print(f"Claimed {len(claimed)} experiments for '{runner}':")
    for exp in claimed:
        print(f"  {exp['experiment_id']}")

    _refresh_tracker(experiments, load_results())


def cmd_submit(args):
    """Submit results from a Harbor trials directory or manual input."""
    experiments = load_experiments()
    exp_map = {e["experiment_id"]: e for e in experiments}

    results = []

    if args.trials_dir:
        # Auto-extract from Harbor trials directory
        trials_dir = Path(args.trials_dir)
        results = _extract_harbor_results(trials_dir, exp_map, args.runner)
    else:
        # Manual single result
        exp_id = args.experiment_id
        if exp_id not in exp_map:
            print(f"ERROR: Unknown experiment_id: {exp_id}")
            sys.exit(1)

        exp = exp_map[exp_id]
        result = {
            "schema_version": "1",
            "experiment_id": exp_id,
            "run_id": exp.get("run_id") or str(uuid.uuid4()),
            "run_by": args.runner,
            "run_machine": args.machine or "unknown",
            "run_at": datetime.now(timezone.utc).isoformat(),
            "task": exp["task"],
            "agent": exp["agent"],
            "model": exp["model"],
            "model_short": exp["model_short"],
            "round": exp["round"],
            "reward": args.reward,
            "tests_passed": args.tests_passed or 0,
            "tests_total": args.tests_total or 0,
            "pass_rate": (args.tests_passed / args.tests_total) if args.tests_total else 0,
            "cost_usd": args.cost or 0,
            "input_tokens": args.input_tokens or 0,
            "output_tokens": args.output_tokens or 0,
            "agent_time_sec": args.agent_time or 0,
            "total_time_sec": args.total_time or 0,
        }
        results.append(result)

    if not results:
        print("No results to submit.")
        return

    # Write results to JSONL file
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    runner = args.runner or "unknown"
    result_file = RESULTS_DIR / f"{timestamp}_{runner}.jsonl"

    with open(result_file, "w") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Update experiment status
    for r in results:
        exp_id = r["experiment_id"]
        if exp_id in exp_map:
            exp_map[exp_id]["status"] = "done" if r.get("reward") is not None else "error"
            exp_map[exp_id]["completed_at"] = r["run_at"]

    save_experiments(experiments)
    print(f"Submitted {len(results)} results → {result_file}")

    _refresh_tracker(experiments, load_results())


def cmd_refresh(args):
    """Regenerate TRACKER.md from current state."""
    experiments = load_experiments()
    results = load_results()
    _refresh_tracker(experiments, results)
    print(f"Refreshed {TRACKER_MD}")


def cmd_status(args):
    """Show summary statistics."""
    experiments = load_experiments()
    results = load_results()
    result_map = {}
    for r in results:
        result_map[r["experiment_id"]] = r

    total = len(experiments)
    pending = sum(1 for e in experiments if e["status"] == "pending")
    claimed = sum(1 for e in experiments if e["status"] == "claimed")
    done = sum(1 for e in experiments if e["status"] == "done")
    error = sum(1 for e in experiments if e["status"] == "error")

    print(f"=== Finance-Bench Experiment Status ===")
    print(f"Total experiments: {total}")
    print(f"  ⏳ Pending:  {pending} ({pending/total*100:.0f}%)" if total else "")
    print(f"  🏃 Running:  {claimed}")
    print(f"  ✅ Done:     {done}")
    print(f"  ❌ Error:    {error}")
    print(f"  Progress:    {done}/{total} ({done/total*100:.1f}%)" if total else "")

    if done > 0:
        done_results = [result_map[e["experiment_id"]] for e in experiments
                       if e["status"] == "done" and e["experiment_id"] in result_map]
        if done_results:
            avg_reward = sum(r["reward"] for r in done_results) / len(done_results)
            avg_pass_rate = sum(r["pass_rate"] for r in done_results) / len(done_results)
            total_cost = sum(r.get("cost_usd", 0) for r in done_results)
            print(f"\n=== Results Summary ===")
            print(f"  Avg reward:    {avg_reward:.2f}")
            print(f"  Avg pass_rate: {avg_pass_rate:.1%}")
            print(f"  Total cost:    ${total_cost:.2f}")


# ─── Harbor Result Extraction ────────────────────────────────────────────────

def _extract_harbor_results(trials_dir: Path, exp_map: dict, runner: str) -> list[dict]:
    """Extract standardized results from Harbor trial directories."""
    results = []

    for trial_dir in sorted(trials_dir.iterdir()):
        if not trial_dir.is_dir():
            continue

        result_json = trial_dir / "result.json"
        ctrf_json = trial_dir / "verifier" / "ctrf.json"

        if not result_json.exists():
            print(f"  SKIP: {trial_dir.name} (no result.json)")
            continue

        try:
            raw = json.loads(result_json.read_text())
        except json.JSONDecodeError:
            print(f"  SKIP: {trial_dir.name} (invalid JSON)")
            continue

        # Extract fields from Harbor result.json
        task_name = raw.get("task_name", "")
        agent_name = raw.get("agent_info", {}).get("name", "")
        model_info = raw.get("agent_info", {}).get("model_info", "")

        # Extract token counts
        agent_ctx = raw.get("agent_result") or {}
        input_tokens = agent_ctx.get("n_input_tokens", 0) or 0
        output_tokens = agent_ctx.get("n_output_tokens", 0) or 0
        cache_tokens = agent_ctx.get("n_cache_tokens", 0) or 0
        cost_usd = agent_ctx.get("cost_usd", 0) or 0

        # Extract rewards
        verifier = raw.get("verifier_result") or {}
        rewards = verifier.get("rewards") or {}
        reward = max(rewards.values()) if rewards else 0.0

        # Extract timing
        def get_duration(timing_key):
            t = raw.get(timing_key) or {}
            start = t.get("started_at")
            finished = t.get("finished_at")
            if start and finished:
                try:
                    s = datetime.fromisoformat(start.replace("Z", "+00:00"))
                    f = datetime.fromisoformat(finished.replace("Z", "+00:00"))
                    return (f - s).total_seconds()
                except (ValueError, TypeError):
                    pass
            return 0

        agent_time = get_duration("agent_execution")
        verifier_time = get_duration("verifier")
        total_time = get_duration("environment_setup") + get_duration("agent_setup") + agent_time + verifier_time

        # Extract test details from CTRF
        tests_passed = 0
        tests_total = 0
        failed_tests = []
        if ctrf_json.exists():
            try:
                ctrf = json.loads(ctrf_json.read_text())
                for test in ctrf.get("results", {}).get("tests", []):
                    tests_total += 1
                    if test.get("status") == "passed":
                        tests_passed += 1
                    elif test.get("status") == "failed":
                        failed_tests.append(test.get("name", "unknown"))
            except (json.JSONDecodeError, KeyError):
                pass

        # Try to match to experiment plan
        # (best effort — match by task + model + round if possible)
        matched_exp_id = None
        for exp_id, exp in exp_map.items():
            if (exp["task"] == task_name and
                exp["status"] in ("claimed", "pending") and
                model_info and model_info in exp["model"]):
                matched_exp_id = exp_id
                break

        result = {
            "schema_version": "1",
            "experiment_id": matched_exp_id or f"unplanned_{trial_dir.name}",
            "run_id": raw.get("id", str(uuid.uuid4())),
            "run_by": runner,
            "run_machine": "cloud",
            "run_at": raw.get("started_at", datetime.now(timezone.utc).isoformat()),
            "task": task_name,
            "agent": agent_name,
            "model": model_info,
            "model_short": trial_dir.name,
            "round": 1,
            "reward": reward,
            "tests_passed": tests_passed,
            "tests_total": tests_total,
            "pass_rate": tests_passed / tests_total if tests_total > 0 else 0,
            "cost_usd": cost_usd,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_tokens": cache_tokens,
            "num_turns": agent_ctx.get("metadata", {}).get("num_turns", 0),
            "agent_time_sec": round(agent_time, 1),
            "verifier_time_sec": round(verifier_time, 1),
            "total_time_sec": round(total_time, 1),
            "failed_tests": failed_tests,
            "artifacts": {
                "result_json": str(result_json.relative_to(trials_dir.parent)),
                "trajectory": str((trial_dir / "agent" / "trajectory.json").relative_to(trials_dir.parent)),
                "ctrf": str(ctrf_json.relative_to(trials_dir.parent)) if ctrf_json.exists() else None,
            },
        }
        results.append(result)
        print(f"  OK: {trial_dir.name} → reward={reward}, pass_rate={tests_passed}/{tests_total}")

    return results


# ─── TRACKER.md Generation ───────────────────────────────────────────────────

STATUS_EMOJI = {
    "pending": "⬜",
    "claimed": "🔵",
    "done": "✅",
    "error": "❌",
}

def _refresh_tracker(experiments: list[dict], results: list[dict]):
    """Regenerate TRACKER.md from experiments + results."""
    result_map = {r["experiment_id"]: r for r in results}

    # Gather unique dimensions
    models = []
    seen_models = set()
    for e in experiments:
        key = (e["model_short"], e["agent"])
        if key not in seen_models:
            seen_models.add(key)
            models.append({"short": e["model_short"], "agent": e["agent"], "model": e["model"]})

    tasks = sorted(set(e["task"] for e in experiments))
    max_round = max((e["round"] for e in experiments), default=3)

    # Build experiment lookup: (model_short, task, round) → experiment
    exp_lookup = {}
    for e in experiments:
        exp_lookup[(e["model_short"], e["task"], e["round"])] = e

    # ─── Generate MD ─────────────────────────────────────────────────────

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total = len(experiments)
    done = sum(1 for e in experiments if e["status"] == "done")
    claimed = sum(1 for e in experiments if e["status"] == "claimed")
    pending = sum(1 for e in experiments if e["status"] == "pending")
    error = sum(1 for e in experiments if e["status"] == "error")

    lines = []
    lines.append("# Finance-Bench Experiment Tracker")
    lines.append("")
    lines.append(f"> Auto-generated by `scripts/tracker.py refresh` at {now}")
    lines.append(f"> **DO NOT edit manually** — changes will be overwritten")
    lines.append("")

    # ─── Progress Bar ────────────────────────────────────────────────────
    pct = done / total * 100 if total else 0
    bar_len = 30
    filled = int(bar_len * done / total) if total else 0
    bar = "█" * filled + "░" * (bar_len - filled)
    lines.append(f"## Progress: {done}/{total} ({pct:.1f}%)")
    lines.append("")
    lines.append(f"`{bar}` {done}/{total}")
    lines.append("")
    lines.append(f"| Status | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| ⬜ Pending | {pending} |")
    lines.append(f"| 🔵 Running | {claimed} |")
    lines.append(f"| ✅ Done | {done} |")
    lines.append(f"| ❌ Error | {error} |")
    lines.append("")

    # ─── Results Summary (if any done) ───────────────────────────────────
    if done > 0:
        lines.append("## Results Summary")
        lines.append("")

        # Model × pass_rate summary table
        lines.append("### Pass Rate by Model (avg across tasks)")
        lines.append("")
        lines.append("| Model | Agent | Avg Pass Rate | Avg Reward | Avg Cost | # Done |")
        lines.append("|-------|-------|--------------|------------|----------|--------|")

        for m in models:
            m_results = [result_map[e["experiment_id"]] for e in experiments
                        if e["model_short"] == m["short"] and e["status"] == "done"
                        and e["experiment_id"] in result_map]
            if m_results:
                avg_pr = sum(r["pass_rate"] for r in m_results) / len(m_results)
                avg_rw = sum(r["reward"] for r in m_results) / len(m_results)
                avg_cost = sum(r.get("cost_usd", 0) for r in m_results) / len(m_results)
                lines.append(f"| {m['short']} | {m['agent']} | {avg_pr:.1%} | {avg_rw:.2f} | ${avg_cost:.2f} | {len(m_results)} |")

        lines.append("")

    # ─── Master Grid: Model × Task ──────────────────────────────────────
    lines.append("## Experiment Grid")
    lines.append("")
    lines.append("Each cell shows status for rounds 1-3. Click experiment ID for details.")
    lines.append("")
    lines.append("Legend: ⬜ pending · 🔵 running · ✅ done (pass_rate) · ❌ error")
    lines.append("")

    # One table per model (wide table with all tasks would be unreadable)
    for m in models:
        lines.append(f"### {m['short']} (`{m['agent']}`)")
        lines.append("")

        # Header
        header = "| Task |"
        separator = "|------|"
        for r in range(1, max_round + 1):
            header += f" R{r} |"
            separator += "------|"
        lines.append(header)
        lines.append(separator)

        for task in tasks:
            # Short task name for readability
            task_short = task[:30]
            row = f"| `{task_short}` |"

            for r in range(1, max_round + 1):
                key = (m["short"], task, r)
                exp = exp_lookup.get(key)
                if not exp:
                    row += " - |"
                    continue

                status = exp["status"]
                emoji = STATUS_EMOJI.get(status, "?")

                if status == "done" and exp["experiment_id"] in result_map:
                    res = result_map[exp["experiment_id"]]
                    pr = res.get("pass_rate", 0)
                    rw = res.get("reward", 0)
                    icon = "✅" if rw == 1 else "🟡"  # 🟡 = partial (pass_rate > 0 but reward=0)
                    if pr == 0:
                        icon = "❌"
                    row += f" {icon} {pr:.0%} |"
                elif status == "claimed":
                    runner = exp.get("claimed_by", "?")
                    row += f" 🔵 {runner} |"
                elif status == "error":
                    row += f" ❌ err |"
                else:
                    row += f" {emoji} |"

            lines.append(row)

        lines.append("")

    # ─── Claimed experiments detail ──────────────────────────────────────
    claimed_exps = [e for e in experiments if e["status"] == "claimed"]
    if claimed_exps:
        lines.append("## Currently Running")
        lines.append("")
        lines.append("| Experiment ID | Runner | Claimed At |")
        lines.append("|--------------|--------|------------|")
        for e in claimed_exps:
            lines.append(f"| `{e['experiment_id']}` | {e['claimed_by']} | {e.get('claimed_at', '-')[:19]} |")
        lines.append("")

    # ─── How to contribute ───────────────────────────────────────────────
    lines.append("## How to Contribute")
    lines.append("")
    lines.append("```bash")
    lines.append("# 1. Claim experiments")
    lines.append("python3 infra/scripts/tracker.py claim --runner <your-name> --count 16 --model cc-sonnet-4")
    lines.append("")
    lines.append("# 2. Run Harbor benchmarks (claimed experiments)")
    lines.append("# ... (see infra/README.md for setup)")
    lines.append("")
    lines.append("# 3. Submit results")
    lines.append("python3 infra/scripts/tracker.py submit --runner <your-name> --trials-dir /path/to/trials/")
    lines.append("")
    lines.append("# 4. Push updated tracker")
    lines.append("git add infra/ && git commit -m 'results: <your-name> <model> batch' && git push")
    lines.append("```")
    lines.append("")

    # ─── Footer ──────────────────────────────────────────────────────────
    lines.append("---")
    lines.append(f"*Generated: {now} | Schema: fb-result-v1 | {len(models)} models × {len(tasks)} tasks × {max_round} rounds = {total} experiments*")

    TRACKER_MD.write_text("\n".join(lines) + "\n")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Finance-Bench Experiment Tracker")
    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="Generate experiment plan")
    p_init.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS, help="Rounds per experiment")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing plan")

    # claim
    p_claim = sub.add_parser("claim", help="Claim experiments")
    p_claim.add_argument("--runner", required=True, help="Your name/identifier")
    p_claim.add_argument("--count", type=int, default=16, help="Number to claim")
    p_claim.add_argument("--model", help="Filter by model_short")
    p_claim.add_argument("--task", help="Filter by task name")

    # submit
    p_submit = sub.add_parser("submit", help="Submit results")
    p_submit.add_argument("--runner", required=True, help="Your name/identifier")
    p_submit.add_argument("--trials-dir", help="Harbor trials directory to extract from")
    p_submit.add_argument("--experiment-id", help="Manual: experiment ID")
    p_submit.add_argument("--machine", help="Machine identifier")
    p_submit.add_argument("--reward", type=float, help="Manual: reward (0 or 1)")
    p_submit.add_argument("--tests-passed", type=int)
    p_submit.add_argument("--tests-total", type=int)
    p_submit.add_argument("--cost", type=float)
    p_submit.add_argument("--input-tokens", type=int)
    p_submit.add_argument("--output-tokens", type=int)
    p_submit.add_argument("--agent-time", type=float)
    p_submit.add_argument("--total-time", type=float)

    # refresh
    sub.add_parser("refresh", help="Regenerate TRACKER.md")

    # status
    sub.add_parser("status", help="Show summary")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    {"init": cmd_init, "claim": cmd_claim, "submit": cmd_submit,
     "refresh": cmd_refresh, "status": cmd_status}[args.command](args)


if __name__ == "__main__":
    main()
