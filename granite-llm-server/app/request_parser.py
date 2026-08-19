import os
import math

from app.config import env_int
from app.image_input import validate_internal_image_block

# Default model for when no model is provided by the request/env
DEFAULT_MODEL_NAME = "gemma4:latest"
MAX_OUTPUT_TOKENS = env_int("ROCKY_MAX_OUTPUT_TOKENS", 2048, minimum=1)
MAX_IMAGES_PER_REQUEST = env_int(
    "ROCKY_MAX_IMAGES_PER_REQUEST", 4, minimum=1, maximum=16
)
MAX_IMAGE_BYTES = env_int(
    "ROCKY_MAX_IMAGE_BYTES", 4 * 1024 * 1024, minimum=1
)
MAX_IMAGE_TOTAL_BYTES = env_int(
    "ROCKY_MAX_IMAGE_TOTAL_BYTES", 6 * 1024 * 1024, minimum=1
)
MAX_IMAGE_PIXELS = env_int(
    "ROCKY_MAX_IMAGE_PIXELS", 20_000_000, minimum=1
)
MAX_IMAGE_TOTAL_PIXELS = env_int(
    "ROCKY_MAX_IMAGE_TOTAL_PIXELS", 40_000_000, minimum=1
)
if MAX_IMAGE_TOTAL_BYTES < MAX_IMAGE_BYTES:
    raise RuntimeError(
        "ROCKY_MAX_IMAGE_TOTAL_BYTES must be at least ROCKY_MAX_IMAGE_BYTES."
    )
if MAX_IMAGE_TOTAL_PIXELS < MAX_IMAGE_PIXELS:
    raise RuntimeError(
        "ROCKY_MAX_IMAGE_TOTAL_PIXELS must be at least ROCKY_MAX_IMAGE_PIXELS."
    )

ALLOWED_REASONING_EFFORTS = {
    "low",
    "medium",
    "high",
    "max",
}

# Reads the configured Ollama model from the environment so local dev and Granite can use different models without changing cod
def get_default_model():
    return os.getenv("OLLAMA_MODEL", DEFAULT_MODEL_NAME).strip() or DEFAULT_MODEL_NAME

def extract_model(payload):
    model = payload.get("model")
    if model:
        return model
    
    return get_default_model()


def extract_stream(payload):
    value = payload.get("stream", False)
    if type(value) is not bool:
        raise ValueError("stream must be of type bool.")
    return value

# Converts Rocky style input blocks into Ollama chat messages
def extract_messages(payload, *, allow_images=False):
    input_items = payload.get("input")

    if input_items is None:
        raise ValueError("Input field is missing.")
    if not isinstance(input_items, list) or not input_items:
        raise ValueError("Input field must be a non-empty list.")

    messages = []
    image_count = 0
    image_bytes = 0
    image_pixels = 0

    for message in input_items:
        if not isinstance(message, dict):
            raise ValueError("Each input message must be an object.")
        role = message.get("role", "user")
        if role not in {"user", "assistant", "system"}:
            raise ValueError("Input message role is not supported.")
        content_list = message.get("content")
        if not isinstance(content_list, list) or not content_list:
            raise ValueError("Input message content must be a non-empty list.")

        ordered_parts = []
        images = []
        text_after_image = False
        image_seen = False

        for block in content_list:
            if not isinstance(block, dict):
                raise ValueError("Each input content block must be an object.")
            block_type = block.get("type")
            if block_type in {"input_text", "output_text"}:
                if set(block) != {"type", "text"}:
                    raise ValueError("Text input blocks contain unsupported fields.")
                text = block.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("Text input blocks must contain text.")
                if image_seen:
                    text_after_image = True
                ordered_parts.append(("text", text))
                continue
            if block_type == "input_image":
                if not allow_images:
                    raise ValueError("Image input is not enabled.")
                if role != "user":
                    raise ValueError("Images are supported only in user messages.")
                if image_count >= MAX_IMAGES_PER_REQUEST:
                    raise ValueError("Too many input images were provided.")
                encoded, decoded_bytes, decoded_pixels = validate_internal_image_block(
                    block,
                    max_image_bytes=MAX_IMAGE_BYTES,
                    remaining_bytes=MAX_IMAGE_TOTAL_BYTES - image_bytes,
                    max_pixels=MAX_IMAGE_PIXELS,
                    remaining_pixels=MAX_IMAGE_TOTAL_PIXELS - image_pixels,
                )
                image_count += 1
                image_bytes += decoded_bytes
                image_pixels += decoded_pixels
                images.append(encoded)
                ordered_parts.append(("image", encoded))
                image_seen = True
                continue
            raise ValueError("Input content block type is not supported.")

        text_parts = [value for kind, value in ordered_parts if kind == "text"]
        combined_text = "\n".join(text_parts).strip()

        if text_after_image:
            message_fragments = []
            for kind, value in ordered_parts:
                if kind == "text":
                    if message_fragments and not message_fragments[-1].get("images"):
                        message_fragments[-1]["content"] = (
                            f'{message_fragments[-1]["content"]}\n{value}'
                        )
                    else:
                        message_fragments.append({"role": role, "content": value})
                elif message_fragments and message_fragments[-1].get("images"):
                    message_fragments[-1]["images"].append(value)
                else:
                    message_fragments.append({
                        "role": role,
                        "content": "",
                        "images": [value],
                    })
            messages.extend(message_fragments)
        elif combined_text or images:
            ollama_message = {
                "role": role,
                "content": combined_text,
            }
            if images:
                ollama_message["images"] = images
            messages.append(ollama_message)

    if not messages:
        raise ValueError("No usable input messages found.")

    return messages

