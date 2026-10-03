"""
Script to assign roles to players in the reference database.
"""

import sqlite3
import sys
import os

from dotenv import load_dotenv
import psycopg2

load_dotenv()


def _mirror_role_to_postgres(player_id, role_value):
    """Best-effort mirror of a role assignment into the live Postgres DB
    that the bot/API actually reads at runtime -- squadrons_reference.db
    (this script's own db_path) was a one-time migration source
    (db/sqlite_migration.py) and nothing has read it live since, so a
    sqlite-only write here silently never reaches production. Row ids are
    shared 1:1 between the two stores (the migration preserves them
    unchanged), so player_id works against both without translation.
    Prints a warning instead of raising if Postgres is unreachable, so a
    correction still lands in sqlite even when Postgres is briefly down --
    callers should re-run this script once Postgres is back to pick up
    anything that only made it into sqlite."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Warning: DATABASE_URL not set -- role NOT mirrored to Postgres.")
        return
    try:
        conn = psycopg2.connect(database_url)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE ref_players SET primary_role = %s WHERE id = %s",
                    (role_value, player_id))
            conn.commit()
        finally:
            conn.close()
        print(f"Mirrored to Postgres: player id {player_id} -> {role_value}")
    except Exception as e:
        print(f"Warning: failed to mirror role to Postgres: {e}")


def list_players(db_path, limit=20, offset=0):
    """List players from the reference database"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT id, name, primary_role 
    FROM ref_players 
    ORDER BY name
    LIMIT ? OFFSET ?
    """, (limit, offset))
    
    rows = cursor.fetchall()
    
    print(f"\n{'ID':4} {'Name':25} {'Current Role':12}")
    print("-" * 45)
    for row in rows:
        role = row[2] if row[2] else "None"
        print(f"{row[0]:<4} {row[1]:<25} {role:<12}")
    
    conn.close()
    return rows

def assign_role(db_path, player_id, role):
    """Assign a role to a player"""
    valid_roles = [None, "Farmer", "Flex", "Support"]
    
    if role not in valid_roles and role.lower() != "none":
        print(f"Error: Invalid role '{role}'. Valid options are: {', '.join([r for r in valid_roles if r])}, None")
        return False
    
    role_value = None if role.lower() == "none" else role
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Verify player exists
    cursor.execute("SELECT name FROM ref_players WHERE id = ?", (player_id,))
    player = cursor.fetchone()
    
    if not player:
        print(f"Error: No player found with ID {player_id}")
        conn.close()
        return False
    
    # Update role
    cursor.execute("UPDATE ref_players SET primary_role = ? WHERE id = ?", (role_value, player_id))
    conn.commit()

    print(f"Role for player '{player[0]}' (ID: {player_id}) set to: {role_value}")

    conn.close()

    _mirror_role_to_postgres(player_id, role_value)
    return True

def assign_roles_interactive(db_path):
    """Interactive mode to assign roles to players"""
    offset = 0
    limit = 20
    
    while True:
        print("\n=== Assign Roles to Players ===")
        print("1. List next 20 players")
        print("2. Search for players by name")
        print("3. Assign role to a player")
        print("4. View players by role")
        print("5. Exit")
        
        choice = input("\nEnter your choice (1-5): ").strip()
        
        if choice == "1":
            # List next 20 players
            rows = list_players(db_path, limit, offset)
            if rows:
                offset += limit
            else:
                print("No more players to display. Resetting to beginning.")
                offset = 0
                
        elif choice == "2":
            # Search for players
            search_term = input("Enter player name to search (or part of it): ").strip()
            if not search_term:
                print("No search term provided.")
                continue
                
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
            SELECT id, name, primary_role 
            FROM ref_players 
            WHERE name LIKE ?
            ORDER BY name
            LIMIT 30
            """, (f"%{search_term}%",))
            
            rows = cursor.fetchall()
            
            if rows:
                print(f"\n{'ID':4} {'Name':25} {'Current Role':12}")
                print("-" * 45)
                for row in rows:
                    role = row[2] if row[2] else "None"
                    print(f"{row[0]:<4} {row[1]:<25} {role:<12}")
            else:
                print(f"No players found matching '{search_term}'")
                
            conn.close()
            
        elif choice == "3":
            # Assign role
            player_id = input("Enter player ID: ").strip()
            if not player_id.isdigit():
                print("Invalid player ID. Please enter a number.")
                continue
                
            print("\nValid roles: Farmer, Flex, Support, None")
            role = input("Enter role: ").strip()
            
            if role:
                # Capitalize first letter for consistency
                role = role[0].upper() + role[1:].lower()
                assign_role(db_path, int(player_id), role)
                
        elif choice == "4":
            # View players by role
            print("\nRoles: Farmer, Flex, Support, None")
            role = input("Enter role to view (or leave empty to see all): ").strip()
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            if role:
                # Capitalize first letter for consistency
                role = role[0].upper() + role[1:].lower()
                if role.lower() == "none":
                    cursor.execute("""
                    SELECT id, name, primary_role 
                    FROM ref_players 
                    WHERE primary_role IS NULL
                    ORDER BY name
                    LIMIT 50
                    """)
                else:
                    cursor.execute("""
                    SELECT id, name, primary_role 
                    FROM ref_players 
                    WHERE primary_role = ?
                    ORDER BY name
                    LIMIT 50
                    """, (role,))
            else:
                cursor.execute("""
                SELECT primary_role, COUNT(*) as count
                FROM ref_players
                GROUP BY primary_role
                ORDER BY count DESC
                """)
                
                rows = cursor.fetchall()
                print("\n=== Role Distribution ===")
                print(f"{'Role':12} {'Count':8}")
                print("-" * 22)
                for row in rows:
                    role_name = row[0] if row[0] else "None"
                    print(f"{role_name:<12} {row[1]:<8}")
                conn.close()
                continue
                
            rows = cursor.fetchall()
            
            if rows:
                print(f"\n{'ID':4} {'Name':25} {'Role':12}")
                print("-" * 45)
                for row in rows:
                    role = row[2] if row[2] else "None"
                    print(f"{row[0]:<4} {row[1]:<25} {role:<12}")
                print(f"\nFound {len(rows)} players")
            else:
                print(f"No players found with role '{role}'")
                
            conn.close()
                
        elif choice == "5":
            # Exit
            print("Exiting role assignment tool.")
            break
            
        else:
            print("Invalid choice. Please enter a number from 1-5.")

if __name__ == "__main__":
    db_path = "squadrons_reference.db"
    
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    
    if not os.path.exists(db_path):
        print(f"Error: Database file not found: {db_path}")
        sys.exit(1)
    
    # Check if primary_role column exists
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(ref_players)")
    columns = [col[1] for col in cursor.fetchall()]
    conn.close()
    
    if 'primary_role' not in columns:
        print(f"Error: 'primary_role' column not found in ref_players table.")
        print("Please run add_role_columns.py first to add the required columns.")
        sys.exit(1)
    
    # Interactive mode
    assign_roles_interactive(db_path)
