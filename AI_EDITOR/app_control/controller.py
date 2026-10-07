from .after_effects import AfterEffectsController
from .chrome import ChromeController
from .file_explorer import FileExplorerController


class ApplicationController:
    """Coordinates explicit application launches."""

    def __init__(
        self,
        after_effects: AfterEffectsController | None = None,
        chrome: ChromeController | None = None,
        file_explorer: FileExplorerController | None = None,
    ) -> None:
        self.after_effects = after_effects
        self.chrome = chrome
        self.file_explorer = file_explorer or FileExplorerController()

    def launch_after_effects(self):
        """Launch Adobe After Effects 2022."""
        if self.after_effects is None:
            raise RuntimeError(
                "After Effects controller is not configured."
            )

        return self.after_effects.launch()

    def open_after_effects(self):
        """Semantic action: open After Effects."""
        return self.launch_after_effects()

    def launch_chrome(self):
        """Launch Google Chrome with the configured profile."""
        if self.chrome is None:
            raise RuntimeError(
                "Chrome controller is not configured."
            )

        return self.chrome.launch()

    def open_chrome(self):
        """Semantic action: open Chrome."""
        return self.launch_chrome()

    def launch_file_explorer(self, path: str):
        """Launch Windows File Explorer at path."""
        if self.file_explorer is None:
            raise RuntimeError(
                "File Explorer controller is not configured."
            )

        return self.file_explorer.open(path)

    def open_file_explorer(self, path: str):
        """Semantic action: open File Explorer."""
        return self.launch_file_explorer(path)