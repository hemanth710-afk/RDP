from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from .script_runner import AEScriptRunner, jsx_string


PathLike = Union[str, Path]


class ProjectController:
    """Controlled After Effects project automation."""

    def __init__(self, runner: AEScriptRunner) -> None:
        self.runner = runner

    def create_project(self) -> str:
        """Create a new After Effects project."""
        script = r"""
(function () {
    app.newProject();
    if (!app.project) {
        throw new Error("After Effects failed to create a project.");
    }

    $.writeln("success=true;operation=create_project;projectOpen=true");
})();
"""
        return self.runner.run(script)

    def open_project(self, project_path: PathLike) -> str:
        """Open an existing After Effects project."""
        path = self._validate_path(project_path)

        script = f"""
(function () {{
    var projectFile = new File({jsx_string(str(path))});

    if (!projectFile.exists) {{
        throw new Error("Project file does not exist.");
    }}

    if (app.project) {{
        try {{
            app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);
        }} catch (closeError) {{
            throw new Error("Unable to close the current project: " + closeError.toString());
        }}
    }}

    app.open(projectFile);

    if (!app.project) {{
        throw new Error("After Effects failed to open the project.");
    }}

    $.writeln(JSON.stringify({{
        success: true,
        operation: "open_project",
        projectPath: projectFile.fsName,
        projectOpen: true
    }}));
}})();
"""
        return self.runner.run(script)

    def save_project(self) -> str:
        """Save the current After Effects project."""
        script = r"""
(function () {
    if (!app.project) {
        throw new Error("No After Effects project is open.");
    }

    app.project.save();

    $.writeln(JSON.stringify({
        success: true,
        operation: "save_project",
        projectPath: app.project.file ? app.project.file.fsName : null
    }));
})();
"""
        return self.runner.run(script)

    def save_project_as(self, project_path: PathLike) -> str:
        """Save the current project to a specified path."""
        path = self._validate_path(project_path)

        script = f"""
(function () {{
    if (!app.project) {{
        throw new Error("No After Effects project is open.");
    }}

    var destination = new File({jsx_string(str(path))});
    app.project.save(destination);

    $.writeln(JSON.stringify({{
        success: true,
        operation: "save_project_as",
        projectPath: destination.fsName
    }}));
}})();
"""
        return self.runner.run(script)

    def close_project(self, save: bool = False) -> str:
        """Close the current project, optionally saving it first."""
        if not isinstance(save, bool):
            raise TypeError("save must be a boolean.")

        close_option = "CloseOptions.DO_NOT_SAVE_CHANGES"

        script = f"""
(function () {{
    if (!app.project) {{
        $.writeln(JSON.stringify({{
            success: true,
            operation: "close_project",
            projectOpen: false
        }}));
        return;
    }}

    if ({str(save).lower()}) {{
        app.project.save();
    }}

    app.project.close({close_option});

    $.writeln(JSON.stringify({{
        success: true,
        operation: "close_project",
        projectOpen: app.project !== null
    }}));
}})();
"""
        return self.runner.run(script)

    def is_project_open(self) -> str:
        """Check whether an After Effects project is currently open."""
        script = r"""
(function () {
    var projectOpen = app.project !== null;

    $.writeln(JSON.stringify({
        success: true,
        operation: "is_project_open",
        projectOpen: projectOpen
    }));
})();
"""
        return self.runner.run(script)

    def get_project_info(self) -> str:
        """Return structured information about the current project."""
        script = r"""
(function () {
    var project = app.project;

    if (!project) {
        $.writeln(JSON.stringify({
            success: true,
            operation: "get_project_info",
            projectOpen: false
        }));
        return;
    }

    var activeItem = project.activeItem;
    var items = [];

    for (var i = 1; i <= project.numItems; i++) {
        var item = project.item(i);

        items.push({
            index: i,
            name: item.name,
            typeName: item.typeName,
            width: item.width !== undefined ? item.width : null,
            height: item.height !== undefined ? item.height : null,
            duration: item.duration !== undefined ? item.duration : null
        });
    }

    $.writeln(JSON.stringify({
        success: true,
        operation: "get_project_info",
        projectOpen: true,
        projectPath: project.file ? project.file.fsName : null,
        projectName: project.file ? project.file.name : null,
        numItems: project.numItems,
        activeItem: activeItem ? {
            name: activeItem.name,
            typeName: activeItem.typeName,
            index: activeItem.index
        } : null,
        items: items
    }));
})();
"""
        return self.runner.run(script)

    @staticmethod
    def _validate_path(project_path: PathLike) -> Path:
        if not isinstance(project_path, (str, Path)):
            raise TypeError("project_path must be a string or pathlib.Path.")

        path = Path(project_path).expanduser()

        if not str(path).strip():
            raise ValueError("project_path must not be empty.")

        return path.resolve()
