"""
database/db_setup.py
---------------------
Handles all SQLite database operations for the Smart Waste Management System.

WHY SQLite?
- Zero-config, file-based DB -> perfect for a demo / prototype.
- In production (real IoT deployment) you would swap this for PostgreSQL /
  TimescaleDB and point the same function signatures at it -- the rest of the
  app (app.py) never touches raw SQL directly, it only calls functions from
  this file. That separation is what makes the future hardware migration easy.

TABLES:
1. bins         -> static metadata about each bin (id, location, coordinates)
2. bin_readings -> time-series sensor data (fill %, weight, timestamp)
                   This is what would be populated by real sensors via
                   MQTT/HTTP in a production deployment.
"""

import sqlite3
import os
import random
from datetime import datetime, timedelta

# Absolute path so the DB is found no matter where the script is run from
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "waste_management.db")

# ---------------------------------------------------------------------------
# Simulated bin metadata (stand-in for a real city's bin inventory).
# In a real deployment this table would be populated once when a physical
# bin + sensor unit is installed and registered (e.g. via an admin panel
# or auto-registration when a new device ID pings the server for the
# first time).
# ---------------------------------------------------------------------------
BIN_LOCATIONS = [
    {"id": "BIN-001", "name": "MG Road Market",        "lat": 16.7050, "lng": 74.2433, "zone": "Central"},
    {"id": "BIN-002", "name": "Rajarampuri Square",    "lat": 16.6939, "lng": 74.2370, "zone": "Central"},
    {"id": "BIN-003", "name": "Shivaji University Gate","lat": 16.6991, "lng": 74.2424, "zone": "North"},
    {"id": "BIN-004", "name": "Bus Stand Complex",     "lat": 16.6912, "lng": 74.2356, "zone": "South"},
    {"id": "BIN-005", "name": "Rankala Lake Park",     "lat": 16.6943, "lng": 74.2280, "zone": "West"},
    {"id": "BIN-006", "name": "Kasba Bawda",           "lat": 16.6850, "lng": 74.2480, "zone": "South"},
    {"id": "BIN-007", "name": "Tarabai Park",          "lat": 16.7080, "lng": 74.2300, "zone": "North"},
    {"id": "BIN-008", "name": "Shahupuri Commercial",  "lat": 16.6970, "lng": 74.2330, "zone": "Central"},
]


def get_connection():
    """Return a new SQLite connection with row access by column name."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Create tables if they do not exist, and seed bin metadata + a bit of
    historical reading data so charts have something to show on first run.
    Safe to call every time the app starts (idempotent).
    """
    conn = get_connection()
    cur = conn.cursor()

    # --- bins: static info about each physical/simulated bin -------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bins (
            bin_id   TEXT PRIMARY KEY,
            name     TEXT NOT NULL,
            lat      REAL NOT NULL,
            lng      REAL NOT NULL,
            zone     TEXT NOT NULL,
            capacity_kg REAL DEFAULT 100.0
        )
    """)

    # --- bin_readings: time-series sensor data ----------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bin_readings (
            reading_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            bin_id      TEXT NOT NULL,
            fill_level  REAL NOT NULL,      -- percentage 0-100
            weight_kg   REAL NOT NULL,      -- kilograms
            status      TEXT NOT NULL,      -- 'green' | 'yellow' | 'red'
            timestamp   TEXT NOT NULL,      -- ISO format
            FOREIGN KEY (bin_id) REFERENCES bins (bin_id)
        )
    """)

    # --- alerts: log of full-bin alerts for dashboard / history -----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            alert_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            bin_id     TEXT NOT NULL,
            message    TEXT NOT NULL,
            severity   TEXT NOT NULL,       -- 'warning' | 'critical'
            timestamp  TEXT NOT NULL,
            resolved   INTEGER DEFAULT 0,
            FOREIGN KEY (bin_id) REFERENCES bins (bin_id)
        )
    """)

    conn.commit()

    # --- seed bin metadata (only if table is empty) -----------------------
    cur.execute("SELECT COUNT(*) AS c FROM bins")
    if cur.fetchone()["c"] == 0:
        for b in BIN_LOCATIONS:
            cur.execute(
                "INSERT INTO bins (bin_id, name, lat, lng, zone) VALUES (?, ?, ?, ?, ?)",
                (b["id"], b["name"], b["lat"], b["lng"], b["zone"])
            )
        conn.commit()

    # --- seed some historical readings so charts aren't empty on first run
    cur.execute("SELECT COUNT(*) AS c FROM bin_readings")
    if cur.fetchone()["c"] == 0:
        _seed_historical_readings(conn)

    conn.close()


def _status_from_level(fill_level):
    """Map a fill percentage to a traffic-light status string."""
    if fill_level >= 70:
        return "red"
    elif fill_level >= 40:
        return "yellow"
    else:
        return "green"


def _seed_historical_readings(conn):
    """
    Generate ~7 days of simulated historical readings (one every 2 hours)
    for every bin, so that the trend charts have realistic-looking data
    the very first time the dashboard is opened.
    """
    cur = conn.cursor()
    now = datetime.now()
    start = now - timedelta(days=7)

    for b in BIN_LOCATIONS:
        # Each bin starts at a random fill level and trends upward with
        # occasional resets (simulating a collection truck emptying it).
        fill = random.uniform(5, 25)
        t = start
        while t <= now:
            # Bin fills up gradually over time
            fill += random.uniform(0.5, 4.5)
            if fill >= 95 or random.random() < 0.03:
                fill = random.uniform(2, 10)  # collected -> emptied

            fill = max(0, min(100, fill))
            weight = round((fill / 100) * 80 + random.uniform(-3, 3), 1)  # capacity ~80kg
            weight = max(0, weight)
            status = _status_from_level(fill)

            cur.execute(
                """INSERT INTO bin_readings (bin_id, fill_level, weight_kg, status, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (b["id"], round(fill, 1), weight, status, t.isoformat())
            )
            t += timedelta(hours=2)

    conn.commit()


