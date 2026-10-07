from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Union


PathLike = Union[str, os.PathLike[str]]


class AEScriptError(RuntimeError):
    """Raised when an After Effects JSX automation operation fails."""


def jsx_string(value: str) -> str:
    """Return a safely escaped JavaScript string literal."""
    if not isinstance(value, str):
        raise TypeError("JSX string values must be strings.")
    return json.dumps(value, ensure_ascii=True)


def jsx_value(value: object) -> str:
    """Serialize a JSON-compatible Python value for use in JSX."""
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


class AEScriptRunner:
    """Execute controlled JSX files through Adobe After Effects."""

    ENVIRONMENT_VARIABLE = "AI_EDITOR_AFTER_EFFECTS_2022_PATH"

    def __init__(self, executable_path: Optional[PathLike] = None) -> None:
        configured_path = (
            executable_path
            if executable_path is not None
            else os.environ.get(self.ENVIRONMENT_VARIABLE)
        )

        if not configured_path:
            raise AEScriptError(
                f"After Effects executable path is not configured. "
                f"Set {self.ENVIRONMENT_VARIABLE} or provide executable_path."
            )

        self.executable_path = Path(configured_path).expanduser()

        if not self.executable_path.exists():
            raise AEScriptError(
                f"After Effects executable does not exist: "
                f"{self.executable_path}"
            )

        if not self.executable_path.is_file():
            raise AEScriptError(
                f"After Effects executable path is not a file: "
                f"{self.executable_path}"
            )

    def run(self, script: str) -> str:
        """
        Execute a non-empty JSX script through After Effects.

        The script is written to a temporary UTF-8 .jsx file and executed
        using the After Effects command-line scripting interface.
        """
        if not isinstance(script, str):
            raise TypeError("script must be a string.")

        if not script.strip():
            raise ValueError("script must be a non-empty string.")

        temporary_path: Optional[Path] = None
        output_path: Optional[Path] = None

        try:
            with tempfile.NamedTemporaryFile(suffix=".out.txt", delete=False) as out_file:
                output_path = Path(out_file.name)

            wrapper_script = f"""
if (typeof JSON !== "object") {{
    JSON = {{}};
}}
if (!JSON.stringify) {{
    JSON.stringify = function(obj) {{
        if (obj === null) return "null";
        if (typeof obj === "string") return '"' + obj.replace(/\\\\/g, '\\\\\\\\').replace(/"/g, '\\\\"') + '"';
        if (typeof obj === "number" || typeof obj === "boolean") return obj.toString();
        if (obj instanceof Array) {{
            var res = [];
            for (var i = 0; i < obj.length; i++) res.push(JSON.stringify(obj[i]));
            return "[" + res.join(",") + "]";
        }}
        var res = [];
        for (var k in obj) {{
            if (obj.hasOwnProperty(k)) res.push('"' + k + '":' + JSON.stringify(obj[k]));
        }}
        return "{{" + res.join(",") + "}}";
    }};
}}

var __ai_editor_output = [];
var __original_writeln = $.writeln;
$.writeln = function(msg) {{
    __ai_editor_output.push(msg);
}};

try {{
    {script}
}} catch (e) {{
    __ai_editor_output.push("Error: " + e.toString());
}}

var __out_file = new File({jsx_string(str(output_path))});
__out_file.open("w");
__out_file.write(__ai_editor_output.join("\\n"));
__out_file.close();
"""

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".jsx",
                prefix="ai_editor_ae_",
                delete=False,
            ) as temporary_file:
                temporary_file.write(wrapper_script)
                temporary_path = Path(temporary_file.name)

            command = [
                str(self.executable_path),
                "-r",
                str(temporary_path),
            ]

            env = os.environ.copy()
            env["AE_DISABLE_GPU_SNIFFER"] = "1"
            env["AE_DISABLE_GPU"] = "1"

            try:
                process = subprocess.Popen(
                    command,
                    shell=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    text=True,
                )
                try:
                    stdout, stderr = process.communicate(timeout=90)
                    returncode = process.returncode
                except subprocess.TimeoutExpired as exc:
                    import subprocess as sp
                    sp.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
                    
                    stdout = exc.stdout if exc.stdout else ""
                    stderr = exc.stderr if exc.stderr else ""
                    if isinstance(stdout, bytes): stdout = stdout.decode('utf-8', errors='replace')
                    if isinstance(stderr, bytes): stderr = stderr.decode('utf-8', errors='replace')
                    
                    tl_res = sp.run(["tasklist", "/FI", "IMAGENAME eq AfterFX.exe"], capture_output=True, text=True)
                    is_running = "AfterFX.exe" in tl_res.stdout
                    details = [
                        "After Effects script timed out (90s).",
                        f"Command line: {' '.join(command)}",
                        f"Captured stdout: {stdout.strip()}",
                        f"Captured stderr: {stderr.strip()}",
                        f"Temporary script path: {temporary_path}",
                        f"Temporary output path: {output_path}",
                        f"AfterFX.exe still running: {is_running}"
                    ]
                    temporary_path = None
                    output_path = None
                    raise AEScriptError("\n".join(details))
            except OSError as exc:
                raise AEScriptError(f"Unable to launch After Effects: {exc}") from exc

            # If the script ran successfully, it should have written to output_path.
            output_content = ""
            if output_path.exists():
                output_content = output_path.read_text(encoding="utf-8").strip()

            if output_content:
                return output_content
            
            # If nothing was written, it failed to execute the script at all.
            import subprocess as sp
            tl_res = sp.run(["tasklist", "/FI", "IMAGENAME eq AfterFX.exe"], capture_output=True, text=True)
            is_running = "AfterFX.exe" in tl_res.stdout
            
            details = [
                "After Effects JSX execution failed.",
                f"Command line: {' '.join(command)}",
                f"Executable path: {self.executable_path}",
                f"Exit code: {returncode}",
                f"Captured stdout: {stdout.strip()}",
                f"Captured stderr: {stderr.strip()}",
                f"Temporary script path: {temporary_path}",
                f"Temporary output path: {output_path}",
                f"AfterFX.exe still running: {is_running}"
            ]
            
            # Unlink files only on success, preserve on failure
            temporary_path = None
            output_path = None
                
            raise AEScriptError("\n".join(details))
            
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
            if output_path is not None:
                try:
                    output_path.unlink(missing_ok=True)
                except OSError:
                    pass