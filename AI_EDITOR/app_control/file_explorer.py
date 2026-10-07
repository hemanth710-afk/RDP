import os
import subprocess


class FileExplorerError(Exception):
    """Raised when file explorer cannot be opened."""


class FileExplorerController:
    """Controller for opening Windows File Explorer."""

    def open(self, path: str) -> subprocess.Popen:
        """Open Windows File Explorer at the specified directory."""
        if not path:
            raise FileExplorerError(
                "Path is required."
            )

        if not os.path.isdir(path):
            raise FileExplorerError(
                f"Directory does not exist: {path}"
            )

        return subprocess.Popen(
            ["explorer", path]
        )
