# Haiku Autoresearch Loop — Project Wiki

## Project Overview

Haiku is a task-agnostic autoresearch loop implementation that automatically optimizes an artifact (prompt, config, prompt weights, etc.) against a metric using an LLM-driven optimization process.

The loop:
1. **Scores** a current candidate artifact on a labelled dataset (train/dev/test splits)
2. **Diagnoses** what the artifact gets wrong (Stage A: failure mode generalization)
3. **Proposes** mutations of the artifact that target those failure modes (Stage B: sibling proposals)
4. **Selects** which proposal to keep, based on held-out signal (Stage C: selector decision)
5. Repeats indefinitely, maintaining an append-only experiment log

## Core Invariants

All features are built to enforce these invariants (from DesignDoc §2):

### Cache by Content Hash
- Every artifact has id: `sha256(serialise(artifact))[:16]`
- All expensive work (scoring, diagnosis) is keyed by this id and persisted
- Re-runs never redo work already in cache
- Cache is self-describing (includes artifact text alongside results)

### Append-Only Experiment Log
- Single source of truth: `state/experiments.jsonl`
- Each iteration writes one JSON line (never rewritten)
- Enables resumability, audit trail, time-travel replay

### Crash & Ctrl+C Safe
- All writes are line-buffered or atomic
- Partially-written scorer results are skipped on resume
- No data corruption on process death

### Held-Out Evaluation
- Three splits: train / dev / test (configurable ratio, e.g. 40/20/40)
- Loop sees train + dev metrics
- Test metrics logged but never surfaced to proposer/selector (detect overfitting)

### Single-Edit Attribution
- Each candidate applies ONE focused change to its parent
- Multi-change candidates forbidden (cannot attribute improvements)
- Aggregate stats per `plan_id` become meaningful only with single edits

### Bi-Directional Notebook
- Shared text file (`notes.md`): user can inject constraints mid-run
- Re-read fresh every iteration (never cached)
- Out-of-band channel for domain knowledge injection without restart

## Repository Structure

```
haiku/
├── DesignDoc.md               # Design patterns & reference (READ FIRST)
├── AGENTS.md                  # Agent instructions
├── WIKI.md                    # This file
├── PROGRESS.md                # Feature implementation status
├── OPS.md                     # Deployment & operations runbook
│
├── autoresearch/              # Core autoresearch loop
│   ├── __init__.py
│   ├── DOCUMENTATION.md       # Core module docs
│   ├── paths.py               # Centralized path & config management
│   ├── main.py                # Main loop entry point
│   └── loop.py                # Main loop implementation
│
├── artifacts/                 # Artifact handling
│   ├── __init__.py
│   ├── DOCUMENTATION.md
│   └── artifact.py            # Artifact class, serialization, hashing
│
├── splitter/                  # Dataset splitting
│   ├── __init__.py
│   ├── DOCUMENTATION.md
│   └── splitter.py            # Stratified train/dev/test split
│
├── scorer/                    # Scoring subprocess wrapper
│   ├── __init__.py
│   ├── DOCUMENTATION.md
│   └── scorer.py              # Cache, parallel scoring, metric computation
│
├── stages/                    # Four refiner stages (A/B/C/M)
│   ├── __init__.py
│   ├── DOCUMENTATION.md
│   ├── stage_a.py             # Disagreement generalization
│   ├── stage_b.py             # Proposal generation (K siblings)
│   ├── stage_c.py             # Selection (pick parent or merge)
│   └── stage_m.py             # Merge synthesis
│
├── history/                   # History rendering
│   ├── __init__.py
│   ├── DOCUMENTATION.md
│   └── renderer.py            # Compact vs full history for context
│
├── report/                    # Experiment reporting
│   ├── __init__.py
│   ├── DOCUMENTATION.md
│   └── report.py              # Auto-regenerate experiments_report.md
│
├── state/                     # Runtime state (created at runtime)
│   ├── cache/                 # <hash>/{artifact.txt, metrics_*.jsonl, diagnosis.md}
│   ├── iterations/            # Per-iteration data
│   ├── batches/               # Per-batch data (notes_before/after, attempts)
│   └── experiments.jsonl      # Append-only log
│
└── tests/                     # Unit tests
    ├── __init__.py
    ├── test_artifacts.py
    ├── test_splitter.py
    ├── test_scorer.py
    ├── test_stages.py
    ├── test_history.py
    └── test_report.py
```

