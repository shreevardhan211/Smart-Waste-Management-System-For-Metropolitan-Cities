"""
app.py
-------
Main Flask application for the Smart Waste Management System.

Run with:  python app.py
Then open: http://127.0.0.1:5000

ARCHITECTURE OVERVIEW
----------------------
- database/db_setup.py   -> all SQLite reads/writes (the only file that
                             touches SQL).
- sensors/simulator.py   -> generates fake sensor readings today; would be
                             replaced/supplemented by real hardware POSTing
                             to /api/sensor-data in production.
- optimization/route_planner.py -> nearest-neighbor route optimization.
- optimization/predictor.py     -> linear-regression fill-level forecasting.
- templates/index.html   -> the single-page dashboard (Jinja2 template).
- static/css, static/js  -> dashboard styling & client-side logic.

A background thread periodically calls the simulator + db_setup to mimic
sensors reporting in continuously, just like real devices would.
"""

from flask import Flask, render_template, jsonify, request
import threading
import time
import random

from database import db_setup
from sensors import simulator
from optimization import route_planner
from optimization import predictor

app = Flask(__name__)

# How often (seconds) the background simulator generates a new reading
# for each bin. Real hardware would push at its own interval instead.
SIMULATION_INTERVAL_SECONDS = 8


# ---------------------------------------------------------------------------
# Background simulation thread
# ---------------------------------------------------------------------------
def simulate_sensors_forever():
    """
    Runs in a background daemon thread. Every SIMULATION_INTERVAL_SECONDS,
    generates a new reading for each bin (based on its previous reading,
    so data trends realistically) and stores it in the database.

    This is the ONLY place "fake" data is generated continuously. To go
    live with real sensors, you would simply stop this thread (or leave
    it running for any bins that don't yet have hardware) and let real
    devices call POST /api/sensor-data instead.
    """
    while True:
        try:
            bins = db_setup.get_all_bins_with_latest_reading()
            for b in bins:
                prev_level = b["fill_level"]
                new_level, new_weight = simulator.generate_reading(
                    previous_fill_level=prev_level,
                    capacity_kg=b["capacity_kg"] or 80
                )
                db_setup.insert_reading(b["bin_id"], new_level, new_weight)
        except Exception as e:
            # In production this would log to a proper logger / monitoring
            print(f"[simulator] error: {e}")

        time.sleep(SIMULATION_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# Page route
# ---------------------------------------------------------------------------
@app.route("/")
def dashboard():
    """Render the main dashboard page (data is loaded client-side via API)."""
    return render_template("index.html")


# ---------------------------------------------------------------------------
# API: bins + readings
# ---------------------------------------------------------------------------
@app.route("/api/bins", methods=["GET"])
def api_get_bins():
    """
    Return all bins with their latest reading.
    Powers: dashboard cards, map markers, status summary.
    """
    bins = db_setup.get_all_bins_with_latest_reading()
    return jsonify({"success": True, "bins": bins, "count": len(bins)})


@app.route("/api/sensor-data", methods=["POST"])
def api_post_sensor_data():
    """
    Accepts a new sensor reading. This is the endpoint REAL hardware
    (ESP32 / Arduino / Raspberry Pi) would call in production:

        POST /api/sensor-data
        { "bin_id": "BIN-001", "fill_level": 73.5, "weight_kg": 41.2 }

    The simulator currently writes directly via db_setup for efficiency,
    but this route exists so the frontend (or external devices/tools) can
    also push readings manually, proving the system is hardware-ready.
    """
    data = request.get_json(force=True, silent=True) or {}
    bin_id = data.get("bin_id")
    fill_level = data.get("fill_level")
    weight_kg = data.get("weight_kg")

    if not bin_id or fill_level is None or weight_kg is None:
        return jsonify({"success": False, "error": "bin_id, fill_level, and weight_kg are required"}), 400

    try:
        fill_level = float(fill_level)
        weight_kg = float(weight_kg)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "fill_level and weight_kg must be numbers"}), 400

    status = db_setup.insert_reading(bin_id, fill_level, weight_kg)
    return jsonify({"success": True, "bin_id": bin_id, "status": status})


