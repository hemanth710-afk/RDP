"""
Component 7 – ae_automation test suite.

Tests for:
  AEScriptRunner, ProjectController, CompositionController,
  LayerController, EffectsController, AEAutomationCommands,
  and safety invariants.

All subprocess interactions are mocked.  Adobe After Effects is never
launched, and no real .aep project is opened or modified.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

from ae_automation.script_runner import AEScriptError, AEScriptRunner
from ae_automation.project import ProjectController
from ae_automation.composition import CompositionController
from ae_automation.layers import LayerController
from ae_automation.effects import EffectsController
from ae_automation.commands import AEAutomationCommands


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_exe() -> str:
    """Create a zero-byte temporary file that stands in for AfterFX.exe."""
    fd, path = tempfile.mkstemp(suffix=".exe", prefix="fake_afterfx_")
    os.close(fd)
    return path


def _completed_process(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    """Return a synthetic CompletedProcess suitable for mocking."""
    return subprocess.CompletedProcess(
        args=["fake.exe", "-r", "script.jsx"],
        returncode=0,
        stdout=stdout,
        stderr=stderr,
    )


# ---------------------------------------------------------------------------
# AEScriptRunner Tests
# ---------------------------------------------------------------------------

class TestAEScriptRunnerConstruction(unittest.TestCase):
    """Construction and path-resolution tests for AEScriptRunner."""

    def setUp(self) -> None:
        self.fake_exe = _make_fake_exe()
        self.runner = AEScriptRunner(executable_path=self.fake_exe)
        self.patcher1 = patch('ae_automation.script_runner.Path.exists', return_value=True)
        self.patcher2 = patch('ae_automation.script_runner.Path.read_text', return_value='success=true')
        self.mock_exists = self.patcher1.start()
        self.mock_read = self.patcher2.start()

    def tearDown(self) -> None:
        self.patcher1.stop()
        self.patcher2.stop()
        try:
            os.unlink(self.fake_exe)
        except OSError:
            pass

    # 1. Explicit valid executable path
    def test_explicit_valid_path(self) -> None:
        runner = AEScriptRunner(executable_path=self.fake_exe)
        self.assertTrue(runner.executable_path.exists())

    # 2. Reads the environment variable
    def test_reads_env_variable(self) -> None:
        env_key = AEScriptRunner.ENVIRONMENT_VARIABLE
        with patch.dict(os.environ, {env_key: self.fake_exe}):
            runner = AEScriptRunner()
            self.assertTrue(runner.executable_path.exists())

    # 3. Rejects a missing executable path
    def test_rejects_missing_path(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            env_key = AEScriptRunner.ENVIRONMENT_VARIABLE
            os.environ.pop(env_key, None)
            with self.assertRaises(AEScriptError):
                AEScriptRunner()

    # 4. Rejects a nonexistent executable
    def test_rejects_nonexistent_executable(self) -> None:
        with self.assertRaises(AEScriptError):
            AEScriptRunner(executable_path=r"C:\nonexistent\afterfx.exe")

    # 5. Environment variable name is correct
    def test_environment_variable_name(self) -> None:
        self.assertEqual(
            AEScriptRunner.ENVIRONMENT_VARIABLE,
            "AI_EDITOR_AFTER_EFFECTS_2022_PATH",
        )


class TestProjectController(unittest.TestCase):
    """ProjectController tests – AEScriptRunner is mocked."""

    def setUp(self) -> None:
        self.mock_runner = MagicMock(spec=AEScriptRunner)
        self.mock_runner.run.return_value = '{"success": true}'
        self.controller = ProjectController(self.mock_runner)

    # 1. Create project
    def test_create_project(self) -> None:
        result = self.controller.create_project()
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("newProject", script)
        self.assertEqual(result, '{"success": true}')

    # 2. Open project
    def test_open_project(self) -> None:
        result = self.controller.open_project(r"C:\projects\test.aep")
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("app.open", script)

    # 3. Save project
    def test_save_project(self) -> None:
        result = self.controller.save_project()
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("project.save()", script)

    # 4. Save As
    def test_save_project_as(self) -> None:
        result = self.controller.save_project_as(r"C:\projects\new.aep")
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("save(", script)

    # 5. Close project
    def test_close_project(self) -> None:
        result = self.controller.close_project()
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("close", script)

    def test_close_project_with_save(self) -> None:
        result = self.controller.close_project(save=True)
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("true", script)

    # 6. Get project information
    def test_get_project_info(self) -> None:
        result = self.controller.get_project_info()
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("get_project_info", script)

    def test_is_project_open(self) -> None:
        result = self.controller.is_project_open()
        self.mock_runner.run.assert_called_once()


# ---------------------------------------------------------------------------
# CompositionController Tests
# ---------------------------------------------------------------------------

class TestCompositionController(unittest.TestCase):
    """CompositionController tests – AEScriptRunner is mocked."""

    def setUp(self) -> None:
        self.mock_runner = MagicMock(spec=AEScriptRunner)
        self.mock_runner.run.return_value = '{"success": true}'
        self.controller = CompositionController(self.mock_runner)

    # 1. Create a composition
    def test_create_composition(self) -> None:
        result = self.controller.create_composition(
            name="Main Comp",
            width=1920,
            height=1080,
        )
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("addComp", script)
        self.assertIn("Main Comp", script)

    def test_create_composition_with_all_params(self) -> None:
        result = self.controller.create_composition(
            name="Comp2",
            width=3840,
            height=2160,
            pixel_aspect=1.0,
            duration=15.0,
            frame_rate=60.0,
            background_color=(1.0, 0.0, 0.0),
        )
        self.mock_runner.run.assert_called_once()

    # 2. Find a composition
    def test_find_composition(self) -> None:
        result = self.controller.find_composition("Main Comp")
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("find_composition", script)

    # 3. Rename a composition
    def test_rename_composition(self) -> None:
        result = self.controller.rename_composition("Old Name", "New Name")
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("rename_composition", script)

    # 4. Change dimensions
    def test_change_width(self) -> None:
        result = self.controller.change_width("Main Comp", 3840)
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("width", script)

    def test_change_height(self) -> None:
        result = self.controller.change_height("Main Comp", 2160)
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("height", script)

    # 5. Change duration
    def test_change_duration(self) -> None:
        result = self.controller.change_duration("Main Comp", 20.0)
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("change_duration", script)

    # 6. Change frame rate
    def test_change_frame_rate(self) -> None:
        result = self.controller.change_frame_rate("Main Comp", 60.0)
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("change_frame_rate", script)

    # 7. Change background color
    def test_change_background_color(self) -> None:
        result = self.controller.change_background_color(
            "Main Comp", (0.5, 0.5, 0.5)
        )
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("change_background_color", script)

    # 8. Duplicate a composition
    def test_duplicate_composition(self) -> None:
        result = self.controller.duplicate_composition("Main Comp")
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("duplicate_composition", script)

    def test_duplicate_composition_with_new_name(self) -> None:
        result = self.controller.duplicate_composition("Main Comp", "Copy")
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("Copy", script)

    # 9. Delete a composition
    def test_delete_composition(self) -> None:
        result = self.controller.delete_composition("Main Comp")
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("delete_composition", script)

    # Validation tests
    def test_rejects_empty_name(self) -> None:
        with self.assertRaises(ValueError):
            self.controller.create_composition("", 1920, 1080)

    def test_rejects_non_string_name(self) -> None:
        with self.assertRaises(TypeError):
            self.controller.create_composition(123, 1920, 1080)

    def test_rejects_zero_width(self) -> None:
        with self.assertRaises(ValueError):
            self.controller.create_composition("Comp", 0, 1080)

    def test_rejects_negative_duration(self) -> None:
        with self.assertRaises(ValueError):
            self.controller.change_duration("Comp", -1.0)

    def test_rejects_invalid_color(self) -> None:
        with self.assertRaises(ValueError):
            self.controller.change_background_color("Comp", (2.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# LayerController Tests
# ---------------------------------------------------------------------------

class TestLayerController(unittest.TestCase):
    """LayerController tests – AEScriptRunner is mocked."""

    def setUp(self) -> None:
        self.mock_runner = MagicMock(spec=AEScriptRunner)
        self.mock_runner.run.return_value = '{"success": true}'
        self.controller = LayerController(self.mock_runner)
        self.comp = "Main Comp"

    # 1. Add solid
    def test_add_solid(self) -> None:
        result = self.controller.add_solid(self.comp, "BG Solid")
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("addSolid", script)
        self.assertIn("BG Solid", script)

    def test_add_solid_with_options(self) -> None:
        result = self.controller.add_solid(
            self.comp, "Custom Solid",
            color=(1.0, 0.0, 0.0), width=1920, height=1080, duration=5.0,
        )
        self.mock_runner.run.assert_called_once()

    # 2. Add text layer
    def test_add_text(self) -> None:
        result = self.controller.add_text(self.comp, "Title", "Hello World")
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("addText", script)
        self.assertIn("Hello World", script)

    # 3. Add null layer
    def test_add_null(self) -> None:
        result = self.controller.add_null(self.comp, "Control Null")
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("addNull", script)

    # 4. Add adjustment layer
    def test_add_adjustment_layer(self) -> None:
        result = self.controller.add_adjustment_layer(self.comp, "Adj Layer")
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("adjustmentLayer", script)

    # 5. Import footage
    def test_import_footage(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            footage_path = f.name
        try:
            result = self.controller.import_footage(footage_path)
            self.mock_runner.run.assert_called_once()
            script = self.mock_runner.run.call_args[0][0]
            self.assertIn("import_footage", script)
        finally:
            os.unlink(footage_path)

    def test_import_footage_nonexistent_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            self.controller.import_footage(r"C:\nonexistent\video.mp4")

    # 6. Add footage to a composition
    def test_add_imported_footage(self) -> None:
        result = self.controller.add_imported_footage(self.comp, "clip.mp4")
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("add_imported_footage", script)

    # 7. Find a layer
    def test_find_layer(self) -> None:
        result = self.controller.find_layer(self.comp, "BG Solid")
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("find_layer", script)

    # 8. Rename a layer
    def test_rename_layer(self) -> None:
        result = self.controller.rename_layer(self.comp, "Old", "New")
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("rename_layer", script)

    # 9. Delete a layer
    def test_delete_layer(self) -> None:
        result = self.controller.delete_layer(self.comp, "Unwanted")
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("delete_layer", script)

    # 10. Move a layer
    def test_move_layer(self) -> None:
        result = self.controller.move_layer(self.comp, "Layer 1", 3)
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("move_layer", script)

    # 11. Duplicate a layer
    def test_duplicate_layer(self) -> None:
        result = self.controller.duplicate_layer(self.comp, "Source")
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("duplicate_layer", script)

    def test_duplicate_layer_with_new_name(self) -> None:
        result = self.controller.duplicate_layer(self.comp, "Source", "Copy")
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("Copy", script)

    # 12. Enable/disable a layer
    def test_set_enabled_true(self) -> None:
        result = self.controller.set_enabled(self.comp, "Layer", True)
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("set_layer_enabled", script)

    def test_set_enabled_false(self) -> None:
        result = self.controller.set_enabled(self.comp, "Layer", False)
        self.mock_runner.run.assert_called_once()

    def test_set_enabled_rejects_non_bool(self) -> None:
        with self.assertRaises(TypeError):
            self.controller.set_enabled(self.comp, "Layer", 1)

    # 13. Set opacity
    def test_set_opacity(self) -> None:
        result = self.controller.set_opacity(self.comp, "Layer", 50.0)
        self.mock_runner.run.assert_called_once()

    # 14. Set position
    def test_set_position(self) -> None:
        result = self.controller.set_position(self.comp, "Layer", [960, 540])
        self.mock_runner.run.assert_called_once()

    # 15. Set scale
    def test_set_scale(self) -> None:
        result = self.controller.set_scale(self.comp, "Layer", [100, 100])
        self.mock_runner.run.assert_called_once()

    # 16. Set rotation
    def test_set_rotation(self) -> None:
        result = self.controller.set_rotation(self.comp, "Layer", 45.0)
        self.mock_runner.run.assert_called_once()

    # 17. Set anchor point
    def test_set_anchor_point(self) -> None:
        result = self.controller.set_anchor_point(self.comp, "Layer", [960, 540])
        self.mock_runner.run.assert_called_once()

    # 18. Set parent
    def test_set_parent(self) -> None:
        result = self.controller.set_parent(self.comp, "Child", "Parent")
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("set_parent", script)

    def test_clear_parent(self) -> None:
        result = self.controller.set_parent(self.comp, "Child", None)
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("null", script)

    # 19. Create keyframes
    def test_add_keyframe(self) -> None:
        result = self.controller.add_keyframe(
            self.comp, "Layer", "position", 0.0, [960, 540],
        )
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("add_keyframe", script)

    def test_add_keyframe_opacity(self) -> None:
        result = self.controller.add_keyframe(
            self.comp, "Layer", "opacity", 1.0, 100,
        )
        self.mock_runner.run.assert_called_once()

    # 20. Set keyframe values
    def test_set_keyframe_value(self) -> None:
        result = self.controller.set_keyframe_value(
            self.comp, "Layer", "position", 1, [100, 200],
        )
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("set_keyframe_value", script)

    # 21. Remove keyframes
    def test_remove_keyframes(self) -> None:
        result = self.controller.remove_keyframes(
            self.comp, "Layer", "position",
        )
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("remove_keyframes", script)

    # set_transform with multiple properties
    def test_set_transform_multiple_properties(self) -> None:
        result = self.controller.set_transform(
            self.comp, "Layer",
            {"position": [960, 540], "opacity": 80},
        )
        self.mock_runner.run.assert_called_once()

    def test_set_transform_rejects_unsupported_property(self) -> None:
        with self.assertRaises(ValueError):
            self.controller.set_transform(
                self.comp, "Layer", {"nonexistent": 42},
            )

    def test_set_transform_rejects_empty_properties(self) -> None:
        with self.assertRaises(ValueError):
            self.controller.set_transform(self.comp, "Layer", {})

    def test_add_keyframe_rejects_unsupported_property(self) -> None:
        with self.assertRaises(ValueError):
            self.controller.add_keyframe(
                self.comp, "Layer", "nonexistent", 0.0, 42,
            )

    def test_add_keyframe_rejects_negative_time(self) -> None:
        with self.assertRaises(ValueError):
            self.controller.add_keyframe(
                self.comp, "Layer", "position", -1.0, [0, 0],
            )

    def test_get_layer_info(self) -> None:
        result = self.controller.get_layer_info(self.comp, "Layer")
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("get_layer_info", script)

    def test_opacity_range_validation(self) -> None:
        with self.assertRaises(ValueError):
            self.controller.set_opacity(self.comp, "Layer", 150.0)


# ---------------------------------------------------------------------------
# EffectsController Tests
# ---------------------------------------------------------------------------

class TestEffectsController(unittest.TestCase):
    """EffectsController tests – AEScriptRunner is mocked."""

    def setUp(self) -> None:
        self.mock_runner = MagicMock(spec=AEScriptRunner)
        self.mock_runner.run.return_value = '{"success": true}'
        self.controller = EffectsController(self.mock_runner)
        self.comp = "Main Comp"
        self.layer = "Solid Layer"

    # 1. Inspect effects
    def test_inspect_effects(self) -> None:
        result = self.controller.inspect_effects(self.comp, self.layer)
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("inspect_effects", script)

    # 2. Add an effect by name
    def test_add_effect_by_name(self) -> None:
        result = self.controller.add_effect(
            self.comp, self.layer, "Gaussian Blur",
        )
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("Gaussian Blur", script)
        self.assertIn("addProperty", script)

    # 3. Add an effect using a match name
    def test_add_effect_with_match_name(self) -> None:
        result = self.controller.add_effect(
            self.comp, self.layer, "Gaussian Blur",
            match_name="ADBE Gaussian Blur 2",
        )
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("ADBE Gaussian Blur 2", script)

    # 4. Find an effect
    def test_find_effect(self) -> None:
        result = self.controller.find_effect(
            self.comp, self.layer, "Gaussian Blur",
        )
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("find_effect", script)

    def test_find_effect_with_match_name(self) -> None:
        result = self.controller.find_effect(
            self.comp, self.layer, "Blur",
            match_name="ADBE Gaussian Blur 2",
        )
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("ADBE Gaussian Blur 2", script)

    # 5. Set an effect property
    def test_set_effect_property(self) -> None:
        result = self.controller.set_effect_property(
            self.comp, self.layer, "Gaussian Blur", "Blurriness", 25.0,
        )
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("set_effect_property", script)
        self.assertIn("Blurriness", script)

    # 6. Get an effect property
    def test_get_effect_property(self) -> None:
        result = self.controller.get_effect_property(
            self.comp, self.layer, "Gaussian Blur", "Blurriness",
        )
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("get_effect_property", script)

    # 7. Enable an effect
    def test_enable_effect(self) -> None:
        result = self.controller.enable_effect(
            self.comp, self.layer, "Gaussian Blur", True,
        )
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("enable_effect", script)

    # 8. Disable an effect
    def test_disable_effect(self) -> None:
        result = self.controller.enable_effect(
            self.comp, self.layer, "Gaussian Blur", False,
        )
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("false", script)

    def test_enable_effect_rejects_non_bool(self) -> None:
        with self.assertRaises(TypeError):
            self.controller.enable_effect(
                self.comp, self.layer, "Gaussian Blur", 1,
            )

    # 9. Reorder an effect
    def test_reorder_effect(self) -> None:
        result = self.controller.reorder_effect(
            self.comp, self.layer, "Gaussian Blur", 2,
        )
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("reorder_effect", script)

    def test_reorder_effect_with_match_name(self) -> None:
        result = self.controller.reorder_effect(
            self.comp, self.layer, "Blur", 1,
            match_name="ADBE Gaussian Blur 2",
        )
        self.mock_runner.run.assert_called_once()

    # Remove effect
    def test_remove_effect(self) -> None:
        result = self.controller.remove_effect(
            self.comp, self.layer, "Gaussian Blur",
        )
        self.mock_runner.run.assert_called_once()
        script = self.mock_runner.run.call_args[0][0]
        self.assertIn("remove_effect", script)

    def test_remove_effect_with_match_name(self) -> None:
        result = self.controller.remove_effect(
            self.comp, self.layer, "Blur",
            match_name="ADBE Gaussian Blur 2",
        )
        self.mock_runner.run.assert_called_once()

    # Dynamic effect names
    def test_effect_names_can_be_dynamic(self) -> None:
        """Effect names are supplied as parameters – not hardcoded."""
        for effect_name in ["Fill", "Tint", "Levels", "Curves", "Glow"]:
            self.mock_runner.reset_mock()
            self.controller.add_effect(self.comp, self.layer, effect_name)
            script = self.mock_runner.run.call_args[0][0]
            self.assertIn(effect_name, script)

    # Validation
    def test_rejects_empty_effect_name(self) -> None:
        with self.assertRaises(ValueError):
            self.controller.add_effect(self.comp, self.layer, "")

    def test_rejects_non_string_effect_name(self) -> None:
        with self.assertRaises(TypeError):
            self.controller.add_effect(self.comp, self.layer, 42)

    def test_set_effect_property_with_match_name(self) -> None:
        result = self.controller.set_effect_property(
            self.comp, self.layer, "Blur", "Blurriness", 10.0,
            match_name="ADBE Gaussian Blur 2",
        )
        self.mock_runner.run.assert_called_once()

    def test_get_effect_property_with_match_name(self) -> None:
        result = self.controller.get_effect_property(
            self.comp, self.layer, "Blur", "Blurriness",
            match_name="ADBE Gaussian Blur 2",
        )
        self.mock_runner.run.assert_called_once()


# ---------------------------------------------------------------------------
# AEAutomationCommands Tests
# ---------------------------------------------------------------------------

class TestAEAutomationCommands(unittest.TestCase):
    """High-level AEAutomationCommands delegation tests."""

    def setUp(self) -> None:
        self.mock_runner = MagicMock(spec=AEScriptRunner)
        self.mock_runner.run.return_value = '{"success": true}'
        self.commands = AEAutomationCommands(runner=self.mock_runner)

        # Patch the internal controllers with fresh mocks
        self.commands.project = MagicMock(spec=ProjectController)
        self.commands.composition = MagicMock(spec=CompositionController)
        self.commands.layers = MagicMock(spec=LayerController)
        self.commands.effects = MagicMock(spec=EffectsController)

        # MagicMock methods return MagicMock by default, which is sufficient
        # for verifying delegation.

    # --- create_project ---
    def test_create_project_delegates(self) -> None:
        self.commands.create_project()
        self.commands.project.create_project.assert_called_once()

    # --- open_project ---
    def test_open_project_delegates(self) -> None:
        self.commands.open_project(r"C:\test.aep")
        self.commands.project.open_project.assert_called_once_with(
            r"C:\test.aep"
        )

    # --- save_project ---
    def test_save_project_delegates(self) -> None:
        self.commands.save_project()
        self.commands.project.save_project.assert_called_once()

    # --- save_project_as ---
    def test_save_project_as_delegates(self) -> None:
        self.commands.save_project_as(r"C:\new.aep")
        self.commands.project.save_project_as.assert_called_once_with(
            r"C:\new.aep"
        )

    # --- create_composition ---
    def test_create_composition_delegates(self) -> None:
        self.commands.create_composition("Comp", 1920, 1080)
        self.commands.composition.create_composition.assert_called_once()

    # --- add_layer (solid) ---
    def test_add_layer_solid_delegates(self) -> None:
        self.commands.add_layer("Comp", "Solid", "solid")
        self.commands.layers.add_solid.assert_called_once()

    # --- add_layer (text) ---
    def test_add_layer_text_delegates(self) -> None:
        self.commands.add_layer("Comp", "Title", "text", text="Hello")
        self.commands.layers.add_text.assert_called_once()

    # --- add_layer (null) ---
    def test_add_layer_null_delegates(self) -> None:
        self.commands.add_layer("Comp", "Null", "null")
        self.commands.layers.add_null.assert_called_once()

    # --- add_layer (adjustment) ---
    def test_add_layer_adjustment_delegates(self) -> None:
        self.commands.add_layer("Comp", "Adj", "adjustment")
        self.commands.layers.add_adjustment_layer.assert_called_once()

    # --- add_layer (footage) ---
    def test_add_layer_footage_delegates(self) -> None:
        self.commands.add_layer(
            "Comp", "FG", "footage", footage_name="clip.mp4",
        )
        self.commands.layers.add_imported_footage.assert_called_once()

    # --- add_layer (unsupported) ---
    def test_add_layer_unsupported_type_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.commands.add_layer("Comp", "X", "particle")

    # --- add_text ---
    def test_add_text_delegates(self) -> None:
        self.commands.add_text("Comp", "Title", "Hello")
        self.commands.layers.add_text.assert_called_once_with(
            "Comp", "Title", "Hello",
        )

    # --- add_solid ---
    def test_add_solid_delegates(self) -> None:
        self.commands.add_solid("Comp", "BG")
        self.commands.layers.add_solid.assert_called_once()

    # --- import_footage ---
    def test_import_footage_delegates(self) -> None:
        self.commands.import_footage(r"C:\clip.mp4")
        self.commands.layers.import_footage.assert_called_once_with(
            r"C:\clip.mp4"
        )

    # --- rename_layer ---
    def test_rename_layer_delegates(self) -> None:
        self.commands.rename_layer("Comp", "Old", "New")
        self.commands.layers.rename_layer.assert_called_once_with(
            "Comp", "Old", "New",
        )

    # --- set_transform ---
    def test_set_transform_delegates(self) -> None:
        props = {"position": [960, 540]}
        self.commands.set_transform("Comp", "Layer", props)
        self.commands.layers.set_transform.assert_called_once_with(
            "Comp", "Layer", props,
        )

    # --- set_keyframe ---
    def test_set_keyframe_delegates(self) -> None:
        self.commands.set_keyframe("Comp", "Layer", "position", 0.0, [960, 540])
        self.commands.layers.add_keyframe.assert_called_once_with(
            "Comp", "Layer", "position", 0.0, [960, 540],
        )

    # --- add_effect ---
    def test_add_effect_delegates(self) -> None:
        self.commands.add_effect("Comp", "Layer", "Blur")
        self.commands.effects.add_effect.assert_called_once_with(
            "Comp", "Layer", "Blur", None,
        )

    def test_add_effect_with_match_name_delegates(self) -> None:
        self.commands.add_effect(
            "Comp", "Layer", "Blur", match_name="ADBE Gaussian Blur 2",
        )
        self.commands.effects.add_effect.assert_called_once_with(
            "Comp", "Layer", "Blur", "ADBE Gaussian Blur 2",
        )

    # --- remove_effect ---
    def test_remove_effect_delegates(self) -> None:
        self.commands.remove_effect("Comp", "Layer", "Blur")
        self.commands.effects.remove_effect.assert_called_once_with(
            "Comp", "Layer", "Blur", None,
        )

    # --- set_effect_property ---
    def test_set_effect_property_delegates(self) -> None:
        self.commands.set_effect_property(
            "Comp", "Layer", "Blur", "Blurriness", 25.0,
        )
        self.commands.effects.set_effect_property.assert_called_once()

    # --- get_project_info ---
    def test_get_project_info_delegates(self) -> None:
        self.commands.get_project_info()
        self.commands.project.get_project_info.assert_called_once()

    # --- get_composition_info ---
    def test_get_composition_info_delegates(self) -> None:
        self.commands.get_composition_info("Comp")
        self.commands.composition.get_composition_info.assert_called_once_with(
            "Comp",
        )

    # --- get_layer_info ---
    def test_get_layer_info_delegates(self) -> None:
        self.commands.get_layer_info("Comp", "Layer")
        self.commands.layers.get_layer_info.assert_called_once_with(
            "Comp", "Layer",
        )

    # --- find_composition ---
    def test_find_composition_delegates(self) -> None:
        self.commands.find_composition("Comp")
        self.commands.composition.find_composition.assert_called_once_with(
            "Comp",
        )

    # --- find_layer ---
    def test_find_layer_delegates(self) -> None:
        self.commands.find_layer("Comp", "Layer")
        self.commands.layers.find_layer.assert_called_once_with(
            "Comp", "Layer",
        )

    # --- find_effect ---
    def test_find_effect_delegates(self) -> None:
        self.commands.find_effect("Comp", "Layer", "Blur")
        self.commands.effects.find_effect.assert_called_once_with(
            "Comp", "Layer", "Blur", None,
        )

    # --- set_parent ---
    def test_set_parent_delegates(self) -> None:
        self.commands.set_parent("Comp", "Child", "Parent")
        self.commands.layers.set_parent.assert_called_once_with(
            "Comp", "Child", "Parent",
        )

    # --- delete_layer ---
    def test_delete_layer_delegates(self) -> None:
        self.commands.delete_layer("Comp", "Layer")
        self.commands.layers.delete_layer.assert_called_once_with(
            "Comp", "Layer",
        )

    # --- duplicate_layer ---
    def test_duplicate_layer_delegates(self) -> None:
        self.commands.duplicate_layer("Comp", "Layer")
        self.commands.layers.duplicate_layer.assert_called_once_with(
            "Comp", "Layer", None,
        )

    # --- move_layer ---
    def test_move_layer_delegates(self) -> None:
        self.commands.move_layer("Comp", "Layer", 2)
        self.commands.layers.move_layer.assert_called_once_with(
            "Comp", "Layer", 2,
        )

    # --- enable_layer ---
    def test_enable_layer_delegates(self) -> None:
        self.commands.enable_layer("Comp", "Layer", True)
        self.commands.layers.set_enabled.assert_called_once_with(
            "Comp", "Layer", True,
        )

    # --- set_parent_layer ---
    def test_set_parent_layer_delegates(self) -> None:
        self.commands.set_parent_layer("Comp", "Child", "Parent")
        self.commands.layers.set_parent.assert_called_once_with(
            "Comp", "Child", "Parent",
        )

    # --- remove_keyframes ---
    def test_remove_keyframes_delegates(self) -> None:
        self.commands.remove_keyframes("Comp", "Layer", "position")
        self.commands.layers.remove_keyframes.assert_called_once_with(
            "Comp", "Layer", "position",
        )

    # --- set_keyframe_value ---
    def test_set_keyframe_value_delegates(self) -> None:
        self.commands.set_keyframe_value(
            "Comp", "Layer", "position", 1, [100, 200],
        )
        self.commands.layers.set_keyframe_value.assert_called_once_with(
            "Comp", "Layer", "position", 1, [100, 200],
        )

    # --- inspect_effects ---
    def test_inspect_effects_delegates(self) -> None:
        self.commands.inspect_effects("Comp", "Layer")
        self.commands.effects.inspect_effects.assert_called_once_with(
            "Comp", "Layer",
        )

    # --- get_effect_property ---
    def test_get_effect_property_delegates(self) -> None:
        self.commands.get_effect_property(
            "Comp", "Layer", "Blur", "Blurriness",
        )
        self.commands.effects.get_effect_property.assert_called_once()

    # --- enable_effect ---
    def test_enable_effect_delegates(self) -> None:
        self.commands.enable_effect("Comp", "Layer", "Blur", True)
        self.commands.effects.enable_effect.assert_called_once()

    # --- reorder_effect ---
    def test_reorder_effect_delegates(self) -> None:
        self.commands.reorder_effect("Comp", "Layer", "Blur", 1)
        self.commands.effects.reorder_effect.assert_called_once()


class TestAEAutomationCommandsInit(unittest.TestCase):
    """Verify AEAutomationCommands wiring with a real (mocked) runner."""

    def test_uses_provided_runner(self) -> None:
        mock_runner = MagicMock(spec=AEScriptRunner)
        cmds = AEAutomationCommands(runner=mock_runner)
        self.assertIs(cmds.runner, mock_runner)
        self.assertIsInstance(cmds.project, ProjectController)
        self.assertIsInstance(cmds.composition, CompositionController)
        self.assertIsInstance(cmds.layers, LayerController)
        self.assertIsInstance(cmds.effects, EffectsController)

    def test_creates_runner_from_executable_path(self) -> None:
        fake_exe = _make_fake_exe()
        try:
            cmds = AEAutomationCommands(executable_path=fake_exe)
            self.assertIsInstance(cmds.runner, AEScriptRunner)
        finally:
            os.unlink(fake_exe)


# ---------------------------------------------------------------------------
# Safety Tests
# ---------------------------------------------------------------------------

class TestSafety(unittest.TestCase):
    """Safety invariants that must hold for every ae_automation module."""

    MODULE_NAMES = [
        "ae_automation",
        "ae_automation.script_runner",
        "ae_automation.project",
        "ae_automation.composition",
        "ae_automation.layers",
        "ae_automation.effects",
        "ae_automation.commands",
    ]

    SOURCE_FILES = [
        os.path.join("ae_automation", "__init__.py"),
        os.path.join("ae_automation", "script_runner.py"),
        os.path.join("ae_automation", "project.py"),
        os.path.join("ae_automation", "composition.py"),
        os.path.join("ae_automation", "layers.py"),
        os.path.join("ae_automation", "effects.py"),
        os.path.join("ae_automation", "commands.py"),
    ]

    def _get_project_root(self) -> str:
        """Return the project root directory."""
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # 1. No subprocess call on import
    @patch("ae_automation.script_runner.subprocess.run")
    def test_no_subprocess_on_import(self, mock_run: MagicMock) -> None:
        """Importing modules must not trigger subprocess.run."""
        for name in self.MODULE_NAMES:
            if name in sys.modules:
                importlib.reload(sys.modules[name])
            else:
                importlib.import_module(name)
        mock_run.assert_not_called()

    # 2. No subprocess call when creating controller objects
    @patch("ae_automation.script_runner.subprocess.run")
    def test_no_subprocess_on_controller_creation(self, mock_run: MagicMock) -> None:
        """Instantiating controllers must not trigger subprocess.run."""
        mock_runner = MagicMock(spec=AEScriptRunner)
        _ = ProjectController(mock_runner)
        _ = CompositionController(mock_runner)
        _ = LayerController(mock_runner)
        _ = EffectsController(mock_runner)
        mock_run.assert_not_called()

    # 3. subprocess calls use shell=False
    def test_subprocess_uses_shell_false(self) -> None:
        """The script_runner source must contain shell=False."""
        root = self._get_project_root()
        runner_path = os.path.join(root, "ae_automation", "script_runner.py")
        with open(runner_path, "r", encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn("shell=False", source)
        self.assertNotIn("shell=True", source)

    # 4. No credentials hard-coded
    def test_no_hardcoded_credentials(self) -> None:
        """Source files must not contain hard-coded credentials."""
        root = self._get_project_root()
        credential_patterns = [
            "password",
            "api_key",
            "secret_key",
            "access_token",
            "client_secret",
        ]
        for rel_path in self.SOURCE_FILES:
            full = os.path.join(root, rel_path)
            if not os.path.isfile(full):
                continue
            with open(full, "r", encoding="utf-8") as fh:
                source = fh.read().lower()
            for pattern in credential_patterns:
                # Allow mentions in docstrings / comments about the concept,
                # but reject literal assignments like   password = "..."
                assignment = f'{pattern} = "'
                self.assertNotIn(
                    assignment,
                    source,
                    msg=f"Possible hard-coded credential in {rel_path}: {pattern}",
                )

    # 5. No network library usage
    def test_no_network_library(self) -> None:
        """ae_automation must not import networking libraries."""
        root = self._get_project_root()
        network_imports = [
            "import requests",
            "import urllib.request",
            "import http.client",
            "import httpx",
            "import aiohttp",
            "from requests",
            "from urllib.request",
            "from http.client",
            "from httpx",
            "from aiohttp",
            "import socket",
            "from socket",
        ]
        for rel_path in self.SOURCE_FILES:
            full = os.path.join(root, rel_path)
            if not os.path.isfile(full):
                continue
            with open(full, "r", encoding="utf-8") as fh:
                source = fh.read()
            for pattern in network_imports:
                self.assertNotIn(
                    pattern,
                    source,
                    msg=f"Network library usage in {rel_path}: {pattern}",
                )

    # 6. No Chrome automation
    def test_no_chrome_automation(self) -> None:
        """ae_automation must not use Chrome or Selenium."""
        root = self._get_project_root()
        chrome_patterns = [
            "selenium",
            "chromedriver",
            "webdriver",
            "from selenium",
            "import selenium",
            "Chrome(",
            "chrome_options",
            "playwright",
            "puppeteer",
        ]
        for rel_path in self.SOURCE_FILES:
            full = os.path.join(root, rel_path)
            if not os.path.isfile(full):
                continue
            with open(full, "r", encoding="utf-8") as fh:
                source = fh.read()
            for pattern in chrome_patterns:
                self.assertNotIn(
                    pattern,
                    source,
                    msg=f"Chrome automation reference in {rel_path}: {pattern}",
                )

    # 7. No arbitrary PowerShell execution
    def test_no_powershell_execution(self) -> None:
        """ae_automation must not spawn arbitrary PowerShell processes."""
        root = self._get_project_root()
        powershell_patterns = [
            "powershell",
            "pwsh",
            "Invoke-Expression",
            "Invoke-Command",
        ]
        for rel_path in self.SOURCE_FILES:
            full = os.path.join(root, rel_path)
            if not os.path.isfile(full):
                continue
            with open(full, "r", encoding="utf-8") as fh:
                source = fh.read()
            for pattern in powershell_patterns:
                self.assertNotIn(
                    pattern,
                    source,
                    msg=f"PowerShell reference in {rel_path}: {pattern}",
                )


class TestSafetySubprocessIsolation(unittest.TestCase):
    """Ensure subprocess is only used through AEScriptRunner."""

    def test_controllers_do_not_import_subprocess(self) -> None:
        """Only script_runner.py should import subprocess directly."""
        controlled_modules = [
            "ae_automation.project",
            "ae_automation.composition",
            "ae_automation.layers",
            "ae_automation.effects",
            "ae_automation.commands",
        ]
        for mod_name in controlled_modules:
            mod = sys.modules.get(mod_name) or importlib.import_module(mod_name)
            source_file = inspect.getfile(mod)
            with open(source_file, "r", encoding="utf-8") as fh:
                source = fh.read()
            self.assertNotIn(
                "import subprocess",
                source,
                msg=f"{mod_name} should not import subprocess directly.",
            )


class TestSafetyModuleImport(unittest.TestCase):
    """Verify no side effects on module import."""

    @patch("ae_automation.script_runner.subprocess.run")
    def test_import_ae_automation_package(self, mock_run: MagicMock) -> None:
        """The top-level ae_automation package must import cleanly."""
        importlib.reload(sys.modules["ae_automation"])
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
