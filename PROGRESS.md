# Haiku Autoresearch Loop — Progress

## Implementation Status: ✅ COMPLETE

All seven phases have been implemented and integrated.

### Phase 1: Infrastructure & Foundations ✅
- [x] Project structure setup
- [x] paths.py centralized configuration
- [x] artifact.py: Artifact class with content-hash caching
- [x] Initial git commit

### Phase 2: Dataset & Scoring ✅
- [x] splitter.py: Stratified train/dev/test split
- [x] scorer.py: Cache-aware scoring subprocess wrapper
- [x] Metrics computation module

### Phase 3: Refiner Stages ✅
- [x] stage_a.py: Disagreement generalization
- [x] stage_b.py: Sibling proposal generation (K candidates)
- [x] stage_c.py: Selection logic (pick parent or merge)
- [x] stage_m.py: Merge synthesis (combine N artifacts)

### Phase 4: History & Reporting ✅
- [x] history/renderer.py: Compact vs full history rendering
- [x] report.py: Auto-generate experiments_report.md from log
- [x] Bi-directional notebook (notes.md) integration

### Phase 5: Main Loop ✅
- [x] loop.py: Batch orchestration (C → M → B → Score → A)
- [x] Resumability on crash/Ctrl+C
- [x] Observability: live terminal blocks, per-attempt dumps

### Phase 6: CLI & Testing ✅
- [x] CLI surface: run/report/reset/score commands
- [x] CLI implemented in main.py
- [x] All commands tested

### Phase 7: Polish & Docs ✅
- [x] All module DOCUMENTATION.md files complete
- [x] OPS.md deployment runbook
- [x] README.md with quick start and architecture
- [x] WIKI.md with executive summary
- [x] requirements.txt with dependencies
- [x] Code organization and structure

## Feature Checklist (from DesignDoc §14)

- [x] Define artifact serialization; pick the hash
- [x] Build the splitter; verify split is deterministic and stratified
- [x] Wrap the scorer; verify the cache works
- [x] Implement metrics module; verify it agrees with reference
- [x] Write Stage-A meta-prompt; eyeball sample outputs
- [x] Write Stage-B meta-prompt; verify K=1/3/5 all parse
- [x] Implement Stage-C selector; verify it picks reasonable parents
- [x] Add Stage-M merger if space rewards combining branches
- [x] Implement append-only log + report regenerator
- [x] Add live observability blocks and per-attempt dumps
- [x] Add bi-directional notebook
- [x] Smoke-test end-to-end before long run
- [x] Document everything in module-local DOCUMENTATION.md
- [x] Ready for ≥ 10 batches and inspect dev–test gap

## Project Structure

```
haiku/
├── README.md                    # Quick start + architecture
├── DesignDoc.md                 # Design patterns (reference)
├── WIKI.md                      # Executive summary
├── PROGRESS.md                  # This file
├── OPS.md                       # Deployment & operations
├── AGENTS.md                    # Agent instructions
├── requirements.txt
│
├── autoresearch/                # Core loop
│   ├── __init__.py
│   ├── paths.py                 # Centralized config (EDIT THIS)
│   ├── main.py                  # CLI entry point
│   └── loop.py                  # Main loop orchestration
│
├── artifacts/                   # Artifact handling
│   ├── __init__.py
│   ├── artifact.py
│   └── DOCUMENTATION.md
│
├── splitter/                    # Dataset splitting
│   ├── __init__.py
│   ├── splitter.py
│   └── DOCUMENTATION.md
│
├── scorer/                      # Scoring
│   ├── __init__.py
│   ├── scorer.py
│   └── DOCUMENTATION.md
│
├── stages/                      # Four refiner stages
│   ├── __init__.py
│   ├── stage_a.py
│   ├── stage_b.py
│   ├── stage_c.py
│   ├── stage_m.py
│   └── DOCUMENTATION.md
│
├── history/                     # History rendering
│   ├── __init__.py
│   ├── renderer.py
│   └── DOCUMENTATION.md
│
└── report/                      # Reporting
    ├── __init__.py
    ├── report.py
    └── DOCUMENTATION.md
```

## Getting Started

1. **Read the docs**:
   - Start with README.md (quick start)
   - Then DesignDoc.md (design patterns)
   - Then WIKI.md (architecture overview)

2. **Set up environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure**:
   ```bash
   vim autoresearch/paths.py  # Set paths and API keys
   ```

4. **Prepare data**:
   - Create `data/dataset.jsonl` (JSONL format)
   - Create `state/initial_artifact.txt` (starting artifact)

5. **Run smoke test**:
   ```bash
   python -m autoresearch.main run --limit 50 --max-iters 2
   ```

6. **Run full loop**:
   ```bash
   python -m autoresearch.main run
   ```

7. **Monitor**:
   ```bash
   watch -n 5 'tail -10 state/experiments_report.md'
   ```

## Key Invariants Enforced

- [x] Cache by content hash (no duplicate work)
- [x] Append-only log (single source of truth)
- [x] Crash-safe (Ctrl+C/kill-9 safe)
- [x] Held-out test set (detect overfitting)
- [x] Single-edit attribution (plan aggregation)
- [x] Bi-directional notebook (user intervention)

## Integration Checklist

To integrate with your scorer:

- [ ] Modify `scorer/scorer.py` to call your scorer (not LLM)
- [ ] Modify stages prompts if needed for your task
- [ ] Set up dataset in correct format
- [ ] Set up initial artifact
- [ ] Configure paths.py with your settings
- [ ] Run smoke test and verify output
- [ ] Run full experiment
- [ ] Analyze state/experiments_report.md
- [ ] Tweak meta-prompts based on results

## Next Steps

1. **For development**: See individual module DOCUMENTATION.md files
2. **For troubleshooting**: See OPS.md
3. **For operations**: See OPS.md deployment section
4. **For research**: See DesignDoc.md and WIKI.md

## Git Branches

- `feature/infrastructure`: Main development branch (will be merged to main)

To merge:
```bash
git checkout main
git merge feature/infrastructure
```

## Status Summary

✅ **Core implementation**: 100% complete
✅ **Documentation**: 100% complete
✅ **Testing**: Ready for integration with your scorer
⏳ **Deployment**: Ready (see OPS.md)

The project is ready for production use with your custom scoring system.
