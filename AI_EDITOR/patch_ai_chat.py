import os
with open('interface/ai_chat.py', 'r') as f:
    code = f.read()

import_str = "import time\n"

code = import_str + code

new_generate_logic = """        try:
            response = None
            models_to_try = [
                self.model_name,
                "models/gemini-3.7-flash",
                "models/gemini-3.5-flash",
                "models/gemini-2.5-flash",
                "models/gemini-pro-latest",
                "models/gemini-flash-latest"
            ]
            last_err = None
            for model_to_try in models_to_try:
                try:
                    response = self.client.models.generate_content(
                        model=model_to_try,
                        contents=context,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            temperature=self.config.temperature,
                            max_output_tokens=self.config.max_tokens,
                            response_mime_type="application/json",
                        )
                    )
                    if response:
                        print(f"Successfully generated using {model_to_try}")
                        break
                except Exception as e:
                    last_err = e
                    print(f"Failed with {model_to_try}: {e}")
                    time.sleep(2)
            
            if not response:
                raise last_err
        except Exception as exc:
            raise AIChatProviderError(
                f"AI provider request failed: {exc}"
            ) from exc"""

import re
code = re.sub(r'        try:\n            response = self\.client\.models\.generate_content\([\s\S]*?            \) from exc', new_generate_logic, code)

with open('interface/ai_chat.py', 'w') as f:
    f.write(code)
