import requests
import os

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("ROCKY_OLLAMA_TIMEOUT_SECONDS", "180"))

def call_ollama_chat(model, messages, options=None, think=None):
    url = OLLAMA_BASE_URL + "/api/chat"

    ollama_payload = {
        "model": model,
        "messages": messages,
        "stream": False
    }

    if options:
        ollama_payload["options"] = options

    if think is not None:
        ollama_payload["think"] = think

    response = requests.post(url, json=ollama_payload, timeout=OLLAMA_TIMEOUT_SECONDS)

    response.raise_for_status()

    data = response.json()

    message = data["message"]

    content = message["content"]
    thinking_present = bool(message.get("thinking"))

    # Debug print for parameter testing
    #print("OLLAMA PAYLOAD:", ollama_payload)


    return {
        "content": content,
        "thinking_present": thinking_present,
    }

