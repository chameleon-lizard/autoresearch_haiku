# Splitter Module — DOCUMENTATION

## Overview

The splitter module provides deterministic, stratified splitting of labelled datasets into train/dev/test splits.

**Core invariant** (DesignDoc §2.4): The loop sees train + dev metrics. Test metrics are logged but never surfaced to the proposer/selector. This allows detecting overfitting: if the dev–test gap grows monotonically, the selector is overfitting dev.

## Key Concepts

### Deterministic Split

Same seed → identical split every time. This ensures reproducibility across runs:

```python
splitter1 = DatasetSplitter(dataset_path, seed=42)
splitter2 = DatasetSplitter(dataset_path, seed=42)
assert splitter1.get_train() == splitter2.get_train()  # Identical
```

### Stratified Split

If dataset has a `"domain"` field, the splitter respects domain proportions:

**Input dataset:**
```
{"id": "1", "text": "...", "label": "A", "domain": "science"}
{"id": "2", "text": "...", "label": "B", "domain": "science"}
{"id": "3", "text": "...", "label": "A", "domain": "law"}
{"id": "4", "text": "...", "label": "B", "domain": "law"}
```

**Stratified split (seed=42):**
- If 50% science, 50% law in full dataset
- Then 50% science, 50% law in train, dev, AND test
- Ensures each split has same domain distribution

Without stratification, random split might put all science in train, all law in test → metrics not comparable.

### Train / Dev / Test Roles

- **Train**: Loop sees train metrics; proposer can use for feedback
- **Dev**: Loop sees dev metrics; selector uses for decisions (greedy climb)
- **Test**: Logged but never surfaced to proposer/selector; detects overfitting

Default split: 40% train, 20% dev, 40% test (from DesignDoc).

## API Reference

### DatasetSplitter Class

```python
from splitter.splitter import DatasetSplitter
from pathlib import Path

# Create splitter
splitter = DatasetSplitter(
    dataset_path=Path("data/dataset.jsonl"),
    train_ratio=0.4,
    dev_ratio=0.2,
    test_ratio=0.4,
    seed=42,
    stratify_by_domain=True
)

# Get splits
train = splitter.get_train()      # List[Dict]
dev = splitter.get_dev()          # List[Dict]
test = splitter.get_test()        # List[Dict]
all_ex = splitter.get_all()       # train + dev + test

# Statistics
stats = splitter.stats()
# {
#     "total": 1000,
#     "train": 400,
#     "dev": 200,
#     "test": 400,
#     "train_ratio": 0.4,
#     "dev_ratio": 0.2,
#     "test_ratio": 0.4,
#     "stratified_by_domain": True
# }
```

### subsample_dataset Function

```python
from splitter.splitter import subsample_dataset

# For smoke testing: use only 50 examples
examples = splitter.get_train()
sampled = subsample_dataset(examples, limit=50)
print(len(sampled))  # 50

# No limit
all_ex = subsample_dataset(examples, limit=None)
print(len(all_ex))  # Same as len(examples)
```

## Dataset Format

The splitter expects JSONL (line-delimited JSON):

```json
{"id": "ex_001", "text": "Example input", "label": "A", "domain": "science"}
{"id": "ex_002", "text": "Another input", "label": "B", "domain": "law"}
...
```

**Required fields:**
- `id`: Unique example identifier (string)
- `text`: Input text (string)
- `label`: Ground-truth label (any JSON type)

**Optional:**
- `domain`: Domain/category for stratification (string)
- Other fields: Passed through to scorer

## Examples

### Example 1: Basic Split

```python
from pathlib import Path
from splitter.splitter import DatasetSplitter

# Split dataset
splitter = DatasetSplitter(
    dataset_path=Path("data/dataset.jsonl"),
    train_ratio=0.5,
    dev_ratio=0.25,
    test_ratio=0.25,
    seed=42
)

# Use splits
train_examples = splitter.get_train()
dev_examples = splitter.get_dev()
test_examples = splitter.get_test()

print(f"Train: {len(train_examples)}, Dev: {len(dev_examples)}, Test: {len(test_examples)}")

# Inspect one example
print(train_examples[0])
# {
#     "id": "ex_001",
#     "text": "...",
#     "label": "A",
#     "domain": "science"
# }
```

### Example 2: Stratified by Domain

```python
# With stratification
splitter = DatasetSplitter(
    dataset_path=Path("data/dataset.jsonl"),
    train_ratio=0.4,
    dev_ratio=0.2,
    test_ratio=0.4,
    seed=42,
    stratify_by_domain=True  # Respect domain proportions
)

# If input has 60% science, 40% law:
# Train will have ~60% science, 40% law
# Dev will have ~60% science, 40% law
# Test will have ~60% science, 40% law

# Without stratification (stratify_by_domain=False):
# Random split might have 70% science in train, 50% in dev, etc.
```

### Example 3: Smoke Test with Subsampling

