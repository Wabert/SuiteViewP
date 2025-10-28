#!/usr/bin/env python3
"""SuiteView Data Manager - Main entry point"""

import sys
import logging
from PyQt6.QtWidgets import QApplication
from suiteview.ui.main_window import MainWindow
from suiteview.utils.config import load_config
from suiteview.utils.logger import setup_logging
from suiteview.data.database import get_database

logger = logging.getLogger(__name__)


def main():
    """Application entry point"""
    # Set up logging
    setup_logging()
    logger.info("=" * 60)
    logger.info("SuiteView Data Manager Starting")
    logger.info("=" * 60)

    # Load configuration
    config = load_config()
    logger.info(f"Configuration loaded: {config.app_name} v{config.version}")

    # Initialize database
    try:
        db = get_database()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        sys.exit(1)

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName(config.app_name)
    app.setOrganizationName(config.organization_name)

    logger.info("Qt application created")

    # Create and show main window
    try:
        window = MainWindow(config)
        window.show()
        logger.info("Main window displayed")
    except Exception as e:
        logger.error(f"Failed to create main window: {e}", exc_info=True)
        sys.exit(1)

    # Start event loop
    logger.info("Starting Qt event loop")
    exit_code = app.exec()
    logger.info(f"Application exiting with code: {exit_code}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
