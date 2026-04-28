"""
History rendering: compact vs full history for context windows.

Smart rendering strategy (from DesignDoc §6):
- Best-so-far artifact: full text + metrics + Stage A summary
- Last N=5 iterations: full text + metrics + summary
- Direct parent + parents being merged: full text (always)
- Everything else: compact one-liner

This lets the proposer see long-range trends without dumping 50 prompts
into context.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def render_compact(iteration: Dict[str, Any]) -> str:
    """
    Compact rendering: one-line summary of iteration.
    
    Format:
    iter=N batch=B parent=P plan=PLAN_ID κ=0.635 F1=0.628 Δ=+0.015
    """
    iter_num = iteration.get("iter", "?")
    batch_id = iteration.get("batch_id", "?")
    parent = iteration.get("parent_hash", "?")[:8]
    plan_id = iteration.get("plan_id", "?")
    kappa = iteration.get("metrics_dev", {}).get("kappa", 0)
    f1 = iteration.get("metrics_dev", {}).get("macro_f1", 0)
    delta = iteration.get("delta_dev_kappa", 0)
    
    delta_str = f"+{delta:.3f}" if delta >= 0 else f"{delta:.3f}"
    
    return (
        f"iter={iter_num} batch={batch_id} parent={parent} plan={plan_id} "
        f"κ={kappa:.3f} F1={f1:.3f} Δ={delta_str}"
    )


def render_full(
    iteration: Dict[str, Any],
    artifact_text: Optional[str] = None,
) -> str:
    """
    Full rendering: artifact + metrics + diagnosis.
    
    For recent winners, best-so-far, or parents.
    """
    lines = []
    
    # Header
    iter_num = iteration.get("iter", "?")
    plan_id = iteration.get("plan_id", "?")
    rationale = iteration.get("rationale", "")
    lines.append(f"=== Iteration {iter_num} (plan={plan_id}) ===")
    lines.append(f"Rationale: {rationale}")
    
    # Metrics
    metrics_dev = iteration.get("metrics_dev", {})
    lines.append(f"Train κ={iteration.get('metrics_train', {}).get('kappa', 0):.3f}, "
                 f"Dev κ={metrics_dev.get('kappa', 0):.3f}, "
                 f"Test κ={iteration.get('metrics_test', {}).get('kappa', 0):.3f}")
    
    # Diagnosis
    if "error_summary" in iteration:
        lines.append(f"Errors: {iteration['error_summary']}")
    
    # Artifact (if provided)
    if artifact_text:
        lines.append("\nArtifact:")
        # Show first 500 chars
        preview = artifact_text[:500]
        if len(artifact_text) > 500:
            preview += f"\n... ({len(artifact_text) - 500} more chars)"
        lines.append(preview)
    
    return "\n".join(lines)


def render_history(
    experiments: List[Dict[str, Any]],
    best_iter_num: int,
    parent_iter_nums: List[int],
    recent_n: int = 5,
    artifacts_map: Optional[Dict[int, str]] = None,
) -> str:
    """
    Render history with smart full/compact selection.
    
    Args:
        experiments: List of iteration dicts from log
        best_iter_num: Best iteration so far (by dev κ)
        parent_iter_nums: Iterations being merged (or None)
        recent_n: How many recent iterations to show in full
        artifacts_map: Optional dict mapping iter_num -> artifact_text
    
    Returns:
        Formatted history string for LLM prompt
    """
    if artifacts_map is None:
        artifacts_map = {}
    
    lines = []
    lines.append("# History\n")
    
    # Best-so-far (always full)
    if best_iter_num > 0:
        best_exp = experiments[best_iter_num - 1] if best_iter_num <= len(experiments) else None
        if best_exp:
            lines.append("## Best So Far")
            artifact_text = artifacts_map.get(best_iter_num)
            lines.append(render_full(best_exp, artifact_text))
            lines.append("")
    
    # Recent iterations (full or compact)
    lines.append("## Recent Iterations")
    for i, exp in enumerate(experiments[-recent_n:], len(experiments) - recent_n + 1):
        is_recent = i > len(experiments) - recent_n
        is_parent = i in parent_iter_nums if parent_iter_nums else False
        
        if is_parent or is_recent:
            # Show full
            artifact_text = artifacts_map.get(i)
            lines.append(render_full(exp, artifact_text))
        else:
            # Show compact
            lines.append(render_compact(exp))
        lines.append("")
    
    # All others (compact)
    if len(experiments) > recent_n:
        lines.append("## Earlier Iterations (compact)")
        for i, exp in enumerate(experiments[:-recent_n], 1):
            lines.append(render_compact(exp))
    
    return "\n".join(lines)


def render_plan_aggregate(experiments: List[Dict[str, Any]]) -> str:
    """
    Aggregate statistics per plan_id.
    
    Shows: plan X was proposed N times, won M times, mean Δ=...
    """
    by_plan: Dict[str, List[Dict[str, Any]]] = {}
    
    for exp in experiments:
        plan_id = exp.get("plan_id", "unknown")
        if plan_id not in by_plan:
            by_plan[plan_id] = []
        by_plan[plan_id].append(exp)
    
    lines = ["# Plan Aggregates\n"]
    
    for plan_id, exps in sorted(by_plan.items()):
        wins = sum(1 for e in exps if e.get("is_winner"))
        mean_delta = sum(e.get("delta_dev_kappa", 0) for e in exps) / len(exps)
        
        lines.append(
            f"**{plan_id}**: proposed {len(exps)}, won {wins}, "
            f"mean Δ={mean_delta:+.4f}"
        )
    
    return "\n".join(lines)
