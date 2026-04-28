"""
Stage A: Disagreement Generalisation

Input: A sample of training examples where the candidate disagrees with
ground truth, balanced across error types.

Output: A free-text generalisation of the failure modes.

Why: Feeding raw errors to the proposer (Stage B) encourages overfitting to
those specific examples. Forcing an abstraction step makes the next-stage
proposal more robust.

Example:

    Input errors:
    - Example 1: Judge predicts "positive" but label is "negative"
      Error: False positive on subjective opinions
    - Example 2: Judge predicts "neutral" but label is "positive"
      Error: Misses enthusiasm in casual language
    - Example 3: Judge predicts "positive" but label is "negative"
      Error: Treats sarcasm as literal positive sentiment

    Output generalisation:
    "The judge struggles with three patterns:
    1. False positives on subjective/opinionated content
    2. Misses informal positive markers (enthusiasm, casual language)
    3. Confuses sarcasm for literal positive sentiment
    
    Recommendations: Add examples of sarcasm; clarify subjective vs factual;
    emphasize informal positive markers."
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from autoresearch.paths import (
    REFINER_API_KEY,
    REFINER_MAX_INPUT_TOKENS,
    REFINER_MAX_OUTPUT_TOKENS,
    REFINER_MODEL,
    REFINER_TEMPERATURE_SCHEDULE,
    get_batch_dir,
)

logger = logging.getLogger(__name__)

# System prompt for Stage A (diagnosis generalisation)
STAGE_A_SYSTEM_PROMPT = """
You are an expert at identifying patterns in machine learning errors.

Given a sample of examples where a judge/classifier disagrees with ground truth,
your task is to:

1. Identify recurring error patterns (not one-off mistakes)
2. Categorize errors by type (false positives, false negatives, boundary cases, etc.)
3. Propose root causes (ambiguity in task, missing examples, unclear instructions, etc.)
4. Generate actionable recommendations for the next iteration

Be concise but thorough. Focus on systematic issues, not individual examples.
Your output should guide the next proposal (Stage B) toward targeted improvements.
"""


class StageA:
    """
    Diagnosis: Generalise failure modes from a sample of errors.
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
        """Initialize Stage A."""
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
        artifact_text: str,
        errors: List[Dict[str, Any]],
        batch_id: str,
    ) -> str:
        """
        Generalise failure modes from a sample of errors.
        
        Args:
            artifact_text: The candidate artifact (e.g., prompt)
            errors: List of error dicts with keys: example_id, prediction, label, reasoning
            batch_id: Batch identifier (for logging/dumping)
        
        Returns:
            Free-text generalisation of failure modes
        """
        # Build error summary for LLM
        error_text = self._format_errors(errors)
        
        # Build prompt
        user_prompt = f"""
Artifact (Judge/Classifier):
{artifact_text}

Sample of errors (where judge disagrees with ground truth):
{error_text}

Generalise the failure patterns. Identify root causes and recommend improvements for the next iteration.
"""
        
        # Retry with temperature schedule
        for attempt, temperature in enumerate(self.temperature_schedule[:self.max_retries]):
            try:
                logger.info(
                    f"Stage A attempt {attempt+1}/{self.max_retries} "
                    f"(temperature={temperature})"
                )
                
                response = self.client.messages.create(
                    model=self.refiner_model,
                    max_tokens=self.max_output_tokens,
                    system=STAGE_A_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=temperature,
                )
                
                diagnosis = response.content[0].text
                
                # Save successful response
                batch_dir = get_batch_dir(batch_id)
                (batch_dir / f"stage_a_output.txt").write_text(diagnosis)
                
                logger.info(f"Stage A succeeded on attempt {attempt+1}")
                return diagnosis
            
            except Exception as e:
                logger.warning(f"Stage A attempt {attempt+1} failed: {e}")
                
                # Save failed attempt
                batch_dir = get_batch_dir(batch_id)
                (batch_dir / f"stage_a_attempt_{attempt+1}.txt").write_text(
                    json.dumps({"error": str(e), "temperature": temperature})
                )
                
                if attempt == self.max_retries - 1:
                    raise RuntimeError(f"Stage A failed after {self.max_retries} attempts")
        
        raise RuntimeError("Stage A failed: no attempts made")
    
    @staticmethod
    def _format_errors(errors: List[Dict[str, Any]]) -> str:
        """Format error sample as readable text."""
        if not errors:
            return "(No errors: artifact achieved perfect agreement on sample)"
        
        lines = []
        for i, err in enumerate(errors[:10], 1):  # Show up to 10 examples
            lines.append(f"\nError {i}:")
            lines.append(f"  Example ID: {err.get('example_id', 'unknown')}")
            lines.append(f"  Text: {err.get('text', 'N/A')[:100]}...")
            lines.append(f"  Judge prediction: {err.get('prediction', 'N/A')}")
            lines.append(f"  Ground truth: {err.get('label', 'N/A')}")
            if err.get("reasoning"):
                lines.append(f"  Judge reasoning: {err['reasoning'][:100]}...")
        
        if len(errors) > 10:
            lines.append(f"\n... and {len(errors) - 10} more errors")
        
        return "\n".join(lines)
