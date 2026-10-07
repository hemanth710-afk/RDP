import unittest
import json
from pathlib import Path

from brain.editing_plan import EditingAction, EditingPlan, EditingPlanError
from brain.plan_parser import EditingPlanParser, PlanParserError
from brain.amv_script import AMVScript, ClipReference, AMVScriptError


class TestAMVPlanner(unittest.TestCase):
    def setUp(self):
        self.parser = EditingPlanParser()
        self.valid_plan_dict = {
            "title": "Test Plan",
            "duration": 60.0,
            "actions": [
                {
                    "action": "cut",
                    "parameters": {
                        "composition_name": "Comp 1",
                        "layer_name": "Clip 1",
                        "timeline_start": 0.0,
                        "timeline_end": 5.0,
                        "source_start": 2.0
                    }
                }
            ]
        }

    def test_parse_valid_plan(self):
        plan = self.parser.parse(self.valid_plan_dict)
        self.assertEqual(plan.title, "Test Plan")
        self.assertEqual(plan.action_count, 1)
        self.assertEqual(plan.actions[0].action, "cut")

    def test_parse_duration_variations(self):
        # duration=2
        data = dict(self.valid_plan_dict, duration=2)
        plan = self.parser.parse(data)
        self.assertEqual(plan.duration, 2.0)

        # duration=300
        data = dict(self.valid_plan_dict, duration=300)
        plan = self.parser.parse(data)
        self.assertEqual(plan.duration, 300.0)

        # duration=1800
        data = dict(self.valid_plan_dict, duration=1800)
        plan = self.parser.parse(data)
        self.assertEqual(plan.duration, 1800.0)

        # duration=7200
        data = dict(self.valid_plan_dict, duration=7200)
        plan = self.parser.parse(data)
        self.assertEqual(plan.duration, 7200.0)

    def test_parse_invalid_durations(self):
        # duration=-5
        data = dict(self.valid_plan_dict, duration=-5)
        with self.assertRaises(PlanParserError):
            self.parser.parse(data)

        # duration=0
        data = dict(self.valid_plan_dict, duration=0)
        with self.assertRaises(PlanParserError):
            self.parser.parse(data)

    def test_parse_unsupported_actions(self):
        data = dict(self.valid_plan_dict)
        data["actions"] = [{"action": "run_python", "parameters": {}}]
        with self.assertRaises(PlanParserError):
            self.parser.parse(data)

        data["actions"] = [{"action": "execute_shell", "parameters": {}}]
        with self.assertRaises(PlanParserError):
            self.parser.parse(data)

    def test_parse_invalid_timeline(self):
        # end < start
        data = dict(self.valid_plan_dict)
        data["actions"] = [{"action": "cut", "start_time": 5.0, "end_time": 2.0}]
        with self.assertRaises(PlanParserError):
            self.parser.parse(data)

        # negative start_time
        data["actions"] = [{"action": "cut", "start_time": -1.0, "end_time": 2.0}]
        with self.assertRaises(PlanParserError):
            self.parser.parse(data)

    def test_parse_markdown_fenced_json(self):
        json_str = json.dumps(self.valid_plan_dict)
        payload = f"```json\n{json_str}\n```"
        plan = self.parser.parse(payload)
        self.assertEqual(plan.title, "Test Plan")

    def test_serialize_deserialize_roundtrip(self):
        plan1 = self.parser.parse(self.valid_plan_dict)
        plan_dict = plan1.to_dict()
        plan2 = EditingPlan.from_dict(plan_dict)
        
        self.assertEqual(plan1.title, plan2.title)
        self.assertEqual(plan1.duration, plan2.duration)
        self.assertEqual(plan1.action_count, plan2.action_count)
        self.assertEqual(plan1.actions[0].action, plan2.actions[0].action)
        self.assertEqual(plan1.actions[0].parameters, plan2.actions[0].parameters)

    def test_parse_valid_amv_script(self):
        data = {
            "title": "My AMV",
            "duration": 60.0,
            "clips": [{"path": "clip1.mp4", "clip_id": "c1"}]
        }
        script = AMVScript.from_dict(data)
        self.assertEqual(script.title, "My AMV")
        self.assertEqual(len(script.clips), 1)

    def test_invalid_amv_script(self):
        with self.assertRaises(AMVScriptError):
            AMVScript.from_dict({"title": "", "clips": []})
        
        with self.assertRaises(AMVScriptError):
            AMVScript.from_dict({"title": "A", "target_duration": -5.0})

    def test_amv_script_validate_paths(self):
        script = AMVScript(title="Test", song_path="nonexistent_song.mp3", clips=[ClipReference(path="nonexistent_clip.mp4")])
        missing = script.validate_paths()
        self.assertEqual(len(missing), 2)
        self.assertTrue(any("nonexistent_song.mp3" in m for m in missing))
        self.assertTrue(any("nonexistent_clip.mp4" in m for m in missing))

    def test_clip_inventory_summary(self):
        clips = [
            ClipReference(path="1.mp4", clip_id="c1", character="Naruto", scene="fight", start_time=0.0, end_time=5.0),
            ClipReference(path="2.mp4", clip_id="", character="Sasuke", start_time=10.0, end_time=12.0)
        ]
        script = AMVScript(title="Test", clips=clips)
        summary = script.clip_inventory_summary()
        self.assertIn("c1 | character=Naruto | scene=fight | duration=5.0s", summary)
        self.assertIn("clip_1 | character=Sasuke | duration=2.0s", summary)

    def test_allowed_actions_in_parser(self):
        allowed = EditingPlanParser.ALLOWED_ACTIONS
        self.assertIn("cut", allowed)
        self.assertIn("add_null", allowed)
        self.assertIn("add_adjustment_layer", allowed)
        self.assertIn("rename_layer", allowed)
        self.assertIn("set_enabled", allowed)

if __name__ == '__main__':
    unittest.main()