```python
from splitter.splitter import DatasetSplitter, subsample_dataset

# Full split
splitter = DatasetSplitter(
    dataset_path=Path("data/dataset.jsonl"),
    train_ratio=0.4,
    dev_ratio=0.2,
    test_ratio=0.4,
    seed=42
)

# But subsample for fast smoke test
train = subsample_dataset(splitter.get_train(), limit=50)
dev = subsample_dataset(splitter.get_dev(), limit=25)
test = subsample_dataset(splitter.get_test(), limit=25)

print(f"Smoke test: {len(train)} train, {len(dev)} dev, {len(test)} test")

# Run loop with subsampled data
# After smoke test passes, run full loop:
# train = splitter.get_train()  (without limit)
```

### Example 4: Print Split Statistics

```python
splitter = DatasetSplitter(
    dataset_path=Path("data/dataset.jsonl"),
    train_ratio=0.4,
    dev_ratio=0.2,
    test_ratio=0.4,
    seed=42
)

stats = splitter.stats()
print(f"Total examples: {stats['total']}")
print(f"Train: {stats['train']} ({stats['train_ratio']:.1%})")
print(f"Dev: {stats['dev']} ({stats['dev_ratio']:.1%})")
print(f"Test: {stats['test']} ({stats['test_ratio']:.1%})")
print(f"Stratified: {stats['stratified_by_domain']}")
```

## Determinism

The splitter is deterministic if and only if:

1. **Same seed**: Pass `seed=42` (or any fixed number)
2. **Same dataset file**: Same bytes on disk
3. **Same split ratios**: Same `train_ratio`, `dev_ratio`, `test_ratio`
4. **Same code**: No changes to splitter.py logic

If any of these change, the split will differ.

**Use case**: After making a code change, run both old and new code on same dataset/seed. If split is identical, your change is safe.

## Overfitting Detection

The dev–test gap reveals selector overfitting:

```python
# After each batch, compute:
dev_kappa = latest_metrics["dev"]["kappa"]
test_kappa = latest_metrics["test"]["kappa"]
gap = dev_kappa - test_kappa

# Log gap over time
for iter in range(1, 50):
    gap = ... (from experiments.jsonl)
    print(f"Iter {iter}: gap = {gap:.3f}")
    
# If gap grows monotonically, selector is overfitting dev
# Action: pause loop, widen train set, or review selector meta-prompt
```

## Edge Cases

### Empty Dataset

```python
# Raises ValueError
splitter = DatasetSplitter(Path("data/empty.jsonl"))
# ValueError: Dataset is empty
```

### Single Example

```python
# With 1 example, splitting doesn't make sense
# But code doesn't error; just produces tiny splits
splitter = DatasetSplitter(
    Path("data/one_example.jsonl"),
    train_ratio=0.5,
    dev_ratio=0.25,
    test_ratio=0.25,
    seed=42
)
# train: 0, dev: 0, test: 1  (all rounding down)
```

### Ratios Don't Sum to 1.0

```python
# Raises ValueError
splitter = DatasetSplitter(
    Path("data/dataset.jsonl"),
    train_ratio=0.4,
    dev_ratio=0.3,  # Oops, forgot test_ratio
    test_ratio=0.3
)
# ValueError: Ratios must sum to 1.0
```

### No Domain Field but stratify_by_domain=True

```python
# No error; just falls back to simple random split
splitter = DatasetSplitter(
    Path("data/no_domain_field.jsonl"),
    stratify_by_domain=True
)
# Still works; ignores domain (not present in data)
```

## Performance

- **Time**: O(N log N) due to sorting within domains
- **Memory**: O(N) to hold entire dataset in memory

For ~100k examples: <1 second, <500 MB RAM.

For larger datasets (>1M examples): Consider lazy streaming split instead of loading all in memory.

## Thread Safety

DatasetSplitter is **NOT thread-safe** (no locking). Use one instance per thread:

```python
import threading

# Safe: one splitter per thread
def thread_func(thread_id):
    splitter = DatasetSplitter(Path("data/dataset.jsonl"), seed=42 + thread_id)
    train = splitter.get_train()
    # Use train
    
threads = [threading.Thread(target=thread_func, args=(i,)) for i in range(4)]
for t in threads:
    t.start()
```

Or use a lock if sharing one instance:

```python
import threading

splitter = DatasetSplitter(Path("data/dataset.jsonl"), seed=42)
lock = threading.Lock()

def thread_func():
    with lock:
        train = splitter.get_train()
    # Use train (outside lock)
```

## Future Enhancements

1. **Lazy loading**: Stream examples instead of loading all into memory
2. **Stratification by label**: Maintain label proportions across splits
3. **Group stratification**: Keep related examples together (e.g., paragraphs from same document)
4. **Cross-validation**: Generate K folds instead of train/dev/test
5. **Time-series split**: Respect temporal ordering for time-series data
