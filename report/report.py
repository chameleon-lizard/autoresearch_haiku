"""
Report generation: auto-generate experiments_report.md from log.

Deterministic report regeneration from append-only log.
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from autoresearch.paths import LOG_FILE, REPORT_FILE


def load_experiments(log_path: Path = LOG_FILE) -> List[Dict[str, Any]]:
    """Load all experiments from jsonl log."""
    experiments = []
    if log_path.exists():
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    experiments.append(json.loads(line))
    return experiments


def generate_report(experiments: List[Dict[str, Any]]) -> str:
    """
    Generate markdown report from experiments.
    
    Includes:
    - Summary statistics
    - Per-batch table
    - Plan aggregates
    - Dev vs test gap (detect overfitting)
    """
    lines = []
    
    lines.append("# Autoresearch Loop Report\n")
    lines.append(f"Total iterations: {len(experiments)}\n")
    
    if not experiments:
        lines.append("(No iterations yet)\n")
        return "\n".join(lines)
    
    # Summary stats
    best_exp = max(experiments, key=lambda e: e.get("metrics_dev", {}).get("kappa", 0))
    best_kappa = best_exp.get("metrics_dev", {}).get("kappa", 0)
    best_iter = best_exp.get("iter", "?")
    
    lines.append(f"## Summary\n")
    lines.append(f"- Best iteration: {best_iter} (κ={best_kappa:.3f})\n")
    
    # Win rate
    wins = sum(1 for e in experiments if e.get("is_winner"))
    win_rate = wins / len(experiments) if experiments else 0
    lines.append(f"- Win rate: {wins}/{len(experiments)} ({win_rate:.1%})\n")
    
    # Dev-test gap (detect overfitting)
    if experiments:
        latest = experiments[-1]
        dev_kappa = latest.get("metrics_dev", {}).get("kappa", 0)
        test_kappa = latest.get("metrics_test", {}).get("kappa", 0)
        gap = dev_kappa - test_kappa
        lines.append(f"- Latest dev-test gap: {gap:+.4f} (overfitting if growing)\n")
    
    lines.append("\n")
    
    # Per-batch table
    lines.append("## Iterations\n")
    lines.append(
        "| Iter | Batch | Plan | κ (dev) | F1 (dev) | Δκ | Winner | Rationale |\n"
    )
    lines.append("|------|-------|------|--------|---------|-----|--------|----------|\n")
    
    for exp in experiments:
        iter_num = exp.get("iter", "?")
        batch_id = exp.get("batch_id", "?")
        plan_id = exp.get("plan_id", "?")
        kappa = exp.get("metrics_dev", {}).get("kappa", 0)
        f1 = exp.get("metrics_dev", {}).get("macro_f1", 0)
        delta = exp.get("delta_dev_kappa", 0)
        is_winner = "✓" if exp.get("is_winner") else ""
        rationale = exp.get("rationale", "")[:40]
        
        delta_str = f"+{delta:.4f}" if delta >= 0 else f"{delta:.4f}"
        
        lines.append(
            f"| {iter_num} | {batch_id} | {plan_id} | {kappa:.3f} | {f1:.3f} | "
            f"{delta_str} | {is_winner} | {rationale} |\n"
        )
    
    lines.append("\n")
    
    # Plan aggregates
    lines.append("## Plan Aggregates\n")
    by_plan: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for exp in experiments:
        plan_id = exp.get("plan_id", "unknown")
        by_plan[plan_id].append(exp)
    
    for plan_id in sorted(by_plan.keys()):
        exps = by_plan[plan_id]
        wins = sum(1 for e in exps if e.get("is_winner"))
        mean_delta = sum(e.get("delta_dev_kappa", 0) for e in exps) / len(exps)
        
        lines.append(f"- **{plan_id}**: {len(exps)} proposed, {wins} won, "
                     f"mean Δ={mean_delta:+.4f}\n")
    
    return "".join(lines)


def regenerate_report(
    log_path: Path = LOG_FILE,
    report_path: Path = REPORT_FILE,
) -> None:
    """Regenerate report from log."""
    experiments = load_experiments(log_path)
    report = generate_report(experiments)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)
