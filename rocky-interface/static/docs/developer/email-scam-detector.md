# Email Scam Detector

## Overview

This example sends the contents of an email to the Rocky API and asks the model whether it appears to be a phishing attempt. The response can help explain warning signs, but it should not replace careful review of suspicious messages.

## Prerequisites

- Rocky API Key
- Python 3
- `requests` library

Install the library if needed:

```bash
pip install requests
```

## Example Email

> **Subject: Your Account Has Been Suspended**
>
> Dear Customer,
>
> We detected suspicious activity on your account. Please verify your information immediately by clicking the secure link below or your account will be permanently suspended.
>
> https://example-phishing-site.com
>
> Thank you,  
> Security Team

## Python Example

Set `ROCKY_API_KEY` in your environment before running the example. The script
discovers the active model, so it does not need a hard-coded model name. Do not
share or commit your key.

```python
import os
import requests

API_KEY = os.environ["ROCKY_API_KEY"]
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

models_response = requests.get(
    "https://rocky.cs.kent.edu/v1/models",
    headers=HEADERS,
    timeout=30,
)
models_response.raise_for_status()
MODEL = models_response.json()["data"][0]["id"]

EMAIL_TEXT = """Subject: Your Account Has Been Suspended

Dear Customer,

We detected suspicious activity on your account. Please verify your information
immediately by clicking the secure link below or your account will be permanently suspended.

https://example-phishing-site.com

Thank you,
Security Team"""

prompt = f"""Analyze this email for phishing. Explain the warning signs and say
whether it is likely phishing:\n\n{EMAIL_TEXT}"""

response = requests.post(
    "https://rocky.cs.kent.edu/v1/responses",
    headers=HEADERS,
    json={"model": MODEL, "input": prompt, "store": False},
    timeout=390,
)
response.raise_for_status()

print(response.json()["output_text"])
```

## Example Output

```text
This email is likely phishing. It creates urgency by threatening account suspension,
uses a generic greeting, and asks the recipient to click an unfamiliar link. Verify
the request through the organization’s official website instead of using the link.
```

## How It Works

1. The email text is sent to the API.
2. The LLM analyzes the content for phishing signals.
3. The model returns a classification and explanation.
4. The application prints the response.
