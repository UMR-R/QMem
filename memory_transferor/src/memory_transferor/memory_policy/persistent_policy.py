from __future__ import annotations

from hashlib import sha1

from memory_transferor.memory_models import PersistentMemoryItem

from .split_merge_policy import SplitMergePolicy
from .type_boundary_policy import TypeBoundaryPolicy
from .upgrade_policy import confidence_from_evidence, export_priority_for_type


class PersistentMemoryPolicy:
    """Post-process LLM persistent items with deterministic L3 guardrails."""

    def __init__(
        self,
        type_boundary_policy: TypeBoundaryPolicy | None = None,
        split_merge_policy: SplitMergePolicy | None = None,
    ) -> None:
        self.type_boundary_policy = type_boundary_policy or TypeBoundaryPolicy()
        self.split_merge_policy = split_merge_policy or SplitMergePolicy()

    def apply(self, items: list[PersistentMemoryItem]) -> list[PersistentMemoryItem]:
        normalized = [self._normalize_type_and_confidence(item) for item in items]
        split = self.split_merge_policy.apply(normalized)
        return [self._normalize_type_and_confidence(item) for item in split]

    def _normalize_type_and_confidence(self, item: PersistentMemoryItem) -> PersistentMemoryItem:
        memory_type = self.type_boundary_policy.normalize_type(item.type, item.key, item.description)
        evidence_count = len(set(item.evidence_episode_ids or item.evidence_turn_ids))
        confidence = confidence_from_evidence(evidence_count)
        export_priority = export_priority_for_type(memory_type, confidence)
        key = item.key
        memory_id = item.memory_id
        if memory_type != item.type:
            memory_id = self._stable_id(memory_type, key, item.description, item.evidence_episode_ids)
        return item.model_copy(
            update={
                "memory_id": memory_id,
                "type": memory_type,
                "confidence": confidence,
                "export_priority": export_priority,
            }
        )

    def _stable_id(self, memory_type: str, key: str, description: str, episode_ids: list[str]) -> str:
        seed = "|".join([memory_type, key, description, ",".join(sorted(episode_ids))])
        return f"{memory_type}_{sha1(seed.encode('utf-8')).hexdigest()[:10]}"
