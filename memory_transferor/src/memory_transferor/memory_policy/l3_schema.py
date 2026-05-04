"""L3 lifecycle policy rules for memory maintenance."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any


class UpgradeDecision(str, Enum):
    UPGRADE = "upgrade"
    ACCUMULATE = "accumulate"
    SKIP = "skip"
    CONFLICT = "conflict"
    USER_CONFIRM = "user_confirm"


class ConflictResolution(str, Enum):
    KEEP_OLD = "keep_old"
    USE_NEW = "use_new"
    MERGE = "merge"
    DEFER = "defer"


class L3Schema:
    """Declarative rules for memory extraction, upgrades, and conflicts."""

    MIN_OCCURRENCES_PREFERENCE: int = 2
    MIN_OCCURRENCES_WORKFLOW: int = 3

    HIGH_STAKES_PROFILE_FIELDS: set[str] = {
        "name_or_alias",
        "role_identity",
        "organization_or_affiliation",
        "common_languages",
    }

    HIGH_STAKES_PREFERENCE_FIELDS: set[str] = {
        "forbidden_expressions",
        "language_preference",
    }

    def is_worth_extracting(self, text: str) -> bool:
        if len(text.strip()) < 20:
            return False
        noise_patterns = {
            "thank you",
            "thanks",
            "ok",
            "okay",
            "sure",
            "got it",
            "understood",
        }
        return text.lower().strip() not in noise_patterns

    def should_upgrade_preference(
        self,
        candidate: str,
        existing: Any,
        occurrence_count: int,
    ) -> UpgradeDecision:
        if occurrence_count < self.MIN_OCCURRENCES_PREFERENCE:
            return UpgradeDecision.ACCUMULATE
        if candidate in (getattr(existing, "forbidden_expressions", []) or []):
            return UpgradeDecision.SKIP
        return UpgradeDecision.UPGRADE

    def should_upgrade_workflow(
        self,
        workflow_name: str,
        occurrence_count: int,
    ) -> UpgradeDecision:
        if occurrence_count < self.MIN_OCCURRENCES_WORKFLOW:
            return UpgradeDecision.ACCUMULATE
        return UpgradeDecision.UPGRADE

    def should_upgrade_profile_field(self, field: str) -> UpgradeDecision:
        if field in self.HIGH_STAKES_PROFILE_FIELDS:
            return UpgradeDecision.USER_CONFIRM
        return UpgradeDecision.UPGRADE

    def resolve_conflict(
        self,
        entity_type: str,
        field: str,
        old_value: Any,
        new_value: Any,
        source: str,
    ) -> ConflictResolution:
        if entity_type == "profile" and field in self.HIGH_STAKES_PROFILE_FIELDS:
            if source in {"user_statement", "l1_signal"}:
                return ConflictResolution.USE_NEW
            return ConflictResolution.DEFER

        if isinstance(old_value, list) and isinstance(new_value, list):
            return ConflictResolution.MERGE

        if entity_type == "preference":
            return ConflictResolution.USE_NEW

        if entity_type == "project":
            if field in {"current_stage", "is_active"}:
                return ConflictResolution.USE_NEW
            return ConflictResolution.MERGE

        return ConflictResolution.DEFER

    def is_temporary(self, text: str) -> bool:
        temp_signals = {
            "today",
            "tonight",
            "right now",
            "this time",
            "just this once",
            "for now",
        }
        lower = text.lower()
        return any(signal in lower for signal in temp_signals)

    def classify_episode(self, episode: Any) -> str:
        if not getattr(episode, "summary", ""):
            return "noise"
        if getattr(episode, "key_decisions", None):
            return "decision_record"
        if getattr(episode, "related_project", ""):
            return "project_update"
        return "task_completion"

    SENSITIVE_PATTERNS: list[str] = [
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
        r"\bpassword\b",
        r"\btoken\b",
        r"\bsecret\b",
        r"\bapi[_-]?key\b",
    ]

    def flag_sensitive(self, text: str) -> list[str]:
        labels = {
            "email": self.SENSITIVE_PATTERNS[0],
            "card_number": self.SENSITIVE_PATTERNS[1],
            "password_mention": self.SENSITIVE_PATTERNS[2],
            "token_mention": self.SENSITIVE_PATTERNS[3],
            "secret_mention": self.SENSITIVE_PATTERNS[4],
            "api_key_mention": self.SENSITIVE_PATTERNS[5],
        }
        return [
            name
            for name, pattern in labels.items()
            if re.search(pattern, text, re.IGNORECASE)
        ]


__all__ = ["ConflictResolution", "L3Schema", "UpgradeDecision"]
