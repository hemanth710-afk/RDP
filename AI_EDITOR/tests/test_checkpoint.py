import unittest
import tempfile
import os
from pathlib import Path

from brain.project_state import ProjectState, ProjectPhase

class TestCheckpoint(unittest.TestCase):
    def test_create_save_load_roundtrip(self):
        state = ProjectState(
            script_path="script.json",
            total_actions=10
        )
        state.advance_phase(ProjectPhase.PLAN_GENERATED)
        state.mark_action_completed(3)
        
        with tempfile.TemporaryDirectory() as tempdir:
            file_path = Path(tempdir) / "state.json"
            state.save(file_path)
            
            loaded_state = ProjectState.load(file_path)
            
            self.assertEqual(loaded_state.project_id, state.project_id)
            self.assertEqual(loaded_state.phase, ProjectPhase.PLAN_GENERATED)
            self.assertEqual(loaded_state.script_path, "script.json")
            self.assertEqual(loaded_state.total_actions, 10)
            self.assertEqual(loaded_state.completed_action_index, 3)

    def test_phase_transitions(self):
        state = ProjectState()
        self.assertEqual(state.phase, ProjectPhase.INITIALIZED)
        
        state.advance_phase(ProjectPhase.EXECUTING)
        self.assertEqual(state.phase, ProjectPhase.EXECUTING)
        self.assertIn(f"phase_{ProjectPhase.EXECUTING.value}", state.timestamps)

    def test_mark_action_completed(self):
        state = ProjectState()
        self.assertEqual(state.completed_action_index, -1)
        
        state.mark_action_completed(2)
        self.assertEqual(state.completed_action_index, 2)
        self.assertEqual(state.next_action_index, 3)

    def test_mark_failed(self):
        state = ProjectState()
        state.mark_failed(5, "Error executing action")
        
        self.assertEqual(state.failed_action_index, 5)
        self.assertEqual(state.failed_action_error, "Error executing action")
        self.assertEqual(state.phase, ProjectPhase.FAILED)

    def test_next_action_index(self):
        state = ProjectState(completed_action_index=4)
        self.assertEqual(state.next_action_index, 5)

    def test_is_resumable(self):
        state = ProjectState(total_actions=10, completed_action_index=5, phase=ProjectPhase.EXECUTING)
        self.assertTrue(state.is_resumable)
        
        state = ProjectState(total_actions=10, completed_action_index=9, phase=ProjectPhase.EXECUTING)
        self.assertFalse(state.is_resumable) # all done
        
        state = ProjectState(total_actions=10, completed_action_index=5, phase=ProjectPhase.COMPLETED)
        self.assertFalse(state.is_resumable) # wrong phase

    def test_from_dict_empty(self):
        state = ProjectState.from_dict({})
        self.assertEqual(state.phase, ProjectPhase.INITIALIZED)
        self.assertEqual(state.script_path, "")
        self.assertEqual(state.total_actions, 0)
        self.assertEqual(state.completed_action_index, -1)

    def test_to_dict_from_dict_roundtrip(self):
        state = ProjectState(
            phase=ProjectPhase.EXECUTING,
            total_actions=5,
            completed_action_index=2,
            script_path="test.json",
            timestamps={"phase_executing": 12345.6}
        )
        data = state.to_dict()
        loaded = ProjectState.from_dict(data)
        
        self.assertEqual(state.project_id, loaded.project_id)
        self.assertEqual(state.phase, loaded.phase)
        self.assertEqual(state.total_actions, loaded.total_actions)
        self.assertEqual(state.completed_action_index, loaded.completed_action_index)
        self.assertEqual(state.script_path, loaded.script_path)
        self.assertEqual(state.timestamps, loaded.timestamps)

if __name__ == '__main__':
    unittest.main()
