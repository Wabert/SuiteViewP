# SuiteView AI Assistant Guide

The SuiteView AI Assistant is an integrated LLM chatbot that provides intelligent assistance for your data management tasks.

## Features

- **Conversational AI**: Chat with various AI models including GPT-4, Claude, and more
- **Conversation History**: All your chats are saved and can be accessed later
- **Multiple Models**: Choose from different AI models based on your needs
- **File Attachments**: Attach files to provide context for your questions
- **Markdown Support**: Responses support markdown formatting

## Getting Started

### Opening the AI Assistant

1. **From the Launcher**: Click the 🤖 (robot) button on the SuiteView launcher toolbar
2. **From System Tray**: Right-click the SuiteView tray icon and select "🤖 AI Assistant"

### Interface Overview

The AI Assistant window has two main areas:

#### Left Sidebar
- **Conversations List**: Shows all your saved conversations
- **+ New Chat**: Creates a new conversation
- **Model Selector**: Choose which AI model to use

#### Main Chat Area
- **Chat Header**: Shows the current conversation title
- **Messages Area**: Displays the conversation history
- **Input Area**: Type your messages and attach files

## Using the Assistant

### Starting a New Conversation

1. Click the **"+ New Chat"** button in the sidebar
2. Type your message in the input box at the bottom
3. Press **Ctrl+Enter** or click **Send**

### Managing Conversations

- **Rename**: Right-click a conversation and select "Rename"
- **Delete**: Right-click a conversation and select "Delete"
- **Clear**: Click the "Clear" button to clear the current conversation

### Attaching Files

1. Click the 📎 button next to the input box
2. Select one or more files
3. Files will appear as chips above the input
4. Click ✕ on a chip to remove it

### Choosing a Model

Use the dropdown at the bottom of the sidebar to select your preferred model:

| Model | Best For |
|-------|----------|
| gpt-4o | General purpose, best quality |
| gpt-4o-mini | Faster responses, good quality |
| claude-3.5-sonnet | Creative writing, analysis |
| claude-3-opus | Complex reasoning |
| o1-preview | Advanced reasoning |
| o1-mini | Quick reasoning tasks |

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+Enter | Send message |

## API Configuration

The AI Assistant connects through VS Code's Language Model API. Make sure:

1. VS Code is running with GitHub Copilot enabled
2. Your GitHub account is connected
3. You have an active Copilot subscription

### Custom API Endpoint

For advanced users, you can configure a custom API endpoint:

1. Set the environment variable `LLM_API_ENDPOINT` to your API URL
2. Set `LLM_API_KEY` if authentication is required

Example:
```
set LLM_API_ENDPOINT=http://localhost:3000/api/chat
set LLM_API_KEY=your-api-key
```

## Data Storage

Conversations are stored locally at:
```
%USERPROFILE%\.suiteview\llm_chat\conversations.json
```

## Troubleshooting

### Connection Issues

If you see connection errors:
1. Ensure you have internet connectivity
2. Check that your API endpoint is correct
3. Verify your API key is valid

### Slow Responses

- Try switching to a faster model (gpt-4o-mini)
- Check your network connection
- Shorter prompts may get faster responses

### Missing Conversations

Conversations are auto-saved. If they're missing:
1. Check the storage location exists
2. Ensure you have write permissions
3. The file may be corrupted - rename it to start fresh

## Future Enhancements

- Context-aware assistance based on your current SuiteView activity
- Integration with database queries
- Code generation for SQL and data transformations
- Document analysis from attachments
