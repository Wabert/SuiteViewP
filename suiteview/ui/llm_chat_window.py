"""
LLM Chat Window - AI Chatbot Interface for SuiteView

Provides a modern chat interface similar to ChatGPT/Claude with:
- Message input with multi-line support
- Chat history display with markdown rendering
- File/attachment support
- Conversation management
- Model selection
"""

import logging
import asyncio
import uuid
import sys
from pathlib import Path
from typing import Optional, List
from datetime import datetime
import json

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QScrollArea, QFrame, QSplitter, QListWidget,
    QListWidgetItem, QComboBox, QFileDialog, QMessageBox,
    QSizePolicy, QApplication, QMenu, QToolButton, QLineEdit,
    QTextBrowser, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer, QSize
from PyQt6.QtGui import QFont, QTextCursor, QIcon, QAction, QColor, QPalette

from suiteview.core.llm_client import (
    LLMClient, MockLLMClient, Conversation, ChatMessage, 
    MessageRole, get_llm_client, VSCodeBridgeClient,
    AgentResponseWatcher, GitHubDirectClient, ClientType
)

logger = logging.getLogger(__name__)


class ConnectionCheckWorker(QThread):
    """Worker thread to check VS Code bridge connection"""
    
    connection_result = pyqtSignal(bool, str)  # connected, message
    
    def __init__(self, client: VSCodeBridgeClient):
        super().__init__()
        self.client = client
    
    def run(self):
        """Check connection in background"""
        try:
            # Use synchronous requests instead of async
            import requests
            response = requests.get(f"{self.client.base_url}/health", timeout=2)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "ok":
                    self.connection_result.emit(True, "Connected to VS Code AI Bridge")
                else:
                    self.connection_result.emit(False, "VS Code AI Bridge not responding correctly")
            else:
                self.connection_result.emit(False, 
                    "VS Code AI Bridge not running. Start VS Code with the SuiteView AI Bridge extension.")
        except Exception as e:
            self.connection_result.emit(False, f"Cannot connect to VS Code bridge: {str(e)}")


class ModelsWorker(QThread):
    """Worker thread to fetch available models from VS Code"""
    
    models_fetched = pyqtSignal(list)  # list of model dictionaries
    
    def __init__(self, client: VSCodeBridgeClient):
        super().__init__()
        self.client = client
    
    def run(self):
        """Fetch models in background"""
        try:
            import requests
            response = requests.get(f"{self.client.base_url}/models", timeout=5)
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                self.models_fetched.emit(models)
            else:
                self.models_fetched.emit([])
        except Exception as e:
            logger.error(f"Failed to fetch models: {e}")
            self.models_fetched.emit([])


class GitHubDirectWorker(QThread):
    """Worker thread for GitHub Direct API operations"""
    
    token_received = pyqtSignal(str)
    response_complete = pyqtSignal(str, str, float)  # response, model_id, duration_seconds
    error_occurred = pyqtSignal(str)
    
    def __init__(self, client: GitHubDirectClient, messages: List[dict], model: str = None):
        super().__init__()
        self.client = client
        self.messages = messages
        self.model = model
        self._is_cancelled = False
        self.start_time = None
    
    def cancel(self):
        """Cancel the current operation"""
        self._is_cancelled = True
    
    def run(self):
        """Run the GitHub Direct API call"""
        try:
            import requests
            import time
            
            self.start_time = time.time()
            model_to_use = self.model or self.client.current_model
            logger.info(f">>> GitHub Direct: model={model_to_use}, messages={len(self.messages)}")
            
            headers = {
                "Authorization": f"Bearer {self.client.token}",
                "Content-Type": "application/json",
            }
            
            payload = {
                "model": model_to_use,
                "messages": self.messages,
                "stream": True
            }
            
            response = requests.post(
                self.client.api_endpoint,
                headers=headers,
                json=payload,
                stream=True,
                timeout=120
            )
            
            response.encoding = 'utf-8'
            
            if response.status_code == 401:
                self.error_occurred.emit(
                    "GitHub token is invalid or expired. Check your GITHUB_TOKEN."
                )
                return
            elif response.status_code == 403:
                self.error_occurred.emit(
                    "Access denied. Your GitHub token may not have access to GitHub Models."
                )
                return
            elif response.status_code == 404:
                self.error_occurred.emit(
                    f"Model not found: {model_to_use}"
                )
                return
            elif response.status_code == 429:
                # Rate limited
                retry_after = response.headers.get('Retry-After', '60')
                rate_type = response.headers.get('x-ratelimit-type', 'unknown')
                self.error_occurred.emit(
                    f"Rate limited for '{model_to_use}'.\n\n"
                    f"Limit type: {rate_type}\n"
                    f"Wait {retry_after} seconds, or:\n\n"
                    f"• Switch to 'VS Code Bridge' API to use your Copilot Pro+ quota\n"
                    f"• GitHub Models API has separate rate limits from Copilot\n"
                    f"• Opt in to paid GitHub Models usage for higher limits"
                )
                return
            
            response.raise_for_status()
            
            full_response = ""
            
            for line in response.iter_lines(decode_unicode=True):
                if self._is_cancelled:
                    break
                    
                if not line or not line.strip():
                    continue
                
                if line.startswith("data: "):
                    data_str = line[6:]
                    
                    if data_str == "[DONE]":
                        break
                    
                    try:
                        import json
                        data = json.loads(data_str)
                        choices = data.get("choices", [])
                        if choices and len(choices) > 0:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            
                            if content:
                                full_response += content
                                if not self._is_cancelled:
                                    self.token_received.emit(content)
                    except json.JSONDecodeError:
                        continue
            
            if not self._is_cancelled:
                duration = time.time() - self.start_time if self.start_time else 0
                self.response_complete.emit(full_response, model_to_use, duration)
                
        except requests.exceptions.ConnectionError as e:
            if not self._is_cancelled:
                self.error_occurred.emit(
                    f"Cannot connect to GitHub Models API. Check your internet connection."
                )
        except Exception as e:
            if not self._is_cancelled:
                logger.error(f"Error in GitHub Direct worker: {e}", exc_info=True)
                self.error_occurred.emit(str(e))


