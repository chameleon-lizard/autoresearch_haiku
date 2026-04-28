# Haiku Autoresearch Loop — Operations Runbook

## Overview

Haiku is a task-agnostic autoresearch loop that autonomously optimizes artifacts (prompts, configs, etc.) using an LLM-driven iterative refinement process. This runbook enables an AI agent (or human operator) to deploy, run, monitor, diagnose, and recover the system.

---

## 1. Deployment Instructions

### 1.1 Prerequisites

- Python 3.10+
- pip or poetry for dependency management
- Access to LLM APIs (Anthropic Claude, or configurable scorer/refiner endpoints)
- Labelled dataset (~1000+ examples recommended)

### 1.2 From Scratch

```bash
# Clone / navigate to repository
cd /path/to/haiku

# Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# OR: venv\Scripts\activate  (Windows)

# Install dependencies
pip install -r requirements.txt

# Verify installation
python -m autoresearch.main --help

# Create state directory (if using custom location)
export AUTORESEARCH_STATE_DIR=/tmp/haiku_run_1
mkdir -p $AUTORESEARCH_STATE_DIR

# Prepare dataset
# Place your labelled dataset in a known location (e.g., data/dataset.jsonl)
# See section 2.2 for dataset format

# Configure paths.py
# Edit autoresearch/paths.py:
#   - DATASET_PATH: path to your labelled data
#   - REFINER_MODEL: your LLM (default: claude-3-5-sonnet-20241022)
#   - SCORER_MODEL: your scorer (default: same)
#   - BATCH_SIZE: K (default: 3)
#   - TRAIN_RATIO, DEV_RATIO, TEST_RATIO: split percentages

# Smoke test with small dataset
python -m autoresearch.main run --limit 20 --max-iters 1

# Check output
ls -la $AUTORESEARCH_STATE_DIR/
cat $AUTORESEARCH_STATE_DIR/experiments.jsonl
cat $AUTORESEARCH_STATE_DIR/experiments_report.md

# If smoke test passes, ready for production run
```

### 1.3 Configuration (paths.py)

All configuration is centralized in `autoresearch/paths.py`. Key settings:

```python
# Core paths
STATE_DIR = Path(os.environ.get("AUTORESEARCH_STATE_DIR", "state"))
DATASET_PATH = Path("data/dataset.jsonl")  # Required: labelled examples

# Refiner LLM (generates proposals)
REFINER_MODEL = "claude-3-5-sonnet-20241022"
REFINER_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
REFINER_TEMPERATURE_SCHEDULE = [0.0, 0.4, 0.7, 0.9]  # For retries
REFINER_MAX_RETRIES = 4

# Scorer LLM (evaluates artifacts)
SCORER_MODEL = "claude-3-5-sonnet-20241022"
SCORER_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Dataset splits
TRAIN_RATIO = 0.4
DEV_RATIO = 0.2
TEST_RATIO = 0.4
SPLIT_SEED = 42

# Batch mode
BATCH_SIZE = 3  # K candidates per batch

# Parallelism
MAX_PARALLEL_SCORES = 15  # K × 3 splits

# Observability
LOG_LEVEL = "INFO"
DUMP_PER_ATTEMPT_TRACES = True
```

### 1.4 Environment Variables

```bash
# Essential
export AUTORESEARCH_STATE_DIR=/path/to/state/dir
export ANTHROPIC_API_KEY=sk-ant-...

# Optional
export LOG_LEVEL=DEBUG                           # Default: INFO
export REFINER_MODEL=claude-3-5-sonnet-20241022  # Override in code
export SCORER_MODEL=claude-3-5-sonnet-20241022
```

---

## 2. Input Data Format

### 2.1 Dataset Structure

The loop expects labelled examples in JSONL format (`data/dataset.jsonl`):

```json
{"id": "ex_001", "text": "...", "label": "A", "domain": "science"}
{"id": "ex_002", "text": "...", "label": "B", "domain": "science"}
{"id": "ex_003", "text": "...", "label": "C", "domain": "law"}
...
```

**Required fields:**
- `id`: unique example identifier
- `text`: input text to be classified/scored
- `label`: ground-truth label (numeric or string)

**Optional:**
- `domain`: for stratified splitting (if present, split respects domain proportions)
- Any other fields: passed through to scorer

### 2.2 Initial Artifact

