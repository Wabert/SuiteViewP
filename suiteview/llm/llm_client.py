"""
LLM Client - Handles communication with VS Code Language Model API

This module provides a client for interacting with GitHub Copilot's language models
through the VS Code extension API. It sends workflow requests and handles responses
using a local server approach that communicates with VS Code.

The SuiteView AI Bridge VS Code extension runs a local HTTP server that exposes:
- /chat - Chat completions with streaming support
- /files/read - Read files from the workspace
- /files/write - Write files to the workspace
- /files/list - List files in a directory
- /terminal/execute - Execute terminal commands
- /workspace - Get workspace information
- /models - List available language models
"""

import logging
import json
import asyncio
import aiohttp
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, AsyncGenerator
from datetime import datetime
from enum import Enum
import os
import subprocess
import sys
import threading
import time

logger = logging.getLogger(__name__)


class MessageRole(Enum):
    """Role of a message in the conversation"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class ChatMessage:
    """Represents a single message in the chat history"""
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    attachments: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API calls"""
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "attachments": self.attachments
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatMessage':
        """Create from dictionary"""
        return cls(
            role=MessageRole(data["role"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now().isoformat())),
            attachments=data.get("attachments", [])
        )


@dataclass
class Conversation:
    """Represents a conversation with message history"""
    id: str
    title: str
    messages: List[ChatMessage] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    model: str = "gpt-4o"
    agent: Optional[str] = None  # Selected agent for this conversation
    
    def add_message(self, role: MessageRole, content: str, attachments: List[str] = None):
        """Add a message to the conversation"""
        message = ChatMessage(
            role=role,
            content=content,
            attachments=attachments or []
        )
        self.messages.append(message)
        self.updated_at = datetime.now()
        return message
    
    def get_messages_for_api(self) -> List[Dict[str, str]]:
        """Get messages formatted for the API"""
        return [
            {"role": msg.role.value, "content": msg.content}
            for msg in self.messages
        ]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for persistence"""
        return {
            "id": self.id,
            "title": self.title,
            "messages": [msg.to_dict() for msg in self.messages],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "model": self.model,
            "agent": self.agent
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Conversation':
        """Create from dictionary"""
        conv = cls(
            id=data["id"],
            title=data["title"],
            model=data.get("model", "gpt-4o"),
            agent=data.get("agent"),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            updated_at=datetime.fromisoformat(data.get("updated_at", datetime.now().isoformat()))
        )
        conv.messages = [ChatMessage.from_dict(m) for m in data.get("messages", [])]
        return conv


class VSCodeBridgeClient:
    """
    Client for interacting with VS Code through the SuiteView AI Bridge extension.
    
    This client communicates with a local HTTP server run by the VS Code extension,
    which provides access to:
    - Language Model API (GitHub Copilot)
    - File system operations
    - Terminal command execution
    - Workspace information
    """
    
    DEFAULT_PORT = 5678
    DEFAULT_HOST = "127.0.0.1"
    
    # Available models through GitHub Copilot
    AVAILABLE_MODELS = [
        "copilot",
        "gpt-4o",
        "gpt-4o-mini", 
        "claude-3.5-sonnet",
        "claude-3-opus",
        "o1-preview",
        "o1-mini"
    ]
    
    def __init__(self, host: str = None, port: int = None):
        """
        Initialize the VS Code Bridge client.
        
        Args:
            host: Host for the bridge server (default: 127.0.0.1)
            port: Port for the bridge server (default: 5678)
        """
        self.host = host or os.environ.get("VSCODE_BRIDGE_HOST", self.DEFAULT_HOST)
        self.port = port or int(os.environ.get("VSCODE_BRIDGE_PORT", self.DEFAULT_PORT))
        self.base_url = f"http://{self.host}:{self.port}"
        self.current_model = "copilot"
        self._session: Optional[aiohttp.ClientSession] = None
        self._connected = False
        
    @property
    def api_endpoint(self) -> str:
        """Chat endpoint URL"""
        return f"{self.base_url}/chat"
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=120, connect=5)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close(self):
        """Close the client session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def check_connection(self) -> bool:
        """Check if the VS Code bridge server is running"""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    self._connected = data.get("status") == "ok"
                    return self._connected
        except Exception as e:
            logger.debug(f"Bridge connection check failed: {e}")
            self._connected = False
        return False
    
    async def get_available_models(self) -> List[Dict[str, Any]]:
        """Get list of available language models from VS Code"""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/models") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("models", [])
        except Exception as e:
            logger.error(f"Failed to get models: {e}")
        return []
    
    def set_model(self, model: str):
        """Set the model to use for chat"""
        self.current_model = model
        logger.info(f"Model set to: {model}")
    
    async def send_message(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        stream: bool = True,
        on_token: Callable[[str], None] = None
    ) -> str:
        """
        Send a message to the LLM via VS Code bridge and get a response.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: Model to use (optional, uses current_model if not specified)
            stream: Whether to stream the response
            on_token: Callback function for streaming tokens
            
        Returns:
            The complete response text
        """
        model = model or self.current_model
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        try:
            session = await self._get_session()
            
            if stream and on_token:
                return await self._stream_response(session, payload, headers, on_token)
            else:
                return await self._get_response(session, payload, headers)
                
        except aiohttp.ClientConnectorError as e:
            logger.error(f"Cannot connect to VS Code bridge: {e}")
            raise ConnectionError(
                f"Cannot connect to VS Code AI Bridge at {self.base_url}. "
                "Make sure VS Code is running with the SuiteView AI Bridge extension active."
            )
        except aiohttp.ClientError as e:
            logger.error(f"API request failed: {e}")
            raise ConnectionError(f"Failed to connect to LLM API: {e}")
        except Exception as e:
            logger.error(f"Error sending message: {e}", exc_info=True)
            raise
    
    async def _get_response(
        self,
        session: aiohttp.ClientSession,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> str:
        """Get a non-streaming response"""
        async with session.post(
            self.api_endpoint,
            json=payload,
            headers=headers
        ) as response:
            if response.status == 401:
                raise ConnectionError(
                    "Not authenticated with GitHub Copilot. "
                    "Please sign in to VS Code with your GitHub account."
                )
            elif response.status == 503:
                raise ConnectionError(
                    "No language models available. "
                    "Make sure GitHub Copilot is enabled in VS Code."
                )
            response.raise_for_status()
            data = await response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    
    async def _stream_response(
        self,
        session: aiohttp.ClientSession,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        on_token: Callable[[str], None]
    ) -> str:
        """Stream the response and call on_token for each chunk"""
        full_response = ""
        
        async with session.post(
            self.api_endpoint,
            json=payload,
            headers=headers
        ) as response:
            if response.status == 401:
                raise ConnectionError(
                    "Not authenticated with GitHub Copilot. "
                    "Please sign in to VS Code with your GitHub account."
                )
            elif response.status == 503:
                raise ConnectionError(
                    "No language models available. "
                    "Make sure GitHub Copilot is enabled in VS Code."
                )
            response.raise_for_status()
            
            async for line in response.content:
                line = line.decode('utf-8').strip()
                
                if not line:
                    continue
                    
                if line.startswith("data: "):
                    data_str = line[6:]
                    
                    if data_str == "[DONE]":
                        break
                    
                    try:
                        data = json.loads(data_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        
                        if content:
                            full_response += content
                            if on_token:
                                on_token(content)
                                
                    except json.JSONDecodeError:
                        continue
        
        return full_response
    
    # ==================== File Operations ====================
    
    async def read_file(self, file_path: str) -> str:
        """
        Read a file from the workspace.
        
        Args:
            file_path: Path to the file (relative to workspace or absolute)
            
        Returns:
            The file contents
        """
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/files/read",
            json={"path": file_path}
        ) as response:
            if response.status == 404:
                raise FileNotFoundError(f"File not found: {file_path}")
            response.raise_for_status()
            data = await response.json()
            return data.get("content", "")
    
    async def write_file(self, file_path: str, content: str) -> bool:
        """
        Write content to a file.
        
        Args:
            file_path: Path to the file (relative to workspace or absolute)
            content: Content to write
            
        Returns:
            True if successful
        """
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/files/write",
            json={"path": file_path, "content": content}
        ) as response:
            response.raise_for_status()
            data = await response.json()
            return data.get("success", False)
    
    async def list_files(self, directory: str = None) -> List[Dict[str, Any]]:
        """
        List files in a directory.
        
        Args:
            directory: Directory path (optional, defaults to workspace root)
            
        Returns:
            List of file info dictionaries
        """
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/files/list",
            json={"path": directory} if directory else {}
        ) as response:
            response.raise_for_status()
            data = await response.json()
            return data.get("files", [])
    
    # ==================== Terminal Operations ====================
    
    async def execute_command(self, command: str, cwd: str = None) -> Dict[str, Any]:
        """
        Execute a terminal command.
        
        Args:
            command: Command to execute
            cwd: Working directory (optional)
            
        Returns:
            Dict with stdout, stderr, and exitCode
        """
        session = await self._get_session()
        payload = {"command": command}
        if cwd:
            payload["cwd"] = cwd
            
        async with session.post(
            f"{self.base_url}/terminal/execute",
            json=payload
        ) as response:
            response.raise_for_status()
            return await response.json()
    
    # ==================== Workspace Operations ====================
    
    async def get_workspace_info(self) -> Dict[str, Any]:
        """
        Get information about the VS Code workspace.
        
        Returns:
            Dict with workspace folders and file information
        """
        session = await self._get_session()
        async with session.get(f"{self.base_url}/workspace") as response:
            response.raise_for_status()
            return await response.json()
    
    # ==================== Agent Operations ====================
    
    async def agent_chat(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        request_id: str = None
    ) -> Dict[str, Any]:
        """
        Send a message to the agent mode which writes responses to a shared file.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: Model to use (optional)
            request_id: Optional request ID for tracking
            
        Returns:
            Dict with request_id, model, response, and response_file path
        """
        model = model or self.current_model
        
        payload = {
            "model": model,
            "messages": messages,
        }
        if request_id:
            payload["request_id"] = request_id
        
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/agent/chat",
            json=payload
        ) as response:
            response.raise_for_status()
            return await response.json()
    
    async def get_agent_responses(
        self,
        after_timestamp: str = None,
        request_id: str = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Get agent responses from the shared file.
        
        Args:
            after_timestamp: Only get responses after this ISO timestamp
            request_id: Only get responses with this request ID
            limit: Maximum number of responses to return
            
        Returns:
            Dict with responses list, count, and file_path
        """
        params = []
        if after_timestamp:
            params.append(f"after={after_timestamp}")
        if request_id:
            params.append(f"request_id={request_id}")
        params.append(f"limit={limit}")
        
        url = f"{self.base_url}/agent/responses"
        if params:
            url += "?" + "&".join(params)
        
        session = await self._get_session()
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.json()
    
    def get_agent_responses_file(self) -> str:
        """
        Get the path to the agent responses file.
        
        Returns:
            Path to ~/.suiteview/agent_responses.jsonl
        """
        home_dir = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
        return os.path.join(home_dir, ".suiteview", "agent_responses.jsonl")
    
    def read_agent_responses_sync(
        self,
        after_timestamp: str = None,
        request_id: str = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Read agent responses directly from the file (synchronous).
        
        This can be used without HTTP, reading the file directly.
        
        Args:
            after_timestamp: Only get responses after this ISO timestamp
            request_id: Only get responses with this request ID
            limit: Maximum number of responses to return
            
        Returns:
            List of response dictionaries
        """
        file_path = self.get_agent_responses_file()
        
        if not os.path.exists(file_path):
            return []
        
        responses = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    
                    # Filter by timestamp
                    if after_timestamp and entry.get("timestamp", "") <= after_timestamp:
                        continue
                    
                    # Filter by request_id
                    if request_id and entry.get("request_id") != request_id:
                        continue
                    
                    responses.append(entry)
                except json.JSONDecodeError:
                    continue
        
        # Return last N entries
        return responses[-limit:] if len(responses) > limit else responses


class GitHubDirectClient:
    """
    Direct client for GitHub Models API.
    
    This connects directly to GitHub's inference API without needing VS Code.
    Requires a GitHub Personal Access Token with appropriate permissions.
    
    Supports models like:
    - gpt-4o, gpt-4.1, gpt-5
    - Note: Claude/Gemini models are ONLY available via VS Code Bridge,
      not through GitHub Direct API
    """
    
    DEFAULT_BASE_URL = "https://models.github.ai/inference"
    
    # Available models on GitHub Models API
    # Note: GPT-5 has very strict rate limits (1 req/min on free tier)
    # Note: Claude/Gemini models are ONLY available via VS Code Bridge
    AVAILABLE_MODELS = [
        # GPT-5 (strict rate limits - 1 req/min)
        {"id": "gpt-5", "name": "GPT-5 (rate limited)", "vendor": "openai"},
        # GPT-4.x series (verified working)
        {"id": "gpt-4o", "name": "GPT-4o", "vendor": "openai"},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "vendor": "openai"},
        {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "vendor": "openai"},
        {"id": "gpt-4", "name": "GPT-4", "vendor": "openai"},
        # GPT-3.5
        {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "vendor": "openai"},
        # o1 reasoning models
        {"id": "o1-preview", "name": "o1 Preview", "vendor": "openai"},
        {"id": "o1-mini", "name": "o1 Mini", "vendor": "openai"},
    ]
    
    def __init__(self, token: str = None, base_url: str = None):
        """
        Initialize the GitHub Direct client.
        
        Args:
            token: GitHub Personal Access Token. If not provided, looks for
                   GITHUB_TOKEN environment variable.
            base_url: Base URL for the API (default: https://models.github.ai/inference)
        """
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.base_url = base_url or os.environ.get("GITHUB_MODELS_URL", self.DEFAULT_BASE_URL)
        self.current_model = "openai/gpt-4o"
        self._connected = False
        
        if not self.token:
            logger.warning("No GitHub token provided. Set GITHUB_TOKEN environment variable.")
    
    @property
    def api_endpoint(self) -> str:
        """Chat completions endpoint URL"""
        return f"{self.base_url}/chat/completions"
    
    def set_model(self, model: str):
        """Set the model to use for chat"""
        self.current_model = model
        logger.info(f"Model set to: {model}")
    
    async def check_connection(self) -> bool:
        """Check if we can connect to GitHub Models API"""
        if not self.token:
            self._connected = False
            return False
        
        try:
            import requests
            response = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=5
            )
            self._connected = response.status_code == 200
            return self._connected
        except Exception as e:
            logger.debug(f"GitHub API connection check failed: {e}")
            self._connected = False
            return False
    
    async def get_available_models(self) -> List[Dict[str, Any]]:
        """Get list of available models"""
        # Return our static list - GitHub doesn't have a simple models list endpoint
        return self.AVAILABLE_MODELS
    
    async def send_message(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        stream: bool = True,
        on_token: Callable[[str], None] = None
    ) -> str:
        """
        Send a message to GitHub Models API and get a response.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: Model to use (optional, uses current_model if not specified)
            stream: Whether to stream the response
            on_token: Callback function for streaming tokens
            
        Returns:
            The complete response text
        """
        import requests
        
        if not self.token:
            raise ConnectionError(
                "No GitHub token configured. Set GITHUB_TOKEN environment variable "
                "or pass token to GitHubDirectClient()."
            )
        
        model = model or self.current_model
        
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream
        }
        
        logger.info(f">>> GitHub Direct: model={model}, messages={len(messages)}, stream={stream}")
        
        try:
            if stream and on_token:
                return self._stream_response_sync(headers, payload, on_token)
            else:
                return self._get_response_sync(headers, payload)
                
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Cannot connect to GitHub Models API: {e}")
            raise ConnectionError(
                f"Cannot connect to GitHub Models API at {self.base_url}. "
                "Check your internet connection and GitHub token."
            )
        except Exception as e:
            logger.error(f"Error sending message: {e}", exc_info=True)
            raise
    
    def _get_response_sync(self, headers: Dict, payload: Dict) -> str:
        """Get a non-streaming response (synchronous)"""
        import requests
        
        payload["stream"] = False
        
        response = requests.post(
            self.api_endpoint,
            headers=headers,
            json=payload,
            timeout=120
        )
        
        if response.status_code == 401:
            raise ConnectionError(
                "GitHub token is invalid or expired. "
                "Please check your GITHUB_TOKEN."
            )
        elif response.status_code == 403:
            raise ConnectionError(
                "Access denied. Your GitHub token may not have access to GitHub Models. "
                "Make sure you have GitHub Copilot or Models access."
            )
        elif response.status_code == 404:
            raise ConnectionError(
                f"Model not found: {payload.get('model')}. "
                "Check the model name is correct."
            )
        
        response.raise_for_status()
        data = response.json()
        
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    
    def _stream_response_sync(
        self,
        headers: Dict,
        payload: Dict,
        on_token: Callable[[str], None]
    ) -> str:
        """Stream the response (synchronous using requests)"""
        import requests
        
        payload["stream"] = True
        full_response = ""
        
        response = requests.post(
            self.api_endpoint,
            headers=headers,
            json=payload,
            stream=True,
            timeout=120
        )
        
        response.encoding = 'utf-8'
        
        if response.status_code == 401:
            raise ConnectionError(
                "GitHub token is invalid or expired. "
                "Please check your GITHUB_TOKEN."
            )
        elif response.status_code == 403:
            raise ConnectionError(
                "Access denied. Your GitHub token may not have access to GitHub Models."
            )
        elif response.status_code == 404:
            raise ConnectionError(
                f"Model not found: {payload.get('model')}."
            )
        
        response.raise_for_status()
        
        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.strip():
                continue
            
            if line.startswith("data: "):
                data_str = line[6:]
                
                if data_str == "[DONE]":
                    break
                
                try:
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    
                    if content:
                        full_response += content
                        if on_token:
                            on_token(content)
                            
                except json.JSONDecodeError:
                    continue
        
        return full_response
    
    async def close(self):
        """Close the client (no-op for requests-based client)"""
        pass


