# Kalman Pairs Trading — Task Design Plan

**Owner:** When2buy CTO Bot  
**Repo:** https://github.com/QF-Bench/QuantitativeFinance-Bench  
**Branch:** dev/kalman-pairs-trading  
**Created:** 2026-03-22  
**Status:** 🟡 In Progress — Phase 0 (Deep Research)

---

## 核心目标

用迭代难度攀升（Difficulty Escalation Loop）设计一个 **Hard** 级别的 pairs trading task。
不是一次设计"足够难"的题，而是从 base 出发，逐步叠加 difficulty items，直到 haiku pass rate < 40%。

---

## Difficulty Escalation Loop

```
Phase 0: Deep Research (Codex deep-dive)
  → 研究每个 difficulty item 对 LLM 的具体难点
  → 输出: .agent-tracking/difficulty_items.json

Phase 1: Base Task (v1)
  → kalman-pairs-trading v1: Kalman Filter 动态 hedge ratio
  → Oracle: reward=1.0
  → Haiku calibration → if pass_rate < 40%: DONE
  → else: escalate

Phase N: Escalation
  → 叠加下一个 difficulty item → rebuild → oracle → haiku
  → 循环直到 hard confirmed
```

---

## Difficulty Items（待 deep research 填充细节）

| ID    | Name                             | Predicted Difficulty | Status   |
|-------|----------------------------------|----------------------|----------|
| DI-01 | kalman_dynamic_hedge             | medium               | 📋 Planned |
| DI-02 | ou_halflife_entry_threshold      | medium-hard          | 📋 Planned |
| DI-03 | transaction_costs_slippage       | medium               | 📋 Planned |
| DI-04 | regime_detection_coint_break     | hard                 | 📋 Planned |
| DI-05 | multi_pair_portfolio_correlation | hard                 | 📋 Planned |

详细内容见: `.agent-tracking/difficulty_items.json`

---

## 现有 pairs trading tasks（避免重复）

| Task                     | Approach           | Difficulty |
|--------------------------|--------------------|------------|
| pairs-trading            | 静态 OLS + z-score | hard       |
| clustering-pairs-trading | 聚类选股 + coint   | hard       |
| **kalman-pairs-trading** | 动态 KF + OU + ... | **hard+**  |

---

## 工作目录结构

```
QuantitativeFinance-Bench/
├── docs/task-design/kalman-pairs-trading/
│   ├── PLAN.md                    ← 本文件 (committed)
│   ├── difficulty_items_draft.md  ← deep research 草稿 (committed)
│   └── versions/
│       ├── v1_base/               ← v1 instruction draft
│       └── v2_ou/                 ← v2 instruction draft (if needed)
│
├── tasks/kalman-pairs-trading/    ← 最终 task (committed when ready)
│
└── .agent-tracking/               ← NOT committed (tmux/codex 运行时追踪)
    ├── difficulty_items.json      ← deep research 输出
    ├── tasks.jsonl                ← code-tmux 全局任务日志
    ├── sessions/                  ← worktree + tmux session 状态
    │   ├── phase0-research.json
    │   ├── phase1-v1-base.json
    │   └── phase2-v2-ou.json
    └── calibration_results.json   ← oracle/haiku 跑分历史
```

---

## 追踪文件说明

### `.agent-tracking/tasks.jsonl`
code-tmux skill 自动写入，每行一个任务记录：
```json
{"session": "code-claude-1742601234", "task": "phase0-deep-research", "status": "running", "started_at": "2026-03-22T01:45:00Z"}
```

### `.agent-tracking/sessions/phase0-research.json`
```json
{
  "phase": 0,
  "name": "deep-research",
  "tmux_session": "code-codex-<ts>",
  "worktree": null,
  "status": "running",
  "started_at": "",
  "completed_at": null,
  "output_files": [".agent-tracking/difficulty_items.json"]
}
```

### `.agent-tracking/calibration_results.json`
```json
{
  "v1_base": {
    "oracle": {"reward": null, "runs": 0},
    "haiku": {"reward": null, "runs": 0, "pass_rate": null},
    "sonnet": {"reward": null, "runs": 0, "pass_rate": null}
  }
}
```

---

## 如何查看当前进度

```bash
# 在 repo 目录下
cd /home/node/.openclaw/workspace-cto/QuantitativeFinance-Bench

# 查看所有 agent 任务状态
~/.openclaw/skills/code-tmux/scripts/status-agents.sh --all

# 查看 tmux sessions
tmux ls

# 查看追踪文件
cat .agent-tracking/tasks.jsonl
cat .agent-tracking/calibration_results.json

# 查看某个 session 实时输出
tail -f .agent-tracking/sessions/*.json
```

---

## Current Phase

**Phase 0: Deep Research**
- [ ] Codex session 分析 DI-01 ~ DI-05 的实现陷阱
- [ ] 输出 `.agent-tracking/difficulty_items.json`
- [ ] 生成 `docs/task-design/kalman-pairs-trading/difficulty_items_draft.md`

**Next:** Phase 1 — v1 base task 生成
