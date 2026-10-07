import json
import urllib.request
import urllib.error
from typing import Dict, Any

class AECepError(RuntimeError):
    """Raised when an After Effects CEP Bridge operation fails."""

class AECepRunner:
    """Execute semantic commands securely via the CEP HTTP Bridge."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8090) -> None:
        self.endpoint = f"http://{host}:{port}/execute"

    def execute(self, action: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Send a validated semantic action to the After Effects CEP Bridge.
        """
        if parameters is None:
            parameters = {}

        payload = {
            "action": action,
            "parameters": parameters
        }
        
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(self.endpoint, data=data, headers={'Content-Type': 'application/json'}, method='POST')
        
        try:
            # 90 second timeout similar to the old subprocess timeout
            with urllib.request.urlopen(req, timeout=90) as response:
                response_data = response.read().decode('utf-8')
                result = json.loads(response_data)
                if not result.get("success"):
                    raise AECepError(f"AE Bridge returned error: {result.get('error', 'Unknown error')}")
                return result
        except urllib.error.URLError as e:
            raise AECepError(f"Failed to connect to AE Bridge at {self.endpoint}. Is the extension open? Error: {e}")
        except json.JSONDecodeError as e:
            raise AECepError(f"Invalid JSON response from AE Bridge: {e}")
        except Exception as e:
            raise AECepError(f"Unexpected error communicating with AE Bridge: {e}")