The loop needs a starting artifact (prompt, config, weights, etc.). Place it in `state/initial_artifact.txt`:

```
You are a classifier. Classify the following text:

Text: {input}

Respond with a single letter: A, B, or C.
```

Or programmatically set `paths.INITIAL_ARTIFACT_TEXT` in paths.py.

---

## 3. Health Checks

### 3.1 System Running?

```bash
# Check if loop is running
ps aux | grep "python.*autoresearch.main run"

# Check state directory exists and has data
ls -la $AUTORESEARCH_STATE_DIR/
test -f $AUTORESEARCH_STATE_DIR/experiments.jsonl && echo "Log exists" || echo "No log"

# Verify recent activity
tail -1 $AUTORESEARCH_STATE_DIR/experiments.jsonl | jq .ts
```

### 3.2 Is Scoring Working?

```bash
# Check cache has entries
ls $AUTORESEARCH_STATE_DIR/cache/ | wc -l

# Check one cache entry
ls -la $AUTORESEARCH_STATE_DIR/cache/*/
cat $AUTORESEARCH_STATE_DIR/cache/abc123def456.../metrics_dev.jsonl

# If no cache entries or metrics missing: scorer is failing
```

### 3.3 Is Report Updating?

```bash
# Check report exists
test -f $AUTORESEARCH_STATE_DIR/experiments_report.md && echo "Report OK"

# Check report timestamp vs log
stat $AUTORESEARCH_STATE_DIR/experiments_report.md
stat $AUTORESEARCH_STATE_DIR/experiments.jsonl

# Report should be more recent than log (regenerated after each batch)
```

### 3.4 Is Refiner LLM Responding?

```bash
# Check latest batch directory
ls -ltr $AUTORESEARCH_STATE_DIR/batches/ | tail -5

# Check for parse failures
ls $AUTORESEARCH_STATE_DIR/batches/*/stage_b_attempt_*.txt

# If many attempts exist: refiner output is malformed
cat $AUTORESEARCH_STATE_DIR/batches/batch_*/stage_b_attempt_1.txt | head -100
```

### 3.5 Full Health Check Script

```bash
#!/bin/bash
STATE_DIR=${AUTORESEARCH_STATE_DIR:-state}

echo "=== Haiku Health Check ==="
echo "State dir: $STATE_DIR"

# Check process
if ps aux | grep -q "[p]ython.*autoresearch.main run"; then
    echo "✓ Loop process running"
else
    echo "✗ Loop process NOT running"
fi

# Check log
if [ -f "$STATE_DIR/experiments.jsonl" ]; then
    lines=$(wc -l < "$STATE_DIR/experiments.jsonl")
    echo "✓ Log exists: $lines iterations"
    tail -1 "$STATE_DIR/experiments.jsonl" | jq '.ts, .metrics_dev.kappa' 2>/dev/null || echo "  (last line unreadable)"
else
    echo "✗ Log NOT found"
fi

# Check cache
if [ -d "$STATE_DIR/cache" ]; then
    cache_entries=$(ls -d "$STATE_DIR/cache"/*/ 2>/dev/null | wc -l)
    echo "✓ Cache: $cache_entries entries"
else
    echo "✗ Cache directory missing"
fi

# Check report
if [ -f "$STATE_DIR/experiments_report.md" ]; then
    echo "✓ Report exists"
else
    echo "✗ Report NOT found"
fi

echo "=== End Check ==="
```

---

## 4. Logs

### 4.1 Log Locations

```
state/
├── experiments.jsonl          # Main append-only log (machine-readable)
├── experiments_report.md      # Human-readable report (auto-generated)
├── notes.md                   # Bi-directional notebook
│
└── batches/
    ├── batch_00001/
    │   ├── stdout.log         # Subprocess output (if captured)
    │   ├── stage_c_decision.json
    │   ├── stage_b_attempt_1.txt
    │   ├── stage_b_attempt_2.txt
    │   └── ...
```

### 4.2 Log Format

**experiments.jsonl** (line-delimited JSON):

```json
{"iter": 1, "ts": "2025-04-29T12:34:56Z", "batch_id": "batch_00001", "artifact_hash": "abc123...", "metrics_dev": {"kappa": 0.635}, "delta_dev_kappa": 0.018, "is_winner": true}
{"iter": 2, "ts": "2025-04-29T12:45:12Z", ...}
...
```

