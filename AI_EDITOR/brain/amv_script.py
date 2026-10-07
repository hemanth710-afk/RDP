"""AMV script/brief model for AI_EDITOR.

Represents the user's creative brief including song, clips,
characters, duration, style, and editing preferences.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence


class AMVScriptError(ValueError):
    """Raised when an AMV script/brief is invalid."""


@dataclass(frozen=True, slots=True)
class ClipReference:
    """A single source clip referenced by the AMV script."""

    path: str
    clip_id: str = ""
    character: str = ""
    scene: str = ""
    notes: str = ""
    start_time: float | None = None
    end_time: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "clip_id": self.clip_id,
            "character": self.character,
            "scene": self.scene,
            "notes": self.notes,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClipReference":
        return cls(
            path=str(data["path"]),
            clip_id=str(data.get("clip_id", "")),
            character=str(data.get("character", "")),
            scene=str(data.get("scene", "")),
            notes=str(data.get("notes", "")),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
        )


@dataclass(frozen=True, slots=True)
class AMVScript:
    """Complete AMV editing brief provided by the user."""

    title: str
    song_path: str = ""
    clips: Sequence[ClipReference] = field(default_factory=tuple)
    target_duration: float | None = None
    lyrics: str = ""
    mood: str = ""
    editing_style: str = ""
    special_requirements: str = ""
    notes: str = ""
    frame_rate: float = 30.0
    width: int = 1920
    height: int = 1080

    def __post_init__(self) -> None:
        if not isinstance(self.title, str) or not self.title.strip():
            raise AMVScriptError("AMV script title is required.")

        if self.target_duration is not None and self.target_duration <= 0:
            raise AMVScriptError(
                "target_duration must be greater than zero."
            )

        if self.frame_rate <= 0:
            raise AMVScriptError(
                "frame_rate must be greater than zero."
            )

        if self.width <= 0 or self.height <= 0:
            raise AMVScriptError(
                "width and height must be greater than zero."
            )

    def validate_paths(self) -> list[str]:
        """Return a list of missing file paths."""
        missing = []

        if self.song_path and not Path(self.song_path).exists():
            missing.append(f"Song: {self.song_path}")

        for clip in self.clips:
            if clip.path and not Path(clip.path).exists():
                missing.append(f"Clip: {clip.path}")

        return missing

    def clip_inventory_summary(self) -> str:
        """Return a concise text summary of available clips."""
        lines = []
        for i, clip in enumerate(self.clips):
            clip_id = clip.clip_id or f"clip_{i}"
            parts = [clip_id]
            if clip.character:
                parts.append(f"character={clip.character}")
            if clip.scene:
                parts.append(f"scene={clip.scene}")
            if clip.start_time is not None and clip.end_time is not None:
                dur = clip.end_time - clip.start_time
                parts.append(f"duration={dur:.1f}s")
            lines.append(" | ".join(parts))
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "song_path": self.song_path,
            "clips": [c.to_dict() for c in self.clips],
            "target_duration": self.target_duration,
            "lyrics": self.lyrics,
            "mood": self.mood,
            "editing_style": self.editing_style,
            "special_requirements": self.special_requirements,
            "notes": self.notes,
            "frame_rate": self.frame_rate,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AMVScript":
        clips_data = data.get("clips", [])
        clips = tuple(
            ClipReference.from_dict(c) for c in clips_data
        )

        return cls(
            title=str(data["title"]),
            song_path=str(data.get("song_path", "")),
            clips=clips,
            target_duration=data.get("target_duration"),
            lyrics=str(data.get("lyrics", "")),
            mood=str(data.get("mood", "")),
            editing_style=str(data.get("editing_style", "")),
            special_requirements=str(
                data.get("special_requirements", "")
            ),
            notes=str(data.get("notes", "")),
            frame_rate=float(data.get("frame_rate", 30.0)),
            width=int(data.get("width", 1920)),
            height=int(data.get("height", 1080)),
        )

    @classmethod
    def from_json_file(cls, path: str | Path) -> "AMVScript":
        """Load an AMV script from a JSON file."""
        file_path = Path(path)
        if not file_path.exists():
            raise AMVScriptError(
                f"AMV script file not found: {file_path}"
            )

        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AMVScriptError(
                f"Invalid JSON in AMV script: {exc}"
            ) from exc

        return cls.from_dict(data)
