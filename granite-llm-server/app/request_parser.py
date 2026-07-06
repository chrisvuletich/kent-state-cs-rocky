import os

# Default model for when no model is provided by the request/env
DEFAULT_MODEL_NAME = "gemma4:latest"

# Reads the configured Ollama model from the environment so local dev and Granite can use different models without changing cod
def get_default_model():
    return os.getenv("OLLAMA_MODEL", DEFAULT_MODEL_NAME)

def extract_model(payload):
    model = payload.get("model")
    if model:
        return model
    
    return get_default_model()

# Converts Rocky style input blocks into Ollama chat messages
def extract_messages(payload):
    input_items = payload.get("input")

    if input_items is None:
        raise ValueError(f"Input field is missing.")
    
    messages = []

    for message in input_items:
        combined_text = ""
        role = message.get("role", "user")
        content_list = message.get("content", [])

        text_parts = []

        for block in content_list:
            if block.get("type") == "input_text":
                text_parts.append(block.get("text", ""))
                
        combined_text = "\n".join(text_parts).strip()

        if combined_text:
            messages.append({
                "role": role,
                "content": combined_text
            })
            
    if not messages:
        raise ValueError("No usable input_text messages found.")
    
    return messages

# Extracts model generation settings from the Rocky request and maps them to Ollama-compatible option names.
def extract_generation_options(payload):
    options = {}

    if "max_output_tokens" in payload:
        options["num_predict"] = payload["max_output_tokens"]

    if "temperature" in payload:
        options["temperature"] = payload["temperature"]

    if "top_p" in payload:
        options["top_p"] = payload["top_p"]

    return options