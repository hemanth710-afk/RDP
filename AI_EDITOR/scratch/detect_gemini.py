import os
import sys
from google import genai
from config.model_config import ModelConfig

def main():
    # Load .env
    conf = ModelConfig.from_environment()
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        print("NO KEY")
        sys.exit(1)

    client = genai.Client(api_key=key)
    try:
        models = client.models.list()
        model_names = [m.name for m in models]
        
        strongest = "unknown"
        for target in [
            "models/gemini-2.5-pro",
            "models/gemini-1.5-pro",
            "models/gemini-2.0-pro-exp",
            "gemini-2.5-pro",
            "gemini-1.5-pro",
            "gemini-pro"
        ]:
            if any(target in name for name in model_names):
                for name in model_names:
                    if target in name:
                        strongest = name
                        break
                break
        
        print(f"STRONGEST MODEL DETECTED: {strongest}")
    except Exception as e:
        print("ERROR:", str(e))

if __name__ == "__main__":
    main()