# Alias for backward compatibility
LLMClient = VSCodeBridgeClient


class MockLLMClient(LLMClient):
    """
    Mock LLM client for testing and offline use.
    
    This provides a functional chatbot experience without requiring
    an actual API connection. Useful for UI development and testing.
    """
    
    def __init__(self):
        super().__init__()
        self.responses = {
            "hello": "Hello! I'm your SuiteView AI Assistant. How can I help you today?",
            "help": """I can help you with various tasks in SuiteView:

• **Database Queries**: Help you write and optimize SQL queries
• **Data Analysis**: Assist with analyzing your data sets
• **Email Management**: Help organize and search emails
• **File Navigation**: Guide you through file explorer features
• **Mainframe Operations**: Assist with mainframe terminal commands

Just ask me anything!""",
            "default": "I understand you're asking about: {query}. Let me help you with that.\n\nAs your SuiteView assistant, I can provide guidance on database operations, data management, and more. Could you provide more details about what you're trying to accomplish?"
        }
    
    async def send_message(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        stream: bool = True,
        on_token: Callable[[str], None] = None
    ) -> str:
        """Send a message and get a mock response"""
        # Get the last user message
        last_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_message = msg.get("content", "").lower()
                break
        
        # Determine response
        if "hello" in last_message or "hi" in last_message:
            response = self.responses["hello"]
        elif "help" in last_message:
            response = self.responses["help"]
        else:
            response = self.responses["default"].format(query=last_message[:100])
        
        # Simulate streaming
        if stream and on_token:
            # Simulate typing delay
            words = response.split(' ')
            for i, word in enumerate(words):
                await asyncio.sleep(0.05)  # 50ms delay between words
                token = word + (' ' if i < len(words) - 1 else '')
                on_token(token)
        
        return response


