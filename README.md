# Haiku: Autonomous LLM-Driven Autoresearch Loop

**Haiku** is a task-agnostic, fully autonomous LLM-driven optimization loop for evolving artifacts (prompts, configs, code, etc.) against a metric using iterative refinement.

The loop runs unattended for hours, generating targeted improvements through a principled sequence of stages: diagnose failures (A), propose improvements (B), select next direction (C), and synthesise merges (M).

**Status**: ✅ Core implementation complete. Ready for integration with your scoring system and dataset.

## Quick Start

```bash
# 1. Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Configure paths.py
vim autoresearch/paths.py
# Set: DATASET_PATH, INITIAL_ARTIFACT_PATH, REFINER_MODEL, SCORER_MODEL

# 3. Prepare dataset (JSONL: id, text, label)
# Place at: data/dataset.jsonl

# 4. Prepare initial artifact
# Place at: state/initial_artifact.txt

# 5. Run
export AUTORESEARCH_STATE_DIR=state
python -m autoresearch.main run --limit 20 --max-iters 2  # Smoke test first
python -m autoresearch.main run                           # Full run
```

## Key Features

✅ **Content-hash caching**: No work repeated; re-run resumes instantly  
✅ **Append-only log**: Immutable audit trail for reproducibility  
✅ **Crash-safe**: Ctrl+C or kill-9 never corrupts state  
✅ **Stratified splits**: Detect overfitting with held-out test set  
✅ **Four stages**: Diagnose (A), propose (B), select (C), merge (M)  
✅ **Parallel scoring**: K×3 candidates scored in parallel  
✅ **Smart history**: Full/compact rendering for context windows  
✅ **Auto-report**: Live-updated experiments_report.md  
✅ **Multi-instance**: Run parallel loops with different state dirs  
✅ **Single-edit attribution**: Per-candidate plan tracking  

## Architecture

```
Batch iteration:
  Stage C: Select parent (or merge targets)
    ↓
  Stage M: If merge, synthesise new parent
    ↓
  Stage B: Generate K sibling proposals
    ↓
  Score K×3 in parallel (with caching)
    ↓
  Stage A: Diagnose errors
    ↓
  Log results (append-only)
    ↓
  Regenerate report
```

## Project Structure

```
haiku/
├── README.md                  # This file
├── DesignDoc.md              # Design patterns & reference
├── WIKI.md                   # Executive summary
├── PROGRESS.md               # Implementation status
├── OPS.md                    # Deployment runbook
│
├── autoresearch/
│   ├── paths.py              # Centralized config (EDIT THIS)
│   ├── main.py               # CLI entry point
│   └── loop.py               # Main loop orchestration
│
├── artifacts/
│   ├── artifact.py           # Artifact class with content hashing
│   └── DOCUMENTATION.md
│
├── splitter/
│   ├── splitter.py           # Stratified train/dev/test split
│   └── DOCUMENTATION.md
│
├── scorer/
│   ├── scorer.py             # Cache-aware scoring
│   └── DOCUMENTATION.md
│
├── stages/
│   ├── stage_a.py            # Diagnosis generalisation
│   ├── stage_b.py            # Proposal generation (K siblings)
│   ├── stage_c.py            # Selection logic
│   ├── stage_m.py            # Merge synthesis
│   └── DOCUMENTATION.md
│
├── history/
│   ├── renderer.py           # Smart history rendering
│   └── DOCUMENTATION.md
│
└── report/
    ├── report.py             # Auto-generate experiments_report.md
    └── DOCUMENTATION.md
```

## Documentation

Start here:
1. **DesignDoc.md** — Read first; explains design patterns & invariants
2. **WIKI.md** — Executive summary of all features
3. **OPS.md** — Deployment, troubleshooting, recovery procedures
4. **Individual module DOCUMENTATION.md** — Deep dives on each component

## Core Invariants

### 1. Cache by Content Hash
Every artifact has id: `sha256(text)[:16]`. All scoring/diagnosis keyed by hash.
- Re-run loop → cache hits → instant resumption
- No duplicate work ever

### 2. Append-Only Log
Single source of truth: `state/experiments.jsonl`
- Each line: one iteration (never rewritten)
- Enables resumability, audit trail, time-travel

### 3. Crash-Safe
Process death never corrupts state (line-buffered writes, atomic updates).
- `Ctrl+C` safe
- `kill -9` safe

### 4. Held-Out Test Set
Split: 40% train / 20% dev / 40% test
- Loop sees: train + dev metrics
- Test: logged but never surfaced (detect overfitting)

### 5. Single-Edit Attribution
Each candidate changes ONE thing (not multiple).
- Enables per-plan aggregation: "plan X: 3 proposed, 1 won, Δ=+0.002"

