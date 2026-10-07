"""Checkpoint and resume support for long-running AMV jobs."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class ProjectPhase(str, Enum):
    """Pipeline phases for an AMV editing project."""

    INITIALIZED = "initialized"
    SCRIPT_LOADED = "script_loaded"
    SOURCE_ANALYZED = "source_analyzed"
    PLAN_GENERATED = "plan_generated"
    PLAN_APPROVED = "plan_approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProjectState:
    """Persistent state for a resumable AMV editing project."""

    project_id: str = field(
        default_factory=lambda: str(uuid.uuid4())
    )
    phase: ProjectPhase = ProjectPhase.INITIALIZED
    script_path: str = ""
    plan_path: str = ""
    plan_version: int = 0
    total_actions: int = 0
    completed_action_index: int = -1
    failed_action_index: int = -1
    failed_action_error: str = ""
    retry_count: int = 0
    source_analysis: dict[str, Any] = field(
        default_factory=dict
    )
    timestamps: dict[str, float] = field(
        default_factory=dict
    )

    def advance_phase(self, new_phase: ProjectPhase) -> None:
        """Move to a new pipeline phase."""
        self.phase = new_phase
        self.timestamps[f"phase_{new_phase.value}"] = time.time()

    def mark_action_completed(self, index: int) -> None:
        """Record successful completion of an action."""
        self.completed_action_index = index

    def mark_failed(
        self, index: int, error: str
    ) -> None:
        """Record a failed action."""
        self.failed_action_index = index
        self.failed_action_error = error
        self.advance_phase(ProjectPhase.FAILED)

    @property
    def next_action_index(self) -> int:
        """Return the index of the next action to execute."""
        return self.completed_action_index + 1

    @property
    def is_resumable(self) -> bool:
        """Return True if the project can be resumed."""
        return (
            self.phase
            in (
                ProjectPhase.EXECUTING,
                ProjectPhase.FAILED,
            )
            and self.completed_action_index
            < self.total_actions - 1
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "phase": self.phase.value,
            "script_path": self.script_path,
            "plan_path": self.plan_path,
            "plan_version": self.plan_version,
            "total_actions": self.total_actions,
            "completed_action_index": self.completed_action_index,
            "failed_action_index": self.failed_action_index,
            "failed_action_error": self.failed_action_error,
            "retry_count": self.retry_count,
            "source_analysis": self.source_analysis,
            "timestamps": self.timestamps,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectState":
        state = cls(
            project_id=str(
                data.get("project_id", str(uuid.uuid4()))
            ),
            phase=ProjectPhase(
                data.get("phase", "initialized")
            ),
            script_path=str(
                data.get("script_path", "")
            ),
            plan_path=str(
                data.get("plan_path", "")
            ),
            plan_version=int(
                data.get("plan_version", 0)
            ),
            total_actions=int(
                data.get("total_actions", 0)
            ),
            completed_action_index=int(
                data.get("completed_action_index", -1)
            ),
            failed_action_index=int(
                data.get("failed_action_index", -1)
            ),
            failed_action_error=str(
                data.get("failed_action_error", "")
            ),
            retry_count=int(
                data.get("retry_count", 0)
            ),
            source_analysis=dict(
                data.get("source_analysis", {})
            ),
            timestamps=dict(
                data.get("timestamps", {})
            ),
        )
        return state

    def save(self, path: str | Path) -> None:
        """Persist project state to a JSON file."""
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            json.dumps(
                self.to_dict(), indent=2, ensure_ascii=False
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "ProjectState":
        """Load project state from a JSON file."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(
                f"Project state file not found: {file_path}"
            )

        data = json.loads(
            file_path.read_text(encoding="utf-8")
        )
        return cls.from_dict(data)
