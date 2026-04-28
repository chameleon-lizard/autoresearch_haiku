# Report Module — DOCUMENTATION

## Overview

The report module auto-generates `experiments_report.md` from the append-only `experiments.jsonl` log.

**Key principle**: Report is deterministic and regenerated after every batch. This lets you open it in an editor and watch the table grow without manual intervention.

## API Reference

### load_experiments(log_path)

Load all experiments from JSONL log:

```python
from report.report import load_experiments
from pathlib import Path

experiments = load_experiments(Path("state/experiments.jsonl"))
# Returns: List[Dict] with all iterations
print(len(experiments))  # e.g., 48
```

### generate_report(experiments)

Generate markdown report from experiments list:

```python
from report.report import generate_report

experiments = load_experiments()
report_text = generate_report(experiments)

print(report_text)
# # Autoresearch Loop Report
# Total iterations: 48
# ...
```

### regenerate_report(log_path, report_path)

Regenerate report from log and save to disk:

```python
from report.report import regenerate_report

regenerate_report()
# Loads state/experiments.jsonl
# Generates report markdown
# Saves to state/experiments_report.md

# Or with custom paths:
regenerate_report(
    log_path=Path("custom.jsonl"),
    report_path=Path("custom_report.md")
)
```

## Report Format

Generated markdown includes:

### Summary Section

```
## Summary

- Best iteration: 42 (κ=0.735)
- Win rate: 16/48 (33.3%)
- Latest dev-test gap: +0.104 (overfitting if growing)
```

Explains:
- Which iteration achieved highest dev κ
- What fraction of proposals improved over parent
- Whether selector is overfitting dev (test gap growing)

### Iterations Table

```
| Iter | Batch | Plan | κ (dev) | F1 (dev) | Δκ | Winner | Rationale |
|------|-------|------|--------|---------|-----|--------|-----------|
| 1 | batch_000001 | baseline | 0.500 | 0.485 | +0.000 | | Reference |
| 2 | batch_000001 | add_examples | 0.635 | 0.628 | +0.135 | ✓ | Add edge cases |
| 3 | batch_000001 | reword | 0.612 | 0.605 | +0.112 | | Simplify language |
...
```

Helps you:
- Spot winners quickly (✓ column)
- Track metric trajectory (κ column)
- See which plans were tested (Plan column)
- Understand rationale for each change (Rationale column)

### Plan Aggregates

```
## Plan Aggregates

- **add_examples**: 3 proposed, 1 won, mean Δ=+0.002
- **reword_prompt**: 2 proposed, 2 won, mean Δ=+0.018
- **expand_scope**: 1 proposed, 0 won, mean Δ=-0.001
```

This answers:
- Which types of edits are most successful?
- How many times was each plan tried?
- What's the average impact per plan type?

## Monitoring

### Live Dashboard

Open report in editor and watch it update:

```bash
# Terminal 1: Run loop
python -m autoresearch.main run

# Terminal 2: Watch report update
watch -n 30 'tail -50 state/experiments_report.md'

# Or in editor (some editors auto-reload):
# Open state/experiments_report.md in VS Code / vim / emacs
# Auto-refresh on save
```

### Detect Overfitting

Check dev-test gap in summary:

```bash
# Latest line of log
tail -1 state/experiments.jsonl | jq '.metrics_dev.kappa, .metrics_test.kappa'
# 0.735
# 0.631

# Gap = 0.735 - 0.631 = 0.104 (10.4% overfitting)

# This is concerning if monotone-increasing
# Action: pause loop, retrain with wider dev/test split
```

### Track Metric Trajectory

Extract κ over time:

```bash
jq '.iter, .metrics_dev.kappa' state/experiments.jsonl | paste - - | column -t

# 1    0.500
# 2    0.635
# 3    0.612
# 4    0.651
# 5    0.641
# ...
```

Or use the table in the report.

## Report Regeneration

### Trigger Manual Regeneration

```bash
python -m autoresearch.main report
```

### Automatic Regeneration

The loop automatically regenerates after each batch:

