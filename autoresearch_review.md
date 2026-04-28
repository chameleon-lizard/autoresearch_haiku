# Autoresearch Implementations — Comparative Review

Comparison of five implementations of the autoresearch loop, evaluated against
[`DesignDoc.md`](DesignDoc.md) (the design pattern) and [`AGENTS.md`](AGENTS.md)
(documentation/git/ops conventions).

| Directory | Verdict at a glance |
|---|---|
| [`codex-spark/`](https://github.com/chameleon-lizard/autoresearch_codex_spark) | Best documented; **does not import** — two blocker bugs |
| [`gemma-31b-openrouter/`](https://github.com/chameleon-lizard/autoresearch_gemma_4_31b_openrouter) | Skeleton only — **does not import**; refiner stages stubbed with mock data |
| [`qwen-27b-openrouter/`](https://github.com/chameleon-lizard/autoresearch_qwen_27b_openrouter) | **Runs**; 39 tests pass; medium cache-key bug; closest to ready |
| [`qwen-27b-q4_k_m/`](https://github.com/chameleon-lizard/autoresearch_qwen_27b_q4_k_m) | **Runs**; complete features; **critical leakage bug** (test metrics shown to selector) |
| [`haiku/`](https://github.com/chameleon-lizard/autoresearch_haiku) | **Runs**; complete CLI + thorough docs; scorer & Stage-A sampler stubbed; no tests |

---

## 1. Headline summary

Two of the five implementations cannot be imported as Python packages:

- **`codex-spark`** — `core/__init__.py` imports `core.types` which does not exist (the file is `autoresearch/types.py`); `runner.py` calls `StatePaths.read_text()` which is not defined. Both prevent any execution.
- **`gemma-31b-openrouter`** — `autoresearch/loop.py:40` uses `Tuple` without importing it; `autoresearch/__init__.py` is missing. Even if imports were fixed, the four refiner stages (`refiner.py:15-72`) return mock/static data — the loop has no real LLM integration.

Three implementations import and run:

- **`qwen-27b-openrouter`** — 39 unit tests pass, CLI responds, all DesignDoc invariants present and largely correct. One medium-severity bug: `loop.py:266` uses `candidate.plan_id[:16]` as the cache key instead of `sha256(artifact)[:16]`, violating invariant 2.1.
- **`qwen-27b-q4_k_m`** — feature-complete, signal-safe, atomic writes, stochastic retries — but `prompts.py:235` includes `metrics_test` in the Stage C selector prompt, **directly violating invariant 2.4** (test set leakage). This single line invalidates held-out evaluation.
- **`haiku`** — imports cleanly, CLI runs, all six CLI commands present, all six per-module DOCUMENTATION.md files present, 22 KB OPS.md. **But the scoring pipeline is stubbed** (multiple `# TODO` markers in `scorer/scorer.py`) and Stage A's error sampler at `loop.py:234` returns placeholder data. Test metrics also reach the proposer's history rendering (`loop.py:219-230`), partially violating invariant 2.4. No unit tests at all.

The two non-running implementations have the cleaner architecture on paper. The three running implementations have real, end-to-end machinery — but each has at least one bug or unfinished hot path that breaks a core invariant.

---

## 2. DesignDoc.md invariant matrix

Legend: ✅ implemented · ⚠ partial / has bug · ❌ missing

| Invariant / Stage | codex-spark | gemma-31b-openrouter | qwen-27b-openrouter | qwen-27b-q4_k_m | haiku |
|---|---|---|---|---|---|
| 2.1 Content-hash cache (`sha256[:16]`) | ✅ `core/utils.py:25-27` | ✅ `cache.py:7-11` | ⚠ uses `plan_id[:16]` at `loop.py:266` | ✅ `cache.py:26-40`, atomic rename | ✅ `artifacts/artifact.py:45-59`; `scorer/scorer.py:53-70` |
| 2.2 Append-only `experiments.jsonl` | ✅ `core/state.py:15-18` | ✅ `loop.py:28-29` | ✅ `history.py:49-59` | ✅ `report.py:36-53` | ✅ `loop.py:276-278` |
| 2.3 Crash/Ctrl+C safe writes | ✅ `core/utils.py:30-46` (fsync) | ⚠ line-buffered, no resume | ✅ KeyboardInterrupt handler | ✅ atomic rename + signal handlers | ⚠ append-mode only; `loop.py:105-108` breaks on exception with no recovery |
| 2.4 Train/dev/test 40/20/40 stratified | ✅ `core/splitter.py:8-46` | ✅ `splitter.py:12` | ✅ `splitter.py` | ⚠ **test leaks to selector** (`prompts.py:235`) | ⚠ split correct (`splitter.py:40-102`) but **test metrics reach proposer history** (`loop.py:219-230`) |
| 2.5 Single-edit attribution | ✅ `stages/stage_b.py:68-100` | ⚠ no semantic validation | ✅ `refiner.py:189-246` | ✅ `stage_b.py:45-90` | ✅ K candidates with one `plan_id` each (`stage_b.py:1-80`); aggregates in `report.py:96-108` |
| 2.6 Bi-directional `notes.md` | ⚠ `paths.read_text()` undefined | ✅ `loop.py:99` re-reads | ✅ `notebook.py` | ✅ snapshots before/after | ✅ re-read each iter (`loop.py:261-265`); snapshots (`loop.py:267-271`) |
| Stage A — disagreement generalisation | ✅ `stages/stage_a.py:14-37` | ❌ stub returns mock | ✅ `refiner.py:134-169` | ✅ `stage_a.py` | ⚠ Stage A class exists; **error sampler stubbed** at `loop.py:234` (`# TODO: Actually compute errors from dev set`) |
| Stage B — K siblings + delimiters | ✅ `stages/stage_b.py` | ❌ dummy edits | ✅ `refiner.py:189-246` | ✅ `stage_b.py:93-150` | ✅ `stages/stage_b.py:39-80+`; system prompt + LLM call |
| Stage C — selector (no argmax) | ✅ `stages/stage_c.py:18-48` | ❌ random | ✅ `refiner.py:297-344` | ⚠ prompt includes test metrics | ✅ `stages/stage_c.py:46-76`; `parse_decision_target()` at line 127 |
| Stage M — merge synthesis | ✅ `stages/stage_m.py` | ❌ static | ✅ `refiner.py:380+` | ✅ `stage_m.py` | ✅ `stages/stage_m.py` |
| §7 stochastic retries `[0.0, 0.4, 0.7, 0.9]` | ✅ `config.py:12` | ✅ but mock LLM | ✅ `refiner.py:57-118` | ✅ `llm.py:83-186` | ⚠ schedule defined (`paths.py:55`) but actual retry-loop usage in stages not verified |
| §8 observability (live blocks, attempt dumps, auto-report) | ✅ `runner.py:195` | ⚠ no live blocks | ✅ `loop.py:105-140` | ✅ banners + snapshots | ⚠ logging present; report auto-regen `loop.py:203`; per-attempt dumps incomplete |
| §9 `AUTORESEARCH_STATE_DIR` env var | ✅ `config.py:51` | ✅ `paths.py:8` | ✅ `paths.py:14` | ✅ `paths.py:34-42` | ✅ `autoresearch/paths.py:21` |
| §12 CLI: `run / report / reset / score` + flags | ✅ all four + flags | ⚠ no `score`; `--limit` unused | ✅ all four + `prepare` | ✅ all four + `status` | ✅ **all four + flags** (`main.py:78-118`); most complete CLI |

---

## 3. AGENTS.md compliance

| Requirement | codex-spark | gemma-31b-openrouter | qwen-27b-openrouter | qwen-27b-q4_k_m | haiku |
|---|---|---|---|---|---|
| Per-module `DOCUMENTATION.md` | ✅ in `core/`, `stages/`, `scorer/`, top-level | ✅ 8 `DOCUMENTATION_*.md` files | ✅ 9 `DOCUMENTATION_*.md` files | ❌ only `docs/DOCUMENTATION.md` | ✅ all 6 modules (`artifacts/`, `splitter/`, `scorer/`, `stages/`, `history/`, `report/`) |
| `WIKI.md` (executive summary) | ✅ | ✅ | ✅ ~156 lines | ✅ ~100 lines | ✅ ~11 KB |
| `PROGRESS.md` | ✅ | ✅ | ✅ 149-line checklist | ✅ | ✅ 6.3 KB, 7 phases tracked |
| `OPS.md` (deploy / env / health / logs / failures / backup / scale / rollback) | ✅ all sections | ⚠ basic | ✅ all sections | ⚠ missing failure modes, backup, scaling, rollback | ✅ **22 KB**, all sections |
| Branch convention `<type>/<feature>` | ⚠ one branch; 2 commits | ❌ rest on main | ⚠ commits OK; branch use unclear | ⚠ commits OK; branch use unclear | ❌ linear history; no branch convention visible |
| Commit message convention `<type>: <desc>` | ✅ | ✅ 13 commits | ✅ 22 commits | ✅ 15 commits | ⚠ ~8 commits, mostly conform |
| One-commit-per-TODO discipline | ❌ 2 commits total | ❌ feature-level | ✅ per-TODO trail | ⚠ feature-level | ❌ may batch multiple TODOs |
| Unit tests | ❌ none | ❌ none | ✅ **39 passing** | ❌ none | ❌ none (`pytest --collect-only` → 0) |

---

## 4. Does it actually run?

| Check | codex-spark | gemma-31b-openrouter | qwen-27b-openrouter | qwen-27b-q4_k_m | haiku |
|---|---|---|---|---|---|
| `python -c "import autoresearch"` | ❌ `ModuleNotFoundError: autoresearch.core.types` | ❌ `NameError: name 'Tuple' is not defined` | ✅ | ✅ | ✅ |
| `pytest --collect-only` | ❌ no tests | ❌ no tests | ✅ 39 collected | ❌ 0 collected | ❌ 0 collected |
| `pytest -x` | n/a | n/a | ✅ 39 passing in 0.7s | n/a | n/a |
| CLI `--help` | ❌ blocked | ❌ blocked | ✅ `./loop --help`, `make help` | ✅ `python -m autoresearch.cli --help` | ✅ `python -m autoresearch.main --help` |
| Real LLM integration | present, untested | **stubbed** static strings | present; scorer not wired | present (OpenAI/Anthropic) | present (Anthropic) but **scoring pipeline stubbed** in `scorer/scorer.py` (multiple `# TODO`) |

---

## 5. Severity-ranked problem list per implementation

### codex-spark — blockers prevent execution

1. **[BLOCKING]** `core/__init__.py:1` imports `.core.types`; the file lives at `autoresearch/types.py`. Same wrong import in `runner.py:16`.
2. **[BLOCKING]** `runner.py:55, 164, 192` call `self.paths.read_text()`; `StatePaths` defines no such method.
3. **[HIGH]** Zero unit tests; PROGRESS.md marks them "planned".
4. **[MEDIUM]** Only 2 commits in git history — does not match AGENTS.md "one commit per TODO" requirement.

### gemma-31b-openrouter — skeleton, not an implementation

1. **[BLOCKING]** `autoresearch/loop.py:40` uses `Tuple` without `from typing import Tuple`.
2. **[BLOCKING]** `autoresearch/__init__.py` does not exist; package import fails.
3. **[BLOCKING]** All four refiner stages are stubbed: Stage A returns mock diagnosis (`refiner.py:19-25`), Stage B returns dummy edits (`refiner.py:35-41`), Stage C returns random selection (`refiner.py:54-57`), Stage M returns a static merge (`refiner.py:69`). `_call_llm` (`refiner.py:96-114`) returns static strings — no LLM is ever called.
4. **[HIGH]** `loop score <artifact>` command not implemented (DesignDoc §12).
5. **[HIGH]** `--limit N` flag parsed (`loop.py:15`) but never plumbed into `AutoresearchLoop.run()`.
6. **[MEDIUM]** No `requirements.txt` / `pyproject.toml`; OPS.md mentions `pip install numpy` only.
7. **[MEDIUM]** No unit tests; only one feature branch; rest committed to main.

### qwen-27b-openrouter — runs, one cache-key bug

1. **[MEDIUM]** `loop.py:266` writes the experiment row with `artifact_hash=candidate.plan_id[:16]` instead of the real content hash. The real `compute_artifact_hash` exists in `scorer.py:27-43` but is unused for the log entry. Cache lookups still work via `scorer.py`, but the log's `artifact_hash` field is misleading and risks collision when plan_ids repeat across batches.
2. **[MEDIUM]** `mock_scorer.py` exists at the repo root but is never wired into the loop; real runs require an external `dredd.py`-style scorer that this repo does not ship.
3. **[LOW]** `loop.py:189-194` reads predictions/labels from a parent log entry but `ExperimentEntry` does not always populate them — Stage A diagnosis can silently degrade.
4. **[LOW]** `refiner.py:118` raises `RuntimeError` when all retries fail, halting the entire loop instead of skipping the batch.

### qwen-27b-q4_k_m — runs, but leaks test metrics

1. **[BLOCKING for methodology]** `prompts.py:235` interpolates `metrics_test` into the Stage C selector prompt:

   ```python
   f"test[{', '.join(f'{k}={v:.4f}' for k, v in line.get('metrics_test', {}).items())}]\n"
   ```

   This violates DesignDoc invariant 2.4 — test metrics must never reach the selector. Until removed, every "improvement" the selector picks is contaminated; held-out evaluation is invalid.
2. **[HIGH]** No unit tests at all (`pytest --collect-only` → 0).
3. **[MEDIUM]** `scorer.py:210` has a `# TODO: implement with retries` in the inline (non-subprocess) scoring path.
4. **[MEDIUM]** Only one `docs/DOCUMENTATION.md`; AGENTS.md requires per-module documentation files.
5. **[MEDIUM]** OPS.md missing common failure modes, backup/restore, scaling, and update/rollback sections.
6. **[LOW]** `config.yaml:56-63` lists `paths.*` entries that `Paths` already derives from `state_dir` (`paths.py:45-47`) — dead config.

### haiku — runs, but scorer and Stage-A sampler are stubbed

1. **[BLOCKING]** `scorer/scorer.py` has multiple `# TODO` markers in the actual scoring path (`# TODO: Read metrics_file…`, `# TODO: Implement full scoring pipeline`). The cache + hashing layer is real; the metric computation that fills the cache is not. The loop will iterate but produce no real scores.
2. **[BLOCKING]** `loop.py:234` returns a placeholder error sample (`# TODO: Actually compute errors from dev set`) instead of pulling real disagreements. Stage A receives synthetic input, so its generalisations are decoupled from actual model failures — the proposer cannot target real error modes.
3. **[HIGH for methodology]** Test metrics surface to the proposer's history rendering at `loop.py:219-230`. Stage C does not see them, but the proposer does — partial violation of invariant 2.4. Less severe than `qwen-27b-q4_k_m`'s direct-to-selector leak, but still leakage.
4. **[HIGH]** No unit tests anywhere. With stubbed hot paths, the absence of tests means there is no scaffold for verifying any future fix.
5. **[MEDIUM]** Exception handler at `loop.py:105-108` `break`s the loop on any error rather than surviving a bad batch. Combined with append-only-but-not-atomic writes, a Ctrl+C can leave cache files written but no log line for them.
6. **[LOW]** Stage A/B `run()` methods past their visible system prompts may rely on the temperature schedule defined in `paths.py:55`; verify retry usage end-to-end before relying on it.
7. **[LOW]** Only ~8 commits with no `<type>/<feature>` branch usage.

---

## 6. Per-implementation strengths

- **codex-spark** — cleanest separation of concerns (`core/`, `scorer/`, `stages/`, plus `runner.py` and `reporter.py`); per-module docs in subpackages; thorough OPS.md. The architecture is the best of the four — *if* the imports were fixed, this would likely become the strongest base.
- **gemma-31b-openrouter** — solid documentation discipline (8 `DOCUMENTATION_*.md` files, full WIKI/PROGRESS/OPS); paths and cache primitives are correct. Just unfinished.
- **qwen-27b-openrouter** — only implementation with a passing test suite (39 tests); proper per-TODO commits; production-grade observability and CLI; thorough OPS.md. The only one a new contributor could pick up and run today.
- **qwen-27b-q4_k_m** — most complete feature surface (`stage_a/b/c/m.py` as separate modules, dedicated `llm.py` and `prompts.py`, signal-safe loop, atomic cache writes, status command).
- **haiku** — most complete CLI (all six DesignDoc §12 commands work end-to-end), most thorough OPS.md (~22 KB), per-module DOCUMENTATION.md for every subpackage, top-level `IMPLEMENTATION_SUMMARY.md`. Imports cleanly and the CLI responds. The architecture (separate top-level packages per concern: `artifacts/`, `splitter/`, `scorer/`, `stages/`, `history/`, `report/`) is the most modular of the five.

---

## 7. Recommendation

If the goal is "pick the one to build on":

1. **Use `qwen-27b-openrouter` as the base.** It is the only one with a passing test suite, and its bugs are localized. Two fixes get it to spec:
   - In `loop.py:266`, replace `candidate.plan_id[:16]` with `compute_artifact_hash(candidate.artifact)`.
   - Either ship a real scorer or wire `mock_scorer.py` in for development runs.
2. **Port the Stage A/B/C/M structure from `qwen-27b-q4_k_m`** — split-into-files layout (`stage_a.py`, `stage_b.py`, …) plus dedicated `llm.py` / `prompts.py` is cleaner than `qwen-27b-openrouter`'s monolithic `refiner.py`. Drop `metrics_test` from `prompts.py:235` during the port.
3. **Borrow OPS.md and the modular package layout from `haiku`.** Its 22 KB OPS, six per-module DOCUMENTATION.md files, complete CLI surface, and top-level package layout (`artifacts/`, `splitter/`, `scorer/`, `stages/`, `history/`, `report/`) are the highest-quality documentation and structure assets among the five.
4. **Borrow the architecture diagram and per-module docs from `codex-spark`.** Its `autoresearch/core/`, `autoresearch/stages/`, `autoresearch/scorer/` package layout is worth keeping even if the code itself is not currently runnable.
5. **Treat `gemma-31b-openrouter` as a documentation reference only** — its code is a stub with mocked stages and missing imports.

If the goal is "ship as-is", only `qwen-27b-openrouter` is viable today, with the two fixes above. `haiku` and `qwen-27b-q4_k_m` import and run, but each has at least one stubbed or invariant-violating hot path that yields nominal output without real signal.

---

## 8. Cross-cutting observations

- **Tests are the differentiator.** The one implementation with tests (`qwen-27b-openrouter`) is also the only one of the five with no stubbed hot paths and no invariant violations of consequence. AGENTS.md's "tests after merge" rule catches exactly the class of bugs the other four suffer from. Of the five, only `qwen-27b-openrouter` honors it.
- **Test-metric leakage is endemic.** Three of five implementations leak the held-out test set somewhere: `qwen-27b-q4_k_m` to the selector (`prompts.py:235`), `haiku` to the proposer's history (`loop.py:219-230`), and `gemma-31b-openrouter` would too if its stages weren't already random. A single unit test asserting "no field named `metrics_test` appears in any LLM input string" would have caught all three.
- **Documentation correlates with completeness, not correctness.** `haiku` has the longest OPS.md and the most per-module docs, yet has stubbed scoring and stubbed Stage-A error sampling. `codex-spark` has thorough docs but does not import. PROGRESS.md and "all phases complete" claims should be checked against working imports and non-stubbed hot paths as a CI step.
- **Per-module DOCUMENTATION.md is honored unevenly.** `qwen-27b-q4_k_m` collapses everything into one `docs/DOCUMENTATION.md`; the other four split per module. `haiku` is the strictest about this — every subpackage has its own.
- **Stubs hiding behind a working CLI is the worst failure mode.** `haiku` imports, the CLI responds, the cache layer works, the report regenerates — all the surface signals say "this works". But the scoring pipeline is stubbed, so the loop will run for hours and produce no real metrics. This is harder to diagnose than `gemma-31b-openrouter`'s import error: the import error fails fast; a stubbed scorer fails silently.
