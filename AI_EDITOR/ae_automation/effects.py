from __future__ import annotations

from typing import Any, Mapping

from .script_runner import AEScriptRunner, jsx_string, jsx_value


class EffectsController:
    """Controlled After Effects effect and plugin automation."""

    EFFECT_PARade = "ADBE Effect Parade"

    def __init__(self, runner: AEScriptRunner) -> None:
        self.runner = runner

    def inspect_effects(
        self,
        composition_name: str,
        layer_name: str,
    ) -> str:
        """Inspect all effects exposed by a layer."""
        self._validate_name(composition_name, "composition_name")
        self._validate_name(layer_name, "layer_name")

        script = f"""
(function () {{
    var composition = findComposition({jsx_string(composition_name)});

    if (!composition) {{
        throw new Error("Composition not found.");
    }}

    var layer = findLayer(composition, {jsx_string(layer_name)});

    if (!layer) {{
        throw new Error("Layer not found.");
    }}

    var effects = layer.property({jsx_string(self.EFFECT_PARade)});
    var result = [];

    if (effects) {{
        for (var i = 1; i <= effects.numProperties; i++) {{
            var effect = effects.property(i);

            result.push({{
                index: i,
                name: effect.name,
                matchName: effect.matchName,
                enabled: effect.enabled,
                numProperties: effect.numProperties
            }});
        }}
    }}

    $.writeln(JSON.stringify({{
        success: true,
        operation: "inspect_effects",
        layerName: layer.name,
        effects: result
    }}));

    function findComposition(targetName) {{
        for (var index = 1; index <= app.project.numItems; index++) {{
            var item = app.project.item(index);

            if (item instanceof CompItem && item.name === targetName) {{
                return item;
            }}
        }}

        return null;
    }}

    function findLayer(comp, targetName) {{
        for (var layerIndex = 1; layerIndex <= comp.numLayers; layerIndex++) {{
            if (comp.layer(layerIndex).name === targetName) {{
                return comp.layer(layerIndex);
            }}
        }}

        return null;
    }}
}})();
"""
        return self.runner.run(script)

    def add_effect(
        self,
        composition_name: str,
        layer_name: str,
        effect_name: str,
        match_name: str | None = None,
    ) -> str:
        """
        Add an effect using a supplied display name or match name.

        After Effects determines whether the requested effect exists. This
        method does not assume that any third-party plugin is installed.
        """
        self._validate_name(composition_name, "composition_name")
        self._validate_name(layer_name, "layer_name")
        self._validate_name(effect_name, "effect_name")

        if match_name is not None:
            self._validate_name(match_name, "match_name")

        effect_identifier = match_name if match_name is not None else effect_name

        script = f"""
(function () {{
    var composition = findComposition({jsx_string(composition_name)});

    if (!composition) {{
        throw new Error("Composition not found.");
    }}

    var layer = findLayer(composition, {jsx_string(layer_name)});

    if (!layer) {{
        throw new Error("Layer not found.");
    }}

    var effects = layer.property({jsx_string(self.EFFECT_PARade)});

    if (!effects) {{
        throw new Error("Layer does not expose an effect property group.");
    }}

    var effect = effects.addProperty({jsx_string(effect_identifier)});

    if (!effect) {{
        throw new Error("After Effects could not add the requested effect.");
    }}

    $.writeln(JSON.stringify({{
        success: true,
        operation: "add_effect",
        layerName: layer.name,
        effect: {{
            name: effect.name,
            matchName: effect.matchName,
            index: effect.propertyIndex,
            enabled: effect.enabled
        }}
    }}));

    function findComposition(targetName) {{
        for (var index = 1; index <= app.project.numItems; index++) {{
            var item = app.project.item(index);

            if (item instanceof CompItem && item.name === targetName) {{
                return item;
            }}
        }}

        return null;
    }}

    function findLayer(comp, targetName) {{
        for (var layerIndex = 1; layerIndex <= comp.numLayers; layerIndex++) {{
            if (comp.layer(layerIndex).name === targetName) {{
                return comp.layer(layerIndex);
            }}
        }}

        return null;
    }}
}})();
"""
        return self.runner.run(script)

    def remove_effect(
        self,
        composition_name: str,
        layer_name: str,
        effect_name: str,
        match_name: str | None = None,
    ) -> str:
        """Remove an effect by display name or match name."""
        self._validate_name(composition_name, "composition_name")
        self._validate_name(layer_name, "layer_name")
        self._validate_name(effect_name, "effect_name")

        if match_name is not None:
            self._validate_name(match_name, "match_name")

        match_expression = (
            f"effect.matchName === {jsx_string(match_name)}"
            if match_name is not None
            else f"effect.name === {jsx_string(effect_name)}"
        )

        script = f"""
(function () {{
    var composition = findComposition({jsx_string(composition_name)});

    if (!composition) {{
        throw new Error("Composition not found.");
    }}

    var layer = findLayer(composition, {jsx_string(layer_name)});

    if (!layer) {{
        throw new Error("Layer not found.");
    }}

    var effects = layer.property({jsx_string(self.EFFECT_PARade)});

    if (!effects) {{
        throw new Error("Layer does not expose an effect property group.");
    }}

    var effect = findEffect(effects);

    if (!effect) {{
        throw new Error("Effect not found.");
    }}

    var deletedName = effect.name;
    var deletedMatchName = effect.matchName;

    effect.remove();

    $.writeln(JSON.stringify({{
        success: true,
        operation: "remove_effect",
        deletedName: deletedName,
        deletedMatchName: deletedMatchName
    }}));

    function findEffect(effectGroup) {{
        for (var index = 1; index <= effectGroup.numProperties; index++) {{
            var effect = effectGroup.property(index);

            if ({match_expression}) {{
                return effect;
            }}
        }}

        return null;
    }}

    function findComposition(targetName) {{
        for (var index = 1; index <= app.project.numItems; index++) {{
            var item = app.project.item(index);

            if (item instanceof CompItem && item.name === targetName) {{
                return item;
            }}
        }}

        return null;
    }}

    function findLayer(comp, targetName) {{
        for (var layerIndex = 1; layerIndex <= comp.numLayers; layerIndex++) {{
            if (comp.layer(layerIndex).name === targetName) {{
                return comp.layer(layerIndex);
            }}
        }}

        return null;
    }}
}})();
"""
        return self.runner.run(script)

    def find_effect(
        self,
        composition_name: str,
        layer_name: str,
        effect_name: str,
        match_name: str | None = None,
    ) -> str:
        """Find an effect on a layer."""
        self._validate_name(composition_name, "composition_name")
        self._validate_name(layer_name, "layer_name")
        self._validate_name(effect_name, "effect_name")

        if match_name is not None:
            self._validate_name(match_name, "match_name")

        match_expression = (
            f"effect.matchName === {jsx_string(match_name)}"
            if match_name is not None
            else f"effect.name === {jsx_string(effect_name)}"
        )

        script = f"""
(function () {{
    var composition = findComposition({jsx_string(composition_name)});

    if (!composition) {{
        throw new Error("Composition not found.");
    }}

    var layer = findLayer(composition, {jsx_string(layer_name)});

    if (!layer) {{
        throw new Error("Layer not found.");
    }}

    var effects = layer.property({jsx_string(self.EFFECT_PARade)});

    if (!effects) {{
        throw new Error("Layer does not expose an effect property group.");
    }}

    var result = null;

    for (var index = 1; index <= effects.numProperties; index++) {{
        var effect = effects.property(index);

        if ({match_expression}) {{
            result = {{
                index: index,
                name: effect.name,
                matchName: effect.matchName,
                enabled: effect.enabled,
                numProperties: effect.numProperties
            }};
            break;
        }}
    }}

    $.writeln(JSON.stringify({{
        success: true,
        operation: "find_effect",
        found: result !== null,
        effect: result
    }}));

    function findComposition(targetName) {{
        for (var itemIndex = 1; itemIndex <= app.project.numItems; itemIndex++) {{
            var item = app.project.item(itemIndex);

            if (item instanceof CompItem && item.name === targetName) {{
                return item;
            }}
        }}

        return null;
    }}

    function findLayer(comp, targetName) {{
        for (var layerIndex = 1; layerIndex <= comp.numLayers; layerIndex++) {{
            if (comp.layer(layerIndex).name === targetName) {{
                return comp.layer(layerIndex);
            }}
        }}

        return null;
    }}
}})();
"""
        return self.runner.run(script)

    def set_effect_property(
        self,
        composition_name: str,
        layer_name: str,
        effect_name: str,
        property_name: str,
        value: Any,
        match_name: str | None = None,
    ) -> str:
        """Set an effect property value."""
        self._validate_name(composition_name, "composition_name")
        self._validate_name(layer_name, "layer_name")
        self._validate_name(effect_name, "effect_name")
        self._validate_name(property_name, "property_name")

        if match_name is not None:
            self._validate_name(match_name, "match_name")

        effect_match_expression = (
            f"candidate.matchName === {jsx_string(match_name)}"
            if match_name is not None
            else f"candidate.name === {jsx_string(effect_name)}"
        )

        script = f"""
(function () {{
    var composition = findComposition({jsx_string(composition_name)});

    if (!composition) {{
        throw new Error("Composition not found.");
    }}

    var layer = findLayer(composition, {jsx_string(layer_name)});

    if (!layer) {{
        throw new Error("Layer not found.");
    }}

    var effects = layer.property({jsx_string(self.EFFECT_PARade)});

    if (!effects) {{
        throw new Error("Layer does not expose an effect property group.");
    }}

    var effect = null;

    for (var effectIndex = 1; effectIndex <= effects.numProperties; effectIndex++) {{
        var candidate = effects.property(effectIndex);

        if ({effect_match_expression}) {{
            effect = candidate;
            break;
        }}
    }}

    if (!effect) {{
        throw new Error("Effect not found.");
    }}

    var property = findProperty(effect, {jsx_string(property_name)});

    if (!property) {{
        throw new Error("Effect property not found.");
    }}

    property.setValue({jsx_value(value)});

    $.writeln(JSON.stringify({{
        success: true,
        operation: "set_effect_property",
        effectName: effect.name,
        effectMatchName: effect.matchName,
        propertyName: property.name,
        propertyMatchName: property.matchName,
        value: property.value
    }}));

    function findProperty(group, targetName) {{
        for (var index = 1; index <= group.numProperties; index++) {{
            var property = group.property(index);

            if (
                property.name === targetName ||
                property.matchName === targetName
            ) {{
                return property;
            }}
        }}

        return null;
    }}

    function findComposition(targetName) {{
        for (var itemIndex = 1; itemIndex <= app.project.numItems; itemIndex++) {{
            var item = app.project.item(itemIndex);

            if (item instanceof CompItem && item.name === targetName) {{
                return item;
            }}
        }}

        return null;
    }}

    function findLayer(comp, targetName) {{
        for (var layerIndex = 1; layerIndex <= comp.numLayers; layerIndex++) {{
            if (comp.layer(layerIndex).name === targetName) {{
                return comp.layer(layerIndex);
            }}
        }}

        return null;
    }}
}})();
"""
        return self.runner.run(script)

    def get_effect_property(
        self,
        composition_name: str,
        layer_name: str,
        effect_name: str,
        property_name: str,
        match_name: str | None = None,
    ) -> str:
        """Get an effect property value."""
        self._validate_name(composition_name, "composition_name")
        self._validate_name(layer_name, "layer_name")
        self._validate_name(effect_name, "effect_name")
        self._validate_name(property_name, "property_name")

        if match_name is not None:
            self._validate_name(match_name, "match_name")

        effect_match_expression = (
            f"candidate.matchName === {jsx_string(match_name)}"
            if match_name is not None
            else f"candidate.name === {jsx_string(effect_name)}"
        )

        script = f"""
(function () {{
    var composition = findComposition({jsx_string(composition_name)});

    if (!composition) {{
        throw new Error("Composition not found.");
    }}

    var layer = findLayer(composition, {jsx_string(layer_name)});

    if (!layer) {{
        throw new Error("Layer not found.");
    }}

    var effects = layer.property({jsx_string(self.EFFECT_PARade)});

    if (!effects) {{
        throw new Error("Layer does not expose an effect property group.");
    }}

    var effect = null;

    for (var effectIndex = 1; effectIndex <= effects.numProperties; effectIndex++) {{
        var candidate = effects.property(effectIndex);

        if ({effect_match_expression}) {{
            effect = candidate;
            break;
        }}
    }}

    if (!effect) {{
        throw new Error("Effect not found.");
    }}

    var property = findProperty(effect, {jsx_string(property_name)});

    if (!property) {{
        throw new Error("Effect property not found.");
    }}

    $.writeln(JSON.stringify({{
        success: true,
        operation: "get_effect_property",
        effectName: effect.name,
        effectMatchName: effect.matchName,
        propertyName: property.name,
        propertyMatchName: property.matchName,
        value: property.value
    }}));

    function findProperty(group, targetName) {{
        for (var index = 1; index <= group.numProperties; index++) {{
            var property = group.property(index);

            if (
                property.name === targetName ||
                property.matchName === targetName
            ) {{
                return property;
            }}
        }}

        return null;
    }}

    function findComposition(targetName) {{
        for (var itemIndex = 1; itemIndex <= app.project.numItems; itemIndex++) {{
            var item = app.project.item(itemIndex);

            if (item instanceof CompItem && item.name === targetName) {{
                return item;
            }}
        }}

        return null;
    }}

    function findLayer(comp, targetName) {{
        for (var layerIndex = 1; layerIndex <= comp.numLayers; layerIndex++) {{
            if (comp.layer(layerIndex).name === targetName) {{
                return comp.layer(layerIndex);
            }}
        }}

        return null;
    }}
}})();
"""
        return self.runner.run(script)

    def enable_effect(
        self,
        composition_name: str,
        layer_name: str,
        effect_name: str,
        enabled: bool,
        match_name: str | None = None,
    ) -> str:
        """Enable or disable an effect."""
        self._validate_name(composition_name, "composition_name")
        self._validate_name(layer_name, "layer_name")
        self._validate_name(effect_name, "effect_name")

        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a boolean.")

        if match_name is not None:
            self._validate_name(match_name, "match_name")

        effect_match_expression = (
            f"candidate.matchName === {jsx_string(match_name)}"
            if match_name is not None
            else f"candidate.name === {jsx_string(effect_name)}"
        )

        script = f"""
(function () {{
    var composition = findComposition({jsx_string(composition_name)});

    if (!composition) {{
        throw new Error("Composition not found.");
    }}

    var layer = findLayer(composition, {jsx_string(layer_name)});

    if (!layer) {{
        throw new Error("Layer not found.");
    }}

    var effects = layer.property({jsx_string(self.EFFECT_PARade)});

    if (!effects) {{
        throw new Error("Layer does not expose an effect property group.");
    }}

    var effect = null;

    for (var index = 1; index <= effects.numProperties; index++) {{
        var candidate = effects.property(index);

        if ({effect_match_expression}) {{
            effect = candidate;
            break;
        }}
    }}

    if (!effect) {{
        throw new Error("Effect not found.");
    }}

    effect.enabled = {str(enabled).lower()};

    $.writeln(JSON.stringify({{
        success: true,
        operation: "enable_effect",
        effectName: effect.name,
        enabled: effect.enabled
    }}));

    function findComposition(targetName) {{
        for (var itemIndex = 1; itemIndex <= app.project.numItems; itemIndex++) {{
            var item = app.project.item(itemIndex);

            if (item instanceof CompItem && item.name === targetName) {{
                return item;
            }}
        }}

        return null;
    }}

    function findLayer(comp, targetName) {{
        for (var layerIndex = 1; layerIndex <= comp.numLayers; layerIndex++) {{
            if (comp.layer(layerIndex).name === targetName) {{
                return comp.layer(layerIndex);
            }}
        }}

        return null;
    }}
}})();
"""
        return self.runner.run(script)

    def reorder_effect(
        self,
        composition_name: str,
        layer_name: str,
        effect_name: str,
        target_index: int,
        match_name: str | None = None,
    ) -> str:
        """Move an effect to a supported 1-based effect-stack position."""
        self._validate_name(composition_name, "composition_name")
        self._validate_name(layer_name, "layer_name")
        self._validate_name(effect_name, "effect_name")
        self._validate_positive_int(target_index, "target_index")

        if match_name is not None:
            self._validate_name(match_name, "match_name")

        effect_match_expression = (
            f"candidate.matchName === {jsx_string(match_name)}"
            if match_name is not None
            else f"candidate.name === {jsx_string(effect_name)}"
        )

        script = f"""
(function () {{
    var composition = findComposition({jsx_string(composition_name)});

    if (!composition) {{
        throw new Error("Composition not found.");
    }}

    var layer = findLayer(composition, {jsx_string(layer_name)});

    if (!layer) {{
        throw new Error("Layer not found.");
    }}

    var effects = layer.property({jsx_string(self.EFFECT_PARade)});

    if (!effects) {{
        throw new Error("Layer does not expose an effect property group.");
    }}

    var effect = null;

    for (var index = 1; index <= effects.numProperties; index++) {{
        var candidate = effects.property(index);

        if ({effect_match_expression}) {{
            effect = candidate;
            break;
        }}
    }}

    if (!effect) {{
        throw new Error("Effect not found.");
    }}

    var targetIndex = {int(target_index)};

    if (targetIndex > effects.numProperties) {{
        targetIndex = effects.numProperties;
    }}

    if (targetIndex < 1) {{
        targetIndex = 1;
    }}

    if (effect.propertyIndex !== targetIndex) {{
        effect.moveTo(targetIndex);
    }}

    $.writeln(JSON.stringify({{
        success: true,
        operation: "reorder_effect",
        effectName: effect.name,
        index: effect.propertyIndex
    }}));

    function findComposition(targetName) {{
        for (var itemIndex = 1; itemIndex <= app.project.numItems; itemIndex++) {{
            var item = app.project.item(itemIndex);

            if (item instanceof CompItem && item.name === targetName) {{
                return item;
            }}
        }}

        return null;
    }}

    function findLayer(comp, targetName) {{
        for (var layerIndex = 1; layerIndex <= comp.numLayers; layerIndex++) {{
            if (comp.layer(layerIndex).name === targetName) {{
                return comp.layer(layerIndex);
            }}
        }}

        return null;
    }}
}})();
"""
        return self.runner.run(script)

    @staticmethod
    def _validate_name(value: str, field_name: str) -> None:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string.")

        if not value.strip():
            raise ValueError(f"{field_name} must not be empty.")

    @staticmethod
    def _validate_positive_int(value: int, field_name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{field_name} must be an integer.")

        if value <= 0:
            raise ValueError(f"{field_name} must be greater than zero.")