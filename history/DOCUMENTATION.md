# History Module — DOCUMENTATION

## Overview

The history module provides smart rendering of experiment history for inclusion in LLM prompts.

**Key principle** (DesignDoc §6): Render history intelligently to fit context windows:
- Best-so-far and recent iterations: full text + metrics + diagnosis
- Direct parents: full text (always)
- Everything else: compact one-liners

This lets the proposer (Stage B) see long-range trends without dumping 50 prompts into context.

## API Reference

### render_compact(iteration)

Compact single-line rendering:

```python
from history.renderer import render_compact

iteration = {
    "iter": 5,
    "batch_id": "batch_00005",
    "parent_hash": "abc123def456...",
    "plan_id": "add_examples",
    "metrics_dev": {"kappa": 0.635, "macro_f1": 0.628},
    "delta_dev_kappa": 0.015,
}

output = render_compact(iteration)
# "iter=5 batch=batch_00005 parent=abc123de plan=add_examples κ=0.635 F1=0.628 Δ=+0.015"
```

### render_full(iteration, artifact_text)

Full rendering with artifact preview:

```python
from history.renderer import render_full

iteration = {...}
artifact_text = "Your prompt..."

output = render_full(iteration, artifact_text)
# === Iteration 5 (plan=add_examples) ===
# Rationale: Add 5 diverse examples to improve...
# Train κ=0.742, Dev κ=0.635, Test κ=0.612
# Errors: 5 disagreements on edge cases
# 
# Artifact:
# Your prompt...
# ... (rest of artifact preview)
```

### render_history(experiments, best_iter_num, parent_iter_nums, recent_n, artifacts_map)

Smart history rendering for LLM context:

```python
from history.renderer import render_history
from report.report import load_experiments

experiments = load_experiments()
best_iter = 10  # Best by κ

history_text = render_history(
    experiments=experiments,
    best_iter_num=best_iter,
    parent_iter_nums=[5, 10],  # If merging
    recent_n=5,  # Show 5 most recent in full
    artifacts_map={10: "artifact text", 5: "artifact text"},
)

print(history_text)
# # History
# 
# ## Best So Far
# === Iteration 10 (plan=...) ===
# ...
# 
# ## Recent Iterations
# === Iteration 9 (plan=...) ===
# ...
# (compact one-liners for older)
```

### render_plan_aggregate(experiments)

Aggregate statistics per plan_id:

```python
from history.renderer import render_plan_aggregate
from report.report import load_experiments

experiments = load_experiments()
agg = render_plan_aggregate(experiments)

print(agg)
# # Plan Aggregates
# 
# **add_examples**: proposed 3, won 1, mean Δ=+0.002
# **reword_prompt**: proposed 2, won 2, mean Δ=+0.018
# **expand_scope**: proposed 1, won 0, mean Δ=-0.001
```

## Strategy

The rendering strategy is optimized for LLM context windows (finite token budget):

### Priority Levels

1. **High priority (always full):**
   - Best-so-far iteration (by dev κ)
   - Direct parents (iteration to merge or current parent)
   - Last N=5 iterations (recent history)

2. **Medium priority (abbreviated):**
   - Older winning iterations (one-line summary)

3. **Low priority (omitted or very compact):**
   - Very old iterations
   - Iterations that lost (unless notable pattern)

### Example

With 100 iterations, history rendering might produce:

```
## Best So Far
=== Iteration 42 (plan=...) ===
Full text, metrics, diagnosis (500 tokens)

## Recent Iterations
=== Iteration 99 (plan=...) ===
Full text (300 tokens)
=== Iteration 98 (plan=...) ===
Full text (300 tokens)
=== Iteration 97 (plan=...) ===
iter=97 batch=... plan=... κ=0.631 (compact, 10 tokens)
... (more compact older)

## Older Iterations (Top Winners)
iter=40: proposed best, mean Δ=+0.023
iter=35: won 3 times, mean Δ=+0.008
...
```

Total: ~1500 tokens for full context, vs 10,000+ if all full.

## Customization

### Change Number of Recent Iterations

```python
# Show more recent iterations in full
history_text = render_history(
    experiments,
    best_iter_num=best,
    recent_n=10,  # was 5
    artifacts_map=artifacts,
)
```

### Change Artifact Preview Length

Edit `render_full()`:

```python
# Show 1000 chars instead of 500
preview = artifact_text[:1000]  # was 500
```

### Include Additional Metrics

Edit `render_compact()` to include more fields:

```python
# Add accuracy in addition to κ and F1
return (
    f"iter={iter_num} ... κ={kappa:.3f} acc={accuracy:.3f} F1={f1:.3f} ..."
)
```

## Integration with Loop

History is rendered in two contexts:

1. **Stage B (Proposal)**:
   - User: "Generate K proposals"
   - Input includes: full history via `render_history()`
   - Proposer uses history to avoid re-proposing failed edits
   - Decision: which metrics matter? which branches to explore?

2. **Stage C (Selection)**:
   - User: "Choose next parent"
   - Input includes: full history (same `render_history()` output)
   - Selector uses history trajectory to make strategic decisions

## Performance

Rendering is deterministic and fast (~10ms for 1000 iterations).

Cache artifacts in memory if re-rendering frequently:

```python
from pathlib import Path

artifacts_map = {}
for iter_num in range(1, 100):
    cache_dir = Path("state/cache") / exp["artifact_hash"]
    artifact_file = cache_dir / "artifact.txt"
    if artifact_file.exists():
        artifacts_map[iter_num] = artifact_file.read_text()

history_text = render_history(
    experiments,
    best_iter_num=best,
    artifacts_map=artifacts_map,
)
```

## Debugging

### Is History Too Long?

Check rendered length:

```python
history_text = render_history(...)
print(f"History length: {len(history_text)} chars")
# Aim for <20k chars (~4k tokens)

if len(history_text) > 20000:
    print("History too long; reduce recent_n or abbreviate more")
```

### Are Recent Iterations Missing?

Verify `recent_n` parameter:

```python
# recent_n=5 means last 5 iterations shown in full
# If you have 100 iterations, iter 96-100 are full, 1-95 are compact
```

### Are Best Artifacts Included?

Pass `artifacts_map` with cached artifact texts:

```python
# Without artifacts_map
history1 = render_history(experiments, best_iter_num=10)
# Won't include artifact text (None)

# With artifacts_map
history2 = render_history(experiments, best_iter_num=10, 
                          artifacts_map={10: "artifact text"})
# Will include artifact preview
```

## Future Enhancements

1. **Adaptive rendering**: Automatically reduce context if too long
2. **Domain-aware history**: Show history filtered by domain tags
3. **Metric-aware rendering**: Emphasize trajectory for different metrics (κ vs F1 vs accuracy)
4. **Merge history**: Show which iterations were merged and how
5. **Plan-tree history**: Visualize which plan led to which subsequent plans
