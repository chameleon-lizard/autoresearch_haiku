# Artifacts Module — DOCUMENTATION

## Overview

The artifacts module defines the `Artifact` class, a serializable, hashable representation of optimizable objects (prompts, configs, code patches, weights, etc.).

**Core invariant** (DesignDoc §2.1): Every artifact has a deterministic content hash computed from its text. This hash is the cache key; no work is ever repeated on an artifact with the same hash.

## Key Concepts

### Content Hash

```python
artifact = Artifact("Your prompt text...")
print(artifact.content_hash)  # e.g., "abc123def456789a"
```

The content hash is:
- **Deterministic**: same text → same hash (byte-for-byte reproducible)
- **Collision-resistant**: sha256 (16-char hex)
- **Independent of metadata**: timestamps, run IDs, etc. do NOT affect the hash
- **The cache key**: scorer results, diagnoses, and metrics are stored keyed by this hash

### Why Content Hash?

1. **Resumability**: Lose the report? Regenerate from log. Re-run the loop? Cache hits short-circuit scoring.
2. **Deduplication**: If the proposer generates the same sibling twice, the second uses cached results.
3. **Immutable audit trail**: The hash is the artifact's unique identifier; it never changes.

### What's NOT in the Hash

Explicitly excluded (see DesignDoc §2.1):
- Timestamps
- Run IDs / batch IDs
- Iteration numbers
- Metadata fields
- Directory structure

Only the `artifact.text` is hashed. Metadata is stored separately (in cache subdirectories, iteration directories) but does not affect the hash.

## API Reference

### Artifact Class

```python
from artifacts.artifact import Artifact

# Create from text
artifact = Artifact(text="Your prompt here...")

# Access hash
hash_val = artifact.content_hash  # str, e.g., "abc123def456789a"

# Serialize/deserialize
text = artifact.serialize()  # str
artifact2 = Artifact.deserialize(text)
assert artifact == artifact2  # Equal by content hash

# File I/O
artifact.save_to_file(Path("my_artifact.txt"))
artifact = Artifact.load_from_file(Path("my_artifact.txt"))

# Metadata (bookkeeping, not in hash)
artifact = Artifact(
    text="...",
    metadata={"plan_id": "experiment_1", "iter": 5}
)
print(artifact.metadata)  # Dict

# String representations
str(artifact)    # "Artifact(abc123...): First 50 chars..."
repr(artifact)   # "Artifact(hash=abc123..., len=1234)"

# Equality (by content hash)
a1 = Artifact("text")
a2 = Artifact("text")
a3 = Artifact("other")
assert a1 == a2
assert a1 != a3

# Hashable (can use in sets/dicts)
s = {a1, a2}  # Set contains 1 element (a1 == a2)
d = {a1: "value"}
d[a2] = "new_value"  # Overwrites: a1 == a2
```

### ArtifactSet Class

```python
from artifacts.artifact import ArtifactSet

# Deduplicating set
artifacts = ArtifactSet()
artifacts.add(Artifact("text1"))
artifacts.add(Artifact("text1"))  # Ignored
artifacts.add(Artifact("text2"))

print(len(artifacts))  # 2

# Membership
a = Artifact("text1")
print(a in artifacts)  # True

# Iteration
for artifact in artifacts:
    print(artifact.content_hash)

# Lookup by hash
hash_val = "abc123def456789a"
artifact = artifacts.get_by_hash(hash_val)
```

## Cache Layout

Artifacts are stored in the cache directory by content hash:

```
state/
└── cache/
    ├── abc123def456789a/
    │   ├── artifact.txt              # The artifact text
    │   ├── metrics_train.jsonl       # Scorer results on train set
    │   ├── metrics_dev.jsonl         # Scorer results on dev set
    │   ├── metrics_test.jsonl        # Scorer results on test set
    │   └── diagnosis.md              # Stage-A error summary
    │
    └── def456789abc123a/
        └── ...
```

The cache key is `artifact.content_hash`. If two different runs generate identical artifact text, they will find the same cache entry and reuse scoring results.

## Examples

### Example 1: Create and Cache an Artifact