Each line is a complete iteration. Parse with:

```python
import json
with open("state/experiments.jsonl") as f:
    for line in f:
        record = json.loads(line)
        print(f"Iter {record['iter']}: κ={record['metrics_dev']['kappa']:.3f}")
```

### 4.3 Querying Logs

```bash
# Count iterations
wc -l state/experiments.jsonl

# Show last N iterations
tail -10 state/experiments.jsonl | jq '.iter, .metrics_dev.kappa'

# Find winners (positive delta)
jq 'select(.is_winner) | .iter' state/experiments.jsonl

# Show plan statistics
jq -s 'group_by(.plan_id) | map({plan: .[0].plan_id, count: length, wins: (map(select(.is_winner)) | length)})' state/experiments.jsonl

# Check for overfitting (dev vs test gap)
jq '.metrics_dev.kappa as $dev | .metrics_test.kappa as $test | [$dev, $test, ($dev - $test)]' state/experiments.jsonl | tail -5
```

### 4.4 Common Log Patterns & Interpretation

| Pattern | Meaning | Action |
|---------|---------|--------|
| Missing `metrics_dev` field | Scorer crashed on this artifact | Check scorer API / dataset format |
| `delta_dev_kappa` = 0 for N iterations | No improvement signal | Audit proposer meta-prompt; widen dataset |
| `metrics_dev.kappa` > `metrics_test.kappa` by >0.10 | Overfitting dev | Pause loop; retrain with wider split |
| Parse failures in `stage_b_attempt_*.txt` | LLM truncated or malformed output | Check input context budget in paths.py; compress history |
| Empty `errors_summary` | Scorer agreement on all examples | Artifact too perfect or dataset too easy; widen scope |

---

## 5. Common Failure Modes & Resolution

### 5.1 Loop Exits with "No candidate improved"

**Symptom:** Loop terminates after N iterations with message about all proposals failing.

**Root cause:** Proposer is generating invalid artifacts or metrics are stale.

**Resolution:**
```bash
# 1. Check latest batch attempts
ls -ltr state/batches/batch_*/stage_b_attempt_*.txt | tail -3
cat state/batches/batch_*/stage_b_attempt_1.txt | tail -50

# 2. Check if scorer is working
python -m autoresearch.main score state/cache/abc123def456.../artifact.txt

# 3. If scorer works, proposer meta-prompt may be wrong
# Edit stage_b.py meta-prompt (STAGE_B_SYSTEM_PROMPT)

# 4. Resume loop
python -m autoresearch.main run
```

### 5.2 "Cache is stale / metrics don't match"

**Symptom:** Scoring same artifact twice gives different metrics.

**Root cause:** Dataset changed, or cache key logic is broken.

**Resolution:**
```bash
# 1. Verify dataset hasn't changed
ls -l data/dataset.jsonl

# 2. Check cache key computation
python -c "from autoresearch.artifacts import Artifact; a = Artifact.from_file('state/cache/abc123.../artifact.txt'); print(a.content_hash)"

# 3. Verify artifact.txt actually contains the right content
diff state/cache/abc123.../artifact.txt <(jq -r .artifact_text state/experiments.jsonl | head -1)

# 4. If cache is genuinely stale: rebuild
rm -rf state/cache
python -m autoresearch.main reset --keep-cache  # This command varies
# Or manually: python -m autoresearch.main score <artifact> to refresh
```

### 5.3 "Process killed / OOM"

**Symptom:** Loop exits abruptly with no error message; system memory usage spikes.

**Root cause:** Parallel scorer spawned too many subprocesses, or dataset too large in memory.

**Resolution:**
```bash
# 1. Check system resources at crash
dmesg | grep -i "killed\|oom" | tail -20

# 2. Reduce parallelism in paths.py
MAX_PARALLEL_SCORES = 5  # was 15, now 5

# 3. Reduce batch size
BATCH_SIZE = 1  # was 3, now 1

# 4. Subsample dataset for testing
python -m autoresearch.main run --limit 100

# 5. Restart
python -m autoresearch.main run
```

### 5.4 "Ctrl+C corruption: experiments.jsonl is malformed"

**Symptom:** After Ctrl+C, log contains incomplete JSON line.

**Root cause:** Write was interrupted mid-line (should never happen with line-buffering).

