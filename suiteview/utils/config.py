"""Configuration management for SuiteView Data Manager"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    """Application configuration"""

    app_name: str = "SuiteView Data Manager"
    organization_name: str = "SuiteView"
    version: str = "1.0.0"

    # Window settings
    window_width: int = 1600
    window_height: int = 900
    window_min_width: int = 1200
    window_min_height: int = 700

    # Panel settings
    left_panel_width: int = 200
    middle_panel_width: int = 300

    # Database
    db_path: Optional[str] = None

    # Logging
    log_dir: Optional[str] = None
    log_level: str = "INFO"


def load_config() -> Config:
    """Load configuration (currently returns defaults)"""
    config = Config()

    # Set up default paths
    home = Path.home()
    app_dir = home / '.suiteview'
    app_dir.mkdir(exist_ok=True)

    config.log_dir = str(app_dir / 'logs')
    Path(config.log_dir).mkdir(exist_ok=True)

    return config