### 6. Bi-Directional Notebook
User can edit `state/notes.md` mid-run.
- Out-of-band channel for domain knowledge injection
- No restart needed

## CLI

```bash
# Main loop (infinite)
python -m autoresearch.main run

# Bounded run
python -m autoresearch.main run --max-iters 10

# Smoke test (subsample dataset)
python -m autoresearch.main run --limit 50 --max-iters 2

# Regenerate report from log
python -m autoresearch.main report

# Delete iterations & log (keep cache)
python -m autoresearch.main reset

# Score one artifact
python -m autoresearch.main score path/to/artifact.txt
```

## Configuration

Edit `autoresearch/paths.py`:

```python
# Paths
DATASET_PATH = Path("data/dataset.jsonl")
INITIAL_ARTIFACT_PATH = Path("state/initial_artifact.txt")

# LLM (proposer & scorer)
REFINER_MODEL = "claude-3-5-sonnet-20241022"
SCORER_MODEL = "claude-3-5-sonnet-20241022"

# Dataset split
TRAIN_RATIO = 0.4
DEV_RATIO = 0.2
TEST_RATIO = 0.4

# Batch mode
BATCH_SIZE = 3  # K candidates per iteration

# Retries (on parse failure)
REFINER_TEMPERATURE_SCHEDULE = [0.0, 0.4, 0.7, 0.9]
```

Or set env vars:

```bash
export AUTORESEARCH_STATE_DIR=/tmp/haiku_run_1
export ANTHROPIC_API_KEY=sk-ant-...
export REFINER_MODEL=claude-3-5-sonnet-20241022
```

## Input Data Format

Dataset (JSONL):

```json
{"id": "ex_001", "text": "Input text", "label": "A", "domain": "science"}
{"id": "ex_002", "text": "Another", "label": "B", "domain": "law"}
```

Initial artifact (text file):

```
You are a classifier. Classify:

Text: {input}

Respond: A, B, or C
```

## Output

### state/experiments.jsonl

Append-only log (one line per iteration):

```json
{
  "iter": 1,
  "batch_id": "batch_000001",
  "artifact_hash": "abc123def456...",
  "plan_id": "add_examples",
  "rationale": "Add diverse examples to improve coverage",
  "metrics_train": {"kappa": 0.742, "macro_f1": 0.735, ...},
  "metrics_dev": {"kappa": 0.635, "macro_f1": 0.628, ...},
  "metrics_test": {"kappa": 0.612, "macro_f1": 0.605, ...},
  "delta_dev_kappa": 0.018,
  "is_winner": true
}
```

### state/experiments_report.md

Auto-generated markdown report:

```markdown
# Autoresearch Loop Report

Total iterations: 48

## Summary
- Best iteration: 42 (κ=0.735)
- Win rate: 16/48 (33.3%)
- Latest dev-test gap: +0.104

## Iterations
| Iter | Plan | κ (dev) | Δκ | Winner |
|------|------|--------|-----|--------|
| 1    | baseline | 0.500 | +0.000 | |
| 2    | add_examples | 0.635 | +0.135 | ✓ |
...

## Plan Aggregates
- **add_examples**: 3 proposed, 1 won, mean Δ=+0.002
- **reword_prompt**: 2 proposed, 2 won, mean Δ=+0.018
...
```

### state/cache/

Per-artifact cache (by content hash):

```
state/cache/
└── abc123def456789a/
    ├── artifact.txt          # The artifact
    ├── metrics_train.jsonl   # Scores on train set
    ├── metrics_dev.jsonl     # Scores on dev set
    ├── metrics_test.jsonl    # Scores on test set
    └── diagnosis.md          # Stage-A error summary
```

## Example: Optimize a Classification Prompt

```bash
# 1. Create dataset: data/dataset.jsonl
# Format: {"id": "1", "text": "...", "label": "A", "domain": "..."}

# 2. Create initial artifact: state/initial_artifact.txt
cat > state/initial_artifact.txt << 'EOF'
Classify the following text as positive, negative, or neutral:

Text: {input}

Respond with one word: positive, negative, or neutral
EOF

# 3. Configure paths.py
vim autoresearch/paths.py
# - DATASET_PATH = Path("data/dataset.jsonl")
# - REFINER_MODEL = "claude-3-5-sonnet-20241022"
# - SCORER_MODEL = "claude-3-5-sonnet-20241022"

# 4. Set API key
export ANTHROPIC_API_KEY=sk-ant-...

# 5. Smoke test
python -m autoresearch.main run --limit 50 --max-iters 1

# 6. Check output
cat state/experiments.jsonl | jq '.iter, .plan_id, .metrics_dev.kappa'
cat state/experiments_report.md

# 7. Full run
python -m autoresearch.main run
```

## Lessons Learned (from DesignDoc §10)

