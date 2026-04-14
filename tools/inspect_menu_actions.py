import json
import sys
import os
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

def main():
    base_url = "http://localhost:8080"
    
    print(f"Checking bridge status at {base_url}...")
    
    endpoints = ["/health", "/snapshot", "/actions"]
    
    for endpoint in endpoints:
        print(f"\n--- {endpoint} ---")
        try:
            req = Request(f"{base_url}{endpoint}")
            with urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                print(json.dumps(data, indent=2, ensure_ascii=False))
        except HTTPError as e:
            print(f"HTTP Error {e.code}: {e.reason}")
            try:
                print(e.read().decode("utf-8"))
            except:
                pass
        except URLError as e:
            print(f"URL Error: {e.reason}")
            print("Is the game and Bridge Mod running?")
        except Exception as e:
            print(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()
