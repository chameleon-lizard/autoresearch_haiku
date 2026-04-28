"""
Stage B: Proposal

Input:
- Parent artifact (full text)
- Stage-A summary (failure modes)
- History (compact or full rendering)
- Shared notebook (user constraints)

Output: K ∈ [1, 5] sibling candidates, each with:
- plan_id: identifier for this type of proposal
- rationale: short explanation of the proposed change
- artifact_text: new artifact text (between explicit delimiters like <PROMPT>...</PROMPT>)

Why K parallel: Each is one focused edit; scoring K in parallel multiplies
throughput; sibling design lets the next selector compare apples-to-apples.

Example output (K=3):

    [
        {
            "plan_id": "add_examples",
            "rationale": "Add 5 diverse examples of sarcasm to help judge recognize sarcasm",
            "artifact_text": "<PROMPT>...(new prompt with examples)...</PROMPT>"
        },
        {
            "plan_id": "clarify_subjectivity",
            "rationale": "Add explicit instruction to distinguish subjective opinions from facts",
            "artifact_text": "<PROMPT>...(prompt with subjectivity guidance)...</PROMPT>"
        },
        {
            "plan_id": "reweight_confidence",
            "rationale": "Lower confidence threshold for negative predictions to reduce false positives",
            "artifact_text": "<PROMPT>...(modified confidence handling)...</PROMPT>"
        }
    ]
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

# System prompt for Stage B (proposal generation)
STAGE_B_SYSTEM_PROMPT = """
You are an expert prompt engineer and system designer. Your task is to generate
targeted improvements to an existing artifact (prompt, config, system design, etc.)
based on identified failure modes.

Constraints:
1. Generate K ∈ [1, 5] independent sibling proposals
2. Each proposal should change ONE focused aspect (not multiple things)
3. Each proposal should be motivated by one or more failure modes from the diagnosis
4. Each proposal should include a plan_id (short identifier) and rationale
5. Sibling proposals should explore different solutions to the same problem
   (e.g., two different approaches to fixing sarcasm detection)

Output format:
```json
[
    {
        "plan_id": "short_id_1",
        "rationale": "Why this change should help",
        "artifact_text": "<PROMPT>Full new artifact text here</PROMPT>"
    },
    ...
]
```

Be specific and actionable. Include the full artifact text in artifact_text,
not just a summary of changes.
"""


class StageB:
    """
    Proposal: Generate K sibling candidates with single-edit changes.
    """
    
    def __init__(
        self,
        refiner_model: str = REFINER_MODEL,
        api_key: str = REFINER_API_KEY,
        max_input_tokens: int = REFINER_MAX_INPUT_TOKENS,
        max_output_tokens: int = REFINER_MAX_OUTPUT_TOKENS,
        temperature_schedule: List[float] = REFINER_TEMPERATURE_SCHEDULE,
        max_retries: int = 4,
        batch_size: int = 3,
    ):
        """Initialize Stage B."""
        self.refiner_model = refiner_model
        self.api_key = api_key
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens
        self.temperature_schedule = temperature_schedule
        self.max_retries = max_retries
        self.batch_size = batch_size
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
        parent_artifact: str,
        diagnosis: str,
        history_context: str,
        notebook_constraints: str,
        batch_id: str,
        k: int = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate K sibling proposals.
        
        Args:
            parent_artifact: Current best artifact (full text)
            diagnosis: Stage-A failure mode summary
            history_context: Compact history rendering (previous iterations)
            notebook_constraints: User-injected constraints from notes.md
            batch_id: Batch identifier (for logging)
            k: Number of proposals (default: self.batch_size)
        
        Returns:
            List of K dicts with plan_id, rationale, artifact_text
        """
        if k is None:
            k = self.batch_size
        
        # Build prompt
        user_prompt = f"""
Parent Artifact:
{parent_artifact}

Failure Mode Analysis (from previous errors):
{diagnosis}

Recent History:
{history_context}

User Constraints / Notes:
{notebook_constraints}

Generate {k} sibling proposals. Each should:
1. Address one or more failure modes identified above
2. Make a focused, single-edit change (not multiple unrelated changes)
3. Include a short plan_id and clear rationale
4. Include the full modified artifact text

Return valid JSON array of objects with keys: plan_id, rationale, artifact_text
"""
        
        # Retry with temperature schedule
        for attempt, temperature in enumerate(self.temperature_schedule[:self.max_retries]):
            try:
                logger.info(
                    f"Stage B attempt {attempt+1}/{self.max_retries} "
                    f"(temperature={temperature})"
                )
                
                response = self.client.messages.create(
                    model=self.refiner_model,
                    max_tokens=self.max_output_tokens,
                    system=STAGE_B_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=temperature,
                )
                
                response_text = response.content[0].text
                
                # Parse JSON response
                candidates = self._parse_candidates(response_text)
                
                # Validate
                if not candidates or len(candidates) == 0:
                    raise ValueError("No candidates parsed from response")
                
                # Save successful response and parsed candidates
                batch_dir = get_batch_dir(batch_id)
                (batch_dir / f"stage_b_output.json").write_text(
                    json.dumps(candidates, indent=2)
                )
                (batch_dir / "stage_b_response_raw.txt").write_text(response_text)
                
                logger.info(f"Stage B succeeded on attempt {attempt+1}: {len(candidates)} candidates")
                return candidates
            
            except Exception as e:
                logger.warning(f"Stage B attempt {attempt+1} failed: {e}")
                
                # Save failed attempt
                batch_dir = get_batch_dir(batch_id)
                (batch_dir / f"stage_b_attempt_{attempt+1}.txt").write_text(
                    json.dumps({
                        "error": str(e),
                        "temperature": temperature,
                        "response_preview": response_text[:500] if 'response_text' in locals() else None,
                    })
                )
                
                if attempt == self.max_retries - 1:
                    raise RuntimeError(f"Stage B failed after {self.max_retries} attempts")
        
        raise RuntimeError("Stage B failed: no attempts made")
    
    @staticmethod
    def _parse_candidates(response_text: str) -> List[Dict[str, Any]]:
        """
        Parse candidates from LLM response.
        
        Expected format: JSON array of objects with plan_id, rationale, artifact_text
        """
        # Try to extract JSON array
        import re
        
        # Look for ```json ... ```
        json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(1)
        
        # Look for [ ... ]
        array_match = re.search(r"\[.*\]", response_text, re.DOTALL)
        if array_match:
            response_text = array_match.group(0)
        
        # Parse JSON
        candidates = json.loads(response_text)
        
        if not isinstance(candidates, list):
            raise ValueError(f"Expected list, got {type(candidates)}")
        
        # Validate each candidate
        for c in candidates:
            if not isinstance(c, dict):
                raise ValueError(f"Expected dict, got {type(c)}")
            if "plan_id" not in c or "artifact_text" not in c:
                raise ValueError(f"Missing plan_id or artifact_text in {c}")
        
        return candidates
