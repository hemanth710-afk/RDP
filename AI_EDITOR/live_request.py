import os
import sys

from config.model_config import ModelConfig
from models.provider_factory import create_provider
from interface.chat import AIChatSession

def main():
    conf = ModelConfig.from_environment()
    provider = create_provider(conf)
    session = AIChatSession()
    session.add_user_message("Reply exactly: AI EDITOR CHAT WORKS")
    
    try:
        response = provider.send(session, include_script=False)
        print(response)
    except Exception as e:
        print("Error:", str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()
