import sqlite3
from flask import g

class Database:
    def __init__(self, db_name='sniffed_data.db'):
        self.db_name = db_name

    def get_connection(self):
        if 'db' not in g:
            g.db = sqlite3.connect(self.db_name)
        return g.db

    def create_tables(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DROP TABLE IF EXISTS sniffed_data')
            cursor.execute('DROP TABLE IF EXISTS sniffed_security')  # Drop the security table as well
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sniffed_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mac_address TEXT NOT NULL,
                    ssid TEXT NOT NULL,
                    signal_strength INTEGER,
                    latitude REAL,
                    longitude REAL,
                    client_number INTEGER,
                    security_type TEXT,
                    password TEXT,
                    is_wps BOOLEAN DEFAULT 0,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS security_types (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL UNIQUE
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sniffed_security (
                    sniffed_id INTEGER,
                    security_id INTEGER,
                    FOREIGN KEY (sniffed_id) REFERENCES sniffed_data(id),
                    FOREIGN KEY (security_id) REFERENCES security_types(id),
                    PRIMARY KEY (sniffed_id, security_id)
                )
            ''')
            conn.commit()

    def insert_data(self, mac_address, ssid, signal_strength, latitude, longitude, client_number, password, security_types, is_wep):
        # Convert security_types list to a comma-separated string
        if isinstance(security_types, list):
            security_types = ','.join(security_types)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sniffed_data (mac_address, ssid, signal_strength, latitude, longitude, client_number, security_type, password, is_wps)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (mac_address, ssid, signal_strength, latitude, longitude, client_number, security_types, password, is_wep))
            
            sniffed_id = cursor.lastrowid
            
            # Insert security types into the security_types table and link them
            for security_type in security_types.split(','):
                # Insert the security type if it doesn't already exist
                cursor.execute('''
                    INSERT OR IGNORE INTO security_types (type) VALUES (?)
                ''', (security_type,))
                
                # Get the security_id for the inserted or existing security type
                cursor.execute('''
                    SELECT id FROM security_types WHERE type = ?
                ''', (security_type,))
                security_id = cursor.fetchone()
                
                if security_id:
                    # Insert into the sniffed_security table if it doesn't already exist
                    try:
                        cursor.execute('''
                            INSERT INTO sniffed_security (sniffed_id, security_id)
                            VALUES (?, ?)
                        ''', (sniffed_id, security_id[0]))
                    except sqlite3.IntegrityError:
                        # Handle the case where the entry already exists
                        pass
            
            conn.commit()

    def fetch_all_data(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM sniffed_data')
            return cursor.fetchall()

    def close(self):
        db = g.pop('db', None)
        if db is not None:
            db.close()
