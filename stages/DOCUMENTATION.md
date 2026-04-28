# Stages Module — DOCUMENTATION

## Overview

The stages module implements the four refiner stages (A/B/C/M) that form the core of the autoresearch loop.

Each stage is a distinct LLM prompt that handles one cognitive task:
- **Stage A**: Diagnose failure modes
- **Stage B**: Propose improvements (K siblings)
- **Stage C**: Select next parent or merge targets
- **Stage M**: Synthesise merge of multiple parents

## Four Stages

### Stage A: Disagreement Generalisation

**Input**: Sample of training examples where the artifact disagrees with ground truth.

**Output**: Free-text generalisation of failure modes.

**Key idea**: Rather than feed raw errors to the proposer (which causes overfitting to specific examples), Stage A abstracts the errors into recurring patterns. This forces an intermediate reasoning step that makes next-stage proposals more robust.

**Example**:

Input (raw errors):
```
- Example 1: Judge predicts "positive" but label is "negative"
- Example 2: Judge predicts "neutral" but label is "positive"
- Example 3: Judge predicts "positive" but label is "negative"
```

Output (generalisation):
```
The judge struggles with three patterns:
1. False positives on subjective/opinionated content
2. Misses informal positive markers
3. Confuses sarcasm for literal positive sentiment

Recommendations: Add sarcasm examples; clarify subjective vs factual;
emphasize informal positive markers.
```

### Stage B: Proposal

**Input**:
- Parent artifact (full text)
- Stage-A diagnosis (failure modes)
- History (recent iterations + best-so-far)
- Notebook constraints (user-injected rules)

**Output**: K ∈ [1, 5] sibling candidates, each with:
- `plan_id`: Identifier for this proposal type (e.g., "add_examples")
- `rationale`: Short explanation of why this change should help
- `artifact_text`: Full modified artifact

**Key idea**: Generate K parallel, diverse proposals that each address one focused failure mode. Siblings allow the selector to compare apples-to-apples.

**Constraint**: Single-edit attribution — each proposal changes ONE thing. This is critical for learning which edits help and which don't (plan aggregation in reports).

### Stage C: Selection

**Input**: History with all metrics (κ, F1, accuracy, Spearman).

**Output**: Either `iter=N` (use iteration N as next parent) or `merge=N1,N2,...` (synthesise merge from these iterations).

**Key idea**: Rather than blindly use `argmax(dev_κ)`, ask the LLM to make a strategic decision. The LLM can:
1. Prefer recent winners (momentum)
2. Revisit older promising branches if recent iterations plateau
3. Suggest merging two complementary branches

### Stage M: Merge Synthesis

**Input**: Two or more parent artifacts.

**Output**: Single merged artifact combining strengths.

**Key idea**: Merging is a different task from incremental editing. Stage M has its own meta-prompt specialized for coherent synthesis.

## API Reference

### Stage A

```python
from stages.stage_a import StageA

stage_a = StageA()

# Diagnose errors
errors = [
    {"example_id": "1", "prediction": "A", "label": "B", "text": "..."},
    {"example_id": "2", "prediction": "C", "label": "A", "text": "..."},
]
diagnosis = stage_a.run(
    artifact_text="Your prompt...",
    errors=errors,
    batch_id="batch_00001"
)

print(diagnosis)
# "The judge struggles with [patterns]... Recommendations: [actions]..."
```

### Stage B

```python
from stages.stage_b import StageB

stage_b = StageB(batch_size=3)

# Generate proposals
candidates = stage_b.run(
    parent_artifact="Your prompt...",
    diagnosis="Pattern analysis from Stage A...",
    history_context="Recent iterations: [history]",
    notebook_constraints="User rules: [constraints]",
    batch_id="batch_00001",
    k=3  # Generate 3 candidates
)

for cand in candidates:
    print(f"{cand['plan_id']}: {cand['rationale']}")
    print(f"Artifact length: {len(cand['artifact_text'])}")

# Returns:
# [
#     {
#         "plan_id": "add_examples",
#         "rationale": "Add 5 diverse examples of sarcasm",
#         "artifact_text": "<PROMPT>...</PROMPT>"
#     },
#     ...
# ]
```

### Stage C

```python
from stages.stage_c import StageC, StageC

stage_c = StageC()

# Select next parent
decision = stage_c.run(
    history_context="Iteration metrics and plan info...",
    batch_id="batch_00001"
)

print(decision)
# {
#     "decision": "iter=5",
#     "reasoning": "iter_5 is best recent winner",
#     "confidence": 0.92
# }

# Or merge:
# {
#     "decision": "merge=[2,5]",
#     "reasoning": "Combine strengths of iter_2 and iter_5",
#     "confidence": 0.85
# }

# Parse decision
target = StageC.parse_decision_target(decision["decision"])
if isinstance(target, int):
    print(f"Using iter {target} as parent")
else:
    print(f"Merging iters {target}")
```

### Stage M

```python
from stages.stage_m import StageM

stage_m = StageM()

# Merge multiple parents
merged = stage_m.run(
    parents=[parent1_text, parent2_text],
    batch_id="batch_00001"
)

print(merged)
# "...merged artifact combining both parents..."
```

## Configuration

All stages use config from `autoresearch/paths.py`:

