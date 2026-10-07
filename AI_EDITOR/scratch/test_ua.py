import urllib.request, ssl

url = "https://agentrouter.org/v1/chat/completions"
token = "sk-MsqKWZioisa0IvOC48qS1DqR4onGkJe1seTiWRU1fxp4sczQ"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def test_ua(ua):
    req = urllib.request.Request(url, method="POST")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("User-Agent", ua)
    req.add_header("Content-Type", "application/json")
    req.data = b"{\"model\": \"gpt-5.6-sol\", \"messages\": [{\"role\": \"user\", \"content\": \"hi\"}], \"max_tokens\": 10}"
    try:
        resp = urllib.request.urlopen(req, context=ctx, timeout=5)
        print("SUCCESS", ua)
    except urllib.error.HTTPError as e:
        print("FAIL", ua, e.code, e.read().decode()[:100])
    except Exception as e:
        print("ERROR", ua, str(e))

test_ua("AI_EDITOR/1.0.0")
