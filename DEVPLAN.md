# QFBench Development Plan

> **蓝图文档** — 所有开发遵循此文档。修改此文档需要 review。

---

## 1. 架构：完全本地开发 + Novita Sandbox 执行

```
┌─────────────────────────────────────────────────────┐
│  OpenClaw workspace (本机)                           │
│  /home/node/.openclaw/workspace-cto/                │
│  └── QuantitativeFinance-Bench/                     │  ← 主 repo (main)
│      ├── DEVPLAN.md               ← 本文档          │
│      ├── scripts/                                   │
│      │   ├── run_oracle.py        ← Novita oracle   │
│      │   ├── run_agent.py         ← Novita agent    │
│      │   └── calibrate.py         ← 批量校准        │
│      ├── tasks/<task-name>/       ← 所有 task 文件   │
│      ├── .agent-tracking/         ← 校准追踪        │
│      │   ├── PROGRESS.md                            │
│      │   └── calibration_results.json               │
│      └── jobs/                    ← 本地 job 结果    │
│                                                     │
│  开发用 worktree:                                    │
│  └── worktrees/<task-name>/       ← git worktree    │
│      └── tasks/<task-name>/       ← 只改这个 task    │
│                                                     │
│  ↓ Novita API ↓                                     │
│  ┌─────────────┐  ┌─────────────┐                   │
│  │ Sandbox 1   │  │ Sandbox 2   │  ...              │
│  │ upload data  │  │ upload data  │                   │
│  │ run solve.sh│  │ run agent   │                   │
│  │ run tests   │  │ run tests   │                   │
│  │ → reward    │  │ → reward    │                   │
│  └─────────────┘  └─────────────┘                   │
└─────────────────────────────────────────────────────┘
```

**关键原则：**
- ❌ 不再 SSH 到 DO droplet 手动操作
- ❌ 不再用 harbor CLI（它需要本地 Docker）
- ✅ 所有代码在 workspace 里，Git 管理
- ✅ 执行用 Novita Sandbox API，本地 Python 脚本驱动
- ✅ Codex/Claude Code 在 worktree 里做开发

---

## 2. 目录结构（唯一权威版）

```
/home/node/.openclaw/workspace-cto/QuantitativeFinance-Bench/
├── DEVPLAN.md                          ← 本文档（蓝图）
├── tasks/                              ← 所有 task 的 source of truth
│   └── <task-name>/
│       ├── task.toml                   ← metadata
│       ├── instruction.md              ← agent 看到的任务描述
│       ├── environment/
│       │   ├── Dockerfile              ← 保留（兼容 harbor 的也可以跑）
│       │   └── data/                   ← 输入数据文件
│       ├── solution/
│       │   └── solve.sh                ← oracle solution
│       └── tests/
│           ├── test.sh                 ← test runner
│           └── test_outputs.py         ← pytest 测试
├── scripts/                            ← 执行脚本（Novita SDK）
│   ├── run_oracle.py                   ← 在 Novita sandbox 跑 oracle
│   ├── run_agent.py                    ← 在 Novita sandbox 跑 LLM agent
│   └── calibrate.py                    ← 批量校准（oracle + haiku + sonnet）
├── .agent-tracking/                    ← 校准追踪
│   ├── PROGRESS.md                     ← 人可读进度
│   └── calibration_results.json        ← 机器可读结果
├── jobs/                               ← 本地 job 结果
│   └── <timestamp>/
│       ├── result.json
│       └── logs/
├── docs/                               ← 设计文档
└── agents/                             ← agent 定义
```

**Worktree 位置：**
```
/home/node/.openclaw/workspace-cto/worktrees/<task-name>/
```
（在 workspace 下面，不再用 `/home/claude-runner/`）

---

## 3. 执行脚本设计

### `scripts/run_oracle.py`

```
用法: python3 scripts/run_oracle.py <task-name>
功能: 创建 Novita sandbox → 上传 data + solve.sh + tests → 跑 solve → 跑 verifier → 读 reward
输出: jobs/<timestamp>/result.json
```

### `scripts/run_agent.py`

```
用法: python3 scripts/run_agent.py <task-name> --model claude-haiku-4-5 [--n 3]
功能: 创建 sandbox → 上传 data + instruction + tests → LLM agent loop → 跑 verifier → 读 reward
输出: jobs/<timestamp>/result.json + trajectory
```

### `scripts/calibrate.py`

```
用法: python3 scripts/calibrate.py <task-name>
功能: 自动执行完整校准流程 (oracle → haiku×3 → sonnet×3)
输出: 更新 .agent-tracking/calibration_results.json
```