def insert_reading(bin_id, fill_level, weight_kg):
    """
    Insert a new sensor reading for a bin. This is the function that would
    be called by a real hardware webhook/MQTT subscriber in production --
    it doesn't care whether the data came from `random.uniform()` (as it
    does now) or a physical ultrasonic + load-cell sensor.
    """
    status = _status_from_level(fill_level)
    timestamp = datetime.now().isoformat()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO bin_readings (bin_id, fill_level, weight_kg, status, timestamp)
           VALUES (?, ?, ?, ?, ?)""",
        (bin_id, fill_level, weight_kg, status, timestamp)
    )

    # Auto-generate an alert if the bin just became full
    if fill_level >= 80:
        severity = "critical" if fill_level >= 90 else "warning"
        message = f"{bin_id} is at {fill_level:.0f}% capacity and needs collection."
        cur.execute(
            """INSERT INTO alerts (bin_id, message, severity, timestamp, resolved)
               VALUES (?, ?, ?, ?, 0)""",
            (bin_id, message, severity, timestamp)
        )

    conn.commit()
    conn.close()
    return status


def get_all_bins_with_latest_reading():
    """
    Return every bin joined with its most recent sensor reading.
    This single query powers the main dashboard cards + map markers.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT b.bin_id, b.name, b.lat, b.lng, b.zone, b.capacity_kg,
               r.fill_level, r.weight_kg, r.status, r.timestamp
        FROM bins b
        LEFT JOIN bin_readings r ON r.reading_id = (
            SELECT reading_id FROM bin_readings
            WHERE bin_id = b.bin_id
            ORDER BY timestamp DESC LIMIT 1
        )
        ORDER BY b.bin_id
    """)
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def get_history_for_bin(bin_id, limit=50):
    """Return the most recent N readings for a single bin, oldest first."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT fill_level, weight_kg, status, timestamp
        FROM bin_readings
        WHERE bin_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (bin_id, limit))
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return list(reversed(rows))  # oldest -> newest for chart plotting


def get_city_wide_trend(hours=48):
    """
    Return average fill level across ALL bins, bucketed by hour, for the
    last `hours` hours. Powers the city-wide trend chart.
    """
    conn = get_connection()
    cur = conn.cursor()
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    cur.execute("""
        SELECT timestamp, fill_level FROM bin_readings
        WHERE timestamp >= ?
        ORDER BY timestamp ASC
    """, (cutoff,))
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()

    # Bucket by hour (YYYY-MM-DDTHH)
    buckets = {}
    for row in rows:
        hour_key = row["timestamp"][:13]
        buckets.setdefault(hour_key, []).append(row["fill_level"])

    labels = sorted(buckets.keys())
    averages = [round(sum(buckets[k]) / len(buckets[k]), 1) for k in labels]
    # Make labels friendlier (just HH:00)
    friendly_labels = [f"{k[11:13]}:00" for k in labels]

    return {"labels": friendly_labels, "averages": averages}


def get_active_alerts(limit=20):
    """Return the most recent unresolved alerts."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT a.alert_id, a.bin_id, b.name AS bin_name, a.message,
               a.severity, a.timestamp
        FROM alerts a
        JOIN bins b ON b.bin_id = a.bin_id
        WHERE a.resolved = 0
        ORDER BY a.timestamp DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def resolve_alerts_for_bin(bin_id):
    """Mark all alerts for a bin as resolved (e.g. after it's been collected)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE alerts SET resolved = 1 WHERE bin_id = ? AND resolved = 0", (bin_id,))
    conn.commit()
    conn.close()


def get_all_bin_ids():
    """Helper used by the simulator to know which bins exist."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT bin_id FROM bins")
    ids = [row["bin_id"] for row in cur.fetchall()]
    conn.close()
    return ids
