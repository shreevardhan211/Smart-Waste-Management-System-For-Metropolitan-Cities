# Smart Waste Management System for Metropolitan Cities

A full-stack IoT-simulated waste management dashboard. Garbage bins across a
city report fill level and weight; the system raises alerts, charts trends,
optimizes truck routes, and forecasts when bins will fill up — all using
realistic **simulated** sensor data, built so real hardware can be plugged in
later with minimal changes.

---

## 1. Folder Structure

```
smart-waste-management/
│
├── app.py                      # Flask app: all routes + API endpoints + simulator thread
├── requirements.txt            # Python dependencies
│
├── database/
│   ├── __init__.py
│   ├── db_setup.py             # SQLite schema, seeding, all DB read/write functions
│   └── waste_management.db     # Created automatically on first run
│
├── sensors/
│   ├── __init__.py
│   └── simulator.py            # Generates random fill-level / weight readings
│
├── optimization/
│   ├── __init__.py
│   ├── route_planner.py        # Nearest-neighbor route optimization (Haversine distance)
│   └── predictor.py            # Linear regression fill-level forecasting
│
├── templates/
│   └── index.html              # Single-page dashboard (Jinja2 template)
│
└── static/
    ├── css/
    │   └── style.css           # "City Operations Console" dark UI theme
    └── js/
        └── dashboard.js        # Fetches API data, renders cards/map/charts, auto-refresh
```

---

## 2. How the System Works

| Layer | Technology | Responsibility |
|---|---|---|
| Sensor simulation | `sensors/simulator.py` + background thread in `app.py` | Generates a new fill % and weight every 8s per bin, trending realistically (gradual fill + random "collection" resets) instead of pure noise |
| Database | SQLite (`database/db_setup.py`) | Stores bin metadata, time-series readings, and alerts |
| Backend API | Flask (`app.py`) | REST JSON endpoints consumed by the dashboard |
| Route optimization | `optimization/route_planner.py` | Nearest-neighbor heuristic + Haversine distance, starting from a depot, visiting all bins ≥70% fill in the shortest practical order |
| AI prediction | `optimization/predictor.py` | Ordinary least-squares linear regression on each bin's recent readings to forecast fill level N hours ahead and estimate "time until full" |
| Frontend | HTML/CSS/JS + Chart.js + Leaflet.js | Card-based dashboard, live map, trend charts, auto-refresh every 8 seconds |

### Designed for real IoT hardware later
- `POST /api/sensor-data` already accepts `{bin_id, fill_level, weight_kg}` —
  this is the exact endpoint a real ESP32/Arduino + ultrasonic + load-cell
  sensor would call. Test it yourself:
  ```bash
  curl -X POST http://127.0.0.1:5000/api/sensor-data \
    -H "Content-Type: application/json" \
    -d '{"bin_id": "BIN-001", "fill_level": 88.5, "weight_kg": 65.2}'
  ```
- All "fake sensor" logic lives in exactly one function
  (`sensors/simulator.py → generate_reading()`). To go live, stop calling
  that function and let real devices POST instead — nothing else changes.
- The database layer (`db_setup.py`) is the only file touching SQL, so
  swapping SQLite for PostgreSQL/TimescaleDB in production only requires
  editing that one file.

---

## 3. Features Implemented

**Scenarios**
- ✅ Optimized Waste Collection Routes — live nearest-neighbor route + map polyline + stop list
- ✅ Proactive Maintenance Alerts — auto-detects bins ≥80%, shows live alert banner, "Mark Collected" action
- ✅ Data-Driven Waste Insights — 7 days of seeded history + live city-wide trend chart + status donut chart

**Core features**
- Random fill level (0–100%) and weight (kg) simulation, trending realistically over time
- Alert system (warning ≥80%, critical ≥90%)
- Card-based dashboard, auto-refreshing every 8 seconds
- Live Leaflet.js map with color-coded bin markers + depot + route line
- Status colors: Green (0–40%), Yellow (40–70%), Red (70–100%)

**Bonus features**
- Route optimization using nearest-neighbor + real Haversine distance
- AI prediction: linear regression forecast of fill level 6h ahead, plus estimated "hours until full", shown both in the Insights panel and per-bin detail modal

---

## 4. Step-by-Step: How to Run

### Prerequisites
- Python 3.8+
- pip

### Steps

1. **Unzip / open the project folder**
   ```bash
   cd smart-waste-management
   ```

2. **(Recommended) Create a virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate        # Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the app**
   ```bash
   python app.py
   ```
   You should see:
   ```
   Smart Waste Management System - Starting Server
   Dashboard: http://127.0.0.1:5000
   ```
   The SQLite database (`database/waste_management.db`) and 7 days of
   seed history are created automatically on first run.

5. **Open the dashboard**
   Go to **http://127.0.0.1:5000** in your browser.

6. **Watch it work**
   - Bin cards, map markers, and charts update automatically every 8 seconds.
   - Click any bin card (or map marker) to open its detail view with history chart + AI prediction.
   - When a bin crosses 80%, an alert appears at the top — click **Mark Collected** to simulate a truck emptying it.
   - The **Collection Route Optimization** panel recalculates the best route across all bins currently over the threshold.

### Resetting the data
Delete `database/waste_management.db` and restart `python app.py` — it will reseed automatically.

---

## 5. Tech Stack Summary

| Category | Choice |
|---|---|
| Backend | Python, Flask |
| Database | SQLite |
| Frontend | HTML5, CSS3, vanilla JavaScript |
| Charts | Chart.js |
| Map | Leaflet.js + OpenStreetMap tiles (no API key needed) |
| Fonts | Space Grotesk (display), Inter (body), JetBrains Mono (data/labels) |