```python
# In loop.py after scoring batch:
regenerate_report()
```

### Verify Report is Fresh

```bash
# Report should be newer than log (regenerated after each batch)
stat state/experiments.jsonl state/experiments_report.md

# Compare modification times
ls -l state/experiments.jsonl state/experiments_report.md
```

## Examples

### Example 1: Find Best Iteration

```python
from report.report import load_experiments

experiments = load_experiments()

# Find by κ
best_exp = max(experiments, key=lambda e: e.get("metrics_dev", {}).get("kappa", 0))
print(f"Best: iter {best_exp['iter']} with κ={best_exp['metrics_dev']['kappa']:.3f}")

# Find by F1
best_f1_exp = max(experiments, key=lambda e: e.get("metrics_dev", {}).get("macro_f1", 0))
print(f"Best F1: iter {best_f1_exp['iter']}")
```

### Example 2: Analyze Win Rate Over Time

```python
from report.report import load_experiments

experiments = load_experiments()

# Rolling win rate (last N iterations)
N = 10
recent = experiments[-N:]
recent_wins = sum(1 for e in recent if e.get("is_winner"))
recent_win_rate = recent_wins / N

print(f"Recent win rate (last {N}): {recent_win_rate:.1%}")
# If < 20%, proposer is struggling
```

### Example 3: Export Data for Analysis

```python
from report.report import load_experiments
import csv

experiments = load_experiments()

# Export to CSV
with open("export.csv", "w") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "iter", "plan_id", "kappa_dev", "delta", "winner"
    ])
    writer.writeheader()
    for exp in experiments:
        writer.writerow({
            "iter": exp["iter"],
            "plan_id": exp["plan_id"],
            "kappa_dev": exp.get("metrics_dev", {}).get("kappa", 0),
            "delta": exp.get("delta_dev_kappa", 0),
            "winner": "Y" if exp.get("is_winner") else "N",
        })

print("Exported to export.csv")
```

### Example 4: Summary Statistics

```python
from report.report import load_experiments, generate_report

experiments = load_experiments()

# Generate and print report
report = generate_report(experiments)
print(report)

# Or access summary programmatically:
if experiments:
    best = max(experiments, key=lambda e: e.get("metrics_dev", {}).get("kappa", 0))
    wins = sum(1 for e in experiments if e.get("is_winner"))
    
    print(f"Iterations: {len(experiments)}")
    print(f"Best κ: {best['metrics_dev']['kappa']:.3f} (iter {best['iter']})")
    print(f"Win rate: {wins}/{len(experiments)} ({100*wins/len(experiments):.1f}%)")
```

## Debugging

### Report Not Updating

Check if process is still running:

```bash
ps aux | grep autoresearch.main

# If running, manually regenerate
python -m autoresearch.main report

# If report didn't change, check log
tail -5 state/experiments.jsonl
```

### Report Looks Wrong

Verify log file is valid JSON:

```bash
jq . state/experiments.jsonl | head -20
# Should print valid JSON

# If errors, log may be corrupted
tail -1 state/experiments.jsonl | jq .
# If last line is invalid, remove it
head -n -1 state/experiments.jsonl > experiments.jsonl.tmp
mv experiments.jsonl.tmp state/experiments.jsonl

# Regenerate report
python -m autoresearch.main report
```

### Report Too Large

If report is very large (many iterations), consider:
1. Archiving old reports
2. Creating summaries (per 10-batch chunks)
3. Filtering report to show last N iterations only

```python
# Show only last 50 iterations
recent_experiments = load_experiments()[-50:]
report = generate_report(recent_experiments)
```

## Future Enhancements

1. **HTML report**: Generate interactive dashboard (with charts)
2. **Real-time updates**: WebSocket to live-update browser view
3. **Comparison reports**: Compare two runs side-by-side
4. **Metric history**: Track multiple metrics simultaneously
5. **Error analysis**: Per-plan error rate and types
6. **Plan recommendation**: "Try plan X next; it's been most successful"
7. **Overfitting detection**: Alert when dev-test gap exceeds threshold