---

## 4. Branch & Worktree 规范

```bash
# 创建新 task 的开发环境
cd /home/node/.openclaw/workspace-cto/QuantitativeFinance-Bench
git branch dev/<task-name>
git worktree add ../worktrees/<task-name> dev/<task-name>

# 在 worktree 里开发
cd ../worktrees/<task-name>/tasks/<task-name>/
# ... 编辑 instruction.md, solve.sh, tests, etc.

# 测试：回主 repo 目录跑 oracle
cd /home/node/.openclaw/workspace-cto/QuantitativeFinance-Bench
python3 scripts/run_oracle.py <task-name>

# 完成后合并
cd ../worktrees/<task-name>
git add tasks/<task-name>/
git commit -m "feat: <task-name> — oracle ✅, haiku X%, sonnet Y%"
git push origin dev/<task-name>
```

---

## 5. Task 开发流程

### Phase 0: 研究
- 用 Codex 做 deep research（在 worktree 里）
- 输出：`docs/task-design/<task-name>-research.md`

### Phase 1: 设计 + Oracle
1. 写 instruction.md（**原则：只写 WHAT，不写 HOW**）
2. 写 solve.sh（oracle 参考实现）
3. 写 test_outputs.py（pytest 验证）
4. 生成 environment/data/
5. 跑 oracle：`python3 scripts/run_oracle.py <task-name>`
6. **目标：reward = 1.000**

### Phase 2: 难度校准
1. 跑 haiku × 3：`python3 scripts/run_agent.py <task-name> --model claude-haiku-4-5 --n 3`
2. **目标：haiku pass_rate ≤ 20%**
3. 如果 haiku 太容易 → 收紧 instruction（去掉更多提示），goto Phase 1.5
4. 跑 sonnet × 3：`python3 scripts/run_agent.py <task-name> --model claude-sonnet-4-5 --n 3`
5. **目标：sonnet pass_rate 30–60%**

### Phase 3: 合并
1. Commit + push + PR
2. 更新 `.agent-tracking/PROGRESS.md`

---

## 6. instruction.md 写作规范

| ✅ 应该有 | ❌ 不应该有 |
|-----------|------------|
| 数学公式（LaTeX 或 text） | Python/伪代码 |
| 初始化参数值（必要时） | 逐步算法描述 |
| 输入输出格式要求 | 提示"用 numpy 的 xxx" |
| 数值容差说明 | step-by-step 伪代码 |
| 领域术语（agent 应该知道的） | 实现细节暗示 |

**黄金法则：** 如果 haiku 读了 instruction 就能复制粘贴出正确答案，你的 instruction 太详细了。

---

## 7. Novita Sandbox 配置

- **SDK**: `novita-sandbox` 1.0.5 (已安装)
- **API Key**: `NOVITA_API_KEY` 环境变量
- **Base sandbox**: Python 3.12, numpy 1.26, pandas 2.2 (预装)
- **Gotchas**: 系统路径操作需 `user="root"`；文件上传用 `WriteEntry`

---

## 8. 当前状态

| Task | Oracle | Haiku | Sonnet | 状态 |
|------|--------|-------|--------|------|
| kalman-pairs-trading | ✅ v2 1.000 | ❌ v1:100%, v2:100% | — | 需要 v3（instruction 仍太详细） |
| 其余 16 个 task | 未在 Novita 测试 | — | — | 待迁移 |

### kalman v3 方向
v1/v2 都太容易因为 instruction 给了完整的 Kalman 数学公式 + 初始化参数。
**v3**: 不给 delta 值，要求 agent 用 MLE 估计最优 delta ∈ [1e-6, 1e-2]。

---

## 9. 待开发 Task Pipeline

| 优先级 | Task | 类别 | 难度目标 |
|--------|------|------|----------|
| P0 | kalman-pairs-trading v3 | stat-arb | hard |
| P1 | merton-credit-model | credit-risk | medium-hard |
| P2 | yield-curve-bootstrap | fixed-income | medium |
| P3 | execution-impact-model | microstructure | hard |

---

## 10. 监工方式

不再 SSH。直接在本地：

```bash
# 看当前 task 状态
cat .agent-tracking/PROGRESS.md

# 跑 oracle 测试
python3 scripts/run_oracle.py kalman-pairs-trading

# 跑 haiku 校准
python3 scripts/run_agent.py kalman-pairs-trading --model claude-haiku-4-5 --n 3

# 看 job 结果
cat jobs/latest/result.json
```

---

*最后更新：2026-03-22 by CTO agent*