**Resolution:**
```bash
# 1. Repair log: remove incomplete last line
head -n -1 state/experiments.jsonl > state/experiments.jsonl.tmp
mv state/experiments.jsonl.tmp state/experiments.jsonl

# 2. Verify repaired log
tail -5 state/experiments.jsonl | jq .  # Should be valid JSON

# 3. Regenerate report from repaired log
python -m autoresearch.main report

# 4. Resume
python -m autoresearch.main run
```

### 5.5 "LLM API rate limit exceeded"

**Symptom:** Requests fail with 429 Too Many Requests; loop stalls.

**Root cause:** Batch parallelism is too high or quota exhausted.

**Resolution:**
```bash
# 1. Temporarily reduce batch size and parallelism
# Edit paths.py:
BATCH_SIZE = 1
MAX_PARALLEL_SCORES = 3

# 2. Add exponential backoff retry (manual or via client library)
# Edit scorer.py or stage_b.py to catch rate limit and sleep

# 3. Resume (backoff should kick in)
python -m autoresearch.main run
```

### 5.6 "Selector always picks same parent / no diversity"

**Symptom:** Stage C output is always `iter=N` (same N); history shows plateaued metrics.

**Root cause:** Proposer is too conservative or selector meta-prompt is broken.

**Resolution:**
```bash
# 1. Inspect latest batches
jq '.plan_id' state/experiments.jsonl | tail -20 | sort | uniq -c

# 2. Read stage C decision log
cat state/batches/batch_*/stage_c_decision.json | jq .decision | tail -10

# 3. Review stage_c.py meta-prompt
# Add instruction: "Sometimes revisit an older branch (iter < 50) to explore alternatives"

# 4. For debugging: set stage C to random selection temporarily
# OR: manually edit next batch decision in stage_c_decision.json

# 5. Resume
python -m autoresearch.main run
```

---

## 6. Backup & Restore

### 6.1 Backing Up State

```bash
# Backup entire run
tar -czf haiku_state_backup_$(date +%s).tar.gz state/

# Backup only the experiment log (smallest, most critical)
cp state/experiments.jsonl backups/experiments_$(date +%Y%m%d_%H%M%S).jsonl

# Backup cache separately (can be large)
tar -czf cache_$(date +%s).tar.gz state/cache/

# Store report snapshot
cp state/experiments_report.md reports/report_$(date +%Y%m%d_%H%M%S).md
```

### 6.2 Restoring from Backup

```bash
# Restore full state
tar -xzf haiku_state_backup_1234567890.tar.gz

# Restore experiments log only (WARNING: overwrites)
cp backups/experiments_20250429_120000.jsonl state/experiments.jsonl

# Regenerate report from restored log
python -m autoresearch.main report

# Resume loop
python -m autoresearch.main run
```

### 6.3 Archiving a Completed Run

```bash
# Save run with timestamp
mkdir -p archive/run_20250429_completed
cp -r state/* archive/run_20250429_completed/

# Generate final summary
python -m autoresearch.main report  # Puts report in archive
cat archive/run_20250429_completed/experiments_report.md
```

---

## 7. Scaling

### 7.1 Scale Up: More Candidates Per Batch

```python
# In paths.py:
BATCH_SIZE = 5  # was 3; more proposals per outer loop
MAX_PARALLEL_SCORES = 15  # K=5 × 3 splits = 15 subprocesses
```

**Effect:** Higher throughput but more wall-clock time per batch if API limited.

### 7.2 Scale Up: Larger Dataset

```bash
# If dataset > 10k examples:
# - Increase DEV_RATIO to catch drift earlier
# - Increase TEST_RATIO to get stable final metric

# In paths.py:
TRAIN_RATIO = 0.3
DEV_RATIO = 0.3
TEST_RATIO = 0.4

# Re-split dataset
python -m autoresearch.main reset --keep-cache
```

### 7.3 Parallel Runs (Multi-Instance Support)

```bash
# Run 1: focus on dev κ
AUTORESEARCH_STATE_DIR=/tmp/run_kappa python -m autoresearch.main run &

# Run 2: focus on macro-F1 (edit stage_c.py to optimize different metric)
AUTORESEARCH_STATE_DIR=/tmp/run_f1 python -m autoresearch.main run &

# Monitor both
watch -n 5 'tail -1 /tmp/run_kappa/experiments.jsonl /tmp/run_f1/experiments.jsonl | jq .'
```

