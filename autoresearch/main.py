"""
CLI entry point for autoresearch loop.

Usage:
    python -m autoresearch.main run [--max-iters N] [--limit N]
    python -m autoresearch.main report
    python -m autoresearch.main reset
    python -m autoresearch.main score <artifact_path>
"""

import argparse
import logging
import sys
from pathlib import Path

from autoresearch.loop import AutoresearchLoop
from autoresearch.paths import (
    BATCH_SIZE,
    DATASET_PATH,
    INITIAL_ARTIFACT_PATH,
    LOG_FILE,
    REPORT_FILE,
    STATE_DIR,
    LOG_LEVEL,
    ensure_state_dir_exists,
)
from report.report import regenerate_report

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Autoresearch loop: LLM-driven artifact optimization"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # run command
    run_parser = subparsers.add_parser("run", help="Run main loop")
    run_parser.add_argument(
        "--max-iters",
        type=int,
        default=None,
        help="Max iterations (default: infinite)",
    )
    run_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Subsample dataset (for smoke test)",
    )
    
    # report command
    subparsers.add_parser("report", help="Regenerate report from log")
    
    # reset command
    subparsers.add_parser("reset", help="Delete iterations and log (keep cache)")
    
    # score command
    score_parser = subparsers.add_parser("score", help="Score one artifact")
    score_parser.add_argument("artifact_path", help="Path to artifact file")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    ensure_state_dir_exists()
    
    try:
        if args.command == "run":
            loop = AutoresearchLoop(
                dataset_path=DATASET_PATH,
                initial_artifact_path=INITIAL_ARTIFACT_PATH,
                state_dir=STATE_DIR,
                batch_size=BATCH_SIZE,
                limit=args.limit,
            )
            loop.run(max_iters=args.max_iters)
        
        elif args.command == "report":
            regenerate_report()
            logger.info(f"Report regenerated: {REPORT_FILE}")
        
        elif args.command == "reset":
            import shutil
            # Delete iterations and log, keep cache
            if LOG_FILE.exists():
                LOG_FILE.unlink()
                logger.info(f"Deleted {LOG_FILE}")
            if REPORT_FILE.exists():
                REPORT_FILE.unlink()
                logger.info(f"Deleted {REPORT_FILE}")
            logger.info("Reset complete (cache preserved)")
        
        elif args.command == "score":
            from scorer.scorer import Scorer
            from artifacts.artifact import Artifact
            from splitter.splitter import DatasetSplitter
            
            artifact = Artifact.load_from_file(Path(args.artifact_path))
            logger.info(f"Artifact hash: {artifact.content_hash}")
            
            # Score on dev set
            splitter = DatasetSplitter(DATASET_PATH)
            scorer = Scorer()
            
            dev_examples = splitter.get_dev()
            metrics = scorer.score(artifact, dev_examples)
            
            logger.info(f"Dev metrics: {metrics}")
    
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
