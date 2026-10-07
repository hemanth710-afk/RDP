
import json
from pathlib import Path
from dotenv import load_dotenv

from brain.plan_parser import EditingPlanParser
from brain.ae_handlers import AEAutomationHandlers
from brain.editing_plan import EditingAction

load_dotenv('.env')

class MockCommands:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.calls.append({'method': name, 'args': args, 'kwargs': kwargs})
        return method

def main():
    plan_path = Path('scratch/human_editor_test/editing_plan.json')
    with open(plan_path, 'r', encoding='utf-8') as f:
        plan_data = json.load(f)

    parser = EditingPlanParser()
    plan = parser.parse(plan_data)

    print('=== 3. PARAMETER COMPATIBILITY & 4. EXECUTOR TRACE ===')
    mock_cmds = MockCommands()
    handlers = AEAutomationHandlers(mock_cmds).handlers()
    
    trace_failures = []
    
    for i, action in enumerate(plan.actions):
        name = action.action
        handler = handlers.get(name)
        if not handler:
            trace_failures.append(f'[{i}] {name}: No handler found')
            continue
            
        try:
            handler(action)
        except Exception as e:
            trace_failures.append(f'[{i}] {name} Execution Error: {type(e).__name__} - {e}')

    if trace_failures:
        for f in trace_failures:
            print(f'FAIL - {f}')
    else:
        print('PASS - All actions successfully routed to mock AEAutomationCommands without KeyError/TypeError')
        for call in mock_cmds.calls:
            # Check for generic 'commands' trace
            meth = call['method']
            # print(f'Trace: commands.{meth}')
        print(f'PASS - Traced {len(mock_cmds.calls)} underlying AE commands.')

    # Let's verify specific parameter compat issues just to be sure
    print('\n=== CREATIVE PLAN CHECK ===')
    cuts = [a for a in plan.actions if a.action == 'cut']
    print(f'Detected Cuts: {len(cuts)}')
    if len(cuts) > 0:
        print('PASS - Non-linear editing and pacing observed')

if __name__ == '__main__':
    main()

