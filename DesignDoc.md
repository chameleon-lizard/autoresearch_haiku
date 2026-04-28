# Autoresearch Loops — Design Document

This document distils the design patterns, invariants, and lessons learned from
building an autonomous LLM-driven optimisation loop. It is intentionally
**task-agnostic**: substitute "artifact" for whatever you are evolving (prompt,
config, code patch, schema, hyperparameters), "scorer" for whatever produces
the metric (LLM judge, unit-test runner, simulator, human eval), and "metric"
for the multi-dimensional success signal you want to maximise.

The reference implementation lives in `autoresearch/`. This doc describes the
*pattern*, not the implementation.

---

## 1. What is an autoresearch loop?

An autoresearch loop is a long-running process that:

1. **Scores** a current candidate artifact on a labelled dataset.
2. **Diagnoses** what the artifact gets wrong (relative to ground truth).
3. **Proposes** mutations of the artifact that target those failure modes.
4. **Selects** which proposal to keep, based on held-out signal.
5. Repeats — indefinitely — accumulating a growing record of which mutations
   helped and which did not.

The unique requirement is **autonomy**: no human in the inner loop. The loop
must protect itself against overfitting, be safe to interrupt, and produce an
audit trail another process (or a future you) can replay.

---

## 2. Core invariants

The loop's correctness rests on a small set of invariants. Violating any of
them produces silent failure modes that are hard to debug after the fact.

### 2.1 Cache by content hash
Every artifact has a deterministic id `sha256(serialise(artifact))[:16]`. All
expensive work (scoring, diagnosis) is keyed by that id and persisted to disk.
A re-run of the loop must **never** redo work it has already done.

- Keep the artifact text alongside the cached results so the cache is
  self-describing.
- Don't include timestamps, run ids, or other non-functional state in the
  hash input — that defeats the cache.
- The cache is your friend during refactor: changing the loop and re-running
  should reproduce identical metrics for already-seen artifacts.

### 2.2 Append-only experiment log
There is exactly one ground-truth file (`experiments.jsonl` in our case) where
every iteration writes one JSON line: `{iter, ts, artifact_hash, parent,
plan_id, rationale, metrics_train, metrics_dev, metrics_test, …}`. Earlier
lines are **never** rewritten. All higher-level views (reports, dashboards,
selector input) are derived from this log.

This gives you:
- Resumability: lose the report, regenerate it from the log.
- Audit: every claimed improvement has a single line of provenance.
- Time-travel: replay the loop's state at any historical point.

### 2.3 Crash- and Ctrl+C-safe
Every write to disk is line-buffered or atomic. If the process dies mid-batch,
restarting from scratch must not corrupt state and must skip any work the
cache already covers.

In practice: the scorer subprocess (e.g. `dredd.py`) writes one judgment per
line and skips ids it has already judged. The loop reads back the partial file
on resume.

### 2.4 Held-out evaluation set
Split the dataset into **train / dev / test** (we used 40 / 20 / 40 stratified
by domain). The loop sees train + dev. Test is logged but **never** surfaced
to the proposer or the selector. Test exists to detect that the loop is
overfitting dev — which it eventually will, because the selector's job is
exactly to climb dev.

If you skip this and let the loop see test, you will get monotone-improving
test metrics that are pure leakage. We saw this in practice: iter_27's dev κ
was 0.335 but its test κ was 0.231 — a 0.10 gap caused by the selector having
peeked at dev for ~30 iterations.

### 2.5 Single-edit attribution
Each candidate is a sibling that applies **one** focused change to its parent.
Multi-change candidates are forbidden because you cannot tell which sub-change
caused the Δ-metric. Aggregate stats per `plan_id` (proposed N times, won M
times, mean Δ) only become meaningful when each iteration is one edit.

### 2.6 Bi-directional notebook
A shared text file that the user can edit at any time during a run, and that
the agent can append to between iterations. User sections are hard
constraints; agent sections are observations. Re-read fresh every iteration
(never cached). This gives the human an out-of-band channel to inject domain
knowledge mid-run without restarting.

---

## 3. Reference architecture

