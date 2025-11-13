"""Constants used throughout the SuiteView Data Manager application"""

# Query Types
class QueryType:
    """Query type constants"""
    DB = "DB"
    XDB = "XDB"


# Tree Item Types
class ItemType:
    """Tree widget item type constants"""
    QUERY_FOLDER = "query_folder"
    QUERY = "query"
    CONNECTION = "connection"
    TABLE = "table"
    FIELD = "field"
    DATA_MAP_FOLDER = "data_map_folder"
    DATA_MAP = "data_map"


# Connection Types
class ConnectionType:
    """Database connection type constants"""
    SQL_SERVER = "SQL_SERVER"
    DB2 = "DB2"
    ORACLE = "ORACLE"
    ACCESS = "ACCESS"
    EXCEL = "EXCEL"
    CSV = "CSV"
    FIXED_WIDTH = "FIXED_WIDTH"
    MAINFRAME_FTP = "MAINFRAME_FTP"
    ODBC = "ODBC"


# Filter Types
class FilterType:
    """Query filter type constants"""
    TEXT = "text"
    STRING = "string"
    EXACT = "exact"
    NUMERIC_EXACT = "numeric_exact"
    NUMERIC_RANGE = "numeric_range"
    DATE_EXACT = "date_exact"
    DATE_RANGE = "date_range"
    CHECKBOX_LIST = "checkbox_list"
    EXPRESSION = "expression"


# Match Types for String Filters
class MatchType:
    """String match type constants"""
    EXACT = "exact"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    CONTAINS = "contains"
    EXPRESSION = "expression"


# UI Colors
class UIColors:
    """UI color constants"""
    PRIMARY = "#3498db"
    PRIMARY_DARK = "#2980b9"
    SUCCESS = "#28a745"
    WARNING = "#ffc107"
    DANGER = "#dc3545"
    INFO = "#17a2b8"
    LIGHT = "#f8f9fa"
    DARK = "#343a40"
    DISABLED = "#bdc3c7"


# Database Metadata
class MetadataStatus:
    """Metadata cache status constants"""
    FRESH = "fresh"
    STALE = "stale"
    EXPIRED = "expired"


# Query Complexity Levels
class QueryComplexity:
    """Query complexity indicator levels"""
    SIMPLE = "simple"      # 1-5 elements
    MEDIUM = "medium"      # 6-15 elements
    COMPLEX = "complex"    # 16+ elements


# Application Settings Keys
class SettingsKey:
    """User preference/settings key constants"""
    THEME = "theme"
    WINDOW_SIZE = "window_size"
    WINDOW_POS = "window_position"
    LAST_CONNECTION = "last_connection"
    RECENT_QUERIES = "recent_queries"
    AUTO_REFRESH_METADATA = "auto_refresh_metadata"
