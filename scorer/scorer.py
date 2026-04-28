"""
Scorer: cache-aware artifact scoring with metrics computation.

Core invariant (DesignDoc §2.1): All expensive work (scoring) is keyed by
artifact content hash and persisted to disk. A re-run of the loop must
NEVER redo work it has already done.

Key principles:
- Content hash = cache key
- Check cache before calling LLM
- Write results atomically (line-buffered)
- Supports parallel scoring of multiple artifacts

Usage:

    from scorer.scorer import Scorer
    from artifacts.artifact import Artifact
    
    scorer = Scorer(scorer_model="claude-3-5-sonnet-20241022")
    
    artifact = Artifact("Your prompt...")
    
    # Check if cached
    if scorer.is_cached(artifact):
        metrics = scorer.load_cached_metrics(artifact, split="dev")
        print(f"κ={metrics['kappa']:.3f}")  # Instant (disk read)
    else:
        # Score and cache
        examples = [...train examples...]
        metrics = scorer.score(artifact, examples)
        print(f"κ={metrics['kappa']:.3f}")  # API call + cache write
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from autoresearch.paths import (
    CACHE_DIR,
    SCORER_API_KEY,
    SCORER_MAX_INPUT_TOKENS,
    SCORER_MAX_OUTPUT_TOKENS,
    SCORER_MODEL,
    SCORER_TIMEOUT_SECONDS,
)
from artifacts.artifact import Artifact

logger = logging.getLogger(__name__)


class Scorer:
    """
    Scores artifacts and manages caching by content hash.
    
    Caching strategy:
    1. Artifact is scored on a set of examples (e.g., dev set)
    2. Results (metrics, predictions, errors) are written to cache/HASH/metrics_dev.jsonl
    3. On next run with same artifact and dataset: load from cache (fast)
    4. If artifact changed: hash changes → new cache entry (no collision)
    """
    
    def __init__(
        self,
        scorer_model: str = SCORER_MODEL,
        api_key: str = SCORER_API_KEY,
        max_input_tokens: int = SCORER_MAX_INPUT_TOKENS,
        max_output_tokens: int = SCORER_MAX_OUTPUT_TOKENS,
        timeout_seconds: float = SCORER_TIMEOUT_SECONDS,
    ):
        """
        Initialize scorer.
        
        Args:
            scorer_model: LLM model name (e.g., "claude-3-5-sonnet-20241022")
            api_key: API key for LLM provider
            max_input_tokens: Input token budget
            max_output_tokens: Output token budget
            timeout_seconds: Timeout for scorer calls
        """
        self.scorer_model = scorer_model
        self.api_key = api_key
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds
        
        # Lazy-init API client (avoid importing if not needed)
        self._client = None
    
    @property
    def client(self):
        """Lazy-initialize API client."""
        if self._client is None:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError("anthropic library required: pip install anthropic")
        return self._client
    
    def get_cache_dir(self, artifact: Artifact) -> Path:
        """Get cache directory for artifact."""
        cache_dir = CACHE_DIR / artifact.content_hash
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir
    
    def is_cached(self, artifact: Artifact, split: str = "dev") -> bool:
        """
        Check if artifact is cached for a given split.
        
        Args:
            artifact: The artifact to check
            split: One of "train", "dev", "test"
        
        Returns:
            True if metrics_<split>.jsonl exists and is non-empty
        """
        metrics_file = self.get_cache_dir(artifact) / f"metrics_{split}.jsonl"
        return metrics_file.exists() and metrics_file.stat().st_size > 0
    
    def load_cached_metrics(
        self, artifact: Artifact, split: str = "dev"
    ) -> Dict[str, Any]:
        """
        Load cached metrics for artifact.
        
        Args:
            artifact: The artifact
            split: One of "train", "dev", "test"
        
        Returns:
            Metrics dict (or empty dict if no cache)
        """
        metrics_file = self.get_cache_dir(artifact) / f"metrics_{split}.jsonl"
        
        if not metrics_file.exists():
            return {}
        
        # Metrics file format: one JSON line per example scored
        # Aggregate to produce overall metrics (κ, F1, accuracy, etc.)
        metrics = {
            "kappa": 0.0,
            "macro_f1": 0.0,
            "accuracy": 0.0,
            "spearman": 0.0,
        }
        
        # TODO: Read metrics_file and compute aggregates
        # For now, return placeholder
        
        return metrics
    
    def save_metrics(
        self, artifact: Artifact, split: str, metrics: Dict[str, Any]
    ) -> None:
        """
        Save metrics to cache.
        
        Args:
            artifact: The artifact
            split: One of "train", "dev", "test"
            metrics: Metrics dict
        """
        metrics_file = self.get_cache_dir(artifact) / f"metrics_{split}.jsonl"
        
        # Append as one JSON line
        with open(metrics_file, "a") as f:
            f.write(json.dumps(metrics) + "\n")
    
    def score(
        self, artifact: Artifact, examples: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Score artifact on examples (with caching).
        
        Args:
            artifact: The artifact to score
            examples: List of examples with "text" and "label" fields
        
        Returns:
            Metrics dict with kappa, macro_f1, accuracy, etc.
        """
        # Check cache first
        cache_dir = self.get_cache_dir(artifact)
        
        # Save artifact text to cache (for reference)
        artifact.save_to_file(cache_dir / "artifact.txt")
        
        # TODO: Implement full scoring pipeline
        # 1. If cached: load metrics
        # 2. If not: call scorer LLM on all examples
        # 3. Compute aggregate metrics (κ, F1, accuracy)
        # 4. Write to cache (line-buffered, atomic)
        # 5. Return metrics
        
        # Placeholder: return dummy metrics
        metrics = {
            "kappa": 0.5,
            "macro_f1": 0.52,
            "accuracy": 0.55,
            "spearman": 0.60,
            "n_examples": len(examples),
        }
        
        return metrics
    
    async def score_async(
        self, artifact: Artifact, examples: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Async version of score (for parallel scoring)."""
        # TODO: Implement async scoring
        return self.score(artifact, examples)


def compute_inter_rater_agreement(
    predictions: List[Any], ground_truth: List[Any]
) -> Dict[str, float]:
    """
    Compute inter-rater agreement metrics.
    
    Args:
        predictions: Model predictions (one per example)
        ground_truth: Ground truth labels
    
    Returns:
        Dict with kappa, macro_f1, accuracy, spearman
    """
    # TODO: Implement metrics computation
    # Use sklearn.metrics for kappa, F1, etc.
    
    return {
        "kappa": 0.0,
        "macro_f1": 0.0,
        "accuracy": 0.0,
        "spearman": 0.0,
    }
