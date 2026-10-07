import unittest
from unittest.mock import MagicMock

from ae_automation.layers import LayerController
from ae_automation.commands import AEAutomationCommands
from brain.ae_handlers import AEAutomationHandlers
from brain.editing_plan import EditingAction

class TestCutClip(unittest.TestCase):
    def setUp(self):
        self.mock_runner = MagicMock()
        self.layer_controller = LayerController(self.mock_runner)
        
        self.mock_commands = MagicMock(spec=AEAutomationCommands)
        self.handlers = AEAutomationHandlers(self.mock_commands)

    def test_cut_clip_valid_params(self):
        self.layer_controller.cut_clip("Comp1", "Layer1", 2.0, 5.0, 1.0)
        self.mock_runner.run.assert_called_once()
        jsx = self.mock_runner.run.call_args[0][0]
        self.assertIn("layer.startTime", jsx)
        self.assertIn("layer.inPoint", jsx)
        self.assertIn("layer.outPoint", jsx)

    def test_cut_clip_empty_composition_name(self):
        with self.assertRaises(ValueError):
            self.layer_controller.cut_clip("", "Layer1", 2.0, 5.0, 1.0)

    def test_cut_clip_empty_layer_name(self):
        with self.assertRaises(ValueError):
            self.layer_controller.cut_clip("Comp1", "", 2.0, 5.0, 1.0)

    def test_cut_clip_negative_timeline_start(self):
        with self.assertRaises(ValueError):
            self.layer_controller.cut_clip("Comp1", "Layer1", -1.0, 5.0, 1.0)

    def test_cut_clip_negative_timeline_end(self):
        with self.assertRaises(ValueError):
            self.layer_controller.cut_clip("Comp1", "Layer1", 2.0, -5.0, 1.0)

    def test_cut_clip_end_le_start(self):
        with self.assertRaises(ValueError):
            self.layer_controller.cut_clip("Comp1", "Layer1", 5.0, 5.0, 1.0)
        with self.assertRaises(ValueError):
            self.layer_controller.cut_clip("Comp1", "Layer1", 5.0, 2.0, 1.0)

    def test_cut_clip_negative_source_start(self):
        with self.assertRaises(ValueError):
            self.layer_controller.cut_clip("Comp1", "Layer1", 2.0, 5.0, -1.0)

    def test_ae_handlers_cut_extracts_parameters(self):
        action = EditingAction(
            action="cut",
            parameters={
                "composition_name": "MyComp",
                "layer_name": "MyLayer",
                "timeline_start": 10.0,
                "timeline_end": 15.0,
                "source_start": 3.0
            }
        )
        self.handlers.cut(action)
        self.mock_commands.cut_clip.assert_called_once_with(
            composition_name="MyComp",
            layer_name="MyLayer",
            timeline_start=10.0,
            timeline_end=15.0,
            source_start=3.0
        )

if __name__ == '__main__':
    unittest.main()
