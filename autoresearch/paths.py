"""
Centralized configuration and paths for autoresearch loop.

All configuration lives here. No CLI flags, no scattered settings.
Use env vars to override paths and API keys at runtime.

Example:
    export AUTORESEARCH_STATE_DIR=/tmp/haiku_run_1
    export ANTHROPIC_API_KEY=sk-ant-...
    python -m autoresearch.main run
"""

import os
from pathlib import Path

# ============================================================================
# Core Paths
# ============================================================================

# State directory: all runtime data, logs, cache, experiments
STATE_DIR = Path(os.environ.get("AUTORESEARCH_STATE_DIR", "state"))

# Dataset: must be JSONL format with at least "id", "text", "label" fields
DATASET_PATH = Path(os.environ.get("AUTORESEARCH_DATASET", "data/dataset.jsonl"))

# Initial artifact: starting point for the loop
INITIAL_ARTIFACT_PATH = STATE_DIR / "initial_artifact.txt"

# Subdirectories (created automatically)
CACHE_DIR = STATE_DIR / "cache"
ITERATIONS_DIR = STATE_DIR / "iterations"
BATCHES_DIR = STATE_DIR / "batches"

# Append-only log: one JSON line per iteration (CRITICAL: never modify earlier lines)
LOG_FILE = STATE_DIR / "experiments.jsonl"

# Auto-generated report: deterministic from log, regenerated after each batch
REPORT_FILE = STATE_DIR / "experiments_report.md"

# Bi-directional notebook: user can edit between iterations
NOTES_FILE = STATE_DIR / "notes.md"

# ============================================================================
# Refiner LLM (Proposer)
# ============================================================================

# Which model generates proposals (edits, merges)
REFINER_MODEL = os.environ.get("REFINER_MODEL", "claude-3-5-sonnet-20241022")

# API key for refiner (shared with scorer if same provider)
REFINER_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Temperature schedule for retries (increasing diversity on failure)
# First attempt deterministic, then increase diversity
REFINER_TEMPERATURE_SCHEDULE = [0.0, 0.4, 0.7, 0.9]

# Max retries before giving up on a proposal
REFINER_MAX_RETRIES = 4

# Max input tokens for refiner prompts (includes history, parent, etc.)
REFINER_MAX_INPUT_TOKENS = 40000

# Max output tokens for refiner responses (artifact + metadata)
REFINER_MAX_OUTPUT_TOKENS = 8000

# ============================================================================
# Scorer LLM (Evaluator)
# ============================================================================

# Which model scores artifacts (may differ from REFINER_MODEL)
SCORER_MODEL = os.environ.get("SCORER_MODEL", "claude-3-5-sonnet-20241022")

# API key for scorer (usually same as REFINER_API_KEY)
SCORER_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Max input tokens for scorer prompts (input text + artifact)
SCORER_MAX_INPUT_TOKENS = 32000

# Max output tokens for scorer responses (judgment + metadata)
SCORER_MAX_OUTPUT_TOKENS = 1000

# Timeout per scoring call (seconds)
SCORER_TIMEOUT_SECONDS = 120.0

# ============================================================================
# Dataset Splits
# ============================================================================

# Deterministic seed for reproducibility
SPLIT_SEED = 42

# Train / dev / test ratios (must sum to 1.0)
# - Train: loop can see metrics (used by proposer for feedback)
# - Dev: loop can see metrics (used by selector for decisions)
# - Test: logged but never surfaced to proposer/selector (detects overfitting)
TRAIN_RATIO = 0.4
DEV_RATIO = 0.2
TEST_RATIO = 0.4

# If dataset has a "domain" field, split respects proportions per domain
# Set False to ignore domain (simple random split)
STRATIFY_BY_DOMAIN = True

# ============================================================================
# Batch Mode
# ============================================================================

# Number of sibling candidates per batch (Stage B output)
# Higher K = more parallelism but higher cost per iteration
BATCH_SIZE = 3

# Early stopping: if all K candidates lose to parent, hard stop
# Set False to keep proposing even if all candidates fail
STOP_IF_NO_WINNER = True

# ============================================================================
# Parallelism
# ============================================================================

# Max parallel scorer subprocesses
# Typically K * num_splits (e.g., 3 candidates * 3 splits = 9)
MAX_PARALLEL_SCORES = 15

# Max parallel proposal attempts (Stage B retries)
MAX_PARALLEL_PROPOSALS = 4

# ============================================================================
# History Rendering
# ============================================================================

# How many recent iterations to show in full in the proposer prompt
HISTORY_FULL_RECENT_ITERS = 5

# How many best-candidates to show in full (by dev metric)
HISTORY_FULL_BEST_ITERS = 3

# All other iterations rendered in one-line compact format

# ============================================================================
# Observability & Debugging
# ============================================================================

# Log level: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# Save full response from each LLM call (even if parsed successfully)
DUMP_FULL_LLM_RESPONSES = True

# Dump per-attempt traces on LLM parse failure
DUMP_PER_ATTEMPT_TRACES = True

# Max length of human-readable blocks (e.g., reasoning) in terminal output
MAX_OBSERVABILITY_BLOCK_CHARS = 1500

# ============================================================================
# Limits (for development / smoke testing)
# ============================================================================

# Optional: subsample dataset to this many examples (set None for full dataset)
# Useful for fast iteration: python -m autoresearch.main run --limit 50
LIMIT_DATASET = None

# ============================================================================
# Error Handling
# ============================================================================

# If True: save stack traces to disk on crash (for post-mortem)
SAVE_CRASH_TRACES = True

# If True: attempt automatic recovery on resume (skip failed batches)
AUTO_RECOVER_ON_RESUME = True

# ============================================================================
# Utility Functions
# ============================================================================


def ensure_state_dir_exists():
    """Create state directory structure if it doesn't exist."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ITERATIONS_DIR.mkdir(parents=True, exist_ok=True)
    BATCHES_DIR.mkdir(parents=True, exist_ok=True)


def get_batch_dir(batch_id: str) -> Path:
    """Get path to a specific batch directory."""
    batch_dir = BATCHES_DIR / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    return batch_dir


def get_cache_dir(artifact_hash: str) -> Path:
    """Get path to cache directory for an artifact."""
    cache_dir = CACHE_DIR / artifact_hash
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_iteration_dir(iteration_num: int) -> Path:
    """Get path to iteration directory."""
    iter_dir = ITERATIONS_DIR / f"iter_{iteration_num:06d}"
    iter_dir.mkdir(parents=True, exist_ok=True)
    return iter_dir
