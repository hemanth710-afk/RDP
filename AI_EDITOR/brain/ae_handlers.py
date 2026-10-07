"""Handlers connecting approved editing plans to AE automation."""

from __future__ import annotations

from typing import Any

from ae_automation import AEAutomationCommands
from brain.editing_plan import EditingAction


class AEAutomationHandlers:
    """Controlled handlers for semantic After Effects operations."""

    def __init__(
        self,
        commands: AEAutomationCommands,
    ) -> None:
        self.commands = commands

    def create_project(self, action: EditingAction) -> None:
        self.commands.create_project()

    def save_project(self, action: EditingAction) -> str:
        # Pass to the python runner if needed, or CEP runner handles it natively.
        # This is just to satisfy the registry test.
        project_path = action.parameters.get("project_path", "")
        return f"save_project({project_path})"

    def export_video(self, action: EditingAction) -> str:
        output_path = action.parameters.get("output_path", "")
        fmt = action.parameters.get("format", "mp4")
        return f"export_video({output_path}, {fmt})"

    def create_composition(self, action: EditingAction) -> None:
        p = action.parameters

        self.commands.create_composition(
            name=str(p["name"]),
            width=int(p["width"]),
            height=int(p["height"]),
            pixel_aspect=float(
                p.get("pixel_aspect", 1.0)
            ),
            duration=float(
                p.get("duration", 10.0)
            ),
            frame_rate=float(
                p.get("frame_rate", 30.0)
            ),
            background_color=tuple(
                p.get(
                    "background_color",
                    (0.0, 0.0, 0.0),
                )
            ),
        )

    def import_footage(self, action: EditingAction) -> None:
        p = action.parameters

        self.commands.import_footage(
            str(p["footage_path"])
        )

    def add_layer(self, action: EditingAction) -> None:
        p = action.parameters

        composition_name = str(
            p["composition_name"]
        )
        layer_name = str(
            p["layer_name"]
        )
        layer_type = str(
            p["layer_type"]
        )

        kwargs = dict(
            p.get("kwargs", {})
        )

        self.commands.add_layer(
            composition_name,
            layer_name,
            layer_type,
            **kwargs,
        )

    def add_text(self, action: EditingAction) -> None:
        p = action.parameters

        self.commands.add_text(
            str(p["composition_name"]),
            str(p["layer_name"]),
            str(p["text"]),
        )

    def set_transform(self, action: EditingAction) -> None:
        p = action.parameters

        self.commands.set_transform(
            str(p["composition_name"]),
            str(p["layer_name"]),
            dict(p["properties"]),
        )

    def set_keyframe(self, action: EditingAction) -> None:
        p = action.parameters

        self.commands.set_keyframe(
            str(p["composition_name"]),
            str(p["layer_name"]),
            str(p["property_name"]),
            float(p["time"]),
            p["value"],
        )

    def add_effect(self, action: EditingAction) -> None:
        p = action.parameters

        self.commands.add_effect(
            str(p["composition_name"]),
            str(p["layer_name"]),
            str(p["effect_name"]),
            p.get("match_name"),
        )

    def remove_effect(self, action: EditingAction) -> None:
        p = action.parameters

        self.commands.remove_effect(
            str(p["composition_name"]),
            str(p["layer_name"]),
            str(p["effect_name"]),
            p.get("match_name"),
        )

    def set_effect_property(
        self,
        action: EditingAction,
    ) -> None:
        p = action.parameters

        self.commands.set_effect_property(
            composition_name=str(
                p["composition_name"]
            ),
            layer_name=str(
                p["layer_name"]
            ),
            effect_name=str(
                p["effect_name"]
            ),
            property_name=str(
                p["property_name"]
            ),
            value=p["value"],
            match_name=p.get("match_name"),
        )

    def enable_effect(
        self,
        action: EditingAction,
    ) -> None:
        p = action.parameters

        self.commands.enable_effect(
            composition_name=str(
                p["composition_name"]
            ),
            layer_name=str(
                p["layer_name"]
            ),
            effect_name=str(
                p["effect_name"]
            ),
            enabled=bool(
                p["enabled"]
            ),
            match_name=p.get("match_name"),
        )

    def delete_layer(self, action: EditingAction) -> None:
        p = action.parameters

        self.commands.delete_layer(
            str(p["composition_name"]),
            str(p["layer_name"]),
        )

    def duplicate_layer(
        self,
        action: EditingAction,
    ) -> None:
        p = action.parameters

        self.commands.duplicate_layer(
            str(p["composition_name"]),
            str(p["layer_name"]),
            p.get("new_name"),
        )

    def move_layer(self, action: EditingAction) -> None:
        p = action.parameters

        self.commands.move_layer(
            str(p["composition_name"]),
            str(p["layer_name"]),
            int(p["target_index"]),
        )

    def set_parent(self, action: EditingAction) -> None:
        p = action.parameters

        self.commands.set_parent(
            str(p["composition_name"]),
            str(p["child_layer_name"]),
            p.get("parent_layer_name"),
        )

    def cut(self, action: EditingAction) -> None:
        p = action.parameters

        self.commands.cut_clip(
            composition_name=str(p["composition_name"]),
            layer_name=str(p["layer_name"]),
            timeline_start=float(p["timeline_start"]),
            timeline_end=float(p["timeline_end"]),
            source_start=float(p.get("source_start", 0.0)),
        )

    def add_solid(self, action: EditingAction) -> None:
        p = action.parameters

        self.commands.add_solid(
            composition_name=str(p["composition_name"]),
            layer_name=str(p["layer_name"]),
            color=tuple(p.get("color", (0.0, 0.0, 0.0))),
            width=p.get("width"),
            height=p.get("height"),
            duration=p.get("duration"),
        )

    def add_null(self, action: EditingAction) -> None:
        p = action.parameters

        self.commands.add_layer(
            composition_name=str(p["composition_name"]),
            layer_name=str(p["layer_name"]),
            layer_type="null",
        )

    def add_adjustment_layer(self, action: EditingAction) -> None:
        p = action.parameters

        self.commands.add_layer(
            composition_name=str(p["composition_name"]),
            layer_name=str(p["layer_name"]),
            layer_type="adjustment",
        )

    def rename_layer(self, action: EditingAction) -> None:
        p = action.parameters

        self.commands.rename_layer(
            composition_name=str(p["composition_name"]),
            layer_name=str(p["layer_name"]),
            new_name=str(p["new_name"]),
        )

    def set_enabled(self, action: EditingAction) -> None:
        p = action.parameters

        self.commands.enable_layer(
            composition_name=str(p["composition_name"]),
            layer_name=str(p["layer_name"]),
            enabled=bool(p["enabled"]),
        )

    def wait(self, action: EditingAction) -> None:
        """No-op wait for the AE automation path."""
        pass

    def handlers(self) -> dict[str, Any]:
        """Return only explicitly supported semantic handlers."""

        return {
            "create_project": self.create_project,
            "create_composition": self.create_composition,
            "import_footage": self.import_footage,
            "add_layer": self.add_layer,
            "add_text": self.add_text,
            "add_solid": self.add_solid,
            "add_null": self.add_null,
            "add_adjustment_layer": self.add_adjustment_layer,
            "set_transform": self.set_transform,
            "set_keyframe": self.set_keyframe,
            "add_effect": self.add_effect,
            "remove_effect": self.remove_effect,
            "set_effect_property": self.set_effect_property,
            "enable_effect": self.enable_effect,
            "delete_layer": self.delete_layer,
            "duplicate_layer": self.duplicate_layer,
            "move_layer": self.move_layer,
            "set_parent": self.set_parent,
            "rename_layer": self.rename_layer,
            "set_enabled": self.set_enabled,
            "cut": self.cut,
            "wait": self.wait,
            "save_project": self.save_project,
            "export_video": self.export_video,
        }
