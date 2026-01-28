#!/usr/bin/env python3
"""Run the LLM Chat Window standalone for testing"""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from suiteview.ui.llm_chat_window import LLMChatWindow
from suiteview.ui.theme import apply_global_theme


def main():
    """Launch the LLM Chat Window"""
    app = QApplication(sys.argv)
    app.setApplicationName("SuiteView AI Assistant")
    
    apply_global_theme(app)
    
    window = LLMChatWindow()
    window.show()
    
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