class ClientType(Enum):
    """Type of LLM client to use"""
    VSCODE_BRIDGE = "vscode_bridge"
    GITHUB_DIRECT = "github_direct"
    MOCK = "mock"


def get_llm_client(
    client_type: ClientType = None,
    use_mock: bool = False,
    github_token: str = None
):
    """
    Factory function to get an LLM client instance.
    
    Args:
        client_type: Type of client to create (ClientType enum)
        use_mock: If True, returns a mock client for testing (deprecated, use client_type)
        github_token: GitHub token for direct API access
        
    Returns:
        An LLM client instance (VSCodeBridgeClient, GitHubDirectClient, or MockLLMClient)
    """
    # Handle legacy use_mock parameter
    if use_mock:
        return MockLLMClient()
    
    # Determine client type
    if client_type is None:
        # Auto-detect: prefer GitHub Direct if token available, else VS Code Bridge
        if github_token or os.environ.get("GITHUB_TOKEN"):
            client_type = ClientType.GITHUB_DIRECT
        else:
            client_type = ClientType.VSCODE_BRIDGE
    
    if client_type == ClientType.MOCK:
        return MockLLMClient()
    elif client_type == ClientType.GITHUB_DIRECT:
        return GitHubDirectClient(token=github_token)
    else:
        return VSCodeBridgeClient()


