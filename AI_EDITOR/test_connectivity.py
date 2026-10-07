import os
from dotenv import load_dotenv
load_dotenv()
from google import genai

client = genai.Client(api_key=os.environ['GOOGLE_API_KEY'])
model = os.environ.get('MODEL_NAME', 'gemini-pro-latest')

print(f"MODEL: {model}")

try:
    response = client.models.generate_content(
        model=model,
        contents="Reply exactly: GEMINI PRO READY",
    )
    print("API RESULT: PASS")
    print(f"RESPONSE: {response.text.strip()}")
except Exception as e:
    print("API RESULT: FAIL")
    print(f"ERROR: {e}")