```python
# LLM model and API key
REFINER_MODEL = "claude-3-5-sonnet-20241022"
REFINER_API_KEY = "sk-ant-..."

# Token budgets
REFINER_MAX_INPUT_TOKENS = 40000    # For Stage B input (history, parent)
REFINER_MAX_OUTPUT_TOKENS = 8000    # For Stage B output (K artifacts)

# Retry schedule (temperature for diversity)
REFINER_TEMPERATURE_SCHEDULE = [0.0, 0.4, 0.7, 0.9]

# Batch size (K candidates per batch)
BATCH_SIZE = 3
```

## Error Handling

Each stage retries with increasing temperature on parse failure:

```python
Temperature schedule: [0.0, 0.4, 0.7, 0.9]

Attempt 1: temperature=0.0 (deterministic; if fails, likely structural)
Attempt 2: temperature=0.4 (more diverse; may help with tokenization)
Attempt 3: temperature=0.7 (more creative; helps if model stuck)
Attempt 4: temperature=0.9 (very diverse; last-resort)
```

If all retries fail, raises RuntimeError.

All attempts are saved to disk for post-mortem:

```
state/batches/batch_00001/
├── stage_a_attempt_1.txt (if failed)
├── stage_a_attempt_2.txt (if failed)
├── stage_a_output.txt (successful)
├── stage_b_attempt_1.txt (if failed)
├── stage_b_attempt_2.txt (if failed)
├── stage_b_output.json (successful)
└── ...
```

## Integration with Main Loop

The main loop orchestrates stages in sequence each batch:

```
Batch N:
  1. Stage C: Select parent (or merge targets)
  2. Stage M: If merge, synthesise merged parent
  3. Stage B: Generate K siblings from parent
  4. Score K siblings in parallel (train/dev/test)
  5. Stage A: Diagnose errors for each sibling
  6. Append K lines to experiments.jsonl
  7. Regenerate report
```

## Examples

### Example 1: Full Stage Pipeline

```python
from artifacts.artifact import Artifact
from stages.stage_a import StageA
from stages.stage_b import StageB

# 1. Score current artifact and collect errors
errors_on_train = [...]  # Failed examples

# 2. Stage A: Diagnose
stage_a = StageA()
diagnosis = stage_a.run(
    artifact_text=current_artifact,
    errors=errors_on_train,
    batch_id="batch_001"
)

# 3. Stage B: Propose improvements
stage_b = StageB(batch_size=3)
candidates = stage_b.run(
    parent_artifact=current_artifact,
    diagnosis=diagnosis,
    history_context=history_rendering,
    notebook_constraints="",
    batch_id="batch_001",
    k=3
)

# 4. Score candidates (placeholder)
for cand in candidates:
    artifact = Artifact(cand["artifact_text"])
    metrics = score(artifact, dev_examples)
    print(f"{cand['plan_id']}: κ={metrics['kappa']:.3f}")
```

### Example 2: Merge Decision

```python
from stages.stage_c import StageC
from stages.stage_m import StageM

# Stage C: Decide what to do
stage_c = StageC()
decision = stage_c.run(
    history_context=formatted_history,
    batch_id="batch_001"
)

# Parse decision
if decision["decision"].startswith("merge="):
    iters_to_merge = StageC.parse_decision_target(decision["decision"])
    
    # Stage M: Synthesise merge
    stage_m = StageM()
    merged = stage_m.run(
        parents=[get_artifact_text(i) for i in iters_to_merge],
        batch_id="batch_001"
    )
    
    # Next batch uses merged as parent
    next_parent = merged
else:
    iter_num = StageC.parse_decision_target(decision["decision"])
    next_parent = get_artifact_text(iter_num)
```

## Debugging

### Parse Failures

If Stage B output doesn't parse:

```bash
# Check saved attempts
cat state/batches/batch_001/stage_b_attempt_1.txt
cat state/batches/batch_001/stage_b_attempt_2.txt

# Check raw response
cat state/batches/batch_001/stage_b_response_raw.txt

# Common issues:
# 1. Missing JSON delimiters (```json ... ```)
# 2. Truncated output (check token budget)
# 3. Malformed JSON (missing commas, unclosed quotes)
```

### Unexpected Decisions

If Stage C makes odd decisions:

```bash
# Check decision details
cat state/batches/batch_001/stage_c_decision.json

# Check reasoning
jq .reasoning state/batches/batch_001/stage_c_decision.json

# The reasoning field explains the logic; helps debug meta-prompt issues
```

## Performance Tuning

### High Token Usage

If hitting token limits:

1. **Reduce history size** (edit history/renderer.py):
   - Show fewer recent iterations
   - Use more compact format

2. **Reduce error sample** (Stage A):
   - Show top 5 errors instead of 10

3. **Reduce parent artifact size**:
   - If prompt is very long, use summary

### High Latency

If proposals are slow:

1. **Use faster model**: Edit REFINER_MODEL in paths.py
2. **Reduce output tokens**: Lower REFINER_MAX_OUTPUT_TOKENS
3. **Parallel proposals**: Use asyncio for multiple proposals

### High Cost

If API bills are high:

1. **Reduce BATCH_SIZE** (fewer candidates per batch)
2. **Subsample dataset** (score on fewer examples)
3. **Use cheaper model** (trade quality for cost)

## Future Enhancements

1. **Caching of diagnoses**: Don't re-diagnose same errors
2. **Constrained generation**: Force JSON schema in Stage B/C
3. **Few-shot examples**: Show example good proposals in Stage B
4. **A/B testing**: Let Stage C choose between multiple selection strategies
5. **Multi-model stages**: Use different models for different stages (e.g., o1 for Stage C)
