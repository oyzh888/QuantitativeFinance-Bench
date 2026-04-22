# Finance-Bench: Multi-Agent Workspace

## What This Is
Quantitative finance benchmark: 16 tasks × multiple LLM models × 3 rounds.
Agents write code to solve finance problems (option pricing, backtesting, risk).
Results are scored by comparing output against known correct answers.

## ⚠️ Session Startup (MANDATORY — do this FIRST)

**Multiple Claude Code sessions work here simultaneously. You MUST coordinate.**

### Step 1: Read shared context
```bash
cat .collab/BULLETIN.md
```
This is the shared whiteboard. Other agents post findings, warnings, and status here.
**Read it before doing anything** — it may contain critical info that affects your work.

### Step 2: Check who else is working
```bash
source .collab/collab.sh
collab_status
```
See what other agents are doing. Avoid duplicate work.

### Step 3: Register yourself
```bash
collab_register "your-focus-area"   # e.g., "result-analysis", "deepseek-runs"
```

### Step 4: Check pending work
```bash
collab_pending                      # unclaimed experiments grouped by model
```

## Collaboration Protocol

### Before running ANY experiment → claim it
```bash
collab_claim "cc-opus-4-6_momentum-backtest_r2"   # atomic flock lock
# ... run the experiment ...
collab_release "cc-opus-4-6_momentum-backtest_r2"
```
If someone else claimed it, you'll get an error. Pick another one.

### When you discover something → share immediately
```bash
# Quick one-liner to the shared whiteboard
collab_bulletin "Gemini 2.5 Pro gets 0.0 on all finance-zero tasks — expected"

# Longer write-up on a specific topic
collab_post "api-issues" "Vertex AI rejects /v1/ prefix in URL, must use OPENAI_BASE_URL"
```

### Before making decisions → check the board
```bash
collab_read_board              # list all topics
collab_read_board "api-issues" # read specific topic
```

### When you finish a major milestone → update bulletin
```bash
collab_bulletin "DONE: all DeepSeek-V3 experiments complete, 48/48, submitting results"
```

### On exit
```bash
collab_deregister
```

## Experiment Execution Strategy (IMPORTANT — read before running anything)

The goal is to find tasks that are **hard enough to differentiate models**. Follow this priority order strictly:

### Step 0: Check Oracle Cache
Before running ANY task, check if the Oracle has already validated it.
```bash
# Check existing oracle results
ls trials/ | grep oracle
python3 infra/scripts/tracker.py status
```
**If Oracle already ran and passed → the task is valid. Do NOT re-run Oracle.**

### Step 1: Run Haiku First (cheapest, fastest)
- Use `cc-haiku-4-5-br` (claude-code agent, Bedrock Haiku)
- If Haiku **succeeds** (gets reward) → **STOP. Skip Sonnet and Opus.**
  - Task is too easy — no need to waste expensive models on it
- If Haiku **fails** → proceed to Step 2

### Step 2: Run Sonnet (only if Haiku failed)
- Use `cc-sonnet-4-5` (claude-code agent, Bedrock Sonnet)
- If Sonnet **succeeds** → record it, move on. Opus optional but not required.
- If Sonnet **fails** → proceed to Step 3

### Step 3: Run Opus (only if Sonnet also failed)
- Use `cc-opus-4-6` (claude-code agent, Bedrock Opus)
- These are the **hard tasks** that differentiate models — the most valuable data points

### Step 4: Cross-model comparison (after tiered filtering)
- Run GPT-5, Gemini, DeepSeek etc. on the interesting tasks
- finance-zero baseline for difficulty calibration

### Why This Order?
- **Cost efficiency**: Haiku is ~50x cheaper than Opus
- **Signal quality**: If Haiku solves it, the task doesn't help differentiate models
- **The interesting tasks are the ones where cheap models fail but expensive ones succeed**

### Summary: Decision Tree Per Task
```
Oracle cached? ──yes──→ Task valid, proceed
      │no
      ▼
Run Haiku ──pass──→ STOP (task too easy)
      │fail
      ▼
Run Sonnet ──pass──→ Record (medium difficulty)
      │fail
      ▼
Run Opus ──pass──→ Record (hard task, high value!)
      │fail
      ▼
Task may be broken or extremely hard — investigate
```

