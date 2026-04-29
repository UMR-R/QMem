from __future__ import annotations

from hashlib import sha1

from memory_transferor.memory_models import PersistentMemoryItem


class SplitMergePolicy:
    """Small deterministic splits that are too brittle to leave only to prompts."""

    _CHECK_MARKERS = (
        "check", "review", "quality", "risk", "claim", "overclaim", "检查", "校验",
        "核对", "过度承诺", "风险", "质量",
    )
    _TOPIC_CONCEPTS = (
        ("aggregation_schema", ("aggregation schema", "聚合 schema", "汇聚", "persistent node")),
        ("retrieval_schema", ("retrieval schema", "检索 schema", "双向索引", "supporting episodes")),
        ("export_schema", ("export package", "export schema", "导出", "注入")),
        ("product_direction", ("browser plugin", "browser extension", "浏览器插件", "插件")),
    )

    def apply(self, items: list[PersistentMemoryItem]) -> list[PersistentMemoryItem]:
        expanded: list[PersistentMemoryItem] = []
        for item in items:
            expanded.extend(self._split_workflow_final_check(item))
        expanded = self._split_topic_concepts(expanded)
        return self._dedupe(expanded)

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

    def _split_topic_concepts(self, items: list[PersistentMemoryItem]) -> list[PersistentMemoryItem]:
        topics = [item for item in items if item.type == "topic"]
        additions: list[PersistentMemoryItem] = []
        for item in items:
            if item.type != "topic":
                continue
            if not self._is_broad_topic(item):
                continue
            text = f"{item.key} {item.description}".lower()
            for suffix, markers in self._TOPIC_CONCEPTS:
                if self._existing_topic_covers_concept(topics, item, markers):
                    continue
                if not any(marker.lower() in text for marker in markers):
                    continue
                key = f"{item.key}_{suffix}" if suffix not in item.key else item.key
                if key == item.key:
                    continue
                description = self._topic_description(item.description, suffix)
                additions.append(
                    item.model_copy(
                        update={
                            "memory_id": self._stable_id("topic", key, description, item.evidence_episode_ids),
                            "type": "topic",
                            "key": key,
                            "description": description,
                            "export_priority": "medium",
                        }
                    )
                )
        return items + additions

    def _is_broad_topic(self, item: PersistentMemoryItem) -> bool:
        text = f"{item.key} {item.description}".lower().replace("_", " ")
        broad_markers = ("system", "project", "platform", "系统", "项目", "平台")
        specific_markers = (
            "schema", "plugin", "extension", "benchmark", "proposal", "retrieval",
            "aggregation", "export", "browser", "插件", "评测", "检索", "导出", "聚合",
        )
        return any(marker in text for marker in broad_markers) and not any(
            marker in item.key.lower().replace("_", " ")
            for marker in specific_markers
        )

    def _existing_topic_covers_concept(
        self,
        topics: list[PersistentMemoryItem],
        source: PersistentMemoryItem,
        markers: tuple[str, ...],
    ) -> bool:
        for topic in topics:
            if topic is source:
                continue
            text = f"{topic.key} {topic.description}".lower().replace("_", " ")
            if any(marker.lower() in text for marker in markers):
                return True
        return False

    def _topic_description(self, parent_description: str, suffix: str) -> str:
        labels = {
            "aggregation_schema": "aggregation schema 设计",
            "retrieval_schema": "retrieval schema 设计",
            "export_schema": "export / injection package 设计",
            "product_direction": "产品或插件方向",
        }
        label = labels.get(suffix, suffix.replace("_", " "))
        return f"围绕该主题的{label}。"

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

    def _is_check_step(self, step: str) -> bool:
        lowered = step.lower()
        return any(marker in lowered for marker in self._CHECK_MARKERS)

    def _stable_id(self, memory_type: str, key: str, description: str, episode_ids: list[str]) -> str:
        seed = "|".join([memory_type, key, description, ",".join(sorted(episode_ids))])
        return f"{memory_type}_{sha1(seed.encode('utf-8')).hexdigest()[:10]}"
