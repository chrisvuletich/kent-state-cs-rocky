# curl Example

Use curl to send a Rocky API request from a terminal.

## Before you begin

Read your course API key through a hidden prompt so it does not appear on screen
or in shell history. Keep it out of code and screenshots.

## Send a request

```bash
printf 'Rocky API key: '
IFS= read -r -s ROCKY_API_KEY
printf '\n'
export ROCKY_API_KEY

curl --request GET https://rocky.cs.kent.edu/v1/models \
  --header "Authorization: Bearer $ROCKY_API_KEY"

printf 'Copy data[0].id from above and enter it here: '
IFS= read -r ROCKY_MODEL
export ROCKY_MODEL

curl --request POST https://rocky.cs.kent.edu/v1/responses \
  --header "Authorization: Bearer $ROCKY_API_KEY" \
  --header 'Content-Type: application/json' \
  --data "{\"model\":\"$ROCKY_MODEL\",\"input\":\"Explain recursion in one paragraph.\",\"store\":false}"

unset ROCKY_API_KEY
unset ROCKY_MODEL
```

`https://rocky.cs.kent.edu/v1/responses` is Rocky’s public Responses API endpoint.
`ROCKY_MODEL` must contain the exact identifier returned by the model-list
request. Do not enter `rocky`; that is the service name, not a model name.

Check the returned JSON's `status` as well as HTTP status. `incomplete` with
reason `max_output_tokens` means the answer is partial or empty. These examples
omit `max_output_tokens` to use the server default; thinking and visible output
share that allowance.

## Stream a response

If the selected model's metadata reports `supports_streaming: true`, use
curl's `--no-buffer` option and add `"stream":true`:

```bash
printf 'Rocky API key: '
IFS= read -r -s ROCKY_API_KEY
printf '\n'
export ROCKY_API_KEY

curl --request GET https://rocky.cs.kent.edu/v1/models \
  --header "Authorization: Bearer $ROCKY_API_KEY"

printf 'Copy data[0].id from above and enter it here: '
IFS= read -r ROCKY_MODEL
export ROCKY_MODEL

curl --no-buffer --request POST https://rocky.cs.kent.edu/v1/responses \
  --header "Authorization: Bearer $ROCKY_API_KEY" \
  --header 'Content-Type: application/json' \
  --header 'Accept: text/event-stream' \
  --data "{\"model\":\"$ROCKY_MODEL\",\"input\":\"Explain recursion in one paragraph.\",\"stream\":true,\"store\":false}"

unset ROCKY_API_KEY
unset ROCKY_MODEL
```

The final success event is `response.completed`; Rocky does not send `[DONE]`.
If the generation allowance runs out, the final event is `response.incomplete`
with `incomplete_details.reason: "max_output_tokens"`. Any text received is partial.
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