# Extracts model generation settings from the Rocky request and maps them to Ollama-compatible option names.
def extract_generation_options(payload):
    options = {}

    if "max_output_tokens" in payload:
        mot_value = payload["max_output_tokens"]
        if type(mot_value) is int:
            if 1 <= mot_value <= MAX_OUTPUT_TOKENS:
                options["num_predict"] = mot_value
            else:
                raise ValueError(f"max_output_tokens is not within the approved range of 1-{MAX_OUTPUT_TOKENS}.")
        else: 
            raise ValueError("max_output_tokens must be of type int.")
        

    if "temperature" in payload:
        temp_value = payload["temperature"]
        if isinstance(temp_value, (int, float)) and not isinstance(temp_value, bool):
            if math.isfinite(temp_value):
                if 0 <= temp_value <= 2:
                    options["temperature"] = temp_value
                else:
                    raise ValueError("temperature is not within the approved range of 0-2.")
            else:
                raise ValueError("temperature must be a finite int or float.")
        else:
            raise ValueError("temperature must be of type int or float.")

    if "top_p" in payload:
        top_p_value = payload["top_p"]
        if isinstance(top_p_value, (int, float)) and not isinstance(top_p_value, bool):
            if math.isfinite(top_p_value):
                if 0 <= top_p_value <= 1:
                    options["top_p"] = top_p_value
                else:
                    raise ValueError("top_p is not within the approved range of 0-1.")
            else:
                raise ValueError("top_p must be a finite int or float.")
        else:
            raise ValueError("top_p must be of type int or float.")
        
    if "frequency_penalty" in payload:
        frequency_penalty_value = payload["frequency_penalty"]
        if isinstance(frequency_penalty_value, (int, float)) and not isinstance(frequency_penalty_value, bool):
            if math.isfinite(frequency_penalty_value):
                if -2 <= frequency_penalty_value <= 2:
                    options["frequency_penalty"] = frequency_penalty_value
                else:
                    raise ValueError("frequency_penalty must be within the range -2 to 2 inclusive.")
            else:
                raise ValueError("frequency_penalty must be a finite int or float.")
        else:
            raise ValueError("frequency_penalty must be of type int or float.")
        
    
    if "presence_penalty" in payload:
        presence_penalty_value = payload["presence_penalty"]
        if isinstance(presence_penalty_value, (int, float)) and not isinstance(presence_penalty_value, bool):
            if math.isfinite(presence_penalty_value):
                if -2 <= presence_penalty_value <= 2:
                    options["presence_penalty"] = presence_penalty_value
                else:
                    raise ValueError("presence_penalty must be within the range -2 to 2 inclusive.")
            else:
                raise ValueError("presence_penalty must be a finite int or float.")
        else:
            raise ValueError("presence_penalty must be of type int or float.")
        
    return options


def extract_reasoning(payload):
    if "reasoning" not in payload:
        return None
    
    reasoning = payload["reasoning"]

    if not isinstance(reasoning, dict):
        raise ValueError("reasoning must be of type dict.")
    
    if "effort" not in reasoning:
        raise ValueError("reasoning.effort is required.")
    
    effort = reasoning["effort"]

    if not isinstance(effort, str):
        raise ValueError("reasoning.effort must be of type str")
    
    if effort not in ALLOWED_REASONING_EFFORTS:
        raise ValueError("reasoning.effort must be 'low', 'medium', 'high', or 'max'.")
    
    if "summary" not in reasoning:
        raise ValueError("reasoning.summary is required.")
    
    summary = reasoning["summary"]

    if not isinstance(summary, str):
        raise ValueError("reasoning.summary must be of type str.")
    
    if summary != "detailed":
        raise ValueError("reasoning.summary must be 'detailed'.")
    
    return {
        "effort": effort,
        "summary": summary,
    }
