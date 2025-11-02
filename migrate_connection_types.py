"""
Migrate connection types to standardized values
"""
from suiteview.data.database import get_database

def migrate_types():
    """Update connection types to use standardized values"""
    db = get_database()
    conn = db.connection
    cursor = conn.cursor()
    
    # Type mappings
    type_updates = {
        'MS Access': 'ACCESS',
        'Local ODBC': 'SQL_SERVER',  # We'll check DB type to determine if SQL or DB2
        'EXCEL': 'EXCEL',
        'CSV': 'CSV',
        'ACCESS': 'ACCESS',
        'DB2': 'DB2',
        'FIXED_WIDTH': 'FIXED_WIDTH'
    }
    
    # Get all connections
    cursor.execute("SELECT connection_id, connection_name, connection_type, database_name, server_name FROM connections WHERE is_active = 1")
    connections = cursor.fetchall()
    
    print("Current connections:")
    print("=" * 80)
    for conn_id, name, conn_type, db_name, server_name in connections:
        print(f"{conn_id:3}: {name:35} Type: {conn_type:20}")
    
    print("\n" + "=" * 80)
    print("Migration Plan:")
    print("=" * 80)
    
    updates_needed = []
    for conn_id, name, conn_type, db_name, server_name in connections:
        # Determine new type
        if conn_type == 'MS Access':
            new_type = 'ACCESS'
            updates_needed.append((new_type, conn_id, name, conn_type))
        elif conn_type == 'Local ODBC':
            # Check database_name or server_name to determine if SQL or DB2
            # If DB2 is in the name, it's DB2, otherwise SQL_SERVER
            if 'DB2' in name.upper() or 'DB2' in str(db_name).upper() or 'DB2' in str(server_name).upper():
                new_type = 'DB2'
            else:
                new_type = 'SQL_SERVER'
            updates_needed.append((new_type, conn_id, name, conn_type))
        elif conn_type in ['Excel File', 'EXCEL']:
            if conn_type != 'EXCEL':
                new_type = 'EXCEL'
                updates_needed.append((new_type, conn_id, name, conn_type))
        elif conn_type in ['CSV File', 'CSV']:
            if conn_type != 'CSV':
                new_type = 'CSV'
                updates_needed.append((new_type, conn_id, name, conn_type))
        elif conn_type in ['Fixed Width File', 'FIXED_WIDTH']:
            if conn_type != 'FIXED_WIDTH':
                new_type = 'FIXED_WIDTH'
                updates_needed.append((new_type, conn_id, name, conn_type))
    
    if updates_needed:
        for new_type, conn_id, name, old_type in updates_needed:
            print(f"{conn_id:3}: {name:35} {old_type:20} -> {new_type}")
        
        print("\n" + "=" * 80)
        response = input("Apply these changes? (yes/no): ")
        
        if response.lower() == 'yes':
            for new_type, conn_id, name, old_type in updates_needed:
                cursor.execute(
                    "UPDATE connections SET connection_type = ? WHERE connection_id = ?",
                    (new_type, conn_id)
                )
                print(f"✓ Updated {name}")
            
            conn.commit()
            print("\n✓ Migration complete!")
        else:
            print("\nMigration cancelled.")
    else:
        print("No updates needed - all connection types are already standardized.")
    
    conn.close()

if __name__ == '__main__':
    migrate_types()
