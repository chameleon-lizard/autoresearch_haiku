"""
Artifact class: serializable, hashable representation of optimizable objects.

Core invariant (DesignDoc §2.1): Every artifact has a deterministic content hash
that is used as the cache key. The hash is computed from the artifact text only
(no timestamps, run IDs, or other non-functional state).

Usage:

    # Create from text
    artifact = Artifact(text="Your prompt here...")
    print(artifact.content_hash)  # e.g., "abc123def456789..."
    
    # Load from file
    artifact = Artifact.load_from_file("state/cache/abc123.../artifact.txt")
    
    # Save to file
    artifact.save_to_file("path/to/artifact.txt")
    
    # Create from template
    artifact = Artifact.from_template("classify", variables={"key": "value"})
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class Artifact:
    """
    An artifact is a serializable, hashable object that can be scored and mutated.
    
    Attributes:
        text: The full artifact text (prompt, config, code, etc.)
        metadata: Optional metadata dict (not included in hash, for bookkeeping)
    """
    
    text: str
    metadata: Optional[Dict[str, Any]] = None
    
    @property
    def content_hash(self) -> str:
        """
        Compute content hash: sha256(artifact_text)[:16].
        
        This is the cache key. It is deterministic and independent of:
        - Timestamps
        - Run IDs
        - Iteration numbers
        - Any metadata
        
        Two artifacts with identical text will have identical hashes, and their
        cached scores will be reused (critical for resumability).
        """
        h = hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:16]
        return h
    
    def serialize(self) -> str:
        """
        Serialize artifact to string (for storage/logging).
        Format: just the text (no metadata; metadata is not cached).
        """
        return self.text
    
    @classmethod
    def deserialize(cls, text: str) -> "Artifact":
        """Deserialize artifact from string."""
        return cls(text=text)
    
    def save_to_file(self, path: Path) -> None:
        """Save artifact to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.text, encoding="utf-8")
    
    @classmethod
    def load_from_file(cls, path: Path) -> "Artifact":
        """Load artifact from disk."""
        text = path.read_text(encoding="utf-8")
        return cls(text=text)
    
    def __str__(self) -> str:
        """String representation: hash + first 50 chars."""
        preview = self.text[:50].replace("\n", " ")
        return f"Artifact({self.content_hash}): {preview}..."
    
    def __repr__(self) -> str:
        """Detailed representation."""
        return f"Artifact(hash={self.content_hash}, len={len(self.text)})"
    
    def __eq__(self, other: Any) -> bool:
        """Two artifacts are equal if they have the same content hash."""
        if not isinstance(other, Artifact):
            return False
        return self.content_hash == other.content_hash
    
    def __hash__(self) -> int:
        """Make artifact hashable (by content hash)."""
        return hash(self.content_hash)


class ArtifactSet:
    """
    Set-like container for artifacts, deduplicates by content hash.
    
    Usage:
        artifacts = ArtifactSet()
        artifacts.add(Artifact("text1"))
        artifacts.add(Artifact("text1"))  # Ignored: already in set
        print(len(artifacts))  # 1
    """
    
    def __init__(self):
        self._by_hash: Dict[str, Artifact] = {}
    
    def add(self, artifact: Artifact) -> None:
        """Add artifact to set (idempotent by content hash)."""
        self._by_hash[artifact.content_hash] = artifact
    
    def __contains__(self, artifact: Artifact) -> bool:
        """Check if artifact is in set."""
        return artifact.content_hash in self._by_hash
    
    def __len__(self) -> int:
        """Number of unique artifacts."""
        return len(self._by_hash)
    
    def __iter__(self):
        """Iterate over artifacts."""
        return iter(self._by_hash.values())
    
    def get_by_hash(self, hash_val: str) -> Optional[Artifact]:
        """Retrieve artifact by its content hash."""
        return self._by_hash.get(hash_val)
