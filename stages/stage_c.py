"""
Stage C: Selection

Input: History with metrics, current "best so far" callout.

Output: Either `iter=N` (use that single iteration as next parent)
or `merge=N1,N2,…` (synthesise a merge from these parents).

Why ask the LLM and not argmax: argmax overfits to one metric and ignores
the trajectory; the LLM sees the full history and can choose to revisit an
older promising branch when recent batches plateau.

Example decision:

Input history:
    iter_1: κ=0.50, plan=baseline
    iter_2: κ=0.52, plan=add_examples (winner)
    iter_3: κ=0.51, plan=reword (loser)
    iter_4: κ=0.53, plan=combine_both (winner)
    iter_5: κ=0.52, plan=simplify (loser)
    iter_6: κ=0.52, plan=expand_scope (tie)

Output decision:
    {"decision": "iter=4", "reasoning": "iter_4 is best and most recent winner"}

Or (if seeing older branch):
    {"decision": "merge=[2,4]", "reasoning": "Combine strengths of iter_2 (examples) and iter_4 (rewording)"}
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from autoresearch.paths import (
    REFINER_API_KEY,
    REFINER_MAX_INPUT_TOKENS,
    REFINER_MAX_OUTPUT_TOKENS,
    REFINER_MODEL,
    REFINER_TEMPERATURE_SCHEDULE,
    get_batch_dir,
)

logger = logging.getLogger(__name__)

# System prompt for Stage C (selection)
STAGE_C_SYSTEM_PROMPT = """
You are an expert at analysing experiment trajectories. Your task is to select
the next parent artifact for the loop to continue from.

You have access to:
- Full history of iterations: metrics (κ, F1, accuracy), plan_id, rationale
- Best-so-far metrics (highlighted)
- Recent wins/losses

Your job is to decide: Should the loop continue from the current best
iteration? Or should it revisit an older promising branch and try to
combine them?

Key principles:
1. Prefer recent winners over old winners (unless old branch looks better)
2. If recent iterations plateau or degrade, consider older branches
3. If multiple branches show promise, suggest a merge (let Stage M synthesise)
4. If metrics are noisy, weight trajectory over single-iteration peak

Output format:
```json
{
    "decision": "iter=42" or "merge=[10,25,40]",
    "reasoning": "Why this choice?",
    "confidence": 0.95
}
```

If unsure, default to the current best iteration.
"""


class StageC:
    """
    Selection: Choose next parent (or merge targets).
    """
    
    def __init__(
        self,
        refiner_model: str = REFINER_MODEL,
        api_key: str = REFINER_API_KEY,
        max_input_tokens: int = REFINER_MAX_INPUT_TOKENS,
        max_output_tokens: int = REFINER_MAX_OUTPUT_TOKENS,
        temperature_schedule: List[float] = REFINER_TEMPERATURE_SCHEDULE,
        max_retries: int = 4,
    ):
        """Initialize Stage C."""
        self.refiner_model = refiner_model
        self.api_key = api_key
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens
        self.temperature_schedule = temperature_schedule
        self.max_retries = max_retries
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
    
    def run(
        self,
        history_context: str,
        batch_id: str,
    ) -> Dict[str, Any]:
        """
        Select next parent iteration or merge targets.
        
        Args:
            history_context: Formatted history with all metrics and plan info
            batch_id: Batch identifier (for logging)
        
        Returns:
            Dict with "decision" (str: "iter=N" or "merge=N1,N2,..."),
            "reasoning" (str), "confidence" (float)
        """
        
        user_prompt = f"""
Experiment History:
{history_context}

Based on this history, which iteration should be the next parent?
Should we continue from the current best, or revisit and potentially merge older branches?

Provide a JSON response with: decision, reasoning, confidence
"""
        
        # Retry with temperature schedule
        for attempt, temperature in enumerate(self.temperature_schedule[:self.max_retries]):
            try:
                logger.info(
                    f"Stage C attempt {attempt+1}/{self.max_retries} "
                    f"(temperature={temperature})"
                )
                
                response = self.client.messages.create(
                    model=self.refiner_model,
                    max_tokens=self.max_output_tokens,
                    system=STAGE_C_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=temperature,
                )
                
                response_text = response.content[0].text
                
                # Parse JSON response
                decision = self._parse_decision(response_text)
                
                # Validate
                if "decision" not in decision:
                    raise ValueError("Missing 'decision' in response")
                
                # Save successful response
                batch_dir = get_batch_dir(batch_id)
                (batch_dir / "stage_c_decision.json").write_text(
                    json.dumps(decision, indent=2)
                )
                
                logger.info(f"Stage C succeeded: {decision['decision']}")
                return decision
            
            except Exception as e:
                logger.warning(f"Stage C attempt {attempt+1} failed: {e}")
                
                # Save failed attempt
                batch_dir = get_batch_dir(batch_id)
                (batch_dir / f"stage_c_attempt_{attempt+1}.txt").write_text(
                    json.dumps({
                        "error": str(e),
                        "temperature": temperature,
                        "response_preview": response_text[:500] if 'response_text' in locals() else None,
                    })
                )
                
                if attempt == self.max_retries - 1:
                    raise RuntimeError(f"Stage C failed after {self.max_retries} attempts")
        
        raise RuntimeError("Stage C failed: no attempts made")
    
    @staticmethod
    def _parse_decision(response_text: str) -> Dict[str, Any]:
        """
        Parse decision from LLM response.
        
        Expected format: JSON object with decision, reasoning, confidence
        """
        import re
        
        # Try to extract JSON
        json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(1)
        
        # Look for { ... }
        obj_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if obj_match:
            response_text = obj_match.group(0)
        
        decision = json.loads(response_text)
        
        if not isinstance(decision, dict):
            raise ValueError(f"Expected dict, got {type(decision)}")
        
        # Validate decision format
        decision_str = decision.get("decision", "")
        if not (decision_str.startswith("iter=") or decision_str.startswith("merge=")):
            raise ValueError(f"Invalid decision format: {decision_str}")
        
        return decision
    
    @staticmethod
    def parse_decision_target(decision_str: str) -> Union[int, List[int]]:
        """
        Parse decision target from decision string.
        
        Args:
            decision_str: One of "iter=N" or "merge=N1,N2,..."
        
        Returns:
            int if iter, list of ints if merge
        """
        if decision_str.startswith("iter="):
            return int(decision_str.split("=")[1])
        elif decision_str.startswith("merge="):
            iters_str = decision_str.split("=")[1]
            return [int(x.strip()) for x in iters_str.split(",")]
        else:
            raise ValueError(f"Invalid decision format: {decision_str}")
