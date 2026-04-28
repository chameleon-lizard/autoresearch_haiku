"""
Main autoresearch loop orchestration.

Orchestrates stages in sequence:
1. Stage C: select parent (or merge targets)
2. Stage M: if merge, synthesise
3. Stage B: generate K siblings
4. Score K siblings in parallel
5. Stage A: diagnose errors for each
6. Append results to experiments.jsonl
7. Regenerate report
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from artifacts.artifact import Artifact
from autoresearch.paths import (
    BATCH_SIZE,
    LOG_FILE,
    NOTES_FILE,
    STATE_DIR,
    ensure_state_dir_exists,
    get_batch_dir,
)
from history.renderer import render_history, render_plan_aggregate
from report.report import generate_report, load_experiments, regenerate_report
from scorer.scorer import Scorer
from splitter.splitter import DatasetSplitter, subsample_dataset
from stages.stage_a import StageA
from stages.stage_b import StageB
from stages.stage_c import StageC
from stages.stage_m import StageM

logger = logging.getLogger(__name__)


class AutoresearchLoop:
    """Main autoresearch loop."""
    
    def __init__(
        self,
        dataset_path: Path,
        initial_artifact_path: Path,
        state_dir: Path = STATE_DIR,
        batch_size: int = BATCH_SIZE,
        limit: Optional[int] = None,
    ):
        """
        Initialize loop.
        
        Args:
            dataset_path: Path to JSONL dataset
            initial_artifact_path: Path to initial artifact
            state_dir: State directory
            batch_size: K candidates per batch
            limit: Optional subsample limit for smoke testing
        """
        self.dataset_path = Path(dataset_path)
        self.initial_artifact_path = Path(initial_artifact_path)
        self.state_dir = Path(state_dir)
        self.batch_size = batch_size
        self.limit = limit
        
        ensure_state_dir_exists()
        
        # Initialize components
        self.splitter = DatasetSplitter(self.dataset_path)
        self.scorer = Scorer()
        self.stage_a = StageA()
        self.stage_b = StageB(batch_size=batch_size)
        self.stage_c = StageC()
        self.stage_m = StageM()
    
    def run(self, max_iters: Optional[int] = None) -> None:
        """
        Run main loop indefinitely (or until max_iters).
        
        Args:
            max_iters: Max iterations (None for infinite)
        """
        iter_num = self._get_next_iter_num()
        
        while True:
            if max_iters and iter_num > max_iters:
                logger.info(f"Reached max_iters={max_iters}, stopping")
                break
            
            try:
                logger.info(f"\n{'='*60}")
                logger.info(f"Batch {iter_num}")
                logger.info(f"{'='*60}\n")
                
                batch_id = f"batch_{iter_num:06d}"
                
                # Run one iteration
                self._run_batch(iter_num, batch_id)
                
                iter_num += 1
            
            except Exception as e:
                logger.error(f"Batch failed: {e}", exc_info=True)
                # Could implement recovery/retry here
                break
    
    def _run_batch(self, iter_num: int, batch_id: str) -> None:
        """Run one batch iteration."""
        batch_dir = get_batch_dir(batch_id)
        
        # Save notebook before
        self._save_notebook_snapshot(batch_dir, "before")
        
        # 1. Stage C: Select parent
        logger.info("Stage C: Selecting parent...")
        history_text = self._render_history()
        decision = self.stage_c.run(history_text, batch_id)
        logger.info(f"Decision: {decision['decision']}")
        
        # 2. Stage M: If merge, synthesise
        parent_artifact = None
        if decision["decision"].startswith("merge="):
            logger.info("Stage M: Merging parents...")
            iters = StageC.parse_decision_target(decision["decision"])
            parents_text = [self._get_artifact_text(i) for i in iters]
            merged = self.stage_m.run(parents_text, batch_id)
            parent_artifact = Artifact(merged)
            logger.info(f"Merged artifact (hash={parent_artifact.content_hash})")
        else:
            iter_num_to_use = StageC.parse_decision_target(decision["decision"])
            parent_artifact = Artifact(self._get_artifact_text(iter_num_to_use))
            logger.info(f"Using iter {iter_num_to_use} as parent")
        
        # 3. Stage B: Generate proposals
        logger.info("Stage B: Generating proposals...")
        errors_sample = self._get_error_sample(parent_artifact)
        diagnosis = self.stage_a.run(parent_artifact.text, errors_sample, batch_id)
        
        candidates = self.stage_b.run(
            parent_artifact=parent_artifact.text,
            diagnosis=diagnosis,
            history_context=self._render_history(),
            notebook_constraints=self._read_notebook(),
            batch_id=batch_id,
            k=self.batch_size,
        )
        logger.info(f"Generated {len(candidates)} candidates")
        
        # 4. Score candidates
        logger.info("Scoring candidates...")
        train_examples = subsample_dataset(
            self.splitter.get_train(), self.limit
        )
        dev_examples = subsample_dataset(
            self.splitter.get_dev(), self.limit
        )
        test_examples = subsample_dataset(
            self.splitter.get_test(), self.limit
        )
        
        results = []
        for cand in candidates:
            artifact = Artifact(cand["artifact_text"])
            
            # Score on all splits
            metrics_train = self.scorer.score(artifact, train_examples)
            metrics_dev = self.scorer.score(artifact, dev_examples)
            metrics_test = self.scorer.score(artifact, test_examples)
            
            # Compute delta
            parent_metrics = self.scorer.score(parent_artifact, dev_examples)
            parent_kappa = parent_metrics.get("kappa", 0)
            delta = metrics_dev.get("kappa", 0) - parent_kappa
            is_winner = delta > 0
            
            result = {
                "iter": iter_num,
                "ts": datetime.now().isoformat() + "Z",
                "batch_id": batch_id,
                "artifact_hash": artifact.content_hash,
                "parent_hash": parent_artifact.content_hash,
                "plan_id": cand["plan_id"],
                "rationale": cand.get("rationale", ""),
                "metrics_train": metrics_train,
                "metrics_dev": metrics_dev,
                "metrics_test": metrics_test,
                "delta_dev_kappa": delta,
                "is_winner": is_winner,
            }
            results.append(result)
            
            logger.info(f"  {cand['plan_id']}: κ={metrics_dev.get('kappa', 0):.3f} "
                       f"Δ={delta:+.4f} {'✓' if is_winner else ''}")
        
        # 5. Append to log
        logger.info("Saving results...")
        self._append_results_to_log(results)
        
        # 6. Regenerate report
        regenerate_report()
        
        # Save notebook after
        self._save_notebook_snapshot(batch_dir, "after")
        
        logger.info(f"Batch {iter_num} complete\n")
    
    def _get_next_iter_num(self) -> int:
        """Get next iteration number (resume from last)."""
        experiments = load_experiments(LOG_FILE)
        if not experiments:
            return 1
        return max(e.get("iter", 0) for e in experiments) + 1
    
    def _render_history(self) -> str:
        """Render history for Stage B/C context."""
        experiments = load_experiments(LOG_FILE)
        if not experiments:
            return "No prior iterations"
        
        best_exp = max(experiments, key=lambda e: e.get("metrics_dev", {}).get("kappa", 0))
        best_iter = best_exp.get("iter", 0)
        
        return render_history(
            experiments,
            best_iter_num=best_iter,
            parent_iter_nums=[],
        )
    
    def _get_error_sample(self, artifact: Artifact) -> List[Dict[str, Any]]:
        """Get sample of errors for Stage A."""
        # TODO: Actually compute errors from dev set
        # For now, return placeholder
        return [
            {
                "example_id": "1",
                "text": "Sample error",
                "prediction": "A",
                "label": "B",
            }
        ]
    
    def _get_artifact_text(self, iter_num: int) -> str:
        """Get artifact text from iteration (or initial if iter_num=0)."""
        if iter_num == 0:
            return self.initial_artifact_path.read_text()
        
        experiments = load_experiments(LOG_FILE)
        for exp in experiments:
            if exp.get("iter") == iter_num:
                # Load from cache
                cache_dir = Path(self.state_dir) / "cache" / exp.get("artifact_hash")
                artifact_file = cache_dir / "artifact.txt"
                if artifact_file.exists():
                    return artifact_file.read_text()
        
        raise ValueError(f"Artifact for iter {iter_num} not found")
    
    def _read_notebook(self) -> str:
        """Read user constraints from notebook."""
        if NOTES_FILE.exists():
            return NOTES_FILE.read_text()
        return ""
    
    def _save_notebook_snapshot(self, batch_dir: Path, when: str) -> None:
        """Save snapshot of notebook."""
        if NOTES_FILE.exists():
            snapshot = batch_dir / f"notes_{when}.md"
            snapshot.write_text(NOTES_FILE.read_text())
    
    def _append_results_to_log(self, results: List[Dict[str, Any]]) -> None:
        """Append results to experiment log."""
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            for result in results:
                f.write(json.dumps(result) + "\n")


# Import after class definition
from stages.stage_c import StageC
