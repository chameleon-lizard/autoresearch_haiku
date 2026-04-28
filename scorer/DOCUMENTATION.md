# Scorer Module — DOCUMENTATION

## Overview

The scorer module provides cache-aware artifact scoring with metrics computation.

**Core invariant** (DesignDoc §2.1): All expensive work (scoring) is keyed by artifact content hash and persisted to disk. A re-run of the loop must never redo work it has already done.

## Key Concepts

### Cache by Content Hash

Each artifact is scored on a dataset (train/dev/test). Results are cached by `artifact.content_hash`:

```
state/
└── cache/
    └── abc123def456789a/
        ├── artifact.txt              # The artifact (for reference)
        ├── metrics_train.jsonl       # Scores on train set
        ├── metrics_dev.jsonl         # Scores on dev set
        ├── metrics_test.jsonl        # Scores on test set
        └── diagnosis.md              # Stage-A error summary
```

If the loop is resumed, same artifacts will have cache hits → no re-scoring.

If the proposer generates artifact with identical text: same hash → cache hit.

### Parallel Scoring

With K=3 candidates and 3 splits (train/dev/test):

```
Batch iteration N:
├── Score candidate 1 on train
├── Score candidate 1 on dev
├── Score candidate 1 on test
├── Score candidate 2 on train
├── Score candidate 2 on dev
├── Score candidate 2 on test
├── Score candidate 3 on train
├── Score candidate 3 on dev
└── Score candidate 3 on test  (9 parallel scorer calls)
```

Each scorer call is independent; parallelism gives ~9× wall-clock speedup (minus overhead).

### Metrics Computed

Standard metrics for classification:

- **Kappa (κ)**: Inter-rater agreement (main optimization target)
- **Macro F1**: Per-class F1, averaged
- **Accuracy**: Percent correct
- **Spearman**: Correlation (if continuous targets)

See `compute_inter_rater_agreement()` for details.

## API Reference

### Scorer Class

```python
from scorer.scorer import Scorer
from artifacts.artifact import Artifact

# Create scorer
scorer = Scorer(
    scorer_model="claude-3-5-sonnet-20241022",
    api_key="sk-ant-...",
    max_input_tokens=32000,
    max_output_tokens=1000,
    timeout_seconds=120.0
)

# Check if cached
artifact = Artifact("Your prompt...")
if scorer.is_cached(artifact, split="dev"):
    print("Cache hit!")
    metrics = scorer.load_cached_metrics(artifact, split="dev")
else:
    print("Cache miss; scoring...")
    examples = [...]  # dev examples
    metrics = scorer.score(artifact, examples)
    # Results automatically cached

# Async scoring (for parallelism)
import asyncio
metrics = asyncio.run(scorer.score_async(artifact, examples))
```

### Caching Methods

```python
# Check cache
is_cached = scorer.is_cached(artifact, split="dev")

# Load from cache
metrics = scorer.load_cached_metrics(artifact, split="dev")

# Save to cache
scorer.save_metrics(artifact, split="dev", metrics={...})

# Get cache directory path
cache_dir = scorer.get_cache_dir(artifact)
# state/cache/abc123def456789a/
```

### Scoring Methods

```python
# Synchronous scoring
metrics = scorer.score(artifact, examples)
# Returns: {"kappa": 0.635, "macro_f1": 0.628, "accuracy": 0.651, ...}

# Asynchronous scoring (for parallelism)
import asyncio
metrics = asyncio.run(scorer.score_async(artifact, examples))

# Metrics computation (standalone)
from scorer.scorer import compute_inter_rater_agreement
metrics = compute_inter_rater_agreement(predictions, ground_truth)
```

## Scoring Pipeline

When `scorer.score(artifact, examples)` is called:

1. **Check cache**: Is `cache/HASH/metrics_<split>.jsonl` present?
   - Yes → load and return (fast path, instant)
   - No → continue to step 2

2. **Save artifact**: Write artifact text to `cache/HASH/artifact.txt` (for reference)

3. **Score all examples**: Call scorer LLM on each example
   - Input: artifact + example text
   - Output: prediction, confidence, reasoning
   - One example per scorer call (or batch if supported)

4. **Compute metrics**: Aggregate predictions
   - Compute κ, macro-F1, accuracy, Spearman
   - One JSON line per example in `cache/HASH/metrics_<split>.jsonl`

5. **Write cache**: Append metrics to `cache/HASH/metrics_<split>.jsonl`
   - Atomic: one line per example
   - Resumable: if process dies mid-batch, restart continues from last example

6. **Return**: Dict with final metrics

## Caching Strategy

### Cache Hit Scenario

```python
# First run
artifact = Artifact("prompt_v1")
metrics = scorer.score(artifact, dev_examples)  # API calls + cache write
# Took 30 seconds

# Second run (same artifact, same dataset)
metrics = scorer.score(artifact, dev_examples)  # Cache load only
# Took 0.1 seconds (100× faster!)
```

### Cache Miss Scenario

```python
# Artifact changed (even one word)
artifact1 = Artifact("prompt_v1")
artifact2 = Artifact("prompt_v2")

# Different hashes
assert artifact1.content_hash != artifact2.content_hash

# Different cache entries
scorer.score(artifact1, examples)  # Cache at state/cache/abc123.../
scorer.score(artifact2, examples)  # Cache at state/cache/def456.../
```

### Partial Cache Hit

```python
# Artifact scored on train/dev, but not test

# First call
metrics_dev = scorer.score(artifact, dev_examples)  # Cache miss → API call
# Cache: state/cache/HASH/metrics_dev.jsonl

# Second call (same artifact, test set)
metrics_test = scorer.score(artifact, test_examples)  # Cache miss → API call
# Cache: state/cache/HASH/metrics_test.jsonl (different file)

# Third call (same artifact, dev again)
metrics_dev2 = scorer.score(artifact, dev_examples)  # Cache hit!
# Loaded from state/cache/HASH/metrics_dev.jsonl
```

