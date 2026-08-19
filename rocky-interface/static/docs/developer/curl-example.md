# curl Example

Use curl to send a Rocky API request from a terminal.

## Before you begin

Read your course API key through a hidden prompt so it does not appear on screen
or in shell history. Keep it out of code and screenshots.

## Send a request

```bash
export ROCKY_MODEL='paste-the-id-returned-by-v1-models'
printf 'Rocky API key: '
IFS= read -r -s ROCKY_API_KEY
printf '\n'
export ROCKY_API_KEY

curl --request GET https://rocky.cs.kent.edu/v1/models \
  --header "Authorization: Bearer $ROCKY_API_KEY"

curl --request POST https://rocky.cs.kent.edu/v1/responses \
  --header "Authorization: Bearer $ROCKY_API_KEY" \
  --header 'Content-Type: application/json' \
  --data "{\"model\":\"$ROCKY_MODEL\",\"input\":\"Explain recursion in one paragraph.\",\"store\":false}"

unset ROCKY_API_KEY
```

`https://rocky.cs.kent.edu/v1/responses` is Rocky’s public Chat API endpoint.
Set `ROCKY_MODEL` to the identifier returned by the model-list request.

## Stream a response

If the selected model's metadata reports `supports_streaming: true`, use
curl's `--no-buffer` option and add `"stream":true`:

```bash
printf 'Rocky API key: '
IFS= read -r -s ROCKY_API_KEY
printf '\n'
export ROCKY_API_KEY

curl --no-buffer --request POST https://rocky.cs.kent.edu/v1/responses \
  --header "Authorization: Bearer $ROCKY_API_KEY" \
  --header 'Content-Type: application/json' \
  --header 'Accept: text/event-stream' \
  --data "{\"model\":\"$ROCKY_MODEL\",\"input\":\"Explain recursion in one paragraph.\",\"stream\":true,\"store\":false}"

unset ROCKY_API_KEY
```

The final success event is `response.completed`; Rocky does not send `[DONE]`.
See the [Streaming Example](/?frame=help&doc=streaming) before writing an
application parser.

## Example response

```json
{
  "object": "response",
  "status": "completed",
  "model": "model-id-from-v1-models",
  "output_text": "Recursion is a technique where a function solves a problem by calling itself with a smaller version of that problem."
}
```