@app.route("/api/bins/<bin_id>/history", methods=["GET"])
def api_bin_history(bin_id):
    """Return historical readings for one bin (used for per-bin detail chart)."""
    limit = request.args.get("limit", default=50, type=int)
    history = db_setup.get_history_for_bin(bin_id, limit=limit)
    return jsonify({"success": True, "bin_id": bin_id, "history": history})


@app.route("/api/trends/city", methods=["GET"])
def api_city_trends():
    """Return city-wide average fill-level trend over time (for main chart)."""
    hours = request.args.get("hours", default=48, type=int)
    trend = db_setup.get_city_wide_trend(hours=hours)
    return jsonify({"success": True, **trend})


# ---------------------------------------------------------------------------
# API: alerts
# ---------------------------------------------------------------------------
@app.route("/api/alerts", methods=["GET"])
def api_get_alerts():
    """Return active (unresolved) alerts for bins that are full/near-full."""
    alerts = db_setup.get_active_alerts()
    return jsonify({"success": True, "alerts": alerts, "count": len(alerts)})


@app.route("/api/alerts/resolve/<bin_id>", methods=["POST"])
def api_resolve_alerts(bin_id):
    """Mark a bin's alerts as resolved (e.g. simulate truck having collected it)."""
    db_setup.resolve_alerts_for_bin(bin_id)
    # Also reset its fill level to simulate a real collection event
    db_setup.insert_reading(bin_id, round(random.uniform(2, 8), 1), round(random.uniform(1, 5), 1))
    return jsonify({"success": True, "bin_id": bin_id})


# ---------------------------------------------------------------------------
# API: route optimization (Scenario 1 + Bonus)
# ---------------------------------------------------------------------------
@app.route("/api/route/optimize", methods=["GET"])
def api_optimize_route():
    """
    Return an optimized collection route covering all bins currently above
    the collection threshold, using a nearest-neighbor heuristic starting
    from the depot.
    """
    threshold = request.args.get("threshold", default=route_planner.COLLECTION_THRESHOLD, type=float)
    bins = db_setup.get_all_bins_with_latest_reading()
    result = route_planner.optimize_route(bins, threshold=threshold)
    return jsonify({"success": True, **result})


# ---------------------------------------------------------------------------
# API: AI prediction (Bonus feature)
# ---------------------------------------------------------------------------
@app.route("/api/bins/<bin_id>/predict", methods=["GET"])
def api_predict_bin(bin_id):
    """
    Return a linear-regression-based forecast of a bin's fill level a few
    hours into the future, plus an estimated "time until full".
    """
    hours_ahead = request.args.get("hours", default=6, type=int)
    history = db_setup.get_history_for_bin(bin_id, limit=30)
    prediction = predictor.predict_fill_level(history, hours_ahead=hours_ahead)
    return jsonify({"success": True, "bin_id": bin_id, **prediction})


@app.route("/api/predict/all", methods=["GET"])
def api_predict_all():
    """Return predictions for every bin at once (used for the insights panel)."""
    bin_ids = db_setup.get_all_bin_ids()
    results = []
    for bin_id in bin_ids:
        history = db_setup.get_history_for_bin(bin_id, limit=30)
        pred = predictor.predict_fill_level(history, hours_ahead=6)
        results.append({"bin_id": bin_id, **pred})
    return jsonify({"success": True, "predictions": results})


# ---------------------------------------------------------------------------
# App entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Initialize DB (creates tables + seeds data if first run)
    db_setup.init_db()

    # Start the background sensor simulation thread
    sim_thread = threading.Thread(target=simulate_sensors_forever, daemon=True)
    sim_thread.start()

    print("=" * 60)
    print(" Smart Waste Management System - Starting Server")
    print(" Dashboard: http://127.0.0.1:5000")
    print("=" * 60)

    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
