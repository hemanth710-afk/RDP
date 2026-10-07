from __future__ import annotations

from typing import Sequence

from .script_runner import AEScriptRunner, jsx_string, jsx_value


class CompositionController:
    """Controlled After Effects composition automation."""

    def __init__(self, runner: AEScriptRunner) -> None:
        self.runner = runner

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
        """Create a composition in the currently open project."""
        self._validate_name(name)
        self._validate_positive_int(width, "width")
        self._validate_positive_int(height, "height")
        self._validate_positive_number(pixel_aspect, "pixel_aspect")
        self._validate_positive_number(duration, "duration")
        self._validate_positive_number(frame_rate, "frame_rate")
        color = self._validate_color(background_color)

        script = f"""
(function () {{
    if (!app.project) {{
        throw new Error("No After Effects project is open.");
    }}

    var composition = app.project.items.addComp(
        {jsx_string(name)},
        {int(width)},
        {int(height)},
        {float(pixel_aspect)},
        {float(duration)},
        {float(frame_rate)}
    );

    composition.bgColor = {jsx_value(list(color))};

    $.writeln("success=true;operation=create_composition;name=" + composition.name + ";width=" + composition.width + ";height=" + composition.height + ";duration=" + composition.duration + ";frameRate=" + composition.frameRate);
}})();
"""
        return self.runner.run(script)

    def find_composition(self, name: str) -> str:
        """Find a composition by exact name."""
        self._validate_name(name)

        script = f"""
(function () {{
    if (!app.project) {{
        throw new Error("No After Effects project is open.");
    }}

    var result = null;

    for (var i = 1; i <= app.project.numItems; i++) {{
        var item = app.project.item(i);

        if (item instanceof CompItem && item.name === {jsx_string(name)}) {{
            result = {{
                index: item.index,
                name: item.name,
                width: item.width,
                height: item.height,
                duration: item.duration,
                frameRate: item.frameRate,
                numLayers: item.numLayers
            }};
            break;
        }}
    }}

    $.writeln(JSON.stringify({{
        success: true,
        operation: "find_composition",
        found: result !== null,
        composition: result
    }}));
}})();
"""
        return self.runner.run(script)

    def get_composition_info(self, name: str) -> str:
        """Return detailed information for a named composition."""
        self._validate_name(name)

        script = f"""
(function () {{
    if (!app.project) {{
        throw new Error("No After Effects project is open.");
    }}

    var composition = null;

    for (var i = 1; i <= app.project.numItems; i++) {{
        var item = app.project.item(i);

        if (item instanceof CompItem && item.name === {jsx_string(name)}) {{
            composition = item;
            break;
        }}
    }}

    if (!composition) {{
        throw new Error("Composition not found.");
    }}

    var layers = [];

    for (var layerIndex = 1; layerIndex <= composition.numLayers; layerIndex++) {{
        var layer = composition.layer(layerIndex);

        layers.push({{
            index: layer.index,
            name: layer.name,
            typeName: layer.matchName,
            enabled: layer.enabled,
            locked: layer.locked,
            inPoint: layer.inPoint,
            outPoint: layer.outPoint,
            startTime: layer.startTime
        }});
    }}

    $.writeln(JSON.stringify({{
        success: true,
        operation: "get_composition_info",
        composition: {{
            index: composition.index,
            name: composition.name,
            width: composition.width,
            height: composition.height,
            duration: composition.duration,
            frameRate: composition.frameRate,
            pixelAspect: composition.pixelAspect,
            backgroundColor: composition.bgColor,
            numLayers: composition.numLayers,
            layers: layers
        }}
    }}));
}})();
"""
        return self.runner.run(script)

    def rename_composition(self, name: str, new_name: str) -> str:
        """Rename a composition."""
        self._validate_name(name)
        self._validate_name(new_name)

        script = f"""
(function () {{
    var composition = findComposition({jsx_string(name)});

    if (!composition) {{
        throw new Error("Composition not found.");
    }}

    composition.name = {jsx_string(new_name)};

    $.writeln(JSON.stringify({{
        success: true,
        operation: "rename_composition",
        name: composition.name
    }}));

    function findComposition(targetName) {{
        if (!app.project) {{
            throw new Error("No After Effects project is open.");
        }}

        for (var i = 1; i <= app.project.numItems; i++) {{
            var item = app.project.item(i);

            if (item instanceof CompItem && item.name === targetName) {{
                return item;
            }}
        }}

        return null;
    }}
}})();
"""
        return self.runner.run(script)

    def change_width(self, name: str, width: int) -> str:
        """Change composition width."""
        self._validate_name(name)
        self._validate_positive_int(width, "width")

        return self._set_dimension(name, "width", width)

    def change_height(self, name: str, height: int) -> str:
        """Change composition height."""
        self._validate_name(name)
        self._validate_positive_int(height, "height")

        return self._set_dimension(name, "height", height)

    def change_duration(self, name: str, duration: float) -> str:
        """Change composition duration."""
        self._validate_name(name)
        self._validate_positive_number(duration, "duration")

        script = f"""
(function () {{
    var composition = findComposition({jsx_string(name)});

    if (!composition) {{
        throw new Error("Composition not found.");
    }}

    composition.duration = {float(duration)};

    $.writeln(JSON.stringify({{
        success: true,
        operation: "change_duration",
        name: composition.name,
        duration: composition.duration
    }}));

    function findComposition(targetName) {{
        if (!app.project) {{
            throw new Error("No After Effects project is open.");
        }}

        for (var i = 1; i <= app.project.numItems; i++) {{
            var item = app.project.item(i);

            if (item instanceof CompItem && item.name === targetName) {{
                return item;
            }}
        }}

        return null;
    }}
}})();
"""
        return self.runner.run(script)

    def change_frame_rate(self, name: str, frame_rate: float) -> str:
        """Change composition frame rate."""
        self._validate_name(name)
        self._validate_positive_number(frame_rate, "frame_rate")

        script = f"""
(function () {{
    var composition = findComposition({jsx_string(name)});

    if (!composition) {{
        throw new Error("Composition not found.");
    }}

    composition.frameRate = {float(frame_rate)};

    $.writeln(JSON.stringify({{
        success: true,
        operation: "change_frame_rate",
        name: composition.name,
        frameRate: composition.frameRate
    }}));

    function findComposition(targetName) {{
        if (!app.project) {{
            throw new Error("No After Effects project is open.");
        }}

        for (var i = 1; i <= app.project.numItems; i++) {{
            var item = app.project.item(i);

            if (item instanceof CompItem && item.name === targetName) {{
                return item;
            }}
        }}

        return null;
    }}
}})();
"""
        return self.runner.run(script)

    def change_background_color(
        self,
        name: str,
        color: Sequence[float],
    ) -> str:
        """Change composition background color."""
        self._validate_name(name)
        validated_color = self._validate_color(color)

        script = f"""
(function () {{
    var composition = findComposition({jsx_string(name)});

    if (!composition) {{
        throw new Error("Composition not found.");
    }}

    composition.bgColor = {jsx_value(list(validated_color))};

    $.writeln(JSON.stringify({{
        success: true,
        operation: "change_background_color",
        name: composition.name,
        backgroundColor: composition.bgColor
    }}));

    function findComposition(targetName) {{
        if (!app.project) {{
            throw new Error("No After Effects project is open.");
        }}

        for (var i = 1; i <= app.project.numItems; i++) {{
            var item = app.project.item(i);

            if (item instanceof CompItem && item.name === targetName) {{
                return item;
            }}
        }}

        return null;
    }}
}})();
"""
        return self.runner.run(script)

    def delete_composition(self, name: str) -> str:
        """Delete a composition by exact name."""
        self._validate_name(name)

        script = f"""
(function () {{
    var composition = findComposition({jsx_string(name)});

    if (!composition) {{
        throw new Error("Composition not found.");
    }}

    var deletedName = composition.name;
    composition.remove();

    $.writeln(JSON.stringify({{
        success: true,
        operation: "delete_composition",
        deleted: deletedName
    }}));

    function findComposition(targetName) {{
        if (!app.project) {{
            throw new Error("No After Effects project is open.");
        }}

        for (var i = 1; i <= app.project.numItems; i++) {{
            var item = app.project.item(i);

            if (item instanceof CompItem && item.name === targetName) {{
                return item;
            }}
        }}

        return null;
    }}
}})();
"""
        return self.runner.run(script)

    def duplicate_composition(
        self,
        name: str,
        new_name: str | None = None,
    ) -> str:
        """Duplicate a composition, optionally assigning a new name."""
        self._validate_name(name)

        if new_name is not None:
            self._validate_name(new_name)

        rename_statement = (
            f"duplicate.name = {jsx_string(new_name)};"
            if new_name is not None
            else ""
        )

        script = f"""
(function () {{
    var composition = findComposition({jsx_string(name)});

    if (!composition) {{
        throw new Error("Composition not found.");
    }}

    var duplicate = composition.duplicate();
    {rename_statement}

    $.writeln(JSON.stringify({{
        success: true,
        operation: "duplicate_composition",
        sourceName: composition.name,
        duplicateName: duplicate.name,
        index: duplicate.index
    }}));

    function findComposition(targetName) {{
        if (!app.project) {{
            throw new Error("No After Effects project is open.");
        }}

        for (var i = 1; i <= app.project.numItems; i++) {{
            var item = app.project.item(i);

            if (item instanceof CompItem && item.name === targetName) {{
                return item;
            }}
        }}

        return null;
    }}
}})();
"""
        return self.runner.run(script)

    def _set_dimension(self, name: str, dimension: str, value: int) -> str:
        script = f"""
(function () {{
    var composition = findComposition({jsx_string(name)});

    if (!composition) {{
        throw new Error("Composition not found.");
    }}

    composition.{dimension} = {int(value)};

    $.writeln(JSON.stringify({{
        success: true,
        operation: "change_{dimension}",
        name: composition.name,
        width: composition.width,
        height: composition.height
    }}));

    function findComposition(targetName) {{
        if (!app.project) {{
            throw new Error("No After Effects project is open.");
        }}

        for (var i = 1; i <= app.project.numItems; i++) {{
            var item = app.project.item(i);

            if (item instanceof CompItem && item.name === targetName) {{
                return item;
            }}
        }}

        return null;
    }}
}})();
"""
        return self.runner.run(script)

    @staticmethod
    def _validate_name(name: str) -> None:
        if not isinstance(name, str):
            raise TypeError("Composition name must be a string.")

        if not name.strip():
            raise ValueError("Composition name must not be empty.")

    @staticmethod
    def _validate_positive_int(value: int, field_name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{field_name} must be an integer.")

        if value <= 0:
            raise ValueError(f"{field_name} must be greater than zero.")

    @staticmethod
    def _validate_positive_number(value: float, field_name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{field_name} must be a number.")

        if value <= 0:
            raise ValueError(f"{field_name} must be greater than zero.")

    @staticmethod
    def _validate_color(
        color: Sequence[float],
    ) -> tuple[float, float, float]:
        if isinstance(color, (str, bytes)) or len(color) != 3:
            raise ValueError("background_color must contain exactly three values.")

        values = tuple(float(component) for component in color)

        if any(component < 0.0 or component > 1.0 for component in values):
            raise ValueError("Color components must be between 0.0 and 1.0.")

        return values