## Current Experiment Status (updated 2026-04-22)

### Batch 1: Original 16 Tasks (model × 16 tasks × 3 rounds = 48 per model)
| Model | Agent | Done | Status | Notes |
|-------|-------|------|--------|-------|
| cc-opus-4-6 | claude-code | 48/48 | ✅ COMPLETE | |
| cc-sonnet-4-5 | claude-code | 48/48 | ✅ COMPLETE | |
| cc-haiku-4-5-br | claude-code | 48/48 | ✅ COMPLETE | |
| fz-gemini-2.5-pro | finance-zero | 48/48 | ✅ COMPLETE | All 0.0 (expected for single-call) |
| fz-gpt-5 | finance-zero | 48/48 | ✅ COMPLETE | All 0.0 (expected for single-call) |
| codex-gpt-5.4 | codex-cli | 91/48 | ✅ COMPLETE | Avg 0.538, 79% success, +extra retry rounds R4-R9 |
| gemcli-gemini-2.5-pro | gemini-cli | 48/48 | ✅ COMPLETE | Avg 0.319, 52% success, via NODE_OPTIONS auth hack |
| gemcli-gemini-2.5-flash | gemini-cli | 48/48 | ✅ COMPLETE | Avg 0.041, 5% success |
| codex-gpt-5 | codex-cli | 0/48 | ❌ BLOCKED | Need OpenAI Platform API key |
| fz-deepseek-v3 | finance-zero | 0/48 | ❌ BLOCKED | Need OpenRouter API key |
| fz-deepseek-r1 | finance-zero | 0/48 | ❌ BLOCKED | Need OpenRouter API key |

### Leaderboard (Batch 1 only, 16 tasks)
```
#  Model                  N     Mean    >0%    =1.0%
1  codex-gpt-5.4         91    0.538   79%    26%
2  cc-opus-4-6          188    0.472   53%    41%
3  gemcli-2.5-pro        48    0.319   52%    15%
4  cc-sonnet-4-5        258    0.293   36%    24%
5  cc-haiku-4-5-br      189    0.269   35%    21%
6  gemcli-2.5-flash      58    0.041    5%     2%
```

### Known Task Issues
- **mc-greeks-surface**: Was broken (OUTPUT_DIR mismatch: instruction=/app/output, verifier=/output). Fixed verifier locally. Still 0.0 due to all-or-nothing grading + Asian option failures.
- **hull-white-swaption**: Only Opus solves it. Codex generates 20 yield curve rows instead of 8.
- **structured-note-risk**: Docker image `quantitative-finance-bench-sandbox` not available on worker.

### Batch 2: PR Tasks (140 total, Haiku-BR R1)

**Status**: 82 done | 58 all-fail (all 3 Claude models get 0)

#### Docker-Fix Rerun (15 tasks, fixed Dockerfile image names)
| Task | Haiku Result | Notes |
|------|-------------|-------|
| black-litterman-allocation | ✅ 1.0 | Easy — Haiku solves |
| option-put-call-parity-forward-audit | ✅ 1.0 | Easy — Haiku solves |
| 13f-amendment-aware-crowding | 0.0 | Tests too strict or task too hard |
| binance-btc-participation-tca | 0.0 | |
| etf-overlap-redemption-pressure | 0.0 | |
| form4-cross-sectional-sale-pressure | 0.0 | |
| lob-pc-signal | 0.0 | |
| perpetual-funding-ledger-reconciliation | 0.0 | |
| polars-api-migration | 0.0 | |
| prediction-markets-cross-venue-dislocation | 0.0 | |
| quantamental-earnings-jumpfilter-committee | 0.0 | |
| sec-10k-report-long | 0.0 | |
| futures-carry-repair | ❌ ERROR | Docker compose fails (NFS symlink issue) |
| insider-buy-clusters | ❌ ERROR | Docker compose fails (NFS symlink issue) |
| post-earnings-drift | ❌ ERROR | Docker compose fails (NFS symlink issue) |

