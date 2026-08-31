# Image Input Example

When `GET /v1/models` advertises `supports_image_input: true`, Rocky can analyze
local JPEG, PNG, and static WebP images. The image is sent as a Base64 data URL
inside an `input_image` content block and Rocky returns text.

Rocky records submitted prompts, images, and responses for university safety
and academic-resource oversight. Use only course-appropriate material and do
not submit personal, confidential, regulated, or otherwise sensitive images.

## Python

```python
import base64
import os
from pathlib import Path
import requests

MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

image_path = Path("diagram.png")
media_type = MEDIA_TYPES.get(image_path.suffix.lower())
if media_type is None:
    raise ValueError("Use a JPEG, PNG, or static WebP image")

encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
image_url = f"data:{media_type};base64,{encoded}"

headers = {"Authorization": f"Bearer {os.environ['ROCKY_API_KEY']}"}
models_response = requests.get(
    "https://rocky.cs.kent.edu/v1/models",
    headers=headers,
    timeout=30,
)
models_response.raise_for_status()
model = models_response.json()["data"][0]
if model.get("metadata", {}).get("supports_image_input") is not True:
    raise RuntimeError("The active Rocky model does not support image input.")

response = requests.post(
    "https://rocky.cs.kent.edu/v1/responses",
    headers=headers,
    json={
        "model": model["id"],
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Explain this diagram."},
                    {
                        "type": "input_image",
                        "image_url": image_url,
                        "detail": "auto",
                    },
                ],
            }
        ],
        "store": False,
    },
    timeout=390,
)
response.raise_for_status()
print(response.json()["output_text"])
```

## JavaScript with Node.js

```javascript
import { readFile } from "node:fs/promises";
import { extname } from "node:path";

const mediaTypes = new Map([
	[".jpg", "image/jpeg"],
	[".jpeg", "image/jpeg"],
	[".png", "image/png"],
	[".webp", "image/webp"]
]);

const imagePath = "diagram.png";
const mediaType = mediaTypes.get(extname(imagePath).toLowerCase());
if (!mediaType) throw new Error("Use a JPEG, PNG, or static WebP image");

const encoded = (await readFile(imagePath)).toString("base64");
const imageUrl = `data:${mediaType};base64,${encoded}`;
const apiKey = process.env.ROCKY_API_KEY;
if (!apiKey) throw new Error("Set ROCKY_API_KEY before running this script.");

const modelsResponse = await fetch("https://rocky.cs.kent.edu/v1/models", {
	headers: { "Authorization": `Bearer ${apiKey}` }
});
if (!modelsResponse.ok) throw new Error(await modelsResponse.text());

const model = (await modelsResponse.json()).data?.[0];
if (!model) throw new Error("Rocky did not return an available model.");
if (model.metadata?.supports_image_input !== true) {
	throw new Error("The active Rocky model does not support image input.");
}

const response = await fetch("https://rocky.cs.kent.edu/v1/responses", {
	method: "POST",
	headers: {
		"Authorization": `Bearer ${apiKey}`,
		"Content-Type": "application/json"
	},
	body: JSON.stringify({
		model: model.id,
		input: [{
			role: "user",
			content: [
				{ type: "input_text", text: "Explain this diagram." },
				{ type: "input_image", image_url: imageUrl, detail: "auto" }
			]
		}],
		store: false
	})
});

if (!response.ok) throw new Error(await response.text());
console.log((await response.json()).output_text);
```

## Limits and rejected inputs

Read the active `max_images_per_request`, byte limits, and pixel limits from the
selected model's `metadata`. Base64 increases the HTTP body size, so check the
original file sizes before encoding and avoid keeping duplicate data URLs.

Rocky does not download remote image URLs and does not accept `file_id`, SVG,
GIF, animated WebP, audio, or video. Images are permitted only in user messages,
and the supported `detail` value is `auto`. A filename extension is not proof of
the real format; Rocky validates the decoded container and pixels on the server.

Set `"stream": true` on the same request to stream its text response when the
model advertises both `supports_image_input` and `supports_streaming`.
