#!/usr/bin/env python3
"""
Test script to verify Apple Podcasts database access
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

def find_podcasts_database():
    """Find the Apple Podcasts database file."""
    # Apple Podcasts stores data in Group Containers
    group_containers = Path.home() / "Library" / "Group Containers"
    
    print(f"Looking in Group Containers: {group_containers}")
    
    # Look for the Podcasts group container
    for container in group_containers.glob("*podcasts*"):
        print(f"Found podcasts container: {container}")
        db_path = container / "Documents" / "MTLibrary.sqlite"
        if db_path.exists():
            print(f"Found database at: {db_path}")
            return db_path
    
    # Alternative location
    alt_path = Path.home() / "Library" / "Containers" / "com.apple.podcasts" / "Data" / "Documents" / "MTLibrary.sqlite"
    if alt_path.exists():
        print(f"Found database at alternative location: {alt_path}")
        return alt_path
    
    print("Database not found!")
    return None

def test_database_access(db_path):
    """Test database access and show available tables."""
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Get all table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"\nAvailable tables: {[table[0] for table in tables]}")
        
        # Try to get some episode data
        try:
            cursor.execute("SELECT COUNT(*) FROM ZMTEPISODE")
            episode_count = cursor.fetchone()[0]
            print(f"Total episodes in database: {episode_count}")
        except:
            print("Could not access ZMTEPISODE table")
        
        # Try to get some podcast data
        try:
            cursor.execute("SELECT COUNT(*) FROM ZMTPODCAST")
            podcast_count = cursor.fetchone()[0]
            print(f"Total podcasts in database: {podcast_count}")
        except:
            print("Could not access ZMTPODCAST table")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error accessing database: {e}")
        return False

def main():
    print("Testing Apple Podcasts database access...")
    
    db_path = find_podcasts_database()
    if db_path:
        test_database_access(db_path)
    else:
        print("Apple Podcasts database not found. Make sure you have the Podcasts app installed and have downloaded some episodes.")

if __name__ == "__main__":
    main()
