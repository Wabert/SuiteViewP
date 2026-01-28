# SuiteView AI Bridge

A VS Code extension that bridges the VS Code Language Model API to external applications via a local HTTP server.

## Features

- **Chat Completions**: Access GitHub Copilot and other VS Code language models
- **Streaming Support**: Real-time streaming responses
- **File Operations**: Read, write, and list files in your workspace
- **Terminal Execution**: Execute commands in your workspace
- **Workspace Info**: Get information about the current workspace

## Installation

### From Source

1. Install dependencies:
   ```bash
   cd vscode-extension/suiteview-ai-bridge
   npm install
   ```

2. Compile the extension:
   ```bash
   npm run compile
   ```

3. Install the extension in VS Code:
   - Open VS Code
   - Press F1 and type "Extensions: Install from VSIX..."
   - Or copy the folder to your VS Code extensions directory

### Package as VSIX (Optional)

```bash
npm install -g vsce
vsce package
```

## Usage

The extension automatically starts a local HTTP server on port 3000 when VS Code opens.

### Configuration

- `suiteviewAiBridge.port`: Port for the local HTTP server (default: 3000)
- `suiteviewAiBridge.autoStart`: Automatically start the server when VS Code opens (default: true)
- `suiteviewAiBridge.defaultModel`: Default language model to use

### Commands

- **SuiteView AI: Start Bridge Server** - Start the HTTP server
- **SuiteView AI: Stop Bridge Server** - Stop the HTTP server
- **SuiteView AI: Show Server Status** - Show the current server status

## API Endpoints

### Health Check
```
GET /health
Response: { "status": "ok", "version": "1.0.0" }
```

### List Models
```
GET /models
Response: { "models": [...] }
```

### Chat Completion
```
POST /chat
Body: {
  "messages": [
    { "role": "user", "content": "Hello!" }
  ],
  "model": "copilot",  // optional
  "stream": true       // optional, default true
}
```

### Read File
```
POST /files/read
Body: { "path": "relative/or/absolute/path.py" }
Response: { "content": "...", "path": "..." }
```

### Write File
```
POST /files/write
Body: { "path": "path/to/file.py", "content": "file content" }
Response: { "success": true, "path": "..." }
```

### List Files
```
POST /files/list
Body: { "path": "directory/path" }  // optional, defaults to workspace root
Response: { "files": [...], "path": "..." }
```

### Execute Terminal Command
```
POST /terminal/execute
Body: { "command": "python --version", "cwd": "..." }
Response: { "stdout": "...", "stderr": "...", "exitCode": 0 }
```

### Workspace Info
```
GET /workspace
Response: { "workspaceFolders": [...], "workspaceFile": "..." }
```

## OpenAI-Compatible API Endpoints

These endpoints follow the OpenAI API format for compatibility with tools like Clawdbot and other OpenAI-compatible clients.

### List Models (OpenAI Format)
```
GET /v1/models
Response: {
  "object": "list",
  "data": [
    {
      "id": "copilot-gpt-4",
      "object": "model",
      "created": 1706000000,
      "owned_by": "copilot",
      ...
    }
  ]
}
```

### Chat Completions (OpenAI Format)
```
POST /v1/chat/completions
Body: {
  "model": "copilot-gpt-4",      // optional
  "messages": [
    { "role": "system", "content": "You are a helpful assistant." },
    { "role": "user", "content": "Hello!" }
  ],
  "stream": false,               // optional, default false
  "temperature": 0.7,            // optional (passed but may not be honored)
  "max_tokens": 1000             // optional (passed but may not be honored)
}

Response (non-streaming): {
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1706000000,
  "model": "copilot-gpt-4",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Hello! How can I help you?"
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 8,
    "total_tokens": 18
  }
}

Response (streaming): Server-Sent Events (SSE)
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706000000,"model":"copilot-gpt-4","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706000000,"model":"copilot-gpt-4","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

### Using with Clawdbot or OpenAI-Compatible Clients

Configure your client with:
- **Base URL**: `http://127.0.0.1:3000/v1`
- **API Key**: Any value (not validated, but some clients require it)

Example with Python OpenAI client:
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:3000/v1",
    api_key="not-needed"  # Required by client but not validated
)

response = client.chat.completions.create(
    model="copilot-gpt-4",
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)
print(response.choices[0].message.content)
```

## Integration with SuiteView

The SuiteView Python application connects to this server automatically. Make sure:

1. VS Code is running with this extension active
2. You're signed in to GitHub with a Copilot subscription
3. The server is running (check status bar)

## Troubleshooting

### "No language models available"
- Make sure GitHub Copilot extension is installed and enabled
- Sign in to VS Code with your GitHub account
- Check that you have an active Copilot subscription

### "Port already in use"
- Change the port in settings: `suiteviewAiBridge.port`
- Or stop whatever is using port 3000

### Connection refused
- Make sure VS Code is running
- Check the status bar to see if the server is running
- Try restarting the server via Command Palette