### 10.1 First Edit Dominates
First major win: **+0.115 κ**. Subsequent wins: +0.001 to +0.028. Diminishing returns kick in fast.

### 10.2 ~⅓ Win Rate
With good setup: ~33% of proposals improve over parent. If <20%, audit proposer meta-prompt or dataset.

### 10.3 Selector Overfitting is Real
Monitor dev–test gap. At iter 27: dev κ=0.335 but test κ=0.231 (0.10 gap). This signals overfitting.

### 10.4 Multiple Correlated Metrics
Don't optimize one metric alone. Use κ + macro-F1 + Spearman. If metrics disagree, that's signal about distribution shift.

### 10.5 Greedy Retries Waste Time
Temperature=0 retries on parse failure produce identical output. Always vary temperature.

### 10.6 Keep the Notebook
`state/notes.md` is the most useful intervention lever. Mid-run, write "Do not propose length edits" and loop respects it.

## Anti-Patterns (Avoid!)

| Anti-pattern | Why it bites |
|---|---|
| Recompute scoring on every loop start | Wastes 100% of budget |
| Single-metric selection | Selector finds metric pathologies, not real improvements |
| No held-out test set | Overfitting hidden until deployment |
| Multi-edit candidates | Can't tell which sub-change helped |
| Selector = argmax | Misses cases where old branch is better |
| Deterministic retries | Retries produce identical output |
| Live human review in loop | Defeats autonomy; use notebook instead |
| Modifying earlier log lines | Breaks resumability |
| Serial scoring | Easy K× speedup left on table |

## Troubleshooting

See **OPS.md** for detailed troubleshooting guide.

Quick checklist:
- [ ] Loop running? `ps aux | grep autoresearch`
- [ ] State dir exists? `ls -l $AUTORESEARCH_STATE_DIR`
- [ ] Log exists? `test -f $AUTORESEARCH_STATE_DIR/experiments.jsonl`
- [ ] Cache has entries? `ls -1 $AUTORESEARCH_STATE_DIR/cache | wc -l`
- [ ] Report updated? `stat $AUTORESEARCH_STATE_DIR/experiments_report.md`
- [ ] Dataset readable? `head -1 $(grep DATASET_PATH autoresearch/paths.py | cut -d'"' -f2) | jq .`

## Performance

| Scenario | Time |
|---|---|
| Cache hit (score cached artifact) | ~10 ms |
| Cache miss (score new artifact) | ~2-5 sec (LLM call) |
| Parallel batch (K=3, 3 splits) | ~15 sec wall-clock |
| Full iteration (A+B+C+Score+A) | ~30-60 sec |

With good cache hit rate, batches get cheaper over time (fewer new artifacts).

## Scale

- **Dataset**: Tested with ~1000 examples. Should scale to ~100k with streaming.
- **Batch size K**: Default 3. Can increase to 5+ for more parallelism.
- **Artifact size**: Tested with prompts up to 10k chars. Larger prompts may hit token budget limits.
- **Parallelism**: Default 15 parallel scorer calls. Can adjust in paths.py.

## Multi-Instance Support

Run multiple parallel loops with different state dirs:

```bash
# Run 1: optimizing κ
AUTORESEARCH_STATE_DIR=/tmp/run_kappa python -m autoresearch.main run &

# Run 2: optimizing F1 (edit stage_c.py selector to prefer F1)
AUTORESEARCH_STATE_DIR=/tmp/run_f1 python -m autoresearch.main run &

# Monitor
watch -n 5 'tail -1 /tmp/run_kappa/experiments.jsonl /tmp/run_f1/experiments.jsonl | jq .'
```

## Integration Points

To integrate with your own scoring system:

1. **scorer.py**: Replace LLM calls with your scorer (test runner, human judge, simulator, etc.)
   - Input: artifact + examples
   - Output: metrics (kappa, F1, accuracy, etc.)

2. **stages/**: Modify stage prompts for your task
   - Stage A: What errors to diagnose?
   - Stage B: What kinds of edits to propose?
   - Stage C: What criteria for selection?
   - Stage M: How to merge artifacts?

3. **artifacts/**: Customize serialization if not plain text
   - Could be JSON (config), YAML (schema), etc.
   - Hash computation same: SHA256(serialized)

See individual DOCUMENTATION.md files for details.

## Contributing

The codebase follows these principles:
- Each module has own DOCUMENTATION.md
- All config in paths.py (no CLI flags scatter)
- Append-only log (never modify earlier lines)
- Content-hash cache (no duplicate work)
- Crash-safe writes (line-buffered or atomic)

## License

TBD

## References

- **DesignDoc.md**: Full design rationale and patterns
- **WIKI.md**: Architectural overview
- **OPS.md**: Deployment and operations
- Original paper: [Link to research paper if applicable]

## Questions?

See the comprehensive documentation in each module's DOCUMENTATION.md file.
