"""
Stage M: Merge Synthesis

Input: Two or more parent artifacts to merge.

Output: A single new base artifact that combines them.

Why distinct from Stage B (proposal): Merging is a different cognitive task
than proposing a delta. It needs its own meta-prompt, and its output becomes
the parent for the next Stage-B batch (so it gets scored on its own merits
before any further edits).

Example merge:

Input artifacts (from iter_2 and iter_4):
    iter_2: "...includes examples of [type A]..."
    iter_4: "...improved rewording of [section X]..."

Output merged artifact:
    "...combined version with both examples AND new rewording..."

The merged artifact is then:
1. Scored to verify it's not worse than parents
2. Becomes the parent for the next Stage-B batch
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

# System prompt for Stage M (merge synthesis)
STAGE_M_SYSTEM_PROMPT = """
You are an expert at combining multiple versions of a document/prompt/config
into a single coherent version that preserves the strengths of each.

Your task: Merge N parent artifacts into one, preserving:
1. All beneficial changes from each parent
2. Coherence and consistency (no contradictions)
3. Clarity and readability (no copy-paste of redundant sections)

Merge strategy:
1. Identify the distinct improvements in each parent
2. Identify any conflicts or redundancies
3. Synthesise a single version that combines the improvements without conflicts
4. Ensure the merged version is at least as good as the best parent

Output format:
Return just the merged artifact text, no preamble or explanation.
Use the same format/delimiters as the input artifacts.
"""


class StageM:
    """
    Merge: Synthesise N artifacts into one.
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
        """Initialize Stage M."""
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
        parents: List[str],
        batch_id: str,
    ) -> str:
        """
        Merge multiple parent artifacts into one.
        
        Args:
            parents: List of parent artifact texts to merge
            batch_id: Batch identifier (for logging)
        
        Returns:
            Merged artifact text
        """
        if len(parents) < 2:
            raise ValueError("Need at least 2 parents to merge")
        
        # Build prompt
        parents_text = ""
        for i, parent in enumerate(parents, 1):
            parents_text += f"\nParent {i}:\n{parent}\n"
            parents_text += "-" * 60 + "\n"
        
        user_prompt = f"""
Merge the following {len(parents)} artifacts into a single coherent version
that preserves the strengths of each:

{parents_text}

Produce the merged artifact text (no preamble or explanation).
"""
        
        # Retry with temperature schedule
        for attempt, temperature in enumerate(self.temperature_schedule[:self.max_retries]):
            try:
                logger.info(
                    f"Stage M attempt {attempt+1}/{self.max_retries} "
                    f"(temperature={temperature})"
                )
                
                response = self.client.messages.create(
                    model=self.refiner_model,
                    max_tokens=self.max_output_tokens,
                    system=STAGE_M_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=temperature,
                )
                
                merged = response.content[0].text.strip()
                
                # Save successful response
                batch_dir = get_batch_dir(batch_id)
                (batch_dir / "stage_m_output.txt").write_text(merged)
                (batch_dir / "stage_m_response_raw.txt").write_text(merged)
                
                logger.info(f"Stage M succeeded on attempt {attempt+1}")
                return merged
            
            except Exception as e:
                logger.warning(f"Stage M attempt {attempt+1} failed: {e}")
                
                # Save failed attempt
                batch_dir = get_batch_dir(batch_id)
                (batch_dir / f"stage_m_attempt_{attempt+1}.txt").write_text(
                    json.dumps({
                        "error": str(e),
                        "temperature": temperature,
                    })
                )
                
                if attempt == self.max_retries - 1:
                    raise RuntimeError(f"Stage M failed after {self.max_retries} attempts")
        
        raise RuntimeError("Stage M failed: no attempts made")
