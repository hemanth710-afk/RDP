"""Structured editing plan models for AI_EDITOR.

The AI may produce natural-language instructions, but actual editing
must be represented as explicit, validated actions before execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


class EditingPlanError(ValueError):
    """Raised when an editing plan is invalid."""


@dataclass(frozen=True, slots=True)
class EditingAction:
    """One deterministic action in an editing plan."""

    action: str
    parameters: Mapping[str, Any] = field(
        default_factory=dict
    )
    start_time: float | None = None
    end_time: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action, str):
            raise EditingPlanError(
                "Action name must be a string."
            )

        if not self.action.strip():
            raise EditingPlanError(
                "Action name cannot be empty."
            )

        if self.start_time is not None:
            if self.start_time < 0:
                raise EditingPlanError(
                    "start_time cannot be negative."
                )

        if self.end_time is not None:
            if self.end_time < 0:
                raise EditingPlanError(
                    "end_time cannot be negative."
                )

        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time < self.start_time
        ):
            raise EditingPlanError(
                "end_time cannot be earlier than start_time."
            )


@dataclass(frozen=True, slots=True)
class EditingPlan:
    """Complete structured plan generated from an AI editing request."""

    title: str
    duration: float
    frame_rate: float = 30.0
    width: int = 1080
    height: int = 1920
    actions: Sequence[EditingAction] = field(
        default_factory=tuple
    )
    source_files: Sequence[str] = field(
        default_factory=tuple
    )
    notes: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.title, str):
            raise EditingPlanError(
                "Plan title must be a string."
            )

        if not self.title.strip():
            raise EditingPlanError(
                "Plan title cannot be empty."
            )

        if self.duration <= 0:
            raise EditingPlanError(
                "Plan duration must be greater than zero."
            )

        if self.frame_rate <= 0:
            raise EditingPlanError(
                "Frame rate must be greater than zero."
            )

        if self.width <= 0:
            raise EditingPlanError(
                "Width must be greater than zero."
            )

        if self.height <= 0:
            raise EditingPlanError(
                "Height must be greater than zero."
            )

        for action in self.actions:
            if not isinstance(
                action,
                EditingAction,
            ):
                raise EditingPlanError(
                    "Every plan action must be an EditingAction."
                )

    @property
    def action_count(self) -> int:
        """Return the number of planned actions."""

        return len(self.actions)

    def to_dict(self) -> dict[str, Any]:
        """Convert the plan into a JSON-compatible dictionary."""

        return {
            "title": self.title,
            "duration": self.duration,
            "frame_rate": self.frame_rate,
            "width": self.width,
            "height": self.height,
            "actions": [
                {
                    "action": action.action,
                    "parameters": dict(
                        action.parameters
                    ),
                    "start_time": action.start_time,
                    "end_time": action.end_time,
                }
                for action in self.actions
            ],
            "source_files": list(
                self.source_files
            ),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any]
    ) -> "EditingPlan":
        """Reconstruct an EditingPlan from a dictionary."""
        actions = tuple(
            EditingAction(
                action=str(a["action"]),
                parameters=dict(
                    a.get("parameters", {})
                ),
                start_time=a.get("start_time"),
                end_time=a.get("end_time"),
            )
            for a in data.get("actions", [])
        )

        return cls(
            title=str(data["title"]),
            duration=float(data["duration"]),
            frame_rate=float(
                data.get("frame_rate", 30.0)
            ),
            width=int(
                data.get("width", 1080)
            ),
            height=int(
                data.get("height", 1920)
            ),
            actions=actions,
            source_files=tuple(
                str(s)
                for s in data.get(
                    "source_files", []
                )
            ),
            notes=str(
                data.get("notes", "")
            ),
        )