class AsyncWorker(QThread):
    """Worker thread for async LLM operations"""
    
    token_received = pyqtSignal(str)
    response_complete = pyqtSignal(str, str, float)  # response, model_id, duration_seconds
    error_occurred = pyqtSignal(str)
    
    def __init__(self, client: LLMClient, messages: List[dict], model: str = None):
        super().__init__()
        self.client = client
        self.messages = messages
        self.model = model
        self._is_cancelled = False
        self.start_time = None
    
    def cancel(self):
        """Cancel the current operation"""
        self._is_cancelled = True
    
    def run(self):
        """Run the async operation in a thread - using requests for synchronous HTTP"""
        try:
            # Use synchronous requests instead of async
            import requests
            import time
            
            self.start_time = time.time()
            model_to_use = self.model or self.client.current_model
            logger.info(f">>> SENDING REQUEST: model={model_to_use}, messages={len(self.messages)}")
            
            payload = {
                "model": model_to_use,
                "messages": self.messages,
                "stream": True
            }
            
            headers = {"Content-Type": "application/json"}
            
            # Stream the response with proper encoding
            logger.info(f">>> Sending to: {self.client.api_endpoint}")
            response = requests.post(
                self.client.api_endpoint,
                json=payload,
                headers=headers,
                stream=True,
                timeout=120
            )
            
            # Set encoding explicitly
            response.encoding = 'utf-8'
            
            logger.info(f">>> Response status: {response.status_code}")
            
            if response.status_code == 401:
                self.error_occurred.emit(
                    "Not authenticated with GitHub Copilot. Please sign in to VS Code."
                )
                return
            elif response.status_code == 503:
                self.error_occurred.emit(
                    "No language models available. Make sure GitHub Copilot is enabled in VS Code."
                )
                return
            
            response.raise_for_status()
            
            full_response = ""
            line_count = 0
            
            # Process streaming response
            for line in response.iter_lines(decode_unicode=True):
                line_count += 1
                if self._is_cancelled:
                    break
                    
                if not line or not line.strip():
                    continue
                
                logger.debug(f">>> Line {line_count}: {line[:100]}...")
                
                if line.startswith("data: "):
                    data_str = line[6:]
                    
                    if data_str == "[DONE]":
                        logger.info(f">>> Stream complete, total lines: {line_count}")
                        break
                    
                    try:
                        import json
                        data = json.loads(data_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        
                        if content:
                            full_response += content
                            if not self._is_cancelled:
                                self.token_received.emit(content)
                    except json.JSONDecodeError as e:
                        logger.warning(f">>> JSON decode error: {e}, line: {data_str[:50]}")
                        continue
            
            logger.info(f">>> Final response length: {len(full_response)}")
            
            if not self._is_cancelled:
                duration = time.time() - self.start_time if self.start_time else 0
                self.response_complete.emit(full_response, model_to_use, duration)
                
        except requests.exceptions.ConnectionError as e:
            if not self._is_cancelled:
                self.error_occurred.emit(
                    f"Cannot connect to VS Code AI Bridge at {self.client.base_url}. "
                    "Make sure VS Code is running with the SuiteView AI Bridge extension active."
                )
        except Exception as e:
            if not self._is_cancelled:
                logger.error(f"Error in LLM worker: {e}", exc_info=True)
                self.error_occurred.emit(str(e))
    
    def _on_token(self, token: str):
        """Handle received token"""
        if not self._is_cancelled:
            self.token_received.emit(token)


class AgentChatWorker(QThread):
    """Worker thread for agent mode LLM operations (writes to shared file)"""
    
    response_complete = pyqtSignal(dict)  # Full response dict from agent
    error_occurred = pyqtSignal(str)
    
    def __init__(self, client: LLMClient, messages: List[dict], model: str = None):
        super().__init__()
        self.client = client
        self.messages = messages
        self.model = model
        self._is_cancelled = False
        self.start_time = None
    
    def cancel(self):
        """Cancel the current operation"""
        self._is_cancelled = True
    
    def run(self):
        """Run the agent chat operation in a thread - non-streaming, writes to file"""
        try:
            import requests
            import uuid
            import time
            
            self.start_time = time.time()
            model_to_use = self.model or self.client.current_model
            request_id = f"req_{uuid.uuid4().hex[:12]}"
            
            logger.info(f">>> AGENT REQUEST: id={request_id}, model={model_to_use}")
            
            payload = {
                "model": model_to_use,
                "messages": self.messages,
                "request_id": request_id
            }
            
            headers = {"Content-Type": "application/json"}
            
            response = requests.post(
                f"{self.client.base_url}/agent/chat",
                json=payload,
                headers=headers,
                timeout=300  # 5 min timeout for longer responses
            )
            
            if self._is_cancelled:
                return
            
            if response.status_code == 401:
                self.error_occurred.emit(
                    "Not authenticated with GitHub Copilot. Please sign in to VS Code."
                )
                return
            elif response.status_code == 503:
                self.error_occurred.emit(
                    "No language models available. Make sure GitHub Copilot is enabled in VS Code."
                )
                return
            
            response.raise_for_status()
            
            data = response.json()
            duration = time.time() - self.start_time if self.start_time else 0
            data['duration_seconds'] = duration
            data['model_id'] = model_to_use
            
            logger.info(f">>> AGENT RESPONSE: {len(data.get('response', ''))} chars, file: {data.get('response_file', 'N/A')}, duration: {duration:.1f}s")
            
            if not self._is_cancelled:
                self.response_complete.emit(data)
                
        except requests.exceptions.ConnectionError as e:
            if not self._is_cancelled:
                self.error_occurred.emit(
                    f"Cannot connect to VS Code AI Bridge at {self.client.base_url}. "
                    "Make sure VS Code is running with the SuiteView AI Bridge extension active."
                )
        except Exception as e:
            if not self._is_cancelled:
                logger.error(f"Error in Agent worker: {e}", exc_info=True)
                self.error_occurred.emit(str(e))


class MessageBubble(QFrame):
    """A single message bubble in the chat"""
    
    def __init__(self, message: ChatMessage, model_id: str = None, parent=None):
        super().__init__(parent)
        self.message = message
        self.model_id = model_id  # Model used for this response
        self.completion_time = None  # Will be set when response completes
        self.duration_seconds = None  # Will be set when response completes
        self.footer_label = None  # Reference to footer for updates
        self.init_ui()
    
    def init_ui(self):
        """Initialize the message bubble UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(1)
        
        # Determine if this is a user or assistant message
        is_user = self.message.role == MessageRole.USER
        
        # Header with role and timestamp on same line
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        
        # For assistant messages, show model name if available
        if is_user:
            role_text = "You"
        else:
            role_text = f"Assistant ({self.model_id})" if self.model_id else "Assistant"
        
        role_label = QLabel(role_text)
        role_label.setStyleSheet(f"""
            font-weight: bold;
            color: {'#2563EB' if is_user else '#D4AF37'};
            font-size: 10px;
        """)
        header_layout.addWidget(role_label)
        self.role_label = role_label  # Store reference for updates
        
        header_layout.addStretch()
        
        time_label = QLabel(self.message.timestamp.strftime("%H:%M"))
        time_label.setStyleSheet("color: #888; font-size: 9px;")
        header_layout.addWidget(time_label)
        
        layout.addLayout(header_layout)
        
        # Message content - use QLabel with text selection enabled
        content_label = QLabel()
        content_label.setWordWrap(True)
        content_label.setTextFormat(Qt.TextFormat.RichText)
        content_label.setOpenExternalLinks(True)
        content_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | 
            Qt.TextInteractionFlag.TextSelectableByKeyboard |
            Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        
        # Render content with basic markdown
        html_content = self._convert_markdown(self.message.content)
        content_label.setText(html_content)
        
        content_label.setStyleSheet(f"""
            QLabel {{
                background-color: {'#E8F0FF' if is_user else '#F5F5F5'};
                border-radius: 4px;
                padding: 4px 6px;
                color: #0A1E5E;
                font-size: 12px;
            }}
        """)
        
        # Store reference for updates
        self.content_label = content_label
        
        # Enable custom context menu for copy functionality
        content_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        content_label.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(content_label)
        
        # Attachments if any
        if self.message.attachments:
            attach_label = QLabel(f"📎 {len(self.message.attachments)}")
            attach_label.setStyleSheet("color: #666; font-size: 9px;")
            layout.addWidget(attach_label)
        
        # Footer for assistant messages (shows timing info when response completes)
        if not is_user:
            self.footer_label = QLabel()
            self.footer_label.setStyleSheet("color: #888; font-size: 9px;")
            self.footer_label.setVisible(False)  # Hidden until response completes
            layout.addWidget(self.footer_label)
        
        # Style the bubble - minimal margins
        self.setStyleSheet(f"""
            MessageBubble {{
                background-color: {'#FFFFFF' if is_user else '#FAFAFA'};
                border: 1px solid {'#2563EB' if is_user else '#D4AF37'};
                border-radius: 6px;
                margin: {'0 0 0 30px' if is_user else '0 30px 0 0'};
            }}
        """)
        
        # Set size policy to not expand unnecessarily
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    
    def _convert_markdown(self, text: str) -> str:
        """Convert markdown and LaTeX to HTML"""
        import re
        html = text
        
        # IMPORTANT: Process LaTeX BEFORE line breaks to preserve multi-line formulas
        
        # Display math: \[ ... \] (can span multiple lines)
        def replace_display_latex(match):
            formula = match.group(1)
            # Remove extra whitespace but preserve structure
            formula = re.sub(r'\s+', ' ', formula).strip()
            # Convert common LaTeX commands to Unicode/HTML
            formula = self._convert_latex_to_unicode(formula)
            return f'<div style="font-family:Cambria Math,Times New Roman;font-size:13px;margin:8px 0;padding:10px;background:#F0F8FF;border-left:3px solid #2563EB;color:#1E3A8A;text-align:center;">{formula}</div>'
        
        html = re.sub(r'\\\[(.*?)\\\]', replace_display_latex, html, flags=re.DOTALL)
        
        # Display math: $$ ... $$ (can span multiple lines)
        html = re.sub(r'\$\$(.*?)\$\$', replace_display_latex, html, flags=re.DOTALL)
        
        # Inline math: \( ... \) (single line)
        def replace_inline_latex(match):
            formula = match.group(1).strip()
            # Convert LaTeX to Unicode/HTML
            formula = self._convert_latex_to_unicode(formula)
            return f'<span style="font-family:Cambria Math,Times New Roman;color:#1E3A8A;">{formula}</span>'
        
        html = re.sub(r'\\\((.*?)\\\)', replace_inline_latex, html)
        
        # Inline math: $ ... $ (single line, but NOT $$)
        # Use negative lookahead/lookbehind to avoid matching $$
        html = re.sub(r'(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)', replace_inline_latex, html)
        
        # Code blocks: ```language\ncode\n``` (process before line breaks)
        html = re.sub(
            r'```(\w+)?\n(.*?)```',
            r'<pre style="background:#2D2D2D;color:#F8F8F2;padding:8px;border-radius:4px;overflow-x:auto;font-family:Consolas,Monaco,monospace;font-size:11px;margin:4px 0;">\2</pre>',
            html,
            flags=re.DOTALL
        )
        
        # Headers (process before line breaks)
        html = re.sub(r'^### (.+)$', r'<h3 style="color:#1E3A8A;margin:8px 0 2px 0;font-weight:bold;font-size:14px;">\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2 style="color:#1E3A8A;margin:10px 0 4px 0;font-weight:bold;font-size:16px;">\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1 style="color:#1E3A8A;margin:12px 0 4px 0;font-weight:bold;font-size:18px;">\1</h1>', html, flags=re.MULTILINE)
        
        # Horizontal rules
        html = re.sub(r'^---+$', '<hr style="border:none;border-top:1px solid #D4AF37;margin:6px 0;">', html, flags=re.MULTILINE)
        
        # Bold: **text** -> <b>text</b>
        html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)
        
        # Italic: *text* -> <i>text</i> (but not **)
        html = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', html)
        
        # Inline code: `code` -> <code>code</code>
        html = re.sub(r'`(.+?)`', r'<code style="background:#e0e0e0;padding:1px 3px;border-radius:2px;font-family:Consolas,Monaco,monospace;font-size:11px;">\1</code>', html)
        
        # Numbered lists (e.g., "1. ", "2. ")
        html = re.sub(r'^(\d+)\.\s+(.+)$', r'<div style="margin:2px 0 2px 20px;"><b>\1.</b> \2</div>', html, flags=re.MULTILINE)
        
        # Bullet lists (must come after numbered lists)
        html = re.sub(r'^-\s+(.+)$', r'<div style="margin:2px 0 2px 20px;">• \1</div>', html, flags=re.MULTILINE)
        
        # Reduce multiple consecutive line breaks to single breaks
        html = re.sub(r'\n\n+', '\n\n', html)
        
        # Line breaks (do this LAST to avoid breaking LaTeX formulas)
        # Single newline -> <br>, double newline -> paragraph break
        html = re.sub(r'\n\n', '<div style="margin:6px 0;"></div>', html)
        html = html.replace('\n', '<br>')
        
        return html
    
    def _convert_latex_to_unicode(self, latex: str) -> str:
        """Convert LaTeX commands to Unicode symbols and HTML"""
        import re
        
        # Remove \text{} wrappers but keep content
        latex = re.sub(r'\\text\{([^}]+)\}', r'\1', latex)
        
        # Convert subscripts: _t or _{text}
        latex = re.sub(r'_\{([^}]+)\}', r'<sub>\1</sub>', latex)
        latex = re.sub(r'_(\w)', r'<sub>\1</sub>', latex)
        
        # Convert superscripts: ^t or ^{text}
        latex = re.sub(r'\^\{([^}]+)\}', r'<sup>\1</sup>', latex)
        latex = re.sub(r'\^(\w)', r'<sup>\1</sup>', latex)
        
        # Convert fractions: \frac{num}{den}
        latex = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1)/(\2)', latex)
        
        # Greek letters (common ones)
        greek_map = {
            r'\\alpha': 'α', r'\\beta': 'β', r'\\gamma': 'γ', r'\\delta': 'δ',
            r'\\epsilon': 'ε', r'\\theta': 'θ', r'\\lambda': 'λ', r'\\mu': 'μ',
            r'\\pi': 'π', r'\\sigma': 'σ', r'\\tau': 'τ', r'\\phi': 'φ',
            r'\\omega': 'ω', r'\\Delta': 'Δ', r'\\Sigma': 'Σ', r'\\Pi': 'Π'
        }
        for latex_cmd, unicode_char in greek_map.items():
            latex = latex.replace(latex_cmd, unicode_char)
        
        # Math operators
        operators = {
            r'\\cdot': '·',
            r'\\times': '×',
            r'\\div': '÷',
            r'\\sum': '∑',
            r'\\prod': '∏',
            r'\\int': '∫',
            r'\\approx': '≈',
            r'\\neq': '≠',
            r'\\leq': '≤',
            r'\\geq': '≥',
            r'\\pm': '±',
            r'\\infty': '∞',
            r'\\partial': '∂',
            r'\\nabla': '∇'
        }
        for latex_cmd, unicode_char in operators.items():
            latex = latex.replace(latex_cmd, unicode_char)
        
        # Remove remaining backslashes from unknown commands
        latex = re.sub(r'\\(\w+)', r'\1', latex)
        
        return latex
    
    def _show_context_menu(self, position):
        """Show context menu for message bubble"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #FFFFFF;
                color: #0A1E5E;
                border: 2px solid #2563EB;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                background-color: transparent;
                padding: 4px 16px;
                border-radius: 2px;
            }
            QMenu::item:selected {
                background-color: #E8F0FF;
                color: #2563EB;
            }
        """)
        
        copy_action = menu.addAction("📋 Copy Text")
        copy_all_action = menu.addAction("📋 Copy All")
        
        action = menu.exec(self.content_label.mapToGlobal(position))
        
        if action == copy_action:
            # Copy selected text or all if nothing selected
            selected_text = self.content_label.selectedText()
            if selected_text:
                QApplication.clipboard().setText(selected_text)
            else:
                QApplication.clipboard().setText(self.message.content)
        elif action == copy_all_action:
            QApplication.clipboard().setText(self.message.content)
    
    def _render_markdown(self, text_browser, content: str):
        """Render markdown content as HTML"""
        try:
            import markdown
            html = markdown.markdown(content, extensions=['fenced_code', 'nl2br'])
            text_browser.setHtml(html)
        except ImportError:
            text_browser.setHtml(self._convert_markdown(content))
    
    def update_content(self, content: str):
        """Update the message content (for streaming)"""
        self.message.content = content
        html_content = self._convert_markdown(content)
        self.content_label.setText(html_content)
    
    def set_model_id(self, model_id: str):
        """Update the model ID displayed in header"""
        self.model_id = model_id
        if hasattr(self, 'role_label') and self.message.role != MessageRole.USER:
            self.role_label.setText(f"Assistant ({model_id})")
    
    def set_timing_info(self, model_id: str, duration_seconds: float):
        """Set the timing info in the footer"""
        self.model_id = model_id
        self.duration_seconds = duration_seconds
        self.completion_time = datetime.now()
        
        # Update header with model
        if hasattr(self, 'role_label') and self.message.role != MessageRole.USER:
            self.role_label.setText(f"Assistant ({model_id})")
        
        # Update footer with timing info
        if self.footer_label:
            time_str = self.completion_time.strftime("%Y-%m-%d %H:%M:%S")
            if duration_seconds >= 60:
                minutes = int(duration_seconds // 60)
                seconds = duration_seconds % 60
                duration_str = f"{minutes}m {seconds:.1f}s"
            else:
                duration_str = f"{duration_seconds:.1f}s"
            
            footer_text = f"✓ {model_id} | Completed: {time_str} | Duration: {duration_str}"
            self.footer_label.setText(footer_text)
            self.footer_label.setVisible(True)


class ConversationListItem(QListWidgetItem):
    """List item representing a conversation"""
    
    def __init__(self, conversation: Conversation):
        super().__init__()
        self.conversation = conversation
        self.setText(conversation.title)
        self.setToolTip(f"Created: {conversation.created_at.strftime('%Y-%m-%d %H:%M')}")


class LLMChatWindow(QWidget):
    """Main LLM Chat Window"""
    
    def __init__(self, parent=None, use_mock=False):
        super().__init__(parent)
        
        # Initialize LLM client
        # Set use_mock=False to use VS Code bridge, True for testing without VS Code
        self.use_mock = use_mock
        self.llm_client = get_llm_client(use_mock=use_mock)
        
        # Settings file for persistence
        self.settings_dir = Path.home() / '.suiteview' / 'llm_chat'
        self.settings_dir.mkdir(parents=True, exist_ok=True)
        
        # Connection state
        self._connected = False
        self._activated = False  # Has the user ever connected?
        self._connection_check_worker: Optional[ConnectionCheckWorker] = None
        self._models_worker: Optional[ModelsWorker] = None
        self._connection_retry_timer: Optional[QTimer] = None
        
        # Dedicated VS Code session tracking
        self._vscode_session_file = self.settings_dir / 'vscode_session.json'
        self._vscode_process_pid: Optional[int] = None
        self._hidden_vscode_hwnd: Optional[int] = None  # Store hidden window handle
        
        # Conversation management
        self.conversations: List[Conversation] = []
        self.current_conversation: Optional[Conversation] = None
        self.worker: Optional[QThread] = None  # Can be AsyncWorker or AgentChatWorker
        self._thread_counter = 1  # Counter for "New Thread X" naming
        self._pending_rename_conversation: Optional[Conversation] = None  # Track conversation pending auto-rename
        self._naming_worker: Optional[QThread] = None  # Worker for generating thread names
        
        # Attachments for current message
        self.pending_attachments: List[str] = []
        
        self.init_ui()
        self.load_conversations()
        
        # Start with a new conversation if none exist
        if not self.conversations:
            self.new_conversation()
        
        # Check connection to VS Code bridge (if not mock)
        if not use_mock:
            self._check_vscode_session()
    
    def _check_vscode_session(self):
        """Check if dedicated VS Code session exists and is running"""
        # First, check if we have a stored session
        session_exists = False
        
        if self._vscode_session_file.exists():
            try:
                with open(self._vscode_session_file, 'r') as f:
                    session_data = json.load(f)
                    self._vscode_process_pid = session_data.get('pid')
                    
                    # Check if the process is still running
                    if self._vscode_process_pid:
                        import psutil
                        try:
                            process = psutil.Process(self._vscode_process_pid)
                            # Verify it's actually a VS Code process
                            if 'code' in process.name().lower():
                                session_exists = True
                                logger.info(f"Found existing VS Code session (PID: {self._vscode_process_pid})")
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            # Process doesn't exist anymore
                            logger.info("Stored VS Code session no longer running")
                            self._vscode_process_pid = None
            except Exception as e:
                logger.warning(f"Error reading VS Code session file: {e}")
        
        if session_exists:
            # We have a session, check if the bridge is responding
            self._check_connection()
        else:
            # No session - show deactivated state
            logger.info("No dedicated VS Code session found - showing deactivated state")
            if hasattr(self, 'deactivated_overlay'):
                self.deactivated_overlay.setVisible(True)
    
    def _check_connection(self):
        """Check connection to VS Code bridge in background"""
        if isinstance(self.llm_client, VSCodeBridgeClient):
            self._connection_check_worker = ConnectionCheckWorker(self.llm_client)
            self._connection_check_worker.connection_result.connect(self._on_connection_result)
            self._connection_check_worker.start()
    
    def cleanup_vscode_session(self):
        """Clean up the dedicated VS Code session"""
        try:
            import psutil
            
            if self._vscode_process_pid:
                logger.info(f"Cleaning up VS Code session (PID: {self._vscode_process_pid})")
                
                try:
                    # Find and kill all VS Code processes from this session
                    for proc in psutil.process_iter(['pid', 'name']):
                        try:
                            if proc.info['name'] and 'code.exe' in proc.info['name'].lower():
                                # Check if this is our process or a child of it
                                if proc.info['pid'] == self._vscode_process_pid:
                                    proc.kill()
                                    logger.info(f"Killed VS Code process {proc.info['pid']}")
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                except Exception as e:
                    logger.error(f"Error killing VS Code processes: {e}")
                
                # Delete the session file
                if self._vscode_session_file.exists():
                    self._vscode_session_file.unlink()
                    logger.info("Deleted VS Code session file")
                
                self._vscode_process_pid = None
                
        except Exception as e:
            logger.error(f"Error cleaning up VS Code session: {e}", exc_info=True)
    
    def _on_connection_result(self, connected: bool, message: str):
        """Handle connection check result"""
        self._connected = connected
        
        if connected:
            self._activated = True
            # Hide deactivated overlay if visible
            if hasattr(self, 'deactivated_overlay') and self.deactivated_overlay:
                self.deactivated_overlay.setVisible(False)
            
            # Update status
            self.chat_title_label.setStyleSheet("""
                color: #FFD700;
                font-size: 18px;
                font-weight: bold;
            """)
            logger.info("Connected to VS Code AI Bridge")
            
            # Fetch available models
            if isinstance(self.llm_client, VSCodeBridgeClient):
                self._fetch_models()
        else:
            # Show connection warning
            self._show_connection_warning(message)
    
    def _fetch_models(self):
        """Fetch available models from VS Code"""
        if isinstance(self.llm_client, VSCodeBridgeClient):
            models_worker = ModelsWorker(self.llm_client)
            models_worker.models_fetched.connect(self._on_models_fetched)
            models_worker.start()
            # Keep reference so it doesn't get garbage collected
            self._models_worker = models_worker
    
    def _on_models_fetched(self, models: list):
        """Handle fetched models"""
        if models:
            # Clear existing models
            self.model_combo.clear()
            
            # Add fetched models to combo box
            for model in models:
                model_id = model.get("id", "")
                model_name = model.get("name", model_id)
                # Use a more friendly display name
                display_name = f"{model_name}" if model_name else model_id
                self.model_combo.addItem(display_name, model_id)
            
            # Select the first model (recommended)
            if self.model_combo.count() > 0:
                self.model_combo.setCurrentIndex(0)
                
            logger.info(f"Loaded {len(models)} models from VS Code")
        else:
            # Fallback to default models if fetch failed
            self.model_combo.clear()
            self.model_combo.addItems(["copilot", "gpt-4", "gpt-3.5-turbo"])
            logger.warning("Failed to fetch models, using defaults")
    
    def _show_connection_warning(self, message: str):
        """Show the deactivated state with friendly explanation"""
        # Show the deactivated overlay
        if hasattr(self, 'deactivated_overlay'):
            self.deactivated_overlay.setVisible(True)
        
        logger.info("VS Code AI Bridge not connected - showing deactivated state")
    
    def _create_deactivated_overlay(self):
        """Create the deactivated state overlay - shown until VS Code Bridge connects"""
        self.deactivated_overlay = QWidget(self)
        self.deactivated_overlay.setStyleSheet("""
            QWidget {
                background-color: rgba(10, 30, 94, 0.95);
            }
        """)
        
        overlay_layout = QVBoxLayout(self.deactivated_overlay)
        overlay_layout.setContentsMargins(40, 40, 40, 40)
        overlay_layout.setSpacing(20)
        
        overlay_layout.addStretch()
        
        # Big friendly robot/AI icon
        icon_label = QLabel("🤖💤")
        icon_label.setStyleSheet("font-size: 72px;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay_layout.addWidget(icon_label)
        
        # Title
        title = QLabel("AI Assistant is Snoozing")
        title.setStyleSheet("""
            color: #FFD700;
            font-size: 28px;
            font-weight: bold;
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay_layout.addWidget(title)
        
        # Friendly explanation
        explanation = QLabel(
            "This chatbot needs a dedicated VS Code session to work.\n\n"
            "Think of it like this: VS Code is the coffee machine ☕ that stays on\n"
            "in the break room. This chat window is your mug, and the AI models\n"
            "(Claude, GPT-4, Gemini, etc.) are the delicious caffeine.\n\n"
            "Click the button below to start a dedicated, minimized VS Code window\n"
            "that will run in the background. It stays out of your way and provides\n"
            "AI superpowers to SuiteView! 🚀\n\n"
            "The VS Code window will minimize automatically - just leave it running!"
        )
        explanation.setStyleSheet("""
            color: #E5E7EB;
            font-size: 14px;
            line-height: 1.5;
        """)
        explanation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        explanation.setWordWrap(True)
        overlay_layout.addWidget(explanation)
        
        overlay_layout.addSpacing(20)
        
        # Connect button
        connect_btn = QPushButton("☕  Start Dedicated VS Code Session")
        connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #D4AF37;
                color: #0A1E5E;
                border: none;
                border-radius: 8px;
                padding: 16px 32px;
                font-size: 16px;
                font-weight: bold;
                min-width: 280px;
            }
            QPushButton:hover {
                background-color: #FFD700;
            }
            QPushButton:pressed {
                background-color: #B8960C;
            }
        """)
        connect_btn.clicked.connect(self._launch_vscode_bridge)
        overlay_layout.addWidget(connect_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Status label for connection attempts
        self.connection_status_label = QLabel("")
        self.connection_status_label.setStyleSheet("""
            color: #9CA3AF;
            font-size: 12px;
        """)
        self.connection_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay_layout.addWidget(self.connection_status_label)
        
        overlay_layout.addStretch()
        
        # Instructions at bottom
        instructions = QLabel(
            "💡 This will launch a minimized VS Code window just for AI.\n"
            "It's completely separate from any other VS Code windows you have open.\n"
            "Leave it running in the background for best results!"
        )
        instructions.setStyleSheet("""
            color: #6B7280;
            font-size: 11px;
        """)
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        instructions.setWordWrap(True)
        overlay_layout.addWidget(instructions)
        
        # First-time setup button (placeholder for distribution)
        setup_btn = QPushButton("🔧  First-Time Setup")
        setup_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #9CA3AF;
                border: 1px solid #4B5563;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(75, 85, 99, 0.3);
                color: #E5E7EB;
            }
        """)
        setup_btn.clicked.connect(self._show_first_time_setup)
        overlay_layout.addWidget(setup_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Hide by default - will be shown if connection fails
        self.deactivated_overlay.setVisible(False)
    
    def _show_first_time_setup(self):
        """Show first-time setup wizard - PLACEHOLDER for distribution
        
        TODO: Before distribution, implement this to:
        1. Check if VS Code is installed (and offer download link)
        2. Check if GitHub Copilot extension is installed
        3. Check if user is signed into GitHub in VS Code
        4. Install the SuiteView AI Bridge extension (from bundled .vsix or marketplace)
        5. Verify the bridge is working
        
        Requirements for new users:
        - VS Code installed with 'code' in PATH
        - GitHub account
        - GitHub Copilot subscription (Individual, Business, or Enterprise)
        - For Claude/Gemini/premium models: Copilot Pro+ ($39/month)
        - SuiteView AI Bridge extension installed in VS Code
        """
        QMessageBox.information(
            self,
            "First-Time Setup",
            "🚧 Setup Wizard Coming Soon!\n\n"
            "For now, you'll need:\n\n"
            "1. VS Code installed\n"
            "2. GitHub Copilot subscription\n"
            "3. SuiteView AI Bridge extension\n\n"
            "Ask your friendly neighborhood developer\n"
            "for help getting set up! 🤖"
        )
    
    def _launch_vscode_bridge(self):
        """Launch dedicated VS Code session and start polling for connection"""
        import subprocess
        import os
        
        self.connection_status_label.setText("☕ Brewing... Starting dedicated VS Code session...")
        self.connection_status_label.setStyleSheet("color: #FFD700; font-size: 12px;")
        QApplication.processEvents()
        
        try:
            # Find VS Code executable
            vscode_path = self._find_vscode()
            
            if not vscode_path:
                self.connection_status_label.setText(
                    "❌ Couldn't find VS Code installation.\n"
                    "Please install VS Code from https://code.visualstudio.com"
                )
                self.connection_status_label.setStyleSheet("color: #EF4444; font-size: 12px;")
                return
            
            # Create a dedicated workspace folder for the AI Bridge
            workspace_path = self.settings_dir / 'ai_bridge_workspace'
            workspace_path.mkdir(parents=True, exist_ok=True)
            
            # Create a simple README so the workspace isn't empty
            readme_path = workspace_path / 'README.md'
            if not readme_path.exists():
                readme_path.write_text(
                    "# SuiteView AI Bridge Workspace\n\n"
                    "This is a dedicated VS Code workspace for the SuiteView AI Bridge.\n"
                    "Keep this VS Code window minimized - it provides AI access to SuiteView.\n\n"
                    "Powered by GitHub Copilot",
                    encoding='utf-8'
                )
            
            # Windows: Launch hidden from taskbar
            if sys.platform == 'win32':
                CREATE_NO_WINDOW = 0x08000000
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE
                
                # Launch with flags to suppress messages and notifications
                process = subprocess.Popen(
                    [
                        str(vscode_path), 
                        '--new-window', 
                        str(workspace_path),
                        '--disable-workspace-trust',  # Skip workspace trust dialog
                        '--skip-release-notes',        # Skip release notes
                        '--skip-welcome'               # Skip welcome page
                    ],
                    startupinfo=startupinfo,
                    creationflags=CREATE_NO_WINDOW
                )
                
                # Schedule multiple attempts to hide the window
                QTimer.singleShot(2000, lambda: self._hide_vscode_window(process.pid))
                QTimer.singleShot(4000, lambda: self._hide_vscode_window(process.pid))
                QTimer.singleShot(6000, lambda: self._hide_vscode_window(process.pid))
            else:
                # macOS/Linux - just open VS Code
                process = subprocess.Popen([
                    str(vscode_path), 
                    '--new-window', 
                    str(workspace_path),
                    '--disable-workspace-trust',
                    '--skip-release-notes',
                    '--skip-welcome'
                ])
            
            # Store the process PID
            self._vscode_process_pid = process.pid
            
            # Save session info
            with open(self._vscode_session_file, 'w') as f:
                json.dump({
                    'pid': self._vscode_process_pid,
                    'workspace': str(workspace_path),
                    'vscode_path': str(vscode_path),
                    'created': datetime.now().isoformat()
                }, f, indent=2)
            
            logger.info(f"Launched dedicated VS Code session (PID: {self._vscode_process_pid})")
            
            self.connection_status_label.setText("☕ VS Code is waking up... Waiting for the AI Bridge...")
            
            # Start polling for connection
            self._start_connection_polling()
            
        except Exception as e:
            logger.error(f"Error launching VS Code: {e}", exc_info=True)
            self.connection_status_label.setText(f"❌ Error launching VS Code: {e}")
            self.connection_status_label.setStyleSheet("color: #EF4444; font-size: 12px;")
    
    def _find_vscode(self) -> Optional[Path]:
        """Find VS Code executable by searching common installation locations"""
        import shutil
        import os
        
        # First, try 'code' command in PATH
        code_path = shutil.which('code')
        if code_path:
            return Path(code_path)
        
        # Search common installation locations
        if sys.platform == 'win32':
            # Windows common locations
            possible_paths = [
                Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Microsoft VS Code' / 'Code.exe',
                Path(os.environ.get('ProgramFiles', '')) / 'Microsoft VS Code' / 'Code.exe',
                Path(os.environ.get('ProgramFiles(x86)', '')) / 'Microsoft VS Code' / 'Code.exe',
            ]
        elif sys.platform == 'darwin':
            # macOS
            possible_paths = [
                Path('/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code'),
                Path.home() / 'Applications' / 'Visual Studio Code.app' / 'Contents' / 'Resources' / 'app' / 'bin' / 'code',
            ]
        else:
            # Linux
            possible_paths = [
                Path('/usr/bin/code'),
                Path('/usr/local/bin/code'),
                Path.home() / '.local' / 'bin' / 'code',
            ]
        
        # Check each path
        for path in possible_paths:
            if path.exists() and path.is_file():
                logger.info(f"Found VS Code at: {path}")
                return path
        
        logger.warning("Could not find VS Code in any common location")
        return None
    
    def _hide_vscode_window(self, pid: int):
        """Hide VS Code window from taskbar on Windows
        
        Only hides the specific AI Bridge workspace window, not all VS Code windows.
        """
        if sys.platform != 'win32':
            return
        
        try:
            import ctypes
            from ctypes import wintypes
            import psutil
            
            logger.info(f"Attempting to hide AI Bridge VS Code window (initial PID: {pid})")
            
            # Get the workspace path we opened
            workspace_path = self.settings_dir / 'ai_bridge_workspace'
            workspace_name = workspace_path.name.upper()  # "AI_BRIDGE_WORKSPACE"
            
            logger.info(f"Looking for window with workspace: {workspace_name}")
            
            # Find all VS Code processes (including child processes)
            vscode_pids = []
            try:
                # Get all processes
                for proc in psutil.process_iter(['pid', 'name', 'exe']):
                    try:
                        # Check if it's a Code.exe process
                        if proc.info['name'] and 'code.exe' in proc.info['name'].lower():
                            vscode_pids.append(proc.info['pid'])
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                
                logger.info(f"Found {len(vscode_pids)} VS Code processes: {vscode_pids}")
            except Exception as e:
                logger.error(f"Error finding VS Code processes: {e}")
                return
            
            # Windows API constants
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000
            SW_HIDE = 0
            
            hidden_count = 0
            windows_found = []
            
            # Find all windows for VS Code processes
            def enum_windows_callback(hwnd, lparam):
                nonlocal hidden_count
                
                try:
                    # Get process ID for this window
                    process_id = wintypes.DWORD()
                    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
                    
                    if process_id.value in vscode_pids:
                        # Get window title
                        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buffer = ctypes.create_unicode_buffer(length + 1)
                            ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
                            title = buffer.value
                            
                            is_visible = ctypes.windll.user32.IsWindowVisible(hwnd)
                            windows_found.append({
                                'hwnd': hwnd,
                                'title': title,
                                'visible': is_visible,
                                'pid': process_id.value
                            })
                            
                            logger.info(f"Found window: HWND={hwnd}, Title='{title}', Visible={is_visible}, PID={process_id.value}")
                            
                            # Only hide if this is OUR workspace window
                            # Check if the title contains our workspace name
                            if is_visible and workspace_name in title.upper():
                                # Get current extended style
                                ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                                
                                # Set tool window style (hides from taskbar)
                                new_style = ex_style | WS_EX_TOOLWINDOW
                                new_style = new_style & ~WS_EX_APPWINDOW
                                
                                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
                                
                                # Hide the window completely
                                result = ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
                                
                                # Store the HWND so we can unhide it later
                                self._hidden_vscode_hwnd = hwnd
                                
                                hidden_count += 1
                                logger.info(f"Hid AI Bridge window '{title}' (HWND: {hwnd}), ShowWindow result: {result}")
                except Exception as e:
                    logger.error(f"Error processing window {hwnd}: {e}")
                
                return True
            
            # Enumerate all windows
            EnumWindowsProc = ctypes.WINFUNCTYPE(
                ctypes.c_bool, 
                ctypes.POINTER(ctypes.c_int), 
                ctypes.POINTER(ctypes.c_int)
            )
            ctypes.windll.user32.EnumWindows(EnumWindowsProc(enum_windows_callback), 0)
            
            logger.info(f"Window enumeration complete. Found {len(windows_found)} windows, hid {hidden_count}")
            
            if hidden_count > 0:
                logger.info(f"Successfully hid {hidden_count} AI Bridge VS Code window(s)")
            else:
                logger.warning(f"No AI Bridge VS Code window found. Found these windows: {windows_found}")
            
        except Exception as e:
            logger.error(f"Could not hide VS Code window: {e}", exc_info=True)
    
    def unhide_vscode_window(self):
        """Unhide the AI Bridge VS Code window"""
        if sys.platform != 'win32':
            return
        
        try:
            import ctypes
            from ctypes import wintypes
            
            if not hasattr(self, '_hidden_vscode_hwnd') or not self._hidden_vscode_hwnd:
                logger.warning("No hidden VS Code window handle stored")
                return
            
            hwnd = self._hidden_vscode_hwnd
            
            # Windows API constants
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000
            SW_SHOW = 5
            SW_RESTORE = 9
            
            logger.info(f"Unhiding VS Code window (HWND: {hwnd})")
            
            # Restore normal window style
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            new_style = ex_style & ~WS_EX_TOOLWINDOW
            new_style = new_style | WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            
            # Show and restore the window
            ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            
            logger.info(f"Successfully unhid VS Code window")
            self._hidden_vscode_hwnd = None
            
        except Exception as e:
            logger.error(f"Could not unhide VS Code window: {e}", exc_info=True)
    
    def _start_connection_polling(self):
        """Start polling for VS Code bridge connection"""
        self._poll_count = 0
        self._max_polls = 30  # Poll for 30 seconds
        
        # Create a timer for polling
        if self._connection_retry_timer:
            self._connection_retry_timer.stop()
        
        self._connection_retry_timer = QTimer(self)
        self._connection_retry_timer.timeout.connect(self._poll_connection)
        self._connection_retry_timer.start(1000)  # Poll every second
    
    def _poll_connection(self):
        """Check if VS Code bridge is available"""
        self._poll_count += 1
        
        # Update status with fun waiting messages
        waiting_messages = [
            "☕ Brewing...", "☕ Almost ready...", "☕ Still warming up...",
            "🔌 Connecting neurons...", "🧠 Loading brain cells...",
            "⚡ Charging AI batteries...", "🎯 Locking on target..."
        ]
        msg_idx = (self._poll_count - 1) % len(waiting_messages)
        self.connection_status_label.setText(f"{waiting_messages[msg_idx]} ({self._poll_count}s)")
        
        # Try to connect
        try:
            import requests
            response = requests.get("http://localhost:5678/health", timeout=1)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "ok":
                    # Connected!
                    self._connection_retry_timer.stop()
                    self._on_connection_result(True, "Connected!")
                    return
        except:
            pass
        
        # Check if we've exceeded max polls
        if self._poll_count >= self._max_polls:
            self._connection_retry_timer.stop()
            self.connection_status_label.setText(
                "😴 VS Code bridge didn't wake up. Try clicking the button again,\n"
                "or make sure the SuiteView AI Bridge extension is installed."
            )
            self.connection_status_label.setStyleSheet("color: #F59E0B; font-size: 12px;")
    
    def resizeEvent(self, event):
        """Handle resize to keep overlay covering the window"""
        super().resizeEvent(event)
        if hasattr(self, 'deactivated_overlay'):
            self.deactivated_overlay.setGeometry(self.rect())

    def init_ui(self):
        """Initialize the UI"""
        self.setWindowTitle("SuiteView AI Assistant")
        self.resize(1000, 700)
        self.setMinimumSize(600, 400)
        
        # Main layout
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Create splitter for sidebar and chat
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left sidebar - Conversation list
        sidebar = self._create_sidebar()
        splitter.addWidget(sidebar)
        
        # Right side - Chat area
        chat_area = self._create_chat_area()
        splitter.addWidget(chat_area)
        
        # Set initial sizes (250px sidebar, rest for chat)
        splitter.setSizes([250, 750])
        
        main_layout.addWidget(splitter)
        
        # Create the deactivated overlay (shown until VS Code Bridge connects)
        self._create_deactivated_overlay()
    
    def _create_sidebar(self) -> QWidget:
        """Create the sidebar with conversation list"""
        sidebar = QWidget()
        sidebar.setMinimumWidth(200)
        sidebar.setMaximumWidth(350)
        sidebar.setStyleSheet("""
            QWidget {
                background-color: #1E3A8A;
            }
        """)
        
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Header
        header = QLabel("Conversations")
        header.setStyleSheet("""
            color: #FFD700;
            font-size: 16px;
            font-weight: bold;
            padding: 8px;
        """)
        layout.addWidget(header)
        
        # New conversation button
        new_btn = QPushButton("+ New Chat")
        new_btn.setStyleSheet("""
            QPushButton {
                background-color: #D4AF37;
                color: #0A1E5E;
                border: none;
                border-radius: 6px;
                padding: 10px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #FFD700;
            }
        """)
        new_btn.clicked.connect(self.new_conversation)
        layout.addWidget(new_btn)
        
        # Conversation list
        self.conversation_list = QListWidget()
        self.conversation_list.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
                color: #E5E7EB;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 2px 4px;
                border-radius: 3px;
                margin: 0px;
                min-height: 18px;
                max-height: 20px;
            }
            QListWidget::item:hover {
                background-color: #2563EB;
            }
            QListWidget::item:selected {
                background-color: #3B82F6;
                color: #FFD700;
            }
        """)
        self.conversation_list.setSpacing(1)
        self.conversation_list.itemClicked.connect(self._on_conversation_selected)
        self.conversation_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.conversation_list.customContextMenuRequested.connect(self._show_conversation_menu)
        layout.addWidget(self.conversation_list)
        
        # Model selector
        model_layout = QHBoxLayout()
        model_label = QLabel("Agent:")
        model_label.setStyleSheet("color: #FFD700; font-size: 11px;")
        model_layout.addWidget(model_label)
        
        self.model_combo = QComboBox()
        self.model_combo.addItems(LLMClient.AVAILABLE_MODELS)
        self.model_combo.setStyleSheet("""
            QComboBox {
                background-color: #0A1E5E;
                color: #FFD700;
                border: 1px solid #D4AF37;
                border-radius: 4px;
                padding: 4px;
                font-size: 11px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #0A1E5E;
                color: #FFD700;
                selection-background-color: #2563EB;
            }
        """)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        model_layout.addWidget(self.model_combo)
        
        layout.addLayout(model_layout)
        
        return sidebar
    
    def _create_chat_area(self) -> QWidget:
        """Create the main chat area"""
        chat_widget = QWidget()
        chat_widget.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #E8F0FF, stop:1 #D0E0F5);
            }
        """)
        
        layout = QVBoxLayout(chat_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Chat header
        header_widget = QWidget()
        header_widget.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #1E3A8A, stop:1 #2563EB);
            border-bottom: 2px solid #D4AF37;
        """)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(16, 8, 16, 8)
        
        self.chat_title_label = QLabel("New Conversation")
        self.chat_title_label.setStyleSheet("""
            color: #FFD700;
            font-size: 18px;
            font-weight: bold;
        """)
        header_layout.addWidget(self.chat_title_label)
        
        header_layout.addStretch()
        
        # Clear chat button
        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #FFD700;
                border: 1px solid #FFD700;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(255, 215, 0, 0.2);
            }
        """)
        clear_btn.clicked.connect(self.clear_current_chat)
        header_layout.addWidget(clear_btn)
        
        layout.addWidget(header_widget)
        
        # Messages scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: #E8F0FF;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #2563EB;
                border-radius: 5px;
                min-height: 20px;
            }
        """)
        
        # Messages container
        self.messages_container = QWidget()
        self.messages_container.setStyleSheet("background: transparent;")
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(8, 8, 8, 8)
        self.messages_layout.setSpacing(4)
        self.messages_layout.addStretch()
        
        scroll_area.setWidget(self.messages_container)
        self.scroll_area = scroll_area
        layout.addWidget(scroll_area, 1)
        
        # Input area
        input_widget = self._create_input_area()
        layout.addWidget(input_widget)
        
        return chat_widget
    
    def _create_input_area(self) -> QWidget:
        """Create the message input area"""
        input_widget = QWidget()
        input_widget.setStyleSheet("""
            QWidget {
                background-color: #F5F8FF;
                border-top: 2px solid #D4AF37;
            }
        """)
        
        layout = QVBoxLayout(input_widget)
        layout.setContentsMargins(12, 8, 12, 8)  # Reduced from 16, 12
        layout.setSpacing(6)  # Reduced from 8
        
        # Attachments display area
        self.attachments_widget = QWidget()
        self.attachments_layout = QHBoxLayout(self.attachments_widget)
        self.attachments_layout.setContentsMargins(0, 0, 0, 0)
        self.attachments_layout.setSpacing(8)
        self.attachments_widget.setVisible(False)
        layout.addWidget(self.attachments_widget)
        
        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        
        # Text input
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Type your message here... (Ctrl+Enter to send)")
        self.input_text.setMaximumHeight(80)  # Reduced from 100
        self.input_text.setStyleSheet("""
            QTextEdit {
                background-color: #FFFFFF;
                border: 2px solid #2563EB;
                border-radius: 8px;
                padding: 6px;
                font-size: 13px;
                color: #0A1E5E;
            }
            QTextEdit:focus {
                border: 2px solid #D4AF37;
            }
        """)
        input_row.addWidget(self.input_text, 1)
        
        # Send button
        self.send_btn = QPushButton("Send")
        self.send_btn.setFixedSize(70, 32)  # Reduced from 80, 40
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #D4AF37;
                color: #0A1E5E;
                border: none;
                border-radius: 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #FFD700;
            }
            QPushButton:disabled {
                background-color: #CCC;
                color: #888;
            }
        """)
        self.send_btn.clicked.connect(self.send_message)
        input_row.addWidget(self.send_btn)
        
        layout.addLayout(input_row)
        
        # Hint text
        hint = QLabel("Press Ctrl+Enter to send • Supports Markdown")
        hint.setStyleSheet("color: #888; font-size: 10px;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)
        
        return input_widget
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        if event.key() == Qt.Key.Key_Return and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.send_message()
        else:
            super().keyPressEvent(event)
    
    def new_conversation(self):
        """Create a new conversation"""
        conv_id = str(uuid.uuid4())
        thread_name = f"New Thread {self._thread_counter}"
        self._thread_counter += 1
        
        conversation = Conversation(
            id=conv_id,
            title=thread_name,
            model=self.model_combo.currentText()
        )
        
        self.conversations.insert(0, conversation)
        self._add_conversation_to_list(conversation)
        self._select_conversation(conversation)
        
        # Mark this conversation for auto-rename after second response
        self._pending_rename_conversation = conversation
        
        self.save_conversations()
    
    def _add_conversation_to_list(self, conversation: Conversation):
        """Add a conversation to the list widget"""
        item = ConversationListItem(conversation)
        self.conversation_list.insertItem(0, item)
    
    def _select_conversation(self, conversation: Conversation):
        """Select and display a conversation"""
        self.current_conversation = conversation
        
        # Update UI
        self.chat_title_label.setText(conversation.title)
        
        # Restore the agent/model for this conversation
        if conversation.agent:
            # Find the model in the combo box by its ID
            for i in range(self.model_combo.count()):
                model_id = self.model_combo.itemData(i)
                if model_id == conversation.agent or self.model_combo.itemText(i) == conversation.agent:
                    self.model_combo.setCurrentIndex(i)
                    break
        else:
            # Fallback to conversation.model for backwards compatibility
            self.model_combo.setCurrentText(conversation.model)
        
        # Clear and reload messages
        self._clear_messages_display()
        
        for message in conversation.messages:
            self._add_message_bubble(message)
        
        # Select in list
        for i in range(self.conversation_list.count()):
            item = self.conversation_list.item(i)
            if isinstance(item, ConversationListItem) and item.conversation.id == conversation.id:
                self.conversation_list.setCurrentItem(item)
                break
    
    def _clear_messages_display(self):
        """Clear the messages display"""
        while self.messages_layout.count() > 1:  # Keep the stretch
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def _add_message_bubble(self, message: ChatMessage, model_id: str = None) -> MessageBubble:
        """Add a message bubble to the display"""
        bubble = MessageBubble(message, model_id=model_id)
        # Insert before the stretch
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)
        
        # Scroll to bottom
        QTimer.singleShot(100, self._scroll_to_bottom)
        
        return bubble
    
    def _scroll_to_bottom(self):
        """Scroll the chat to the bottom"""
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def _on_conversation_selected(self, item: QListWidgetItem):
        """Handle conversation selection"""
        if isinstance(item, ConversationListItem):
            self._select_conversation(item.conversation)
    
    def _show_conversation_menu(self, position):
        """Show context menu for conversation"""
        item = self.conversation_list.itemAt(position)
        if not item or not isinstance(item, ConversationListItem):
            return
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1E3A8A;
                color: #FFD700;
                border: 1px solid #D4AF37;
            }
            QMenu::item:selected {
                background-color: #2563EB;
            }
        """)
        
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        
        action = menu.exec(self.conversation_list.mapToGlobal(position))
        
        if action == rename_action:
            self._rename_conversation(item.conversation)
        elif action == delete_action:
            self._delete_conversation(item.conversation)
    
    def _rename_conversation(self, conversation: Conversation):
        """Rename a conversation"""
        from PyQt6.QtWidgets import QInputDialog
        
        new_title, ok = QInputDialog.getText(
            self, "Rename Conversation", "New title:",
            text=conversation.title
        )
        
        if ok and new_title:
            conversation.title = new_title
            conversation.updated_at = datetime.now()
            
            # Update list item
            for i in range(self.conversation_list.count()):
                item = self.conversation_list.item(i)
                if isinstance(item, ConversationListItem) and item.conversation.id == conversation.id:
                    item.setText(new_title)
                    break
            
            if self.current_conversation and self.current_conversation.id == conversation.id:
                self.chat_title_label.setText(new_title)
            
            self.save_conversations()
    
    def _delete_conversation(self, conversation: Conversation):
        """Delete a conversation"""
        reply = QMessageBox.question(
            self, "Delete Conversation",
            f"Are you sure you want to delete '{conversation.title}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Remove from list
            self.conversations = [c for c in self.conversations if c.id != conversation.id]
            
            # Remove from list widget
            for i in range(self.conversation_list.count()):
                item = self.conversation_list.item(i)
                if isinstance(item, ConversationListItem) and item.conversation.id == conversation.id:
                    self.conversation_list.takeItem(i)
                    break
            
            # If this was the current conversation, select another or create new
            if self.current_conversation and self.current_conversation.id == conversation.id:
                if self.conversations:
                    self._select_conversation(self.conversations[0])
                else:
                    self.new_conversation()
            
            self.save_conversations()
    
    def _on_model_changed(self, model_text: str):
        """Handle model change"""
        # Get the actual model ID from the combo box data
        current_index = self.model_combo.currentIndex()
        model_id = self.model_combo.itemData(current_index)
        
        # If no data stored (old fallback models), use the text
        if model_id is None:
            model_id = model_text
        
        logger.info(f"Model/Agent changed to: {model_id} (display: {model_text})")
        
        self.llm_client.set_model(model_id)
        if self.current_conversation:
            self.current_conversation.model = model_id
            self.current_conversation.agent = model_id  # Save agent selection
            self.save_conversations()
    
    def _on_connection_type_changed(self, index: int):
        """Handle connection type change"""
        conn_type = self.connection_combo.itemData(index)
        logger.info(f"Connection type changed to: {conn_type}")
        
        # Create new client based on connection type
        if conn_type == "github_direct":
            # Check for GitHub token
            import os
            token = os.environ.get("GITHUB_TOKEN")
            if not token:
                QMessageBox.warning(
                    self, 
                    "GitHub Token Required",
                    "GitHub Direct mode requires a GITHUB_TOKEN environment variable.\n\n"
                    "Please set it and restart the application:\n"
                    "  set GITHUB_TOKEN=your_token_here\n\n"
                    "Get a token at: https://github.com/settings/tokens"
                )
                # Revert to VS Code Bridge
                self.connection_combo.setCurrentIndex(0)
                return
            
            self.llm_client = GitHubDirectClient(token=token)
            self._connected = True
            
            # Update models for GitHub Direct
            self.model_combo.clear()
            for model in GitHubDirectClient.AVAILABLE_MODELS:
                self.model_combo.addItem(model["name"], model["id"])
            
            self.chat_title_label.setText("GitHub Direct Mode")
            logger.info("Switched to GitHub Direct client")
            
        else:  # vscode_bridge
            self.llm_client = VSCodeBridgeClient()
            self._check_connection()
            
            # Update models will happen via _fetch_models callback
            self.model_combo.clear()
            self.model_combo.addItems(LLMClient.AVAILABLE_MODELS)
            
            self.chat_title_label.setText("VS Code Bridge Mode")
            logger.info("Switched to VS Code Bridge client")
    
    def attach_file(self):
        """Attach a file to the message"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Attach Files",
            "",
            "All Files (*);;Text Files (*.txt);;Images (*.png *.jpg *.jpeg);;Documents (*.pdf *.doc *.docx)"
        )
        
        if file_paths:
            self.pending_attachments.extend(file_paths)
            self._update_attachments_display()
    
    def _update_attachments_display(self):
        """Update the attachments display"""
        # Clear current display
        while self.attachments_layout.count():
            item = self.attachments_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self.pending_attachments:
            self.attachments_widget.setVisible(False)
            return
        
        self.attachments_widget.setVisible(True)
        
        for path in self.pending_attachments:
            filename = Path(path).name
            
            chip = QFrame()
            chip.setStyleSheet("""
                QFrame {
                    background-color: #E8F0FF;
                    border: 1px solid #2563EB;
                    border-radius: 12px;
                    padding: 4px 8px;
                }
            """)
            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(8, 4, 4, 4)
            chip_layout.setSpacing(4)
            
            label = QLabel(f"📎 {filename[:20]}{'...' if len(filename) > 20 else ''}")
            label.setStyleSheet("color: #0A1E5E; font-size: 11px;")
            chip_layout.addWidget(label)
            
            remove_btn = QPushButton("×")
            remove_btn.setFixedSize(16, 16)
            remove_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #888;
                    border: none;
                    font-size: 14px;
                }
                QPushButton:hover {
                    color: #DC2626;
                }
            """)
            remove_btn.clicked.connect(lambda checked, p=path: self._remove_attachment(p))
            chip_layout.addWidget(remove_btn)
            
            self.attachments_layout.addWidget(chip)
        
        self.attachments_layout.addStretch()
    
    def _remove_attachment(self, path: str):
        """Remove an attachment"""
        if path in self.pending_attachments:
            self.pending_attachments.remove(path)
            self._update_attachments_display()
    
    def send_message(self):
        """Send the current message"""
        text = self.input_text.toPlainText().strip()
        
        if not text and not self.pending_attachments:
            return
        
        if not self.current_conversation:
            self.new_conversation()
        
        # Add user message
        user_message = self.current_conversation.add_message(
            MessageRole.USER, 
            text,
            self.pending_attachments.copy()
        )
        self._add_message_bubble(user_message)
        
        # Update conversation title if this is the first message
        if len(self.current_conversation.messages) == 1:
            title = text[:40] + "..." if len(text) > 40 else text
            self.current_conversation.title = title
            self.chat_title_label.setText(title)
            
            # Update list item
            for i in range(self.conversation_list.count()):
                item = self.conversation_list.item(i)
                if isinstance(item, ConversationListItem) and item.conversation.id == self.current_conversation.id:
                    item.setText(title)
                    break
        
        # Clear input
        self.input_text.clear()
        self.pending_attachments.clear()
        self._update_attachments_display()
        
        # Disable send button while processing
        self.send_btn.setEnabled(False)
        self.send_btn.setText("...")
        
        # Get the actual model ID from the combo box (not the saved conversation model)
        current_index = self.model_combo.currentIndex()
        model_id = self.model_combo.itemData(current_index)
        if model_id is None:
            model_id = self.model_combo.currentText()
        
        # Create placeholder for assistant response with model info
        assistant_message = self.current_conversation.add_message(MessageRole.ASSISTANT, "")
        self.current_bubble = self._add_message_bubble(assistant_message, model_id=model_id)
        
        # Use appropriate worker based on client type
        if isinstance(self.llm_client, GitHubDirectClient):
            # Use GitHub Direct worker for streaming
            self.worker = GitHubDirectWorker(
                self.llm_client,
                self.current_conversation.get_messages_for_api()[:-1],  # Exclude empty assistant message
                model_id
            )
            self.worker.token_received.connect(self._on_token_received)
            self.worker.response_complete.connect(self._on_response_complete)
            self.worker.error_occurred.connect(self._on_error)
            self.worker.finished.connect(self._on_worker_finished)
            self.worker.start()
        else:
            # Use regular streaming worker (VS Code Bridge)
            self.worker = AsyncWorker(
                self.llm_client,
                self.current_conversation.get_messages_for_api()[:-1],  # Exclude empty assistant message
                model_id
            )
            self.worker.token_received.connect(self._on_token_received)
            self.worker.response_complete.connect(self._on_response_complete)
            self.worker.error_occurred.connect(self._on_error)
            self.worker.finished.connect(self._on_worker_finished)
            self.worker.start()
        
        self.save_conversations()
    
    def _on_worker_finished(self):
        """Handle worker thread finished - clean up reference"""
        # Don't set to None immediately, let Python GC handle it after event loop processes
        pass
    
    def _cleanup_worker(self):
        """Safely cleanup the worker thread"""
        if self.worker is not None:
            if self.worker.isRunning():
                self.worker.cancel()
                self.worker.wait(2000)  # Wait up to 2 seconds
            self.worker = None
    
    def _on_token_received(self, token: str):
        """Handle received token during streaming"""
        if self.current_bubble:
            current_content = self.current_bubble.message.content
            self.current_bubble.update_content(current_content + token)
            self._scroll_to_bottom()
    
    def _on_response_complete(self, response: str, model_id: str = None, duration: float = 0):
        """Handle complete response"""
        if self.current_bubble:
            self.current_bubble.update_content(response)
            # Update the message in the conversation
            if self.current_conversation and self.current_conversation.messages:
                self.current_conversation.messages[-1].content = response
            
            # Set timing info on the bubble
            if model_id and duration:
                self.current_bubble.set_timing_info(model_id, duration)
            
            # Check if response contains code blocks that could be saved as files
            self._check_for_saveable_content(response)
            
            # Auto-generate thread name after second response
            self._check_auto_rename_thread()
        
        self.send_btn.setEnabled(True)
        self.send_btn.setText("Send")
        self.current_bubble = None
        # Note: Don't set self.worker = None here, let _on_worker_finished handle cleanup
        
        self.save_conversations()
    
    def _on_agent_response_complete(self, data: dict):
        """Handle complete response from Agent Mode"""
        response = data.get('response', '')
        model_name = data.get('model_name', data.get('model', 'Unknown'))
        model_id = data.get('model_id', model_name)
        response_file = data.get('response_file', '')
        request_id = data.get('request_id', '')
        duration = data.get('duration_seconds', 0)
        
        # Prepend agent info to response
        agent_info = f"[Agent Mode - {model_name}]\n"
        if response_file:
            agent_info += f"📄 Response saved to: {response_file}\n"
        agent_info += "\n"
        
        full_response = agent_info + response
        
        if self.current_bubble:
            self.current_bubble.update_content(full_response)
            # Update the message in the conversation
            if self.current_conversation and self.current_conversation.messages:
                self.current_conversation.messages[-1].content = full_response
            
            # Set timing info on the bubble
            if model_id and duration:
                self.current_bubble.set_timing_info(f"Agent: {model_id}", duration)
            
            # Check if response contains code blocks that could be saved as files
            self._check_for_saveable_content(response)
        
        self.send_btn.setEnabled(True)
        self.send_btn.setText("Send")
        self.current_bubble = None
        # Note: Don't set self.worker = None here, let _on_worker_finished handle cleanup
        
        self.save_conversations()
        
        logger.info(f"Agent response complete: request_id={request_id}, file={response_file}, duration={duration:.1f}s")
    
    def _check_auto_rename_thread(self):
        """Check if we should auto-generate a thread name"""
        if not self._pending_rename_conversation:
            return
        
        # Only rename the current conversation
        if self._pending_rename_conversation != self.current_conversation:
            return
        
        # Count messages - we need at least 2 exchanges (2 user + 2 assistant)
        user_msgs = [m for m in self.current_conversation.messages if m.role == MessageRole.USER]
        assistant_msgs = [m for m in self.current_conversation.messages if m.role == MessageRole.ASSISTANT]
        
        # Wait until we have 2 complete exchanges
        # Exchange 1: User asks, AI responds
        # Exchange 2: User asks again, AI responds again <- RENAME HERE
        if len(user_msgs) >= 2 and len(assistant_msgs) >= 2:
            logger.info(f"Auto-rename triggered: {len(user_msgs)} user msgs, {len(assistant_msgs)} assistant msgs")
            # Time to generate a name based on the SECOND exchange
            self._generate_thread_name()
            self._pending_rename_conversation = None
    
    def _generate_thread_name(self):
        """Generate a thread name based on conversation content using a fast model"""
        if not self.current_conversation or len(self.current_conversation.messages) < 4:
            return
        
        # Get the first TWO exchanges for context
        messages = self.current_conversation.messages
        user_msgs = [m.content for m in messages if m.role == MessageRole.USER]
        assistant_msgs = [m.content for m in messages if m.role == MessageRole.ASSISTANT]
        
        if len(user_msgs) < 2:
            return
        
        # Build context from both exchanges
        first_user = user_msgs[0][:150] if user_msgs[0] else ""
        first_assistant = assistant_msgs[0][:150] if len(assistant_msgs) > 0 else ""
        second_user = user_msgs[1][:150] if len(user_msgs) > 1 else ""
        second_assistant = assistant_msgs[1][:150] if len(assistant_msgs) > 1 else ""
        
        # Create a prompt that analyzes the conversation topic
        naming_prompt = f"""Analyze this conversation and create a descriptive thread title (maximum 40 characters).

