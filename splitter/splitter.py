"""
Dataset splitter: deterministic stratified train/dev/test split.

Core invariant (DesignDoc §2.4): The loop sees train + dev metrics.
Test metrics are logged but never surfaced to the proposer/selector.
This allows us to detect overfitting: if dev/test gap grows monotonically,
the selector is overfitting dev.

Key principles:
- Deterministic: same seed → identical split (reproducible)
- Stratified: respects domain/category proportions if data has "domain" field
- Configurable: ratios set in paths.py
- Immutable: computed once, cached for entire run

Usage:

    from splitter.splitter import DatasetSplitter
    from autoresearch.paths import DATASET_PATH, TRAIN_RATIO, DEV_RATIO, TEST_RATIO
    
    splitter = DatasetSplitter(
        dataset_path=DATASET_PATH,
        train_ratio=TRAIN_RATIO,
        dev_ratio=DEV_RATIO,
        test_ratio=TEST_RATIO,
        seed=42
    )
    
    train_examples = splitter.get_train()
    dev_examples = splitter.get_dev()
    test_examples = splitter.get_test()
"""

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional


class DatasetSplitter:
    """
    Stratified train/dev/test split with deterministic reproducibility.
    
    If the dataset has a "domain" field, split respects domain proportions.
    Otherwise, performs a simple random split.
    """
    
    def __init__(
        self,
        dataset_path: Path,
        train_ratio: float = 0.4,
        dev_ratio: float = 0.2,
        test_ratio: float = 0.4,
        seed: int = 42,
        stratify_by_domain: bool = True,
    ):
        """
        Initialize splitter.
        
        Args:
            dataset_path: Path to JSONL file with examples
            train_ratio: Proportion for training (0.0 - 1.0)
            dev_ratio: Proportion for development (0.0 - 1.0)
            test_ratio: Proportion for testing (0.0 - 1.0)
            seed: Random seed for reproducibility
            stratify_by_domain: If True, split respects "domain" field proportions
        
        Raises:
            ValueError: If ratios don't sum to 1.0 or dataset not found
        """
        if not (0.99 <= train_ratio + dev_ratio + test_ratio <= 1.01):
            raise ValueError(
                f"Ratios must sum to 1.0, got {train_ratio + dev_ratio + test_ratio}"
            )
        
        dataset_path = Path(dataset_path)
        if not dataset_path.exists():
            raise ValueError(f"Dataset not found: {dataset_path}")
        
        self.dataset_path = dataset_path
        self.train_ratio = train_ratio
        self.dev_ratio = dev_ratio
        self.test_ratio = test_ratio
        self.seed = seed
        self.stratify_by_domain = stratify_by_domain
        
        # Load and split dataset
        self._examples = self._load_dataset()
        self._train, self._dev, self._test = self._perform_split()
    
    def _load_dataset(self) -> List[Dict[str, Any]]:
        """Load JSONL dataset into memory."""
        examples = []
        with open(self.dataset_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                example = json.loads(line)
                examples.append(example)
        
        if not examples:
            raise ValueError(f"Dataset is empty: {self.dataset_path}")
        
        return examples
    
    def _perform_split(
        self,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Perform stratified split.
        
        Returns:
            (train_examples, dev_examples, test_examples)
        """
        random.seed(self.seed)
        
        if self.stratify_by_domain and self._has_domain_field():
            return self._stratified_split_by_domain()
        else:
            return self._simple_random_split()
    
    def _has_domain_field(self) -> bool:
        """Check if dataset has a 'domain' field."""
        return any("domain" in ex for ex in self._examples)
    
    def _stratified_split_by_domain(
        self,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Split by domain: maintain domain proportions in each split.
        
        Approach: for each domain, split its examples into train/dev/test,
        then combine across domains.
        """
        # Group examples by domain
        by_domain: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for ex in self._examples:
            domain = ex.get("domain", "default")
            by_domain[domain].append(ex)
        
        train, dev, test = [], [], []
        
        # Split each domain independently
        for domain, examples in by_domain.items():
            domain_train, domain_dev, domain_test = self._simple_random_split_examples(
                examples
            )
            train.extend(domain_train)
            dev.extend(domain_dev)
            test.extend(domain_test)
        
        return train, dev, test
    
    def _simple_random_split(
        self,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Simple random split (no stratification)."""
        return self._simple_random_split_examples(self._examples)
    
    def _simple_random_split_examples(
        self, examples: List[Dict[str, Any]]
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Simple random split of a list of examples.
        
        Args:
            examples: List of examples to split
            
        Returns:
            (train_examples, dev_examples, test_examples)
        """
        # Shuffle
        shuffled = examples.copy()
        random.shuffle(shuffled)
        
        # Compute split indices
        n = len(shuffled)
        train_size = int(n * self.train_ratio)
        dev_size = int(n * self.dev_ratio)
        
        train = shuffled[:train_size]
        dev = shuffled[train_size : train_size + dev_size]
        test = shuffled[train_size + dev_size :]
        
        return train, dev, test
    
    def get_train(self) -> List[Dict[str, Any]]:
        """Get training examples."""
        return self._train
    
    def get_dev(self) -> List[Dict[str, Any]]:
        """Get development examples."""
        return self._dev
    
    def get_test(self) -> List[Dict[str, Any]]:
        """Get test examples."""
        return self._test
    
    def get_all(self) -> List[Dict[str, Any]]:
        """Get all examples (union of train, dev, test)."""
        return self._train + self._dev + self._test
    
    def stats(self) -> Dict[str, Any]:
        """Print split statistics."""
        return {
            "total": len(self._examples),
            "train": len(self._train),
            "dev": len(self._dev),
            "test": len(self._test),
            "train_ratio": len(self._train) / len(self._examples),
            "dev_ratio": len(self._dev) / len(self._examples),
            "test_ratio": len(self._test) / len(self._examples),
            "stratified_by_domain": self._has_domain_field(),
        }


def subsample_dataset(
    examples: List[Dict[str, Any]], limit: int
) -> List[Dict[str, Any]]:
    """
    Subsample dataset to limit examples (for smoke testing).
    
    Args:
        examples: Full list of examples
        limit: Max number to keep (or None for no limit)
    
    Returns:
        First `limit` examples (or all if limit is None)
    """
    if limit is None:
        return examples
    return examples[:limit]
