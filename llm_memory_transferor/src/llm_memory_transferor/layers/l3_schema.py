"""L3 Schema and Policy Layer - rules governing memory lifecycle."""

from __future__ import annotations

from enum import Enum
from typing import Any

from ..models import EpisodicMemory, PreferenceMemory, ProfileMemory, ProjectMemory, WorkflowMemory


class UpgradeDecision(str, Enum):
    UPGRADE = "upgrade"        # Promote to long-term persistent
    ACCUMULATE = "accumulate"  # Keep in episodic, needs more evidence
    SKIP = "skip"              # Not worth storing
    CONFLICT = "conflict"      # Conflicts with existing - needs resolution
    USER_CONFIRM = "user_confirm"  # High-stakes change, requires user approval


class ConflictResolution(str, Enum):
    KEEP_OLD = "keep_old"
    USE_NEW = "use_new"
    MERGE = "merge"
    DEFER = "defer"


class L3Schema:
    """
    Governs how memory is extracted, upgraded, and maintained.
    Rules are declarative - they decide HOW to process facts,
    not what the facts ARE.
    """

    # Minimum evidence occurrences before upgrading to persistent
    MIN_OCCURRENCES_PREFERENCE: int = 2
    MIN_OCCURRENCES_WORKFLOW: int = 3

    # Fields that require user confirmation before upgrade
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

    # ------------------------------------------------------------------
    # Extraction rules
    # ------------------------------------------------------------------

    def is_worth_extracting(self, text: str) -> bool:
        """Quick heuristic: does this text likely contain extractable memory?"""
        if len(text.strip()) < 20:
            return False
        noise_patterns = [
            "thank you",
            "thanks",
            "ok",
            "okay",
            "sure",
            "got it",
            "understood",
        ]
        lower = text.lower().strip()
        if any(lower == p for p in noise_patterns):
            return False
        return True

    # ------------------------------------------------------------------
    # Upgrade rules
    # ------------------------------------------------------------------

    def should_upgrade_preference(
        self, candidate: str, existing: PreferenceMemory, occurrence_count: int
    ) -> UpgradeDecision:
        if occurrence_count < self.MIN_OCCURRENCES_PREFERENCE:
            return UpgradeDecision.ACCUMULATE
        if candidate in existing.forbidden_expressions:
            return UpgradeDecision.SKIP
        return UpgradeDecision.UPGRADE

    def should_upgrade_workflow(
        self, workflow_name: str, occurrence_count: int
    ) -> UpgradeDecision:
        if occurrence_count < self.MIN_OCCURRENCES_WORKFLOW:
            return UpgradeDecision.ACCUMULATE
        return UpgradeDecision.UPGRADE

    def should_upgrade_profile_field(self, field: str) -> UpgradeDecision:
        if field in self.HIGH_STAKES_PROFILE_FIELDS:
            return UpgradeDecision.USER_CONFIRM
        return UpgradeDecision.UPGRADE

    # ------------------------------------------------------------------
    # Conflict resolution rules
    # ------------------------------------------------------------------

    def resolve_conflict(
        self,
        entity_type: str,
        field: str,
        old_value: Any,
        new_value: Any,
        source: str,
    ) -> ConflictResolution:
        """Default conflict resolution policy."""
        # Profile identity fields: prefer explicit user statements
        if entity_type == "profile" and field in self.HIGH_STAKES_PROFILE_FIELDS:
            if source in ("user_statement", "l1_signal"):
                return ConflictResolution.USE_NEW
            return ConflictResolution.DEFER

        # Lists: merge unless values directly contradict
        if isinstance(old_value, list) and isinstance(new_value, list):
            return ConflictResolution.MERGE

        # Preferences: newer platform signal or recent conversation wins
        if entity_type == "preference":
            return ConflictResolution.USE_NEW

        # Projects: merge additive fields, prefer new for state fields
        if entity_type == "project":
            if field in ("current_stage", "is_active"):
                return ConflictResolution.USE_NEW
            return ConflictResolution.MERGE

        return ConflictResolution.DEFER

    # ------------------------------------------------------------------
    # Memory lifecycle rules
    # ------------------------------------------------------------------

    def is_temporary(self, text: str) -> bool:
        """Returns True if this looks like a one-time task, not worth long-term storage."""
        temp_signals = [
            "today",
            "tonight",
            "right now",
            "this time",
            "just this once",
            "for now",
        ]
        lower = text.lower()
        return any(sig in lower for sig in temp_signals)

    def classify_episode(self, episode: EpisodicMemory) -> str:
        """
        Returns what kind of episode this is:
        'task_completion' | 'decision_record' | 'project_update' | 'noise'
        """
        if not episode.summary:
            return "noise"
        if episode.key_decisions:
            return "decision_record"
        if episode.related_project:
            return "project_update"
        return "task_completion"

    # ------------------------------------------------------------------
    # Privacy and deletion rules
    # ------------------------------------------------------------------

    SENSITIVE_PATTERNS: list[str] = [
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # email
        r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",            # credit card
        r"\bpassword\b",
        r"\btoken\b",
        r"\bsecret\b",
        r"\bapi[_-]?key\b",
    ]

    def flag_sensitive(self, text: str) -> list[str]:
        """Returns list of detected sensitive pattern names."""
        import re
        flags = []
        patterns = {
            "email": self.SENSITIVE_PATTERNS[0],
            "card_number": self.SENSITIVE_PATTERNS[1],
            "password_mention": self.SENSITIVE_PATTERNS[2],
            "token_mention": self.SENSITIVE_PATTERNS[3],
            "secret_mention": self.SENSITIVE_PATTERNS[4],
            "api_key_mention": self.SENSITIVE_PATTERNS[5],
        }
        for name, pat in patterns.items():
            if re.search(pat, text, re.IGNORECASE):
                flags.append(name)
        return flags
