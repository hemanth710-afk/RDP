from __future__ import annotations

from typing import Any, Mapping, Sequence

from .composition import CompositionController
from .effects import EffectsController
from .layers import LayerController
from .project import ProjectController
from .script_runner import AEScriptRunner


class AEAutomationCommands:
    """High-level deterministic command interface for After Effects."""

    def __init__(
        self,
        runner: AEScriptRunner | None = None,
        *,
        executable_path: str | None = None,
    ) -> None:
        self.runner = runner or AEScriptRunner(executable_path)

        self.project = ProjectController(self.runner)
        self.composition = CompositionController(self.runner)
        self.layers = LayerController(self.runner)
        self.effects = EffectsController(self.runner)

    def create_project(self) -> str:
        """Create a new After Effects project."""
        return self.project.create_project()

    def open_project(self, project_path: str) -> str:
        """Open an existing After Effects project."""
        return self.project.open_project(project_path)

    def save_project(self) -> str:
        """Save the current project."""
        return self.project.save_project()

    def save_project_as(self, project_path: str) -> str:
        """Save the current project to a new path."""
        return self.project.save_project_as(project_path)

    def create_composition(
        self,
        name: str,
        width: int,
        height: int,
        pixel_aspect: float = 1.0,
        duration: float = 10.0,
        frame_rate: float = 30.0,
        background_color: Sequence[float] = (0.0, 0.0, 0.0),
    ) -> str:
        """Create a composition."""
        return self.composition.create_composition(
            name=name,
            width=width,
            height=height,
            pixel_aspect=pixel_aspect,
            duration=duration,
            frame_rate=frame_rate,
            background_color=background_color,
        )

    def add_layer(
        self,
        composition_name: str,
        layer_name: str,
        layer_type: str,
        **kwargs: Any,
    ) -> str:
        """
        Add a layer using a controlled layer type.

        Supported layer types:
        solid, text, null, adjustment, footage
        """
        normalized_type = layer_type.strip().lower()

        if normalized_type == "solid":
            return self.add_solid(
                composition_name,
                layer_name,
                **kwargs,
            )

        if normalized_type == "text":
            text = kwargs.pop("text", "")
            if kwargs:
                raise ValueError(
                    f"Unsupported text-layer arguments: {sorted(kwargs)}"
                )

            return self.add_text(
                composition_name,
                layer_name,
                text,
            )

        if normalized_type == "null":
            if kwargs:
                raise ValueError(
                    f"Unsupported null-layer arguments: {sorted(kwargs)}"
                )

            return self.layers.add_null(
                composition_name,
                layer_name,
            )

        if normalized_type == "adjustment":
            if kwargs:
                raise ValueError(
                    f"Unsupported adjustment-layer arguments: {sorted(kwargs)}"
                )

            return self.layers.add_adjustment_layer(
                composition_name,
                layer_name,
            )

        if normalized_type == "footage":
            footage_name = kwargs.pop("footage_name", None)

            if kwargs:
                raise ValueError(
                    f"Unsupported footage-layer arguments: {sorted(kwargs)}"
                )

            if not footage_name:
                raise ValueError(
                    "footage_name is required for a footage layer."
                )

            return self.layers.add_imported_footage(
                composition_name,
                footage_name,
            )

        raise ValueError(
            "Unsupported layer_type. "
            "Use solid, text, null, adjustment, or footage."
        )

    def add_text(
        self,
        composition_name: str,
        layer_name: str,
        text: str,
    ) -> str:
        """Add a text layer."""
        return self.layers.add_text(
            composition_name,
            layer_name,
            text,
        )

    def add_solid(
        self,
        composition_name: str,
        layer_name: str,
        color: Sequence[float] = (0.0, 0.0, 0.0),
        width: int | None = None,
        height: int | None = None,
        duration: float | None = None,
    ) -> str:
        """Add a solid layer."""
        return self.layers.add_solid(
            composition_name=composition_name,
            layer_name=layer_name,
            color=color,
            width=width,
            height=height,
            duration=duration,
        )

    def import_footage(self, footage_path: str) -> str:
        """Import footage into the current project."""
        return self.layers.import_footage(footage_path)

    def add_imported_footage(
        self,
        composition_name: str,
        footage_name: str,
    ) -> str:
        """Add imported footage to a composition."""
        return self.layers.add_imported_footage(
            composition_name,
            footage_name,
        )

    def rename_layer(
        self,
        composition_name: str,
        layer_name: str,
        new_name: str,
    ) -> str:
        """Rename a layer."""
        return self.layers.rename_layer(
            composition_name,
            layer_name,
            new_name,
        )

    def set_transform(
        self,
        composition_name: str,
        layer_name: str,
        properties: Mapping[str, Any],
    ) -> str:
        """Set supported layer transform properties."""
        return self.layers.set_transform(
            composition_name,
            layer_name,
            properties,
        )

    def set_keyframe(
        self,
        composition_name: str,
        layer_name: str,
        property_name: str,
        time: float,
        value: Any,
    ) -> str:
        """Add a transform keyframe."""
        return self.layers.add_keyframe(
            composition_name,
            layer_name,
            property_name,
            time,
            value,
        )

    def add_effect(
        self,
        composition_name: str,
        layer_name: str,
        effect_name: str,
        match_name: str | None = None,
    ) -> str:
        """Add a native or exposed third-party effect."""
        return self.effects.add_effect(
            composition_name,
            layer_name,
            effect_name,
            match_name,
        )

    def remove_effect(
        self,
        composition_name: str,
        layer_name: str,
        effect_name: str,
        match_name: str | None = None,
    ) -> str:
        """Remove an effect."""
        return self.effects.remove_effect(
            composition_name,
            layer_name,
            effect_name,
            match_name,
        )

    def set_effect_property(
        self,
        composition_name: str,
        layer_name: str,
        effect_name: str,
        property_name: str,
        value: Any,
        match_name: str | None = None,
    ) -> str:
        """Set an effect property."""
        return self.effects.set_effect_property(
            composition_name=composition_name,
            layer_name=layer_name,
            effect_name=effect_name,
            property_name=property_name,
            value=value,
            match_name=match_name,
        )

    def get_project_info(self) -> str:
        """Get current project information."""
        return self.project.get_project_info()

    def get_composition_info(self, composition_name: str) -> str:
        """Get composition information."""
        return self.composition.get_composition_info(
            composition_name,
        )

    def get_layer_info(
        self,
        composition_name: str,
        layer_name: str,
    ) -> str:
        """Get layer information."""
        return self.layers.get_layer_info(
            composition_name,
            layer_name,
        )

    def find_composition(self, name: str) -> str:
        """Find a composition by exact name."""
        return self.composition.find_composition(name)

    def find_layer(
        self,
        composition_name: str,
        layer_name: str,
    ) -> str:
        """Find a layer by exact name."""
        return self.layers.find_layer(
            composition_name,
            layer_name,
        )

    def find_effect(
        self,
        composition_name: str,
        layer_name: str,
        effect_name: str,
        match_name: str | None = None,
    ) -> str:
        """Find an effect by display name or match name."""
        return self.effects.find_effect(
            composition_name,
            layer_name,
            effect_name,
            match_name,
        )

    def set_parent(
        self,
        composition_name: str,
        child_layer_name: str,
        parent_layer_name: str | None,
    ) -> str:
        """Set or clear a layer parent."""
        return self.layers.set_parent(
            composition_name,
            child_layer_name,
            parent_layer_name,
        )

    def delete_layer(
        self,
        composition_name: str,
        layer_name: str,
    ) -> str:
        """Delete a layer."""
        return self.layers.delete_layer(
            composition_name,
            layer_name,
        )

    def duplicate_layer(
        self,
        composition_name: str,
        layer_name: str,
        new_name: str | None = None,
    ) -> str:
        """Duplicate a layer."""
        return self.layers.duplicate_layer(
            composition_name,
            layer_name,
            new_name,
        )

    def move_layer(
        self,
        composition_name: str,
        layer_name: str,
        target_index: int,
    ) -> str:
        """Move a layer to a target stack position."""
        return self.layers.move_layer(
            composition_name,
            layer_name,
            target_index,
        )

    def cut_clip(
        self,
        composition_name: str,
        layer_name: str,
        timeline_start: float,
        timeline_end: float,
        source_start: float = 0.0,
    ) -> str:
        """Place a source clip segment at a specific timeline position."""
        return self.layers.cut_clip(
            composition_name,
            layer_name,
            timeline_start,
            timeline_end,
            source_start,
        )

    def enable_layer(
        self,
        composition_name: str,
        layer_name: str,
        enabled: bool,
    ) -> str:
        """Enable or disable a layer."""
        return self.layers.set_enabled(
            composition_name,
            layer_name,
            enabled,
        )

    def set_parent_layer(
        self,
        composition_name: str,
        child_layer_name: str,
        parent_layer_name: str | None,
    ) -> str:
        """Set or clear a layer parent."""
        return self.layers.set_parent(
            composition_name,
            child_layer_name,
            parent_layer_name,
        )

    def remove_keyframes(
        self,
        composition_name: str,
        layer_name: str,
        property_name: str,
    ) -> str:
        """Remove all keyframes from a supported transform property."""
        return self.layers.remove_keyframes(
            composition_name,
            layer_name,
            property_name,
        )

    def set_keyframe_value(
        self,
        composition_name: str,
        layer_name: str,
        property_name: str,
        keyframe_index: int,
        value: Any,
    ) -> str:
        """Set an existing transform keyframe value."""
        return self.layers.set_keyframe_value(
            composition_name,
            layer_name,
            property_name,
            keyframe_index,
            value,
        )

    def inspect_effects(
        self,
        composition_name: str,
        layer_name: str,
    ) -> str:
        """Inspect effects exposed by a layer."""
        return self.effects.inspect_effects(
            composition_name,
            layer_name,
        )

    def get_effect_property(
        self,
        composition_name: str,
        layer_name: str,
        effect_name: str,
        property_name: str,
        match_name: str | None = None,
    ) -> str:
        """Get an effect property value."""
        return self.effects.get_effect_property(
            composition_name=composition_name,
            layer_name=layer_name,
            effect_name=effect_name,
            property_name=property_name,
            match_name=match_name,
        )

    def enable_effect(
        self,
        composition_name: str,
        layer_name: str,
        effect_name: str,
        enabled: bool,
        match_name: str | None = None,
    ) -> str:
        """Enable or disable an effect."""
        return self.effects.enable_effect(
            composition_name=composition_name,
            layer_name=layer_name,
            effect_name=effect_name,
            enabled=enabled,
            match_name=match_name,
        )

    def reorder_effect(
        self,
        composition_name: str,
        layer_name: str,
        effect_name: str,
        target_index: int,
        match_name: str | None = None,
    ) -> str:
        """Reorder an effect in the effect stack."""
        return self.effects.reorder_effect(
            composition_name=composition_name,
            layer_name=layer_name,
            effect_name=effect_name,
            target_index=target_index,
            match_name=match_name,
        )