### 7.4 Scale Down: Smoke Test / Fast Iteration

```bash
# Subsample to 50 examples for quick feedback loops
python -m autoresearch.main run --limit 50 --max-iters 3

# Or in code:
# In paths.py: LIMIT_DATASET = 50

# After smoke test, full run:
python -m autoresearch.main run
```

---

## 8. Update & Rollback

### 8.1 Update Code (Backward Compatible)

```bash
# 1. Stash any local changes
git stash

# 2. Pull latest code
git pull origin main

# 3. Install updated dependencies
pip install -r requirements.txt

# 4. Verify compatibility: smoke test
python -m autoresearch.main run --limit 20 --max-iters 1

# 5. Resume with new code
python -m autoresearch.main run
```

### 8.2 Update Configuration (Backward Compatible)

```bash
# 1. Edit paths.py (e.g., change BATCH_SIZE, MODEL)
vim autoresearch/paths.py

# 2. Next run picks up new config automatically
python -m autoresearch.main run

# Note: old iterations/cache not affected; only new batches use new config
```

### 8.3 Rollback to Previous Code Version

```bash
# 1. Find a previous good commit
git log --oneline | head -20

# 2. Checkout that commit
git checkout abc123def456

# 3. Reinstall dependencies from that version
pip install -r requirements.txt

# 4. Resume with old code
python -m autoresearch.main run
```

---

## 9. Disaster Recovery

### 9.1 Complete State Loss (Disk Failure)

**Scenario:** state/ directory lost, only code + dataset remain.

**Recovery:**
```bash
# 1. Recreate state directory structure
mkdir -p state/cache state/iterations state/batches

# 2. Recreate initial log with empty run
echo '{"iter": 0, "batch_id": "init", "artifact_hash": "base", "metrics_dev": {"kappa": 0.0}}' > state/experiments.jsonl

# 3. Re-populate cache with initial artifact (recompute scores)
# This may take a while; leverage cached artifact if available

# 4. Resume (will treat as new run from batch 1)
python -m autoresearch.main run
```

### 9.2 Partial Corruption (Some Cache Entries Lost)

**Scenario:** state/cache/abc123.../metrics_dev.jsonl deleted.

**Recovery:**
```bash
# 1. Identify affected artifact
grep abc123 state/experiments.jsonl

# 2. Re-extract and re-score that artifact
artifact_hash=abc123def456
artifact_text=$(jq -r '.artifact_text' state/experiments.jsonl | head -1)
echo "$artifact_text" > state/cache/$artifact_hash/artifact.txt

# 3. Manually trigger re-score (or delete cache entry, let loop re-do it)
rm -rf state/cache/$artifact_hash/
python -m autoresearch.main score <artifact>

# 4. Regenerate report
python -m autoresearch.main report
```

### 9.3 Unreadable / Corrupted Log

**Scenario:** experiments.jsonl has mixed encodings or truncated lines.

**Recovery:**
```bash
# 1. Validate and repair JSON
python << 'EOF'
valid_lines = []
with open("state/experiments.jsonl") as f:
    for i, line in enumerate(f):
        try:
            json.loads(line)
            valid_lines.append(line)
        except json.JSONDecodeError as e:
            print(f"Line {i+1} invalid: {e}")

with open("state/experiments.jsonl", "w") as f:
    f.writelines(valid_lines)
print(f"Repaired: kept {len(valid_lines)} valid lines")
EOF

# 2. Verify repair
tail -5 state/experiments.jsonl | jq .

# 3. Regenerate report
python -m autoresearch.main report

# 4. Resume
python -m autoresearch.main run
```

---

## 10. Performance Tuning

### 10.1 Slow Scoring

**Symptom:** Each score takes >30 seconds; batch throughput ~1 artifact/min.

**Diagnosis:**
```bash
# Time one score manually
time python -m autoresearch.main score <artifact>

# Check if it's LLM latency or subprocess overhead
# If 25/30 sec is LLM: acceptable; if 10/30 sec is subprocess: fix below

# Check scorer API endpoint
# Make sure not routing through slow proxy/relay
```

**Solutions:**
- Increase batch size K: parallelism absorbs latency
- Reduce history context size: edit history/renderer.py to use more compact format
- Use faster LLM: edit SCORER_MODEL in paths.py (trade quality for speed)
- Cache more aggressively: ensure no duplicate artifacts are re-scored

