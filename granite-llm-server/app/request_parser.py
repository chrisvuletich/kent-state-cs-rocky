import os
import math

# Default model for when no model is provided by the request/env
DEFAULT_MODEL_NAME = "gemma4:latest"
MAX_OUTPUT_TOKENS = 3500

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
        mot_value = payload["max_output_tokens"]
        if type(mot_value) is int:
            if mot_value >=1 and mot_value <=MAX_OUTPUT_TOKENS:
                options["num_predict"] = mot_value
            else:
                raise ValueError(f"max_output_tokens is not within the approved range of 1-{MAX_OUTPUT_TOKENS}.")
        else: 
            raise ValueError("max_output_tokens must be of type int.")
        

    if "temperature" in payload:
        temp_value = payload["temperature"]
        if isinstance(temp_value, (int, float)) and not isinstance(temp_value, bool):
            if math.isfinite(temp_value):
                if temp_value >= 0 and temp_value <=2:
                    options["temperature"] = temp_value
                else:
                    raise ValueError("temperature is not within the approved range of 0-2.")
            else:
                raise ValueError("temperature must be a finite int or float.")
        else:
            raise ValueError("temperature must be of type int or float")

    if "top_p" in payload:
        top_p_value = payload["top_p"]
        if isinstance(top_p_value, (int, float)) and not isinstance(top_p_value, bool):
            if math.isfinite(top_p_value):
                if top_p_value >= 0 and top_p_value <=1:
                    options["top_p"] = top_p_value
                else:
                    raise ValueError("top_p is not within the approved range of 0-1.")
            else:
                raise ValueError("top_p must be a finite int or float.")
        else:
            raise ValueError("top_p must be of type int or float")
        
    return options