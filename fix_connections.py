"""Script to check and fix connection database issues"""

from suiteview.data.database import get_database

def check_connections():
    """Check all connections in database including inactive ones"""
    db = get_database()
    
    # Get ALL connections including inactive
    all_conns = db.fetchall("""
        SELECT connection_id, connection_name, connection_type, is_active, 
               database_name, server_name, connection_string
        FROM connections
        ORDER BY is_active DESC, connection_name
    """)
    
    print(f"\n{'='*80}")
    print(f"Total connections in database: {len(all_conns)}")
    print(f"{'='*80}\n")
    
    for conn in all_conns:
        status = "ACTIVE" if conn[3] else "INACTIVE"
        print(f"ID: {conn[0]:3} | Status: {status:8} | Name: {conn[1]:30} | Type: {conn[2]:12}")
        if conn[4]:  # database_name
            print(f"          Database: {conn[4]}")
        if conn[5]:  # server_name
            print(f"          Server: {conn[5]}")
        if conn[6]:  # connection_string
            print(f"          Connection String: {conn[6][:50]}...")
        print()
    
    # Check for duplicates by name
    print(f"\n{'='*80}")
    print("Checking for duplicate connection names...")
    print(f"{'='*80}\n")
    
    name_counts = db.fetchall("""
        SELECT connection_name, COUNT(*) as count
        FROM connections
        GROUP BY connection_name
        HAVING count > 1
    """)
    
    if name_counts:
        print("Found duplicate connection names:")
        for name, count in name_counts:
            print(f"  '{name}' appears {count} times")
            
            # Show details of duplicates
            dupes = db.fetchall("""
                SELECT connection_id, is_active, created_at
                FROM connections
                WHERE connection_name = ?
                ORDER BY created_at DESC
            """, (name,))
            
            for dupe in dupes:
                status = "ACTIVE" if dupe[1] else "INACTIVE"
                print(f"    - ID: {dupe[0]}, Status: {status}, Created: {dupe[2]}")
    else:
        print("No duplicate connection names found.")

def delete_inactive_connections():
    """Delete all inactive connections"""
    db = get_database()
    
    inactive = db.fetchall("""
        SELECT connection_id, connection_name
        FROM connections
        WHERE is_active = 0
    """)
    
    if not inactive:
        print("\nNo inactive connections to delete.")
        return
    
    print(f"\n{'='*80}")
    print(f"Found {len(inactive)} inactive connections:")
    print(f"{'='*80}\n")
    
    for conn_id, conn_name in inactive:
        print(f"  - ID: {conn_id}, Name: {conn_name}")
    
    response = input("\nDelete all inactive connections? (yes/no): ")
    if response.lower() == 'yes':
        db.execute("DELETE FROM connections WHERE is_active = 0")
        print(f"\nDeleted {len(inactive)} inactive connections.")
    else:
        print("\nNo changes made.")

def delete_specific_connection(name_or_id):
    """Delete a specific connection by name or ID"""
    db = get_database()
    
    # Try as ID first
    try:
        conn_id = int(name_or_id)
        conns = db.fetchall("""
            SELECT connection_id, connection_name, is_active
            FROM connections
            WHERE connection_id = ?
        """, (conn_id,))
    except ValueError:
        # Try as name
        conns = db.fetchall("""
            SELECT connection_id, connection_name, is_active
            FROM connections
            WHERE connection_name LIKE ?
        """, (f"%{name_or_id}%",))
    
    if not conns:
        print(f"\nNo connections found matching '{name_or_id}'")
        return
    
    print(f"\nFound {len(conns)} matching connection(s):")
    for conn_id, conn_name, is_active in conns:
        status = "ACTIVE" if is_active else "INACTIVE"
        print(f"  - ID: {conn_id}, Name: {conn_name}, Status: {status}")
    
    if len(conns) == 1:
        response = input(f"\nDelete this connection? (yes/no): ")
        if response.lower() == 'yes':
            db.execute("DELETE FROM connections WHERE connection_id = ?", (conns[0][0],))
            print(f"\nDeleted connection '{conns[0][1]}'")
    else:
        conn_id = input("\nEnter the connection ID to delete (or 'cancel'): ")
        if conn_id.lower() != 'cancel':
            try:
                conn_id = int(conn_id)
                db.execute("DELETE FROM connections WHERE connection_id = ?", (conn_id,))
                print(f"\nDeleted connection ID {conn_id}")
            except ValueError:
                print("\nInvalid ID. No changes made.")

if __name__ == "__main__":
    print("\n" + "="*80)
    print("Connection Database Check and Fix Tool")
    print("="*80)
    
    while True:
        print("\nOptions:")
        print("  1. Check all connections")
        print("  2. Delete all inactive connections")
        print("  3. Delete specific connection (by name or ID)")
        print("  4. Exit")
        
        choice = input("\nEnter choice (1-4): ")
        
        if choice == "1":
            check_connections()
        elif choice == "2":
            delete_inactive_connections()
        elif choice == "3":
            name_or_id = input("Enter connection name or ID: ")
            delete_specific_connection(name_or_id)
        elif choice == "4":
            print("\nExiting...")
            break
        else:
            print("\nInvalid choice.")
