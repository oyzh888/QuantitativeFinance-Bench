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
        model_info_raw = raw.get("agent_info", {}).get("model_info", "")
        # model_info can be a dict {"name": ..., "provider": ...} or a string
        if isinstance(model_info_raw, dict):
            model_info = model_info_raw.get("name", "")
            model_provider = model_info_raw.get("provider", "")
        else:
            model_info = str(model_info_raw)
            model_provider = ""

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

        # Parse round from trial directory name
        # e.g. fb-s4-r2-bollinger → round 2, fb-s4-bollinger → round 1
        import re as _re
        _round_match = _re.search(r'-r(\d+)-', trial_dir.name)
        trial_round = int(_round_match.group(1)) if _round_match else 1

        # Try to match to experiment plan
        # Match by task + model + round
        # Model matching: strip date-version suffix for fuzzy match
        # e.g. "claude-sonnet-4-5-20250514-v1:0" matches "claude-sonnet-4-5-20250929-v1:0"
        def _model_base(m):
            """Strip date-version suffix: claude-sonnet-4-5-20250514-v1:0 → claude-sonnet-4-5"""
            import re as _re2
            return _re2.sub(r'-\d{8}-v\d+:\d+$', '', m.split('/')[-1])

        model_base = _model_base(model_info) if model_info else ""

        matched_exp_id = None
        for exp_id, exp in exp_map.items():
            if (exp["task"] == task_name and
                exp["round"] == trial_round and
                model_info and (
                    model_info in exp["model"] or
                    exp["model"].endswith(model_info) or
                    _model_base(exp["model"]) == model_base
                )):
                # Prefer claimed/pending, but accept done too (for re-submit)
                if exp["status"] in ("claimed", "pending"):
                    matched_exp_id = exp_id
                    break
                elif matched_exp_id is None:
                    matched_exp_id = exp_id

        # Detect errors: only real infrastructure/API failures
        error_detail = ""
        exception_file = trial_dir / "exception.txt"
        if exception_file.exists():
            exc_text = exception_file.read_text().strip()
            for exc_line in reversed(exc_text.split("\n")):
                exc_line = exc_line.strip()
                if exc_line and not exc_line.startswith("File "):
                    # Only keep meaningful errors, not "stderr: None"
                    if "TimeoutError" in exc_line or "API Error" in exc_line or "invalid" in exc_line.lower():
                        error_detail = exc_line[:200]
                    break

        # Check agent log for API errors (e.g. invalid model ID)
        agent_log = trial_dir / "agent" / f"{agent_name}.txt"
        if not error_detail and agent_log.exists() and input_tokens == 0 and output_tokens == 0:
            try:
                log_text = agent_log.read_text()
                import re
                m = re.search(r'"text":"(API Error[^"]{0,200})"', log_text)
                if m:
                    error_detail = m.group(1)
                elif '"is_error":true' in log_text:
                    m = re.search(r'"result":"([^"]{0,200})"', log_text)
                    if m:
                        error_detail = m.group(1)
            except Exception:
                pass

        # Classify: true errors are infrastructure failures, not task failures
        # - API errors (invalid model, auth failure) → is_error
        # - Timeouts → is_error
        # - Zero tokens + zero reward (agent never ran) → is_error
        # - Has tokens but reward=0 → task failure, NOT an error
        is_error = bool(error_detail) or (input_tokens == 0 and output_tokens == 0 and reward == 0 and tests_total == 0)

        result = {
            "schema_version": "1",
            "experiment_id": matched_exp_id or f"unplanned_{trial_dir.name}",
            "run_id": raw.get("id", str(uuid.uuid4())),
            "run_by": runner,
            "run_machine": "cloud",
            "run_at": raw.get("started_at", datetime.now(timezone.utc).isoformat()),
            "task": task_name,
            "agent": agent_name,
            "model": f"{model_provider}/{model_info}" if model_provider else model_info,
            "model_short": trial_dir.name,
            "round": trial_round,
            "reward": reward,
            "tests_passed": tests_passed,
            "tests_total": tests_total,
            "pass_rate": tests_passed / tests_total if tests_total > 0 else 0,
            "cost_usd": cost_usd,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_tokens": cache_tokens,
            "num_turns": (agent_ctx.get("metadata") or {}).get("num_turns", 0),
            "agent_time_sec": round(agent_time, 1),
            "verifier_time_sec": round(verifier_time, 1),
            "total_time_sec": round(total_time, 1),
            "failed_tests": failed_tests,
            "error_detail": error_detail,
            "is_error": is_error,
            "trial_path": str(trial_dir),
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

    # ─── Summary: Model × Task completion matrix ────────────────────────
    from collections import defaultdict, Counter

    # Per-model summary
    model_stats = {}
    for m in models:
        m_exps = [e for e in experiments if e["model_short"] == m["short"]]
        m_done = [e for e in m_exps if e["status"] == "done" and e["experiment_id"] in result_map]
        m_run  = [e for e in m_exps if e["status"] == "claimed"]
        m_pend = [e for e in m_exps if e["status"] == "pending"]
        m_err  = [e for e in m_exps if e["status"] == "error"]
        m_results = [result_map[e["experiment_id"]] for e in m_done]
        avg_rw = sum(r["reward"] for r in m_results) / len(m_results) if m_results else 0
        avg_pr = sum(r["pass_rate"] for r in m_results) / len(m_results) if m_results else 0
        total_tok = sum(r.get("input_tokens", 0) + r.get("output_tokens", 0) for r in m_results)
        model_stats[m["short"]] = {
            "total": len(m_exps), "done": len(m_done), "run": len(m_run),
            "pend": len(m_pend), "err": len(m_err),
            "avg_rw": avg_rw, "avg_pr": avg_pr, "tokens": total_tok,
        }

    lines.append("### By Model")
    lines.append("")
    lines.append("| Model | Agent | Done | Run | Pend | Avg Reward | Avg Pass | Tokens |")
    lines.append("|-------|-------|------|-----|------|-----------|----------|--------|")
    for m in models:
        s = model_stats[m["short"]]
        if s["total"] == 0:
            continue
        done_str = f"**{s['done']}/{s['total']}**"
        rw_str = f"{s['avg_rw']:.2f}" if s["done"] else "-"
        pr_str = f"{s['avg_pr']:.0%}" if s["done"] else "-"
        tok_str = f"{s['tokens']:,}" if s["tokens"] else "-"
        lines.append(f"| {m['short']} | {m['agent']} | {done_str} | {s['run']} | {s['pend']} | {rw_str} | {pr_str} | {tok_str} |")
    lines.append("")

    # Per-task summary
    task_stats = {}
    for task in tasks:
        t_exps = [e for e in experiments if e["task"] == task]
        t_done = [e for e in t_exps if e["status"] == "done" and e["experiment_id"] in result_map]
        t_results = [result_map[e["experiment_id"]] for e in t_done]
        avg_rw = sum(r["reward"] for r in t_results) / len(t_results) if t_results else 0
        best_rw = max((r["reward"] for r in t_results), default=0)
        task_stats[task] = {
            "total": len(t_exps), "done": len(t_done),
            "remain": len(t_exps) - len(t_done),
            "avg_rw": avg_rw, "best_rw": best_rw,
        }

    lines.append("### By Task")
    lines.append("")
    lines.append("| Task | Done | Remain | Best Reward | Avg Reward |")
    lines.append("|------|------|--------|-------------|------------|")
    for task in tasks:
        s = task_stats[task]
        done_str = f"{s['done']}/{s['total']}"
        best_str = f"{s['best_rw']:.2f}" if s["done"] else "-"
        avg_str = f"{s['avg_rw']:.2f}" if s["done"] else "-"
        lines.append(f"| {task} | {done_str} | {s['remain']} | {best_str} | {avg_str} |")
    lines.append("")

    # ─── Single Flat Table: every experiment = one row ─────────────────────
    all_exps = sorted(experiments, key=lambda e: (e["task"], e["model_short"], e["round"]))

    # Assign global run_id (sequential)
    global_run_id = 0
    run_id_map = {}
    for e in sorted(experiments, key=lambda x: (x.get("completed_at") or "9999", x["experiment_id"])):
        global_run_id += 1
        run_id_map[e["experiment_id"]] = global_run_id

    lines.append("## Experiment Table")
    lines.append("")
    lines.append("| # | Task | Model | Agent | R | Status | Runner | Started | Finished | Reward | Pass | Tests | In Tok | Out Tok | Time | Trial |")
    lines.append("|---|------|-------|-------|---|--------|--------|---------|----------|--------|------|-------|--------|---------|------|-------|")

    def _fmt_ts(ts):
        """'2026-04-19T10:21:49.708323Z' → '04-19 10:21'"""
        if not ts:
            return "-"
        try:
            return ts[5:16].replace("T", " ")
        except Exception:
            return ts[:16]

    for e in all_exps:
        rid = run_id_map[e["experiment_id"]]
        task = e["task"]
        model = e["model_short"]
        agent = e["agent"]
        rnd = e["round"]
        status = e["status"]
        runner = e.get("claimed_by") or "-"
        started = _fmt_ts(e.get("claimed_at"))
        finished = _fmt_ts(e.get("completed_at"))

        if status == "done" and e["experiment_id"] in result_map:
            res = result_map[e["experiment_id"]]
            rw = res.get("reward", 0)
            pr = res.get("pass_rate", 0)
            tp = res.get("tests_passed", 0)
            tt = res.get("tests_total", 0)
            in_tok = res.get("input_tokens", 0)
            out_tok = res.get("output_tokens", 0)
            total_t = res.get("total_time_sec", 0)
            trial_p = res.get("trial_path", "")
            trial_short = trial_p.split("/trials/")[-1] if "/trials/" in trial_p else ""

            if rw >= 1.0:
                rw_str = f"✅ {rw:.2f}"
            elif rw > 0:
                rw_str = f"🟡 {rw:.2f}"
            else:
                rw_str = f"❌ {rw:.2f}"

            time_str = f"{total_t:.0f}s" if total_t else "-"
            trial_link = f"[link](./trials/{trial_short}/)" if trial_short else "-"

            lines.append(
                f"| {rid} | {task} | {model} | {agent} | {rnd} "
                f"| ✅ done | {runner} | {started} | {finished} "
                f"| {rw_str} | {pr:.0%} | {tp}/{tt} "
                f"| {in_tok:,} | {out_tok:,} | {time_str} | {trial_link} |"
            )
        elif status == "claimed":
            lines.append(
                f"| {rid} | {task} | {model} | {agent} | {rnd} "
                f"| 🔵 run | {runner} | {started} | - "
                f"| - | - | - | - | - | - | - |"
            )
        elif status == "error":
            lines.append(
                f"| {rid} | {task} | {model} | {agent} | {rnd} "
                f"| ❌ err | {runner} | {started} | {finished} "
                f"| - | - | - | - | - | - | - |"
            )
        else:
            lines.append(
                f"| {rid} | {task} | {model} | {agent} | {rnd} "
                f"| ⬜ | - | - | - "
                f"| - | - | - | - | - | - | - |"
            )

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