## Examples

### Example 1: Score Single Artifact

```python
from scorer.scorer import Scorer
from artifacts.artifact import Artifact

scorer = Scorer()
artifact = Artifact("Classify the text as positive or negative:\n\nText: {input}")

# Score on dev set
dev_examples = [
    {"id": "1", "text": "I love this!", "label": "positive"},
    {"id": "2", "text": "Terrible product", "label": "negative"},
    # ... more examples
]

metrics = scorer.score(artifact, dev_examples)
print(f"κ={metrics['kappa']:.3f}, F1={metrics['macro_f1']:.3f}")
```

### Example 2: Parallel Scoring with Caching

```python
import asyncio
from scorer.scorer import Scorer
from artifacts.artifact import Artifact

scorer = Scorer()

# Three candidate artifacts
candidates = [
    Artifact("v1"),
    Artifact("v2"),
    Artifact("v3"),
]

async def score_all():
    tasks = []
    for artifact in candidates:
        if scorer.is_cached(artifact, split="dev"):
            # Cache hit: load synchronously
            metrics = scorer.load_cached_metrics(artifact, split="dev")
            print(f"{artifact.content_hash}: cached κ={metrics['kappa']:.3f}")
        else:
            # Cache miss: score asynchronously
            task = scorer.score_async(artifact, dev_examples)
            tasks.append((artifact, task))
    
    # Wait for all async scores to complete
    results = await asyncio.gather(*[t for _, t in tasks])
    for (artifact, _), metrics in zip(tasks, results):
        print(f"{artifact.content_hash}: scored κ={metrics['kappa']:.3f}")

asyncio.run(score_all())
```

### Example 3: Check Cache Status

```python
from scorer.scorer import Scorer
from artifacts.artifact import Artifact

scorer = Scorer()
artifact = Artifact("my_prompt")

# Check what's cached
for split in ["train", "dev", "test"]:
    if scorer.is_cached(artifact, split=split):
        metrics = scorer.load_cached_metrics(artifact, split=split)
        print(f"{split}: κ={metrics['kappa']:.3f}")
    else:
        print(f"{split}: NOT CACHED (need to score)")

# Get cache directory
cache_dir = scorer.get_cache_dir(artifact)
print(f"Cache at: {cache_dir}")
import os
print(os.listdir(cache_dir))  # ['artifact.txt', 'metrics_dev.jsonl', ...]
```

### Example 4: Compute Metrics Standalone

```python
from scorer.scorer import compute_inter_rater_agreement

# Predictions from model
predictions = ["A", "B", "A", "C", "B"]

# Ground truth
ground_truth = ["A", "B", "A", "A", "B"]

# Compute metrics
metrics = compute_inter_rater_agreement(predictions, ground_truth)
print(f"κ={metrics['kappa']:.3f}")
print(f"F1={metrics['macro_f1']:.3f}")
print(f"Accuracy={metrics['accuracy']:.3f}")
```

## Cache File Formats

### artifact.txt

Plain text file containing the full artifact (prompt, config, code, etc.):

```
You are a classifier. Classify the following text:

Text: {input}

Respond with a single letter: A, B, or C.
```

### metrics_<split>.jsonl

Line-delimited JSON, one line per example scored:

```json
{"example_id": "1", "prediction": "A", "confidence": 0.95, "latency_ms": 45}
{"example_id": "2", "prediction": "B", "confidence": 0.87, "latency_ms": 52}
...
```

**Aggregate metrics** computed from all lines (e.g., kappa, F1, accuracy).

## Performance

### Scoring Latency

- **Cache hit**: ~10 ms (disk read)
- **Cache miss**: ~2-5 seconds (LLM call + disk write)
- **Parallel scoring** (K=3, 3 splits): ~6-15 seconds wall-clock (vs 45-50 serial)

### Caching Strategy Impact

With K=3 candidates per batch and 8 batches:

| Scenario | Cached | Latency |
|----------|--------|---------|
| All fresh | 0% | 8 × 15 sec = 120 sec |
| 50% duplicates | 50% | 4 × 15 sec = 60 sec |
| 90% cached | 90% | 1 × 15 sec + 9 × 0.1 sec = 15.9 sec |

**Insight**: First batch is expensive; subsequent batches cheap if reusing artifacts.

## Thread Safety

Scorer is **NOT thread-safe**. Use one scorer per thread or add locking:

```python
import threading
from scorer.scorer import Scorer

# Safe: one scorer per thread
def score_task(artifact, examples):
    scorer = Scorer()  # New instance
    metrics = scorer.score(artifact, examples)
    return metrics

threads = [
    threading.Thread(target=score_task, args=(a, e))
    for a, e in [(artifact1, ex1), (artifact2, ex2)]
]
```

Or use asyncio for parallelism without threading (recommended):

```python
import asyncio
from scorer.scorer import Scorer

scorer = Scorer()

async def main():
    tasks = [
        scorer.score_async(artifact1, examples1),
        scorer.score_async(artifact2, examples2),
    ]
    results = await asyncio.gather(*tasks)
    return results

asyncio.run(main())
```

## Future Enhancements

1. **Batch scoring**: Score multiple examples in one LLM call (save API calls)
2. **Streaming scorer**: For very large datasets, stream results instead of buffering
3. **Scorer metrics**: Track scorer cost, latency, success rate
4. **Retry logic**: Exponential backoff for API failures
5. **Scorer selection**: Different scorer models for different tasks
6. **Pairwise scoring**: Judge which artifact is better (A/B comparison)
