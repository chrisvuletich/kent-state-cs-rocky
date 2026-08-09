# curl Example

Use curl to send a Rocky API request from a terminal.

## Before you begin

Replace the environment-variable value with your own course API key. Keep the key out of shared shell history, code, and screenshots.

## Send a request

```bash
export ROCKY_API_KEY='replace-with-your-course-api-key'
export ROCKY_MODEL='paste-the-id-returned-by-v1-models'

curl --request GET https://rocky.cs.kent.edu/v1/models \
  --header "Authorization: Bearer $ROCKY_API_KEY"

curl --request POST https://rocky.cs.kent.edu/v1/responses \
  --header "Authorization: Bearer $ROCKY_API_KEY" \
  --header 'Content-Type: application/json' \
  --data "{\"model\":\"$ROCKY_MODEL\",\"input\":\"Explain recursion in one paragraph.\",\"store\":false}"
```

`https://rocky.cs.kent.edu/v1/responses` is Rocky’s public Chat API endpoint.
Set `ROCKY_MODEL` to the identifier returned by the model-list request.

## Example response

```json
{
  "object": "response",
  "status": "completed",
  "model": "model-id-from-v1-models",
  "output_text": "Recursion is a technique where a function solves a problem by calling itself with a smaller version of that problem."
}
```