```python
from pathlib import Path
from artifacts.artifact import Artifact
from autoresearch.paths import CACHE_DIR

# Create artifact
prompt = """
You are a classifier. Classify the following text:

Text: {input}

Respond with a single letter: A, B, or C.
"""
artifact = Artifact(text=prompt)

# Save to cache
cache_subdir = CACHE_DIR / artifact.content_hash
cache_subdir.mkdir(parents=True, exist_ok=True)
artifact.save_to_file(cache_subdir / "artifact.txt")

print(f"Cached at: {cache_subdir}")
print(f"Hash: {artifact.content_hash}")
```

### Example 2: Load Artifact and Check Cache

```python
from pathlib import Path
from artifacts.artifact import Artifact

# Load from cache
cache_path = Path("state/cache/abc123def456789a/artifact.txt")
artifact = Artifact.load_from_file(cache_path)

# Check if metrics cached
metrics_dev = cache_path.parent / "metrics_dev.jsonl"
if metrics_dev.exists():
    print("Metrics cached; can skip scoring")
else:
    print("Metrics not cached; need to score this artifact")
```

### Example 3: Deduplicate Artifacts

```python
from artifacts.artifact import Artifact, ArtifactSet

# Proposer generates 5 candidates; some are duplicates
candidates = [
    Artifact("prompt_v1"),
    Artifact("prompt_v2"),
    Artifact("prompt_v1"),  # Duplicate
    Artifact("prompt_v3"),
    Artifact("prompt_v2"),  # Duplicate
]

# Deduplicate
unique = ArtifactSet()
for c in candidates:
    unique.add(c)

print(f"Generated 5, unique {len(unique)}")  # 3
for artifact in unique:
    print(f"Will score: {artifact.content_hash}")
```

## Integration with Loop

The main loop uses artifacts as follows:

1. **Stage M (merge)**: Takes N parent artifacts → produces 1 merged artifact
2. **Stage B (proposal)**: Takes 1 parent artifact → produces K sibling artifacts
3. **Scoring**: For each artifact, check if `artifact.content_hash` in cache
   - If cached: use metrics from disk (fast path)
   - If not cached: run scorer → write to cache
4. **Stage A (diagnosis)**: Reads cached metrics for an artifact
5. **Stage C (selection)**: Compares artifacts by their `content_hash` keys in the log

## Hash Collision Risk

SHA256 produces 256-bit hashes; we use first 16 hex chars = 64 bits.

Birthday paradox: after ~2^32 ≈ 4 billion artifacts, expect 50% collision probability.

**For practical purposes**: 16 chars is sufficient for ~10 million artifacts (< 0.1% collision chance).

If you need stronger guarantees, extend to 32 chars (full SHA256 hex):

```python
@property
def content_hash(self) -> str:
    h = hashlib.sha256(self.text.encode("utf-8")).hexdigest()  # Full 64 chars
    return h
```

## Thread Safety

`Artifact` and `ArtifactSet` are NOT thread-safe (no locking). If using multithreaded scorer:

```python
import threading

# Safe approach: one ArtifactSet per thread, or use a lock
artifact_lock = threading.Lock()

artifacts = ArtifactSet()

def score_safely(artifact):
    with artifact_lock:
        artifacts.add(artifact)
```

Or use a queue/thread-pool abstraction (see scorer.py for example).

## Serialization Format

Currently, artifacts are stored as plain text files (one artifact per file).

If you need to store structured metadata alongside text, consider JSONL:

```json
{
  "artifact_text": "...",
  "metadata": {"plan_id": "...", "created_by": "stage_b"},
  "content_hash": "abc123def456789a"
}
```

To upgrade: modify `Artifact.save_to_file()` and `Artifact.load_from_file()` to read/write JSON.

## Debugging

```python
from artifacts.artifact import Artifact

a = Artifact("My prompt...")

# Inspect
print(f"Hash: {a.content_hash}")
print(f"Length: {len(a.text)} chars")
print(f"First 100 chars: {a.text[:100]}")

# Debug equality
b = Artifact("My prompt...")
c = Artifact("Different")
print(f"a == b: {a == b}")  # True (same text)
print(f"a == c: {a == c}")  # False
print(f"a.content_hash == b.content_hash: {a.content_hash == b.content_hash}")

# Check metadata
print(f"Metadata: {a.metadata}")
```
