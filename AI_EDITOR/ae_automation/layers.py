@'
from pathlib import Path
import re
import shutil

path = Path(r".\ae_automation\layers.py")

if not path.exists():
    raise SystemExit("ERROR: ae_automation/layers.py was not found.")

# ------------------------------------------------------------
# BACKUP
# ------------------------------------------------------------

backup = path.with_name("layers.py.before_amv_cut_fix.bak")
shutil.copy2(path, backup)

text = path.read_text(encoding="utf-8")

# ------------------------------------------------------------
# REMOVE ALL EXISTING cut_clip() METHODS
# ------------------------------------------------------------

pattern = re.compile(
    r"\n    def cut_clip\(\n.*?(?=\n    def |\n    @staticmethod|\n    @classmethod|\Z)",
    re.DOTALL,
)

text = pattern.sub("", text)

# ------------------------------------------------------------
# INSERT ONE CORRECT cut_clip() METHOD
# ------------------------------------------------------------

cut_clip_method = r'''
    def cut_clip(
        self,
        composition_name: str,
        layer_name: str,
        timeline_start: float,
        timeline_end: float,
        source_start: float = 0.0,
    ) -> str:
        """Trim a footage layer and place a source segment on the timeline."""

        self._validate_name(
            composition_name,
            "composition_name",
        )
        self._validate_name(
            layer_name,
            "layer_name",
        )
        self._validate_time(timeline_start)
        self._validate_time(timeline_end)
        self._validate_time(source_start)

        if timeline_end <= timeline_start:
            raise ValueError(
                "timeline_end must be greater than timeline_start."
            )

        script = f"""
(function () {{
    var composition = findComposition(
        {jsx_string(composition_name)}
    );

    if (!composition) {{
        throw new Error("Composition not found.");
    }}

    var layer = findLayer(
        composition,
        {jsx_string(layer_name)}
    );

    if (!layer) {{
        throw new Error("Layer not found.");
    }}

    if (!layer.source) {{
        throw new Error(
            "Layer does not have a source and cannot be cut."
        );
    }}

    var timelineStart = {float(timeline_start)};
    var timelineEnd = {float(timeline_end)};
    var sourceStart = {float(source_start)};

    if (timelineEnd <= timelineStart) {{
        throw new Error(
            "Timeline end must be greater than timeline start."
        );
    }}

    /*
     * Move the source so that sourceStart appears at
     * timelineStart, then trim the visible layer range.
     */
    layer.startTime = timelineStart - sourceStart;
    layer.inPoint = timelineStart;
    layer.outPoint = timelineEnd;

    $.writeln(JSON.stringify({{
        success: true,
        operation: "cut_clip",
        layer: layer.name,
        timelineStart: timelineStart,
        timelineEnd: timelineEnd,
        sourceStart: sourceStart,
        duration: timelineEnd - timelineStart,
        startTime: layer.startTime,
        inPoint: layer.inPoint,
        outPoint: layer.outPoint
    }}));

    function findComposition(targetName) {{
        if (!app.project) {{
            throw new Error(
                "No After Effects project is open."
            );
        }}

        for (
            var index = 1;
            index <= app.project.numItems;
            index++
        ) {{
            var item = app.project.item(index);

            if (
                item instanceof CompItem &&
                item.name === targetName
            ) {{
                return item;
            }}
        }}

        return null;
    }}

    function findLayer(comp, targetName) {{
        for (
            var layerIndex = 1;
            layerIndex <= comp.numLayers;
            layerIndex++
        ) {{
            if (
                comp.layer(layerIndex).name === targetName
            ) {{
                return comp.layer(layerIndex);
            }}
        }}

        return null;
    }}
}})();
"""

# Put cut_clip immediately before add_imported_footage().
marker = "\n    def add_imported_footage(\n"

if marker not in text:
    raise SystemExit(
        "ERROR: Could not find add_imported_footage() in layers.py."
    )

text = text.replace(
    marker,
    "\n" + cut_clip_method + marker,
    1,
)

# ------------------------------------------------------------
# WRITE REPAIRED FILE
# ------------------------------------------------------------

path.write_text(
    text,
    encoding="utf-8",
)

print("SUCCESS")
print(f"Backup: {backup}")
print("cut_clip(): repaired and inserted exactly once.")
'@ | Set-Content .\repair_layers.py -Encoding UTF8

python .\repair_layers.py

Remove-Item .\repair_layers.py

python -m py_compile .\ae_automation\layers.py