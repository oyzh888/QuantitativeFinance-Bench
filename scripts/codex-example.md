# Codex 使用示例 — 如何给 context 让它开发 task

## 目录结构

Codex 工作在 worktree 里，它能看到完整的 repo 结构：

```
~/workspace-cto/worktrees/kalman-pairs-trading/
├── DEVPLAN.md                    ← Codex 读这个了解项目规范
├── docs/
│   └── task-design/
│       └── AGENT_CONTEXT.md      ← 通用 task 设计指南
├── tasks/
│   ├── bollinger-backtest-aapl/  ← 已完成的 task（参考范例）
│   │   ├── instruction.md
│   │   ├── solution/solve.sh
│   │   └── tests/test_outputs.py
│   └── kalman-pairs-trading/     ← Codex 要开发的 task
│       ├── instruction.md        ← 待优化
│       ├── solution/solve.sh     ← 待更新
│       └── tests/test_outputs.py ← 待更新
└── scripts/
    └── run_oracle.py             ← 验证工具
```

## 启动 Codex 的命令

```bash
# 方式 1：OpenClaw spawn（推荐）
# 在 Telegram 里告诉 CTO agent：
"用 codex 在 worktree/kalman-pairs-trading 里做 v3 instruction"

# CTO agent 会执行：
sessions_spawn(
  runtime="acp",
  agentId="codex",
  cwd="/home/node/.openclaw/workspace-cto/worktrees/kalman-pairs-trading",
  task=<下面的 prompt>,
  mode="run"
)

# 方式 2：SSH 到服务器手动跑
cd /home/node/.openclaw/workspace-cto/worktrees/kalman-pairs-trading
export IS_SANDBOX=1
codex --dangerously-skip-permissions "$(cat /tmp/codex-prompt.txt)"
```

## Codex Prompt 示例

### 示例 1: 收紧 instruction（kalman v3）

```
你在 QFBench 项目的 worktree 里。这是一个量化金融 AI benchmark。

目标：优化 tasks/kalman-pairs-trading/ 让 haiku 模型解不出来。

当前问题：
- v1 和 v2 instruction 都太详细，haiku 每次都 reward=1.0
- instruction.md 给了完整的 Kalman 公式和初始化参数，haiku 直接翻译成代码

你要做的：
1. 读 DEVPLAN.md 了解项目规范（特别是 instruction 写作原则）
2. 读当前 tasks/kalman-pairs-trading/instruction.md 理解 v2
3. 读 tasks/kalman-pairs-trading/solution/solve.sh 理解 oracle
4. 参考 tasks/bollinger-backtest-aapl/ 看一个好的 task 长什么样

改动要求：
- 删除 delta=1e-4 这个参数。改为让 agent 自己通过 MLE 找最优 delta ∈ [1e-6, 1e-2]
- 保留 state-space 模型的数学描述（不给代码）
- 更新 solve.sh：加入 MLE 优化 delta 的逻辑
- 更新 test_outputs.py：验证 beta 精度（oracle 的 delta 是通过 MLE 找到的最优值）
- 保留 transaction cost 逻辑（DI-02）

完成后 git add + commit。

不要跑 oracle 验证——那由我来做（用 Novita sandbox）。
```

### 示例 2: 从零创建新 task（merton-credit-model）

```
你在 QFBench 项目的 worktree 里。这是一个量化金融 AI benchmark。

目标：创建新 task "merton-credit-model"

参考：
- DEVPLAN.md 了解项目规范和 task 结构
- tasks/bollinger-backtest-aapl/ 看完整 task 范例
- docs/task-design/AGENT_CONTEXT.md 看 task 设计指南

Task 设计：
- 领域：Credit Risk
- 方法：Merton structural model
- 输入：10 家公司的股价时间序列 + 资产负债表数据（total debt, equity）
- 任务：用 Merton 模型计算每家公司的 Distance-to-Default (DD) 和 PD
- 难度：medium-hard（需要理解 Merton 模型 + Newton-Raphson 求解 asset value）

你需要创建：
1. tasks/merton-credit-model/task.toml
2. tasks/merton-credit-model/instruction.md（遵循 DEVPLAN 写作规范）
3. tasks/merton-credit-model/environment/data/ — 生成合成数据
4. tasks/merton-credit-model/solution/solve.sh — oracle 参考实现
5. tasks/merton-credit-model/tests/test.sh + test_outputs.py

instruction.md 规范：描述 Merton 模型的数学公式，但不给实现代码。
让 agent 自己知道怎么用 Newton-Raphson 从 equity 反推 asset value。

完成后 git add + commit。
```

## 关键：Codex 能看到什么

Codex 启动后，它的 cwd 就是 worktree 根目录。它可以：
- `cat DEVPLAN.md` — 读项目规范
- `ls tasks/` — 看所有 task
- `cat tasks/bollinger-backtest-aapl/instruction.md` — 看范例
- 编辑 `tasks/<target>/` 下的文件
- `git add && git commit` — 提交

它**不需要也不应该**做的：
- 跑 oracle（那是 run_oracle.py 通过 Novita sandbox 做的）
- SSH 到任何服务器
- 安装任何包
