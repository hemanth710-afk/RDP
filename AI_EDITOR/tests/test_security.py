import unittest
from unittest.mock import MagicMock

from brain.plan_parser import EditingPlanParser, PlanParserError
from brain.editing_plan import EditingAction, EditingPlan
from brain.executor import EditingPlanExecutor, ExecutorError
from brain.ae_handlers import AEAutomationHandlers
from ae_visual.actions import AEVisibleActions

class DummyAEVisibleActions(AEVisibleActions):
    def __init__(self):
        pass
    def check_stop(self):
        pass

class TestSecurity(unittest.TestCase):
    def setUp(self):
        self.parser = EditingPlanParser()
        self.base_plan = {
            "title": "Security Test",
            "duration": 10.0,
            "actions": []
        }

    def test_parser_rejects_dangerous_actions(self):
        dangerous_actions = ["run_python", "execute_shell", "eval", "import", "exec", "system", ""]
        
        for action in dangerous_actions:
            data = dict(self.base_plan)
            data["actions"] = [{"action": action, "parameters": {}}]
            
            with self.assertRaises(PlanParserError, msg=f"Should reject {action}"):
                self.parser.parse(data)

    def test_parser_accepts_valid_actions(self):
        data = dict(self.base_plan)
        data["actions"] = [{"action": "cut", "parameters": {}}]
        plan = self.parser.parse(data)
        self.assertEqual(plan.actions[0].action, "cut")

    def test_executor_refuses_unregistered_actions(self):
        actions = DummyAEVisibleActions()
        handlers = {"cut": lambda a: None}
        executor = EditingPlanExecutor(actions, handlers)
        
        plan = EditingPlan(
            title="Test",
            duration=10.0,
            actions=[
                EditingAction(action="cut", parameters={}),
                EditingAction(action="unknown_action", parameters={})
            ]
        )
        
        with self.assertRaises(ExecutorError):
            executor.execute(plan)

    def test_only_declared_semantic_handlers_execute(self):
        actions = DummyAEVisibleActions()
        
        called_handlers = []
        def cut_handler(a): called_handlers.append("cut")
        def safe_handler(a): called_handlers.append("safe")
        
        handlers = {"cut": cut_handler, "safe": safe_handler}
        executor = EditingPlanExecutor(actions, handlers)
        
        plan = EditingPlan(
            title="Test",
            duration=10.0,
            actions=[
                EditingAction(action="cut", parameters={}),
                EditingAction(action="safe", parameters={})
            ]
        )
        
        executor.execute(plan)
        self.assertEqual(called_handlers, ["cut", "safe"])

    def test_ae_handlers_returns_safe_actions(self):
        mock_commands = MagicMock()
        ae_handlers = AEAutomationHandlers(mock_commands)
        handlers_dict = ae_handlers.handlers()
        
        # Verify no dangerous actions are in handlers
        dangerous = ["run_python", "execute_shell", "eval", "import", "exec", "system"]
        for d in dangerous:
            self.assertNotIn(d, handlers_dict)
        
        self.assertIn("cut", handlers_dict)
        self.assertIn("create_project", handlers_dict)

if __name__ == '__main__':
    unittest.main()
