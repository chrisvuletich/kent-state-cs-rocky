# Rocky Model Bridge

This is an internal Flask bridge between the Rocky chat API and Ollama. It is not a public student API and should bind to loopback or another private network interface.

Copy `.env.example` to `.env`, ensure Ollama is running with the configured `OLLAMA_MODEL`, and start it from this directory:

```sh
python -m app.main
```

The public chat service maps model `rocky` to the configured Ollama model before calling this bridge.
