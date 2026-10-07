import os
from dotenv import load_dotenv
load_dotenv()
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ['GOOGLE_API_KEY'])

models_to_test = [
    "models/gemini-2.5-pro",
    "models/gemini-1.5-pro",
    "models/gemini-pro-latest",
    "models/gemini-3.1-pro",
    "gemini-2.5-pro",
]

for model in models_to_test:
    try:
        response = client.models.generate_content(
            model=model,
            contents="test",
            config=types.GenerateContentConfig(max_output_tokens=5)
        )
        print(f"AVAILABLE: {model}")
        break
    except Exception as e:
        print(f"FAILED {model}: {e}")
