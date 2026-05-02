from __future__ import annotations

from hashlib import sha1

from memory_transferor.memory_models import PersistentMemoryItem


class SplitMergePolicy:
    """Small deterministic merge/split guardrails for persistent memory.

    Topic/project memory should default to one parent item per user-owned effort.
    Subareas can still be created by the LLM when evidence supports an
    independent retrieval intent, but this policy should not manufacture them.
    """

    _CHECK_MARKERS = (
        "check", "review", "quality", "risk", "claim", "overclaim", "检查", "校验",
        "核对", "过度承诺", "风险", "质量",
    )

    def apply(self, items: list[PersistentMemoryItem]) -> list[PersistentMemoryItem]:
        expanded: list[PersistentMemoryItem] = []
        for item in items:
            expanded.extend(self._split_workflow_final_check(item))
        deduped = self._dedupe(expanded)
        return self._merge_overlapping_topics(deduped)

    def _split_workflow_final_check(self, item: PersistentMemoryItem) -> list[PersistentMemoryItem]:
        if item.type != "workflow" or len(item.steps) < 3:
            return [item]
        last_step = str(item.steps[-1] or "")
        if not self._is_check_step(last_step):
            return [item]

        main_steps = item.steps[:-1]
        main = item.model_copy(update={"steps": main_steps})
        check_key = f"{item.key}_final_check"
        check = item.model_copy(
            update={
                "memory_id": self._stable_id("workflow", check_key, last_step, item.evidence_episode_ids),
                "type": "workflow",
                "key": check_key,
                "description": f"在完成高风险或正式输出后，执行最终检查：{last_step}",
                "steps": ["完成主要输出", last_step],
                "export_priority": "medium",
            }
        )
        return [main, check]

    def _dedupe(self, items: list[PersistentMemoryItem]) -> list[PersistentMemoryItem]:
        deduped: dict[tuple[str, str], PersistentMemoryItem] = {}
        for item in items:
            key = (item.type, item.key)
            if key not in deduped:
                deduped[key] = item
                continue
            current = deduped[key]
            merged_episode_ids = list(dict.fromkeys(current.evidence_episode_ids + item.evidence_episode_ids))
            merged_turn_ids = list(dict.fromkeys(current.evidence_turn_ids + item.evidence_turn_ids))
            deduped[key] = current.model_copy(
                update={
                    "evidence_episode_ids": merged_episode_ids,
                    "evidence_turn_ids": merged_turn_ids,
                }
            )
        return list(deduped.values())

    def _merge_overlapping_topics(self, items: list[PersistentMemoryItem]) -> list[PersistentMemoryItem]:
        topics = [item for item in items if item.type == "topic"]
        merged_children: set[str] = set()
        parent_updates: dict[str, dict[str, list[str]]] = {}

        for child in topics:
            parent = self._find_parent_topic(child, topics)
            if parent is None:
                continue
            merged_children.add(child.memory_id)
            update = parent_updates.setdefault(
                parent.memory_id,
                {
                    "evidence_episode_ids": list(parent.evidence_episode_ids),
                    "evidence_turn_ids": list(parent.evidence_turn_ids),
                },
            )
            update["evidence_episode_ids"] = list(
                dict.fromkeys(update["evidence_episode_ids"] + child.evidence_episode_ids)
            )
            update["evidence_turn_ids"] = list(dict.fromkeys(update["evidence_turn_ids"] + child.evidence_turn_ids))

        merged: list[PersistentMemoryItem] = []
        for item in items:
            if item.memory_id in merged_children:
                continue
            update = parent_updates.get(item.memory_id)
            if update is None:
                merged.append(item)
                continue
            merged.append(item.model_copy(update=update))
        return merged

    def _find_parent_topic(
        self,
        child: PersistentMemoryItem,
        topics: list[PersistentMemoryItem],
    ) -> PersistentMemoryItem | None:
        if child.type != "topic":
            return None
        candidates = [topic for topic in topics if topic is not child and self._is_parent_topic(topic, child)]
        if not candidates:
            return None
        return max(candidates, key=lambda topic: (len(topic.evidence_episode_ids), -len(topic.key)))

    def _is_parent_topic(self, parent: PersistentMemoryItem, child: PersistentMemoryItem) -> bool:
        parent_key = self._normalized_key(parent.key)
        child_key = self._normalized_key(child.key)
        if not parent_key or not child_key or parent_key == child_key:
            return False

        key_nested = child_key.startswith(f"{parent_key}_") or child_key.startswith(f"{parent_key}-")
        if not key_nested:
            return False

        parent_evidence = set(parent.evidence_episode_ids or parent.evidence_turn_ids)
        child_evidence = set(child.evidence_episode_ids or child.evidence_turn_ids)
        if not child_evidence:
            return False

        overlap = len(parent_evidence & child_evidence) / len(child_evidence)
        if overlap >= 0.7:
            return True

        return overlap >= 0.5 and self._parent_description_mentions_child(parent, child)

    def _parent_description_mentions_child(
        self,
        parent: PersistentMemoryItem,
        child: PersistentMemoryItem,
    ) -> bool:
        parent_text = f"{parent.key} {parent.description}".lower().replace("_", " ")
        child_terms = [
            term
            for term in self._normalized_key(child.key).replace("-", "_").split("_")
            if len(term) >= 4
        ]
        return any(term in parent_text for term in child_terms)

    def _normalized_key(self, key: str) -> str:
        return key.lower().strip().replace(" ", "_")

    def _is_check_step(self, step: str) -> bool:
        lowered = step.lower()
        return any(marker in lowered for marker in self._CHECK_MARKERS)

    def _stable_id(self, memory_type: str, key: str, description: str, episode_ids: list[str]) -> str:
        seed = "|".join([memory_type, key, description, ",".join(sorted(episode_ids))])
        return f"{memory_type}_{sha1(seed.encode('utf-8')).hexdigest()[:10]}"
