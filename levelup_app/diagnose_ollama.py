import httpx
import asyncio
import os

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")

async def check_ollama():
    print(f"Checking Ollama at {OLLAMA_URL}...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            if resp.status_code == 200:
                print("Ollama is reachable!")
                models = resp.json().get("models", [])
                print(f"Available models: {[m['name'] for m in models]}")
                if not any(m['name'].startswith('llava') for m in models):
                    print("WARNING: 'llava' model not found in Ollama!")
            else:
                print(f"Ollama returned status code {resp.status_code}")
    except Exception as e:
        print(f"Failed to connect to Ollama: {e}")

if __name__ == "__main__":
    asyncio.run(check_ollama())