First exchange:
User: {first_user}
Assistant: {first_assistant}

Second exchange:
User: {second_user}
Assistant: {second_assistant}

Based on the overall topic and questions being asked, create a SHORT, descriptive title (max 40 chars).
Do NOT just repeat the first question.
Focus on the TOPIC or SUBJECT of the discussion.
Reply with ONLY the title, nothing else."""
        
        # Use a background worker to generate the name
        try:
            from PyQt6.QtCore import QThread
            
            class NamingWorker(QThread):
                name_generated = pyqtSignal(str)
                
                def __init__(self, client, prompt):
                    super().__init__()
                    self.client = client
                    self.prompt = prompt
                
                def run(self):
                    try:
                        # Use the simplest/fastest model for naming
                        import asyncio
                        import requests
                        
                        # Try synchronous request for simplicity
                        if isinstance(self.client, VSCodeBridgeClient):
                            response = requests.post(
                                f"{self.client.base_url}/chat/completions",
                                json={
                                    "messages": [{"role": "user", "content": self.prompt}],
                                    "model": "gpt-4o-mini",  # Fast, efficient model for naming
                                    "stream": False,
                                    "max_tokens": 50,
                                    "temperature": 0.7
                                },
                                timeout=10
                            )
                            if response.status_code == 200:
                                data = response.json()
                                name = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                                # Clean up the name
                                name = name.replace('"', '').replace("'", "").strip()
                                if len(name) > 40:
                                    name = name[:37] + "..."
                                if name:
                                    self.name_generated.emit(name)
                    except Exception as e:
                        logger.error(f"Failed to generate thread name: {e}")
            
            worker = NamingWorker(self.llm_client, naming_prompt)
            worker.name_generated.connect(self._on_thread_name_generated)
            worker.start()
            # Keep reference so it doesn't get garbage collected
            self._naming_worker = worker
            
        except Exception as e:
            logger.error(f"Failed to start naming worker: {e}")
    
    def _on_thread_name_generated(self, name: str):
        """Handle generated thread name"""
        if self.current_conversation and name:
            self.current_conversation.title = name
            self.current_conversation.updated_at = datetime.now()
            
            # Update the chat title
            self.chat_title_label.setText(name)
            
            # Update the list item
            for i in range(self.conversation_list.count()):
                item = self.conversation_list.item(i)
                if isinstance(item, ConversationListItem) and item.conversation.id == self.current_conversation.id:
                    item.setText(name)
                    break
            
            self.save_conversations()
            logger.info(f"Auto-renamed thread to: {name}")
    
    def _check_for_saveable_content(self, response: str):
        """Check if response contains content that can be saved as a file"""
        import re
        
        # Look for code blocks with file paths mentioned
        # Pattern: ```language followed by code
        code_blocks = re.findall(r'```(\w+)?\n(.*?)```', response, re.DOTALL)
        
        # Look for file paths in the response
        file_patterns = [
            r'([A-Za-z]:\\[^\s\n"\']+\.\w+)',  # Windows paths like C:\Users\...\file.txt
            r'(~/[^\s\n"\']+\.\w+)',  # Unix home paths
            r'create.*?file.*?["\']([^"\']+)["\']',  # "create a file called 'filename'"
            r'save.*?as.*?["\']([^"\']+)["\']',  # "save as 'filename'"
        ]
        
        suggested_path = None
        for pattern in file_patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                suggested_path = match.group(1) if match.lastindex else match.group(0)
                break
        
        if code_blocks and len(code_blocks) > 0:
            # Found code - offer to save it
            code_content = code_blocks[0][1].strip()
            language = code_blocks[0][0] or 'txt'
            
            # Add a save button to the current bubble
            if self.current_bubble and code_content:
                self._add_save_button_to_bubble(self.current_bubble, code_content, suggested_path, language)
    
    def _add_save_button_to_bubble(self, bubble, content: str, suggested_path: str = None, language: str = 'txt'):
        """Add a save file button to a message bubble"""
        save_btn = QPushButton("💾 Save as File")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                margin-top: 4px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        
        # Store content for the save action
        save_btn.clicked.connect(lambda: self._save_content_to_file(content, suggested_path, language))
        
        # Add to bubble layout
        bubble.layout().addWidget(save_btn)
    
    def _save_content_to_file(self, content: str, suggested_path: str = None, language: str = 'txt'):
        """Save content to a file"""
        # Map language to file extension
        ext_map = {
            'python': '.py', 'py': '.py',
            'javascript': '.js', 'js': '.js',
            'typescript': '.ts', 'ts': '.ts',
            'powershell': '.ps1', 'ps1': '.ps1',
            'bash': '.sh', 'sh': '.sh',
            'json': '.json',
            'html': '.html',
            'css': '.css',
            'sql': '.sql',
            'txt': '.txt',
            'text': '.txt',
        }
        default_ext = ext_map.get(language.lower(), '.txt')
        
        # Determine initial path
        if suggested_path:
            initial_path = suggested_path
        else:
            initial_path = f"output{default_ext}"
        
        # Show save dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save File",
            initial_path,
            f"All Files (*);;{language.upper()} Files (*{default_ext})"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                QMessageBox.information(self, "Success", f"File saved to:\n{file_path}")
                logger.info(f"File saved: {file_path}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to save file:\n{str(e)}")
                logger.error(f"Failed to save file: {e}")

    def _on_error(self, error: str):
        """Handle error during LLM request"""
        try:
            if self.current_bubble:
                self.current_bubble.update_content(f"⚠️ Error: {error}")
        except RuntimeError:
            # Widget may have been deleted
            pass
        
        self.send_btn.setEnabled(True)
        self.send_btn.setText("Send")
        self.current_bubble = None
        # Note: Don't set self.worker = None here, let _on_worker_finished handle cleanup
        
        logger.error(f"LLM request error: {error}")
        QMessageBox.warning(self, "Error", f"Failed to get response:\n\n{error}")
    
    def clear_current_chat(self):
        """Clear the current conversation"""
        if not self.current_conversation:
            return
        
        reply = QMessageBox.question(
            self, "Clear Chat",
            "Are you sure you want to clear this conversation?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.current_conversation.messages.clear()
            self._clear_messages_display()
            self.save_conversations()
    
    def save_conversations(self):
        """Save all conversations to disk"""
        try:
            data = {
                "conversations": [c.to_dict() for c in self.conversations]
            }
            
            save_path = self.settings_dir / "conversations.json"
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Failed to save conversations: {e}")
    
    def load_conversations(self):
        """Load conversations from disk"""
        try:
            load_path = self.settings_dir / "conversations.json"
            
            if not load_path.exists():
                return
            
            with open(load_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.conversations = [
                Conversation.from_dict(c) 
                for c in data.get("conversations", [])
            ]
            
            # Populate list
            for conv in self.conversations:
                self._add_conversation_to_list(conv)
            
            # Select most recent
            if self.conversations:
                self._select_conversation(self.conversations[0])
                
        except Exception as e:
            logger.error(f"Failed to load conversations: {e}")
    
    def closeEvent(self, event):
        """Handle window close"""
        # Cancel any running worker threads
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            if not self.worker.wait(3000):  # Wait up to 3 seconds
                logger.warning("Worker thread did not finish in time")
        
        if self._connection_check_worker and self._connection_check_worker.isRunning():
            self._connection_check_worker.wait(1000)
        
        if self._models_worker and self._models_worker.isRunning():
            self._models_worker.wait(1000)
        
        # Save conversations
        self.save_conversations()
        
        # Close LLM client safely
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.llm_client.close())
            loop.close()
        except Exception as e:
            logger.debug(f"Error closing LLM client: {e}")
        
        event.accept()
