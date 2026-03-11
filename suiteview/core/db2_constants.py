"""
SuiteView - DB2 Configuration Constants
Database connection settings and region mappings.

Shared by PolView, Inforce Illustration, and any other module
that needs DB2 access.
"""

# =============================================================================
# REGION CONFIGURATION
# =============================================================================

# Region to DSN mapping (ODBC Data Source Names defined in Control Panel)
REGION_DSN_MAP = {
    "CKPR": "NEON_DSN",    # Production
    "CKMO": "NEON_DSNM",   # Model Office
    "CKAS": "NEON_DSNT",   # Acceptance / Staging
    "CKSR": "NEON_DSNT",   # System Region
    "CKCS": "NEON_DSNT",   # Cybertek / Test
}

# Region to DB2 schema mapping.
# Most regions use 'DB2TAB' as the schema qualifier, but some use
# a non-default schema on the same NEON_DSNT subsystem.
# Regions not listed here default to 'DB2TAB'.
REGION_SCHEMA_MAP = {
    "CKAS": "UNIT",        # Acceptance → UNIT schema
    "CKCS": "CYBERTEK",    # Cybertek  → CYBERTEK schema
    "CKSR": "CKSR",        # System Region → CKSR schema
}

DEFAULT_SCHEMA = "DB2TAB"

# List of available regions (for dropdowns)
REGIONS = list(REGION_DSN_MAP.keys())

# Default region
DEFAULT_REGION = "CKPR"
