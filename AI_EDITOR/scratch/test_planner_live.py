import sys
import os

# Add root directory to sys.path so we can import internal modules
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from brain.planner import AIEditingPlanner, AMV_SYSTEM_PROMPT
from interface.chat import AIChatSession
from models.provider_factory import create_provider
from config.model_config import ModelConfig

def main():
    conf = ModelConfig.from_environment()
    provider = create_provider(conf)
    planner = AIEditingPlanner(chat_provider=provider)
    session = AIChatSession()
    
    amv_context = planner.build_amv_context(
        title="Epic Battle",
        song_path="song.mp3",
        clip_inventory="clip1.mp4: Hero walking (0-2s)\nclip2.mp4: Enemy approaches (0-2s)",
        target_duration=2.0,
        mood="Action",
        special_requirements="Make a very short 2-second sequence. Exactly one cut."
    )

    print("Generating editing plan...")
    try:
        plan = planner.generate(session, amv_context=amv_context)
        print("PLAN GENERATED SUCCESSFULLY:")
        print("Title:", plan.title)
        print("Duration:", plan.duration)
        print("Actions Count:", plan.action_count)
        for idx, action in enumerate(plan.actions):
            print(f"Action {idx+1}: {action.action} - {action.parameters}")
    except Exception as e:
        print("FAILED TO GENERATE:", str(e))
        print("RAW RESPONSE WAS:")
        for msg in session.messages:
            if getattr(msg, "role", "") == "assistant":
                print("-------------")
                print(getattr(msg, "content", str(msg)))
                print("-------------")

if __name__ == "__main__":
    main()