### 10.2 Slow Proposals (Stage B)

**Symptom:** Proposal generation takes >2 minutes; timeout or truncation.

**Diagnosis:**
```bash
# Check actual proposal latency
tail state/batches/batch_*/stage_b_attempt_1.txt | grep -E "Prompt tokens|Completion tokens|Duration"

# Check output length
jq '.candidates | map(.artifact | length)' state/batches/batch_*/stage_b_output.json | tail -5
```

**Solutions:**
- Reduce history context: use more compact rendering in stage_b.py
- Increase input token budget: edit paths.py MAX_INPUT_TOKENS
- Split proposals across multiple calls: propose K=1 then iterate
- Use faster model: REFINER_MODEL (trade quality for speed)

### 10.3 High Memory Usage

**Symptom:** System memory grows over iterations; eventually OOM.

**Root cause:** Cache or history kept in memory; no cleanup.

**Solutions:**
```python
# In paths.py: add memory limits
MAX_CACHE_SIZE_MB = 1000  # Evict old entries if cache exceeds 1GB

# Reduce parallelism (fewer subprocesses)
MAX_PARALLEL_SCORES = 3

# Reduce batch size
BATCH_SIZE = 1

# Regularly trim old batches (keep only last 10)
find state/batches -type d -mtime +7 -delete

# Clear cache before long run
rm -rf state/cache/*  # WARNING: will re-compute all scores
```

---

## 11. Monitoring & Alerting (Optional)

### 11.1 Live Dashboard

```bash
# Watch experiment log update in real-time
watch -n 10 'tail -3 state/experiments.jsonl | jq ".iter, .metrics_dev.kappa, .is_winner"'

# Watch report update
watch -n 30 'tail -20 state/experiments_report.md'

# Watch batch progress
watch -n 5 'ls -ltr state/batches/ | tail -3'
```

### 11.2 Alerting Script

```bash
#!/bin/bash
# Send alert if dev-test gap exceeds threshold

STATE_DIR=${AUTORESEARCH_STATE_DIR:-state}
THRESHOLD=0.10

gap=$(jq -r '.metrics_dev.kappa as $d | .metrics_test.kappa as $t | ($d - $t)' "$STATE_DIR/experiments.jsonl" | tail -1)
gap_num=$(echo "$gap" | tr -d '+' | head -c 4)

if (( $(echo "$gap_num > $THRESHOLD" | bc -l) )); then
    echo "ALERT: Dev-test gap is $gap (threshold: $THRESHOLD)"
    # Trigger alert: send email, Slack, etc.
fi
```

---

## 12. Troubleshooting Checklist

- [ ] Loop running? `ps aux | grep autoresearch`
- [ ] State directory exists and writable? `ls -ld $AUTORESEARCH_STATE_DIR`
- [ ] Log file exists? `test -f $AUTORESEARCH_STATE_DIR/experiments.jsonl`
- [ ] Recent entries in log? `tail -1 $AUTORESEARCH_STATE_DIR/experiments.jsonl`
- [ ] Cache has entries? `ls -1 $AUTORESEARCH_STATE_DIR/cache/ | wc -l`
- [ ] Report updated recently? `stat $AUTORESEARCH_STATE_DIR/experiments_report.md`
- [ ] LLM API accessible? `python -c "from anthropic import Anthropic; c = Anthropic()"`
- [ ] Dataset readable? `head -1 $(grep DATASET_PATH autoresearch/paths.py | cut -d'"' -f2) | jq .`
- [ ] Initial artifact exists? `test -f state/initial_artifact.txt`
- [ ] No parse failures in last batch? `ls state/batches/batch_*/stage_b_attempt_*.txt 2>/dev/null | wc -l`

---

## Conclusion

This runbook enables autonomous operation and recovery of the Haiku autoresearch loop. Key principles:

1. **Centralized config** (paths.py) — no CLI flag scatter
2. **Append-only log** — immutable audit trail
3. **Content-hash cache** — no duplicate work
4. **Multi-instance support** — parallel runs via env var
5. **Crash-safe design** — Ctrl+C or kill-9 never corrupts state

For deeperdives, see:
- WIKI.md — architectural overview
- DesignDoc.md — design patterns & invariants
- Individual module DOCUMENTATION.md — component details