```
       ┌──────────────┐
       │ ground truth │
       └──────┬───────┘
              │
              ▼
       ┌──────────────┐         ┌────────────────────┐
       │ stratified   │────────▶│ train / dev / test │
       │ split (seed) │         │   (deterministic)  │
       └──────────────┘         └─────────┬──────────┘
                                          │
                                          ▼
   ┌────────────────────────────────────────────────────┐
   │  iter loop (batch mode):                           │
   │                                                    │
   │   1. Stage C  selector → pick parent (or merge)    │
   │   2. Stage M  if merge: synthesise base artifact   │
   │   3. Stage B  proposer → K sibling candidates      │
   │   4. score K candidates in parallel (cache hits!)  │
   │   5. Stage A  diagnose each candidate's errors     │
   │   6. append K lines to experiments.jsonl           │
   │   7. regenerate experiments_report.md              │
   │                                                    │
   └────────────────────────────────────────────────────┘
                                          │
                                          ▼
                                ┌──────────────────────┐
                                │  state/cache/<hash>/ │
                                │  state/iterations/   │
                                │  state/batches/      │
                                └──────────────────────┘
```

Each box is a separate file/module so each can be unit-tested in isolation:
splitter, scorer driver, metrics, refiner stages, report generator, main
loop.

---

## 4. The four refiner stages (A / B / C / M)

The proposer LLM (call it the **refiner** to distinguish from the scorer LLM)
is prompted in four distinct modes, each with its own meta-prompt:

