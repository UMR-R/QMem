from __future__ import annotations


def confidence_from_evidence(evidence_count: int, *, platform_saved: bool = False) -> str:
    if platform_saved:
        return "high"
    if evidence_count >= 4:
        return "high"
    if evidence_count >= 2:
        return "medium"
    return "low"


def export_priority_for_type(memory_type: str, confidence: str) -> str:
    if memory_type in {"profile", "preference", "workflow"} and confidence in {"medium", "high"}:
        return "high"
    if memory_type == "topic" and confidence == "high":
        return "high"
    if confidence == "low":
        return "low"
    return "medium"
