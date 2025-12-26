"""
Data Set Model - Dynamic SQL builder with Python scripting
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import ast
import re


@dataclass
class DataSetParameter:
    """Parameter definition for a Data Set"""
    name: str
    param_type: str = "text"  # text, number, date, list, boolean
    required: bool = True
    default_value: Any = None
    description: str = ""
    
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'param_type': self.param_type,
            'required': self.required,
            'default_value': self.default_value,
            'description': self.description
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'DataSetParameter':
        return DataSetParameter(
            name=data['name'],
            param_type=data.get('param_type', 'text'),
            required=data.get('required', True),
            default_value=data.get('default_value'),
            description=data.get('description', '')
        )


@dataclass
class DataSetField:
    """Output field definition for a Data Set"""
    name: str
    data_type: str = "text"  # text, number, date, boolean
    description: str = ""
    
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'data_type': self.data_type,
            'description': self.description
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'DataSetField':
        return DataSetField(
            name=data['name'],
            data_type=data.get('data_type', 'text'),
            description=data.get('description', '')
        )


@dataclass
class DataSet:
    """Data Set definition with Python script for dynamic SQL generation"""
    name: str
    description: str = ""
    script_code: str = ""
    connection_type: str = "SQL Server"  # For future XDB integration
    connection_name: str = ""  # For future XDB integration
    parameters: List[DataSetParameter] = field(default_factory=list)
    display_fields: List[DataSetField] = field(default_factory=list)
    created_date: datetime = field(default_factory=datetime.now)
    modified_date: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'name': self.name,
            'description': self.description,
            'script_code': self.script_code,
            'connection_type': self.connection_type,
            'connection_name': self.connection_name,
            'parameters': [p.to_dict() for p in self.parameters],
            'display_fields': [f.to_dict() for f in self.display_fields],
            'created_date': self.created_date.isoformat(),
            'modified_date': self.modified_date.isoformat()
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'DataSet':
        """Create from dictionary (JSON deserialization)"""
        dataset = DataSet(
            name=data['name'],
            description=data.get('description', ''),
            script_code=data.get('script_code', ''),
            connection_type=data.get('connection_type', 'SQL Server'),
            connection_name=data.get('connection_name', ''),
            parameters=[DataSetParameter.from_dict(p) for p in data.get('parameters', [])],
            display_fields=[DataSetField.from_dict(f) for f in data.get('display_fields', [])],
            created_date=datetime.fromisoformat(data.get('created_date', datetime.now().isoformat())),
            modified_date=datetime.fromisoformat(data.get('modified_date', datetime.now().isoformat()))
        )
        return dataset
    
    def parse_script(self) -> tuple[List[DataSetParameter], Optional[str]]:
        """Parse the Python script to extract function signature and validate.
        
        Returns:
            (parameters, error_message)
            - parameters: List of detected parameters from function signature
            - error_message: Error string if parsing failed, None if successful
        """
        if not self.script_code.strip():
            return [], "Script is empty"
        
        try:
            # Parse the Python code
            tree = ast.parse(self.script_code)
            
            # Find the build_query function
            build_query_func = None
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == 'build_query':
                    build_query_func = node
                    break
            
            if not build_query_func:
                return [], "Script must contain a 'build_query' function"
            
            # Extract parameters from function signature
            params = []
            for arg in build_query_func.args.args:
                param_name = arg.arg
                
                # Try to infer type from default value or annotation
                param_type = "text"
                default_value = None
                required = True
                
                # Check for type annotation
                if arg.annotation:
                    try:
                        annotation_name = ast.unparse(arg.annotation)
                    except:
                        annotation_name = ""
                    
                    if 'int' in annotation_name.lower() or 'float' in annotation_name.lower():
                        param_type = "number"
                    elif 'date' in annotation_name.lower():
                        param_type = "date"
                    elif 'list' in annotation_name.lower():
                        param_type = "list"
                    elif 'bool' in annotation_name.lower():
                        param_type = "boolean"
                
                # Check for default value
                defaults_offset = len(build_query_func.args.args) - len(build_query_func.args.defaults)
                arg_index = build_query_func.args.args.index(arg)
                if arg_index >= defaults_offset:
                    default_index = arg_index - defaults_offset
                    default_node = build_query_func.args.defaults[default_index]
                    
                    if isinstance(default_node, ast.Constant):
                        default_value = default_node.value
                        required = False
                        
                        # Infer type from default value if not annotated
                        if arg.annotation is None:
                            if isinstance(default_value, int):
                                param_type = "number"
                            elif isinstance(default_value, bool):
                                param_type = "boolean"
                            elif isinstance(default_value, (list, tuple)):
                                param_type = "list"
                    elif isinstance(default_node, ast.Name) and default_node.id == 'None':
                        required = False
                    elif isinstance(default_node, ast.Constant) and default_node.value is None:
                        required = False
                
                params.append(DataSetParameter(
                    name=param_name,
                    param_type=param_type,
                    required=required,
                    default_value=default_value,
                    description=""
                ))
            
            return params, None
            
        except SyntaxError as e:
            return [], f"Syntax error in script: {e}"
        except Exception as e:
            return [], f"Error parsing script: {e}"
    
    def execute_script(self, param_values: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
        """Execute the Python script with given parameter values.
        
        Args:
            param_values: Dictionary of parameter names to values
        
        Returns:
            (sql_string, error_message)
            - sql_string: Generated SQL if successful
            - error_message: Error string if execution failed
        """
        if not self.script_code.strip():
            return None, "Script is empty"
        
        try:
            # Create execution namespace
            namespace = {}
            
            # Execute the script to define the function
            exec(self.script_code, namespace)
            
            # Get the build_query function
            if 'build_query' not in namespace:
                return None, "Script must define a 'build_query' function"
            
            build_query = namespace['build_query']
            
            # Call the function with provided parameters
            sql = build_query(**param_values)
            
            if not isinstance(sql, str):
                return None, "build_query must return a string (SQL)"
            
            return sql, None
            
        except Exception as e:
            return None, f"Error executing script: {e}"
    
    def extract_fields_from_sql(self, sql: str) -> List[DataSetField]:
        """Extract field names from a SELECT statement.
        
        This is a simple parser that tries to extract column names.
        Not perfect but good enough for most cases.
        """
        fields = []
        
        # Find SELECT clause
        select_match = re.search(r'\bSELECT\s+(.+?)\s+FROM\b', sql, re.IGNORECASE | re.DOTALL)
        if not select_match:
            return fields
        
        select_clause = select_match.group(1)
        
        # Handle SELECT *
        if select_clause.strip() == '*':
            return [DataSetField(name="*", description="All columns")]
        
        # Split by comma (simple approach - won't handle all edge cases)
        column_parts = select_clause.split(',')
        
        for part in column_parts:
            part = part.strip()
            if not part:
                continue
            
            # Try to extract alias (AS clause)
            as_match = re.search(r'\s+AS\s+["\']?(\w+)["\']?\s*$', part, re.IGNORECASE)
            if as_match:
                field_name = as_match.group(1)
            else:
                # Extract last word as field name (handle table.field notation)
                words = part.replace('.', ' ').split()
                if words:
                    field_name = words[-1].strip('`"\' []')
                else:
                    continue
            
            fields.append(DataSetField(name=field_name))
        
        return fields
    
    def validate(self) -> Optional[str]:
        """Validate the Data Set configuration.
        
        Returns:
            Error message if invalid, None if valid
        """
        if not self.name.strip():
            return "Data Set name is required"
        
        if not self.script_code.strip():
            return "Script code is required"
        
        # Parse script
        _, parse_error = self.parse_script()
        if parse_error:
            return parse_error
        
        return None