## Configuration

All config is centralized in `autoresearch/paths.py`:

```python
# Core paths
STATE_DIR = Path(os.environ.get("AUTORESEARCH_STATE_DIR", "state"))
CACHE_DIR = STATE_DIR / "cache"
ITERATIONS_DIR = STATE_DIR / "iterations"
BATCHES_DIR = STATE_DIR / "batches"
LOG_FILE = STATE_DIR / "experiments.jsonl"
REPORT_FILE = STATE_DIR / "experiments_report.md"
NOTES_FILE = STATE_DIR / "notes.md"

# Refiner LLM (proposer)
REFINER_MODEL = "claude-3-5-sonnet-20241022"
REFINER_TEMPERATURE_SCHEDULE = [0.0, 0.4, 0.7, 0.9]
REFINER_MAX_RETRIES = 4

# Scorer LLM (evaluator)
SCORER_MODEL = "claude-3-5-sonnet-20241022"

# Dataset splitting
TRAIN_RATIO = 0.4
DEV_RATIO = 0.2
TEST_RATIO = 0.4
SPLIT_SEED = 42

# Batch mode
BATCH_SIZE = 3  # K candidates per batch

# Parallelism
MAX_PARALLEL_SCORES = 15  # K × 3 (K candidates × 3 splits)
```

## Key Modules

### autoresearch/main.py & loop.py
- Entry point and main loop orchestration
- Implements batch mode with stages C → M → B → Score → A
- Manages state checkpoints and resumability

### artifacts/artifact.py
- `Artifact` class: serializable, hashable artifact (prompt, config, etc.)
- Content hash computation: `sha256(serialize(artifact))[:16]`
- Deserialization and validation

### splitter/splitter.py
- `DatasetSplitter`: deterministic stratified split into train/dev/test
- Seed-based reproducibility
- Respects group stratification (if present in data)

### scorer/scorer.py
- `Scorer`: wraps subprocess LLM judge (or test runner)
- Cache by content hash: never re-scores same artifact
- Parallel scoring with asyncio/subprocess
- Metrics computation: κ, macro-F1, Spearman correlation, etc.

### stages/
- **stage_a.py**: Input = errors on train; Output = generalisation summary
- **stage_b.py**: Input = parent + summary + history; Output = K siblings with rationale
- **stage_c.py**: Input = history + metrics; Output = `iter=N` or `merge=N1,N2,...`
- **stage_m.py**: Input = N≥2 artifacts; Output = single merged artifact

### history/renderer.py
- Compact rendering: `iter=N batch=B parent=P plan=… κ=…`
- Full rendering: complete artifact + all metrics + stage-A summary
- Smart selection: recent iterations + best-so-far get full; rest get compact

### report/report.py
- Deterministic generation from `experiments.jsonl`
- Per-batch tables with metrics, rationale, plan_id
- Plan aggregation: "plan X proposed N times, won M, mean Δ"
- Live dashboard: open in editor, watch it grow

## CLI Surface

```bash
python -m autoresearch.main run                   # Infinite loop
python -m autoresearch.main run --max-iters 5    # Bounded for testing
python -m autoresearch.main run --limit 20       # Subsample dataset (fast smoke test)
python -m autoresearch.main report               # Regenerate experiments_report.md
python -m autoresearch.main reset                # Delete iterations + log (keep cache)
python -m autoresearch.main score <artifact>    # Score one artifact
```

## State Directory Layout (at runtime)

