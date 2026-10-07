import os
from dotenv import load_dotenv
load_dotenv()
from google import genai

client = genai.Client(api_key=os.environ['GOOGLE_API_KEY'])
try:
    for m in client.models.list():
        print(m.name)
except Exception as e:
    print(e)
