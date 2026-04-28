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
- [ ] Final validation

## Detailed TODO List

### Phase 1 TODO
1. [x] Create autoresearch/__init__.py
2. [x] Create autoresearch/paths.py with all config
3. [x] Create artifacts/__init__.py and artifacts/artifact.py
4. [x] Implement content hash computation
5. [x] Commit: "feat: Initial project structure with paths and artifact class"

### Phase 2 TODO
1. [x] Create splitter/__init__.py and splitter/splitter.py
2. [x] Implement stratified split with seed reproducibility
3. [x] Create scorer/__init__.py and scorer/scorer.py
4. [x] Implement cache-aware scoring and metrics
5. [x] Commit: "feat: Added dataset splitter and cache-aware scorer"

### Phase 3 TODO
1. [ ] Create stages/__init__.py and four stage modules
2. [ ] Implement stage_a (diagnosis generalization)
3. [ ] Implement stage_b (proposal generation with K siblings)
4. [ ] Implement stage_c (selection logic)
5. [ ] Implement stage_m (merge synthesis)
6. [ ] Commit: "feat: Implemented four refiner stages (A/B/C/M)"

### Phase 4 TODO
1. [ ] Create history/__init__.py and history/renderer.py
2. [ ] Implement compact + full history rendering
3. [ ] Create report/__init__.py and report/report.py
4. [ ] Implement report generation from experiments.jsonl
5. [ ] Implement bi-directional notebook integration
6. [ ] Commit: "feat: Added history rendering and experiment reporting"

### Phase 5 TODO
1. [ ] Create autoresearch/loop.py with main batch loop
2. [ ] Implement resumability and crash safety
3. [ ] Implement observability (live blocks, per-attempt dumps)
4. [ ] Test full pipeline
5. [ ] Commit: "feat: Main loop with batch orchestration and observability"

### Phase 6 TODO
1. [ ] Create autoresearch/main.py with CLI
2. [ ] Implement run/report/reset/score commands
3. [ ] Create tests/ directory with unit tests
4. [ ] Test all modules in isolation
5. [ ] Smoke test with --limit flag
6. [ ] Commit: "feat: CLI surface and unit tests"

### Phase 7 TODO
1. [ ] Write DOCUMENTATION.md for each module
2. [ ] Complete OPS.md with deployment procedures
3. [ ] Run linter and formatter
4. [ ] Fix any issues
5. [ ] Final review and validation
6. [ ] Commit: "docs: Complete documentation and final validation"

## Notes

- Each TODO will be committed immediately upon completion
- Use separate git branches for each feature
- Branch naming: feature/<feature_name>
- Merge only after tests pass and code is clean
