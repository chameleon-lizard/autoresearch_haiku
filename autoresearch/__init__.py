"""
Haiku Autoresearch Loop

A task-agnostic LLM-driven autoresearch loop for optimizing artifacts
(prompts, configs, weights, etc.) against a metric using iterative refinement.

Core invariants (from DesignDoc):
- Cache by content hash: no work is ever repeated
- Append-only experiment log: single source of truth
- Crash-safe: Ctrl+C or process death never corrupts state
- Held-out test set: detect overfitting
- Single-edit attribution: each candidate is one focused change
- Bi-directional notebook: user can inject constraints mid-run

Typical usage:

    from autoresearch.main import main
    
    main()  # Infinite loop, reads config from autoresearch/paths.py
    
Command-line usage:

    python -m autoresearch.main run [--max-iters N] [--limit N]
    python -m autoresearch.main report
    python -m autoresearch.main reset
    python -m autoresearch.main score <artifact_path>
"""

__version__ = "0.1.0"