class AgentResponseWatcher:
    """
    Watches the agent responses file for new responses.
    
    This allows a Python program to monitor responses from VS Code
    without needing to keep an HTTP connection open.
    
    Usage:
        def on_response(response):
            print(f"Got response: {response['response']}")
        
        watcher = AgentResponseWatcher(on_response=on_response)
        watcher.start()
        
        # Later...
        watcher.stop()
    """
    
    def __init__(
        self,
        on_response: Callable[[Dict[str, Any]], None] = None,
        poll_interval: float = 0.5
    ):
        """
        Initialize the response watcher.
        
        Args:
            on_response: Callback function called when a new response is found
            poll_interval: How often to check for new responses (seconds)
        """
        self.on_response = on_response
        self.poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_timestamp = datetime.now().isoformat()
        self._file_position = 0
        
        # Get file path
        home_dir = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
        self._file_path = os.path.join(home_dir, ".suiteview", "agent_responses.jsonl")
    
    def start(self):
        """Start watching for responses in a background thread."""
        if self._running:
            return
        
        self._running = True
        
        # Initialize file position if file exists
        if os.path.exists(self._file_path):
            self._file_position = os.path.getsize(self._file_path)
        
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        logger.info(f"Agent response watcher started, monitoring: {self._file_path}")
    
    def stop(self):
        """Stop watching for responses."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("Agent response watcher stopped")
    
    def _watch_loop(self):
        """Main watch loop running in background thread."""
        while self._running:
            try:
                self._check_for_new_responses()
            except Exception as e:
                logger.error(f"Error checking for responses: {e}")
            
            time.sleep(self.poll_interval)
    
    def _check_for_new_responses(self):
        """Check for new responses in the file."""
        if not os.path.exists(self._file_path):
            return
        
        current_size = os.path.getsize(self._file_path)
        
        # No new content
        if current_size <= self._file_position:
            return
        
        # Read new content
        with open(self._file_path, 'r', encoding='utf-8') as f:
            f.seek(self._file_position)
            new_content = f.read()
            self._file_position = f.tell()
        
        # Parse new lines
        for line in new_content.strip().split('\n'):
            if not line:
                continue
            
            try:
                response = json.loads(line)
                
                # Call the callback
                if self.on_response:
                    self.on_response(response)
                    
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse response line: {e}")
    
    def get_pending_responses(self, request_id: str = None) -> List[Dict[str, Any]]:
        """
        Get all pending responses (synchronous).
        
        Args:
            request_id: Only get responses with this request ID
            
        Returns:
            List of response dictionaries
        """
        if not os.path.exists(self._file_path):
            return []
        
        responses = []
        with open(self._file_path, 'r', encoding='utf-8') as f:
            f.seek(self._file_position)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    response = json.loads(line)
                    if request_id and response.get("request_id") != request_id:
                        continue
                    responses.append(response)
                except json.JSONDecodeError:
                    continue
        
        return responses
    
    @property
    def file_path(self) -> str:
        """Get the path to the responses file."""
        return self._file_path
