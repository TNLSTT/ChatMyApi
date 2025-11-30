# ChatMyAPI

ChatMyAPI is a local-first playground that lets you speak to popular REST APIs using natural language. A FastAPI backend asks a local Ollama model to translate your text into a concrete API request, runs it, and returns a clean summary plus raw JSON.

## Features
- FastAPI backend with CORS, validation, and error handling
- Ollama integration to translate prompts into REST calls
- Preconfigured APIs: OpenWeatherMap, Reddit, TMDB
- API keys stored locally with symmetric encryption (Fernet)
- Simple single-page frontend with chat-style UI and raw JSON toggle

## Requirements
- Python 3.10+
- [Ollama](https://ollama.com/download) running locally
- API keys for the services you want to call (place them in the UI)

## Installation
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the stack
1. Start Ollama locally and pull a model (any chat-capable model works):
   ```bash
   ollama pull llama3
   ```
2. Launch the backend:
   ```bash
   uvicorn backend.main:app --reload
   ```
3. Serve the frontend (any static server works). For example:
   ```bash
   python -m http.server 8000 --directory frontend
   ```
4. Open http://localhost:8000 in your browser. The frontend talks to the backend at `http://localhost:8000` by default; if you host the backend elsewhere, adjust fetch URLs accordingly or use a proxy.

## API keys and encryption
- Keys are stored in `backend/keys.json.enc` using Fernet symmetric encryption.
- By default a random key is generated and stored at `backend/.fernet.key`. To use your own secret (e.g., in production), set `CHATMYAPI_SECRET` to a strong passphrase before starting the app.

## Adding new APIs
1. Create a new JSON file under `backend/api_definitions/` following the existing examples. Fields:
   ```json
   {
     "name": "ServiceName",
     "base_url": "https://api.example.com/v1",
     "auth_type": "header | query | oauth2 | none",
     "auth_key_name": "api_key",
     "example_endpoints": [
       { "name": "List Things", "path": "/things", "method": "GET", "description": "List all things" }
     ]
   }
   ```
2. Restart the backend; endpoints are loaded on startup.
3. The Ollama prompt will include the new API and its endpoints automatically.

## Environment variables
- `OLLAMA_URL` (default `http://localhost:11434/api/generate`)
- `OLLAMA_MODEL` (default `llama3`)
- `CHATMYAPI_SECRET` (optional, overrides Fernet key generation)

## Project structure
```
backend/
  main.py                # FastAPI app
  ollama_client.py       # Talk to Ollama
  api_call_executor.py   # Run HTTP requests
  key_storage.py         # Encrypt/decrypt stored keys
  prompts.py             # Prompt templates for LLM
  models.py              # Pydantic schemas
  api_definitions/       # JSON API descriptors
frontend/
  index.html
  app.js
  styles.css
```

## Notes
- The backend validates the JSON returned by Ollama and only executes allowed endpoints/methods defined in each API descriptor.
- Error responses are bubbled up with helpful messages so the chat shows failures gracefully.