```
state/
├── experiments.jsonl              # Append-only log (line per iteration)
├── experiments_report.md          # Auto-generated report
├── notes.md                       # Bi-directional notebook
│
├── cache/
│   ├── abc123def456.../
│   │   ├── artifact.txt           # Full artifact text
│   │   ├── metrics_train.jsonl    # Scorer output on train set
│   │   ├── metrics_dev.jsonl      # Scorer output on dev set
│   │   ├── metrics_test.jsonl     # Scorer output on test set (observational)
│   │   └── diagnosis.md           # Stage-A: failure mode summary
│   │
│   └── def456abc789.../
│       └── ...
│
├── iterations/
│   ├── iter_00001/
│   │   ├── metadata.json          # iter, batch_id, parent_hash, plan_id, etc.
│   │   └── artifacts/             # K sibling candidates
│   │       ├── sibling_1.txt
│   │       ├── sibling_2.txt
│   │       └── sibling_3.txt
│   │
│   └── iter_00002/
│       └── ...
│
└── batches/
    ├── batch_00001/
    │   ├── notes_before.md        # Snapshot of notes.md before batch
    │   ├── notes_after.md         # Snapshot after agent edits
    │   ├── stage_c_decision.json  # Selector output: iter or merge
    │   ├── stage_a_attempt_{1..4}.txt  # Diagnosis attempts (if failed)
    │   ├── stage_b_attempt_{1..4}.txt  # Proposal attempts (if failed)
    │   └── stage_b_output.json    # Parsed K siblings + metadata
    │
    └── batch_00002/
        └── ...
```

## Experiment Log Format (`experiments.jsonl`)

Each line is a JSON object:

```json
{
  "iter": 1,
  "ts": "2025-04-29T12:34:56Z",
  "batch_id": "batch_00001",
  "artifact_hash": "abc123def456...",
  "parent_hash": "00000000000000",
  "plan_id": "improve_accuracy",
  "rationale": "Added emphasis on edge cases in the prompt...",
  "metrics_train": {
    "kappa": 0.742,
    "macro_f1": 0.735,
    "spearman": 0.851,
    "accuracy": 0.758
  },
  "metrics_dev": {
    "kappa": 0.635,
    "macro_f1": 0.628,
    "spearman": 0.715,
    "accuracy": 0.651
  },
  "metrics_test": {
    "kappa": 0.612,
    "macro_f1": 0.605,
    "spearman": 0.688,
    "accuracy": 0.628
  },
  "error_summary": "5 disagreements on edge cases...",
  "delta_dev_kappa": 0.018,
  "is_winner": true
}
```

## Key Features Implemented

1. ✓ Content hash-based caching for artifacts
2. ✓ Stratified train/dev/test splitting
3. ✓ Append-only experiment log
4. ✓ Four refiner stages (A/B/C/M)
5. ✓ Parallel scoring with cache hit short-circuit
6. ✓ History rendering (compact + full)
7. ✓ Auto-generated experiment report
8. ✓ Bi-directional notebook for user intervention
9. ✓ CLI surface for run/report/reset/score
10. ✓ Multi-instance support via `AUTORESEARCH_STATE_DIR` env var
11. ✓ Crash/Ctrl+C safety (line-buffered log, atomic writes)
12. ✓ Observability: live terminal blocks, per-attempt dumps

## Design Principles

- **Modular**: each module has own DOCUMENTATION.md and is independently testable
- **Cache-first**: no work repeated; hash is ground truth for deduplication
- **Audit trail**: immutable append-only log traces every decision
- **Safe to interrupt**: Ctrl+C or process death never corrupts state
- **Observable**: live progress, auto-reports, named per-attempt dumps
- **Configurable**: all knobs in paths.py or env vars, no CLI flag scatter
- **Testable**: unit tests for splitter, scorer, stages, history, report

## Getting Started

1. See PROGRESS.md for implementation status
2. Read OPS.md for deployment instructions
3. See individual module DOCUMENTATION.md files for deep dives