#### Difficulty Tiers (140 PR tasks, based on Haiku/Sonnet/Opus results)
| Tier | Count | Description |
|------|-------|-------------|
| 🟢 Easy | ~50 | Haiku solves (reward > 0) — no need for stronger models |
| 🟡 Medium | ~21 | Haiku fails, Sonnet or Opus solves |
| 🔴 Hard | ~11 | Only Opus solves — high-value differentiators |
| ⚫ All-Fail | ~58 | All 3 Claude models fail — may be broken or extremely hard |

#### Remaining Issues
- **3 Docker errors**: `futures-carry-repair`, `insider-buy-clusters`, `post-earnings-drift` — Docker compose fails when task dir is NFS symlink. Need to copy task dirs locally instead of symlink.
- **2 missing test.sh**: Some PR tasks have no verifier — unfixable without task author
- **58 all-fail tasks**: Need investigation — could be task bugs, overly strict tests, or genuinely very hard problems. **Priority: sample 5-10, check if tests are reasonable.**

### Available Work Directions (Priority Order)
1. **Investigate All-Fail Tasks** — Sample 5-10 of the 58 all-fail tasks, check if tests/specs are reasonable or broken
2. **Fix 3 Remaining Docker Errors** — Copy task dirs locally instead of NFS symlink
3. **Run Sonnet/Opus on Medium/Hard Tasks** — Tiered escalation on tasks where Haiku failed but task seems valid
4. **DeepSeek Runs** — Once OpenRouter key available
5. **Dashboard/Paper** — Visualizations, leaderboard figures

## Key Architecture

### Directory Layout
```
tasks/              16 task definitions (each has spec.md + test cases)
agents/             Agent implementations
  finance_zero.py   Single LLM call baseline (non-agentic)
infra/
  experiments.jsonl  Master experiment plan (536 entries)
  scripts/           tracker.py, batch_runner.sh, auth scripts
  results/           Submitted result JSONL files
.collab/             Multi-agent coordination (locks, board, bulletin)
trials/              → symlink to /sensei-fs-3/.../trials/ (Harbor output)
```

### Running Experiments

**Agentic (claude-code agent) — upstream Harbor:**
```bash
harbor trials start -p "tasks/taskname" -a claude-code \
  -m "bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0" \
  --trial-name "fb-haiku-taskname" \
  --trials-dir "/sensei-fs-3/users/zouyang/fb-harbor/trials" \
  --ae "AWS_BEARER_TOKEN_BEDROCK=$AWS_BEARER_TOKEN_BEDROCK" \
  --ae "AWS_REGION=us-west-2" \
  --ae "CLAUDE_CODE_USE_BEDROCK=1"
```

**Non-agentic (finance-zero baseline):**
```bash
harbor run --agent-import-path "agents.finance_zero:FinanceZeroAgent" \
  -m "openai/google/gemini-2.5-pro" \
  --run-id "fb-fz-gem-taskname" tasks/taskname
```

**⚠️ CLI Note**: Local fork uses `harbor run --run-id`, upstream uses `harbor trials start --trial-name`. Check which version is installed.

### Token Setup
- Bedrock: `/sensei-fs-3/users/zouyang/.bedrock_env`
- Gemini (Vertex AI): `/sensei-fs-3/users/zouyang/.gemini_env` → save to `GEMINI_OPENAI_API_KEY`
- Azure GPT-5: `/sensei-fs-3/users/zouyang/.azure_env`
- **WARNING**: .azure_env overwrites `OPENAI_API_KEY`. Load Gemini first, save to separate var.

### Known Gotchas
1. `harbor --ae` only sets Docker env, NOT os.environ → custom agents won't see them
2. Vertex AI endpoint rejects `/v1/` prefix — use `OPENAI_BASE_URL` (not `OPENAI_API_BASE`)
3. finance-zero is NOT a built-in Harbor agent — must use `--agent-import-path`
4. Pluto DinD needs `enable_docker=True` in job config

## Results & Tracking
```bash
python3 infra/scripts/tracker.py status    # summary
python3 infra/scripts/tracker.py submit    # collect from trials/
python3 infra/scripts/tracker.py refresh   # update TRACKER.md
```