### Stage A — Disagreement generalisation
Input: a sample of training examples where the candidate disagrees with
ground truth, balanced across error types.
Output: a free-text **generalisation** of the failure modes (e.g. "judge
penalises long answers even when length is justified").
Why: feeding raw errors to the proposer encourages overfitting to those
specific examples. Forcing an abstraction step makes the next-stage proposal
more robust.

### Stage B — Proposal
Input: parent artifact (full text), Stage-A summary, history (some full,
most compact), shared notebook.
Output: K ∈ [1, 5] sibling candidates, each with `plan_id`, `rationale`,
and the new artifact text (between explicit delimiters like `<PROMPT>…
</PROMPT>`).
Why K parallel: each is one focused edit; scoring K in parallel multiplies
throughput; sibling design lets the next selector compare apples-to-apples.

### Stage C — Selection
Input: history with metrics, current "best so far" callout.
Output: either `iter=N` (use that single iteration as next parent) or
`merge=N1,N2,…` (synthesise a merge from these parents).
Why ask the LLM and not argmax: argmax overfits to one metric and ignores
the trajectory; the LLM sees the full history and can choose to revisit an
older promising branch when recent batches plateau.

### Stage M — Merge synthesis
Input: two or more parent artifacts to merge.
Output: a single new base artifact that combines them.
Why distinct from B: merging is a different cognitive task than proposing a
delta. It needs its own meta-prompt, and its output becomes the parent for
the next Stage-B batch (so it gets scored on its own merits before any
further edits).

---

## 5. Batch mode and parallel scoring

**Batch** = one outer-loop iteration that produces K siblings.

- The selector runs once per batch (not per candidate).
- All K candidates are scored against train, dev (and test, observationally)
  in parallel — typically K × 3 = 15 scorer subprocesses. Cache hits
  short-circuit any artifact you've already seen.
- All K rows hit `experiments.jsonl` together with the same `batch_id`.

This delivers ~K× wall-clock speedup over serial mode, at the cost of letting
K-1 candidates live or die without cross-information from their siblings. In
our experience that is a good trade — the selector's next decision will pick
whichever of the K worked.

---

## 6. History rendering: compact vs full

The proposer needs to see the past to avoid re-proposing failed edits, but
context budgets are finite.

**Rule of thumb we converged on:**

| Item | Render |
|---|---|
| Best-so-far artifact | Full text + all metrics + Stage-A summary |
| Last N=5 iterations | Full text + metrics + summary |
| Direct parent + parents being merged | Full text (always) |
| Everything else | One line: `iter=N batch=B parent=P plan=… train-κ=… dev-κ=…` |

Plus an auto-generated `experiments_report.md` (deterministic from the log)
with per-batch tables and a `plan_id` aggregate ("plan X was proposed 3
times, won 1, mean Δ=−0.018"). This gives the proposer the long-range trend
without dumping 50 prompts into context.

The compact format must include enough provenance (batch, parent, plan_id,
rationale, **all** metric components) that the proposer can identify a
promising older branch and ask the selector to revisit it.

---

## 7. Stochasticity for retries

LLM outputs sometimes fail to parse (missing delimiter, truncated output,
malformed JSON). The retry loop must vary the temperature; otherwise greedy
decoding produces byte-identical replies and you waste retries.

Concrete schedule that worked: `[0.0, 0.4, 0.7, 0.9]` — first attempt deterministic,
then increasing diversity. Save every attempt's full reply to disk for
post-mortem.

If the failure is "output truncated mid-thought", the cause is usually the
**server-side** `max_total_tokens` cap (input + output share one budget),
not your request-side `max_tokens`. Compress the input (use the compact
history rendering above) instead of bumping the request limit further.

---

## 8. Observability

The loop runs unattended for hours. You need to be able to glance at it and
know what's happening.

- **Live terminal blocks**: print the model's reasoning prose (the leading
  text before the structured output block) under a banner like
  `[batch 47] Stage B plan rationale`. Cap each block at ~1500 chars.
- **Per-attempt dumps on failure**: write `stage_b_attempt_{1..4}.txt` to a
  batch directory whenever proposal fails to parse, with metadata
  (length, has-think-open, has-think-close, parse-tag presence) to make
  diagnosis a one-glance affair.
- **Auto-regenerated report** after every batch. Open it in another window
  and watch the table grow.
- **State-directory snapshots**: dump the notebook before and after every
  batch (`notes_before.md`, `notes_after.md`) so you can see what the
  agent added or what the user injected mid-run.

---

## 9. Multi-instance support

Set the state directory via env var, not hard-coded path:

```
STATE_DIR = Path(os.environ.get("AUTORESEARCH_STATE_DIR", default))
```

Then `AUTORESEARCH_STATE_DIR=/tmp/runA AUTORESEARCH_STATE_DIR=/tmp/runB`
can run side-by-side without scribbling over each other. We used this to
run one pipeline per scorer model in parallel.

---

## 10. Lessons learned (the surprising ones)

These are observations that were not obvious going in.

### 10.1 Aggregating winners ≠ improvement
We catalogued every "winning" iteration (16 wins out of 48 proposals) and
manually merged all their distinguishing edits into one combined artifact
("ultimate prompt"). Result: **dev κ dropped from 0.335 to 0.196** while
test κ moved +0.013. The marginal winners were noise; combining them
over-constrains the artifact and removes coherence. Greedy hill-climbing
on dev does not produce a globally-good artifact via post-hoc concatenation.

**Implication**: trust the loop's own selector. If the selector chose a
specific lineage, that lineage *is* the best aggregate, by construction.

### 10.2 First edit dominates
The first major win in our loop was **+0.115 dev κ**. Every subsequent
winner was +0.001 to +0.028. The loop spends most of its time finding
microscopic improvements over a strong baseline. Once you cross the
diminishing-returns boundary, batch K=1 mode (faster cycle) often beats
batch K=5 (more candidates per batch).

### 10.3 ~⅓ of proposals win
With our setup, win rate was 16 / 48 ≈ 33% (a "win" being any positive
Δ on dev). If your proposer's win rate falls below ~20%, your meta-prompt
or your dataset is too noisy and you are exploring noise rather than
signal.

### 10.4 Selector overfit is real
At iteration 27 our dev κ = 0.335 but combined-split κ = 0.274 and test
κ = 0.231. The dev–test gap of 0.10 is the cumulative price of letting the
selector see dev for 27 iterations. Keep the gap visible in the dashboard;
when it grows monotonically, the loop is overfitting dev and it is time
to pause or to widen the dataset.

### 10.5 Use multiple correlated metrics, not one
Optimising on a single metric (κ alone) is brittle — small label-set
shifts can move it sharply. Track three (κ, macro-F1, Spearman) and require
the selector to "jointly maximise" them. If the metrics disagree, that
itself is signal that the new artifact is changing the response
distribution, not just calibration.

### 10.6 Wrap, don't reimplement
The scorer in our case (dredd) is a mature CLI tool with built-in caching,
A/B position-swap, and retry logic. We wrap it via subprocess and inherit
all of that for free, instead of reimplementing scoring in-process. The
extra ~200 ms per call is irrelevant against scorer-LLM latency, and the
cost of *not* having the scorer's battle-tested behaviour would have been
weeks.

### 10.7 The notebook is load-bearing
The shared bidirectional notebook (`notes.md`) was added late but became
the most useful intervention surface. Mid-run we could write
`## USER\nDo not propose any more length-related edits, that lever is
exhausted` and the next batch would respect it. Without this, the only
lever is restart-the-loop.

### 10.8 Greedy retries are useless
`temperature=0` retries on parse failures produce byte-identical replies.
Always vary temperature across attempts. This wasted ~6 hours of compute
in our pilot before we noticed.

### 10.9 Server token budgets bite
SGLang (and most serving stacks) cap **input + output** together. A long
prompt with a long expected response will silently truncate. Watch for
`</think>=False` in the output (i.e. the model never closed its reasoning
block) — that is the symptom. Fix: compress the input, do not bump the
request-side `max_tokens`.

### 10.10 Document while building
Per-module `DOCUMENTATION.md` and a top-level `WIKI.md` / `OPS.md` are not
overhead — they are the artifact that lets a future Claude Code session (or
human) resume the project. We wrote them as TODOs alongside the code, not
after the fact.

---

## 11. Anti-patterns (do not do)

| Anti-pattern | Why it bites you |
|---|---|
| Recompute scoring on every loop start | Wastes 100% of budget; no excuse — hash-cache |
| Single-metric selection | Selector finds metric pathologies, not real improvements |
| No held-out test set | Loop overfits dev; you only find out at deployment |
| Mutate multiple things per candidate | No attribution; can't aggregate plan-level stats |
| Selector = `argmax(dev_metric)` | Misses the case where an older branch is the best base |
| Deterministic retries | Retries produce identical output; pure waste |
| In-loop human review | Defeats the point; use the notebook for async injection |
| Modifying earlier log lines | Breaks resumability and audit; treat the log as immutable |
| Scoring serially across candidates | Easy K× speedup left on the floor |
| Embedding paths in code | Multi-instance impossible; centralise in `paths.py` |
| Live editing the artifact under the cache | Cache key becomes wrong; mysterious correctness drift |

---

## 12. Minimal CLI surface

A useable autoresearch loop needs only:

```
loop run                   # main loop, infinite
loop run --max-iters N     # bounded for tests
loop run --limit N         # subsample dataset for fast smoke test
loop report                # regenerate experiments_report.md from log
loop reset                 # delete iterations + log; preserve cache
loop score <artifact>      # score one artifact, print metrics, no proposal
```

Everything else (judge URL, model name, K, parallelism) is config in one
YAML or `paths.py`-style module — never CLI flags scattered across files.

---

## 13. When *not* to use this pattern

Autoresearch is appropriate when:

- The artifact is small (< 100 KB) and changes are local edits.
- Scoring is automatic, deterministic-given-cache, and cheap relative to
  proposal.
- Ground truth exists at scale (~1000+ labelled examples).
- The metric you optimise correlates with the property you actually care
  about (verify this before building the loop, not after).

It is the wrong pattern when:

- Scoring requires human judgement that cannot be cached or reused.
- The artifact is a large codebase: edits compose in non-local ways and
  per-iter scoring becomes a full CI run.
- Your dataset has < 200 examples — the dev-overfit risk swamps any
  optimisation signal.
- The proposer LLM is no smarter than the scorer LLM; in that case the
  loop just walks a random path through artifact space.

---

## 14. Checklist for adopting this pattern in a new project

- [ ] Define artifact serialisation; pick the hash.
- [ ] Build the splitter; verify split is deterministic and stratified.
- [ ] Wrap the scorer; verify the cache works (re-run = no scorer calls).
- [ ] Implement metrics module; verify it agrees with any existing
      reference implementation byte-for-byte.
- [ ] Write Stage-A meta-prompt; eyeball 3 sample outputs before automating.
- [ ] Write Stage-B meta-prompt; verify K=1 K=3 K=5 all parse.
- [ ] Implement Stage-C selector; verify it picks reasonable parents on
      hand-crafted history.
- [ ] Add Stage-M merger if your space rewards combining branches.
- [ ] Implement append-only log + report regenerator.
- [ ] Add live observability blocks and per-attempt dumps.
- [ ] Add the bi-directional notebook.
- [ ] Smoke-test with `--limit 20` end-to-end before any long run.
- [ ] Document everything in module-local `DOCUMENTATION.md`.
- [ ] Run for ≥ 10 batches and inspect the dev–test gap; halt if it
      diverges.
