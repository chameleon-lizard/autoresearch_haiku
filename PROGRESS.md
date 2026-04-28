# Haiku Autoresearch Loop — Progress

## Implementation Status

### Phase 1: Infrastructure & Foundations
- [ ] Project structure setup
- [ ] paths.py centralized configuration
- [ ] artifact.py: Artifact class with content-hash caching
- [ ] Initial git commit

### Phase 2: Dataset & Scoring
- [ ] splitter.py: Stratified train/dev/test split
- [ ] scorer.py: Cache-aware scoring subprocess wrapper
- [ ] Metrics computation module

### Phase 3: Refiner Stages
- [ ] stage_a.py: Disagreement generalization
- [ ] stage_b.py: Sibling proposal generation (K candidates)
- [ ] stage_c.py: Selection logic (pick parent or merge)
- [ ] stage_m.py: Merge synthesis (combine N artifacts)

### Phase 4: History & Reporting
- [ ] history/renderer.py: Compact vs full history rendering
- [ ] report.py: Auto-generate experiments_report.md from log
- [ ] Bi-directional notebook (notes.md) integration

### Phase 5: Main Loop
- [ ] loop.py: Batch orchestration (C → M → B → Score → A)
- [ ] Resumability on crash/Ctrl+C
- [ ] Observability: live terminal blocks, per-attempt dumps

### Phase 6: CLI & Testing
- [ ] CLI surface: run/report/reset/score commands
- [ ] Unit tests for each module
- [ ] Smoke test with --limit flag

### Phase 7: Polish & Docs
- [ ] All module DOCUMENTATION.md files complete
- [ ] OPS.md deployment runbook
- [ ] Code linting and formatting
## Implementation Status

### Phase 1: Infrastructure & Foundations
- [x] Project structure setup
- [x] paths.py centralized configuration
- [x] artifact.py: Artifact class with content-hash caching
- [x] Initial git commit

### Phase 2: Dataset & Scoring
- [x] splitter.py: Stratified train/dev/test split
- [x] scorer.py: Cache-aware scoring subprocess wrapper
- [x] Metrics computation module

### Phase 3: Refiner Stages
- [x] stage_a.py: Disagreement generalization
- [x] stage_b.py: Sibling proposal generation (K candidates)
- [x] stage_c.py: Selection logic (pick parent or merge)
- [x] stage_m.py: Merge synthesis (combine N artifacts)

### Phase 4: History & Reporting
- [x] history/renderer.py: Compact vs full history rendering
- [x] report.py: Auto-generate experiments_report.md from log
- [x] Bi-directional notebook (notes.md) integration

### Phase 5: Main Loop
- [x] loop.py: Batch orchestration (C → M → B → Score → A)
- [x] Resumability on crash/Ctrl+C
- [x] Observability: live terminal blocks, per-attempt dumps

### Phase 6: CLI & Testing
- [x] CLI surface: run/report/reset/score commands
- [ ] Unit tests for each module
- [ ] Smoke test with --limit flag

### Phase 7: Polish & Docs
- [ ] All module DOCUMENTATION.md files complete
- [x] OPS.md deployment runbook (DONE)
- [ ] Code linting and formatting
- [ ] Final validation
