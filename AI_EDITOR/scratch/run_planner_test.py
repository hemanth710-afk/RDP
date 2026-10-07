
import json
from pathlib import Path
from dotenv import load_dotenv

from config.model_config import ModelConfig
from models.provider_factory import create_provider
from brain.planner import AIEditingPlanner
from interface.chat import AIChatSession

load_dotenv('.env')

def run_test():
    config = ModelConfig.from_environment()
    chat_provider = create_provider(config)
    planner = AIEditingPlanner(chat_provider=chat_provider)
    session = AIChatSession()

    amv_context = planner.build_amv_context(
        title='Naruto Vs Sasuke Human Editor Test',
        song_path=r'C:\Users\L.Thirumala Teja\Downloads\fragment - slowed - slxughter.mp3',
        clip_inventory=r'''
CLIP 1: C:\Users\L.Thirumala Teja\Downloads\Naruto Vs Sasuke-2x-RIFE-RIFE4.0-120fps.mp4
Duration: approx 21 seconds
Resolution: 2160x3840 @ 120 FPS
Content: High intensity action fight between Naruto and Sasuke, emotional impact, rapid movement.
        '''.strip(),
        target_duration=21.0,
        mood='Intense, emotional, professional cinematic AMV',
        editing_style='Professional motion design, dynamic pacing, varied rhythm, storytelling focus, restrained but impactful effects.',
        frame_rate=60.0,
        width=2160,
        height=3840
    )

    print('Generating plan...')
    plan = planner.generate(session, amv_context=amv_context)

    out_dir = Path('scratch/human_editor_test')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / 'editing_plan.json'
    
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(plan.to_dict(), f, indent=2)
    
    print(f'\nPlan saved to: {out_file}\n')
    print('--- ANALYSIS REPORT ---')
    print(f'Notes / Explanation: {plan.notes}')
    print(f'Total Actions: {plan.action_count}')
    
    cuts = [a for a in plan.actions if a.action == 'cut']
    print(f'Number of cuts: {len(cuts)}')
    
    print('-----------------------')

if __name__ == '__main__':
    run_test()

