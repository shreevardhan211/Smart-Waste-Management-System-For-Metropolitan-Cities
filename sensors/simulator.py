"""
sensors/simulator.py
---------------------
Simulates IoT sensor readings (ultrasonic fill-level sensor + load-cell
weight sensor) for every bin in the system.

REAL-HARDWARE MIGRATION NOTE:
------------------------------
In a real deployment, each physical bin would have:
  - An ultrasonic distance sensor (e.g. HC-SR04) measuring empty space
    from the lid -> converted to a fill percentage.
  - A load cell + HX711 amplifier measuring weight.
  - A microcontroller (ESP32/Arduino) pushing readings to this same
    Flask backend via a POST request to /api/sensor-data, OR via
    MQTT -> a small bridge service that calls db_setup.insert_reading().

Because all the "fake" sensor logic lives in ONE function
(`generate_reading`), swapping simulation for real hardware only means
replacing the body of that function (or, better, adding a new HTTP route
that real devices call directly) -- nothing else in the app changes.
"""

import random


def generate_reading(previous_fill_level=None, capacity_kg=80):
    """
    Generate one simulated sensor reading.

    If `previous_fill_level` is given, the new reading trends upward from
    it (mimicking a bin gradually filling with waste over time) with a
    small chance of a "collection event" that empties the bin -- this
    produces realistic-looking sawtooth data instead of pure random noise.

    Returns: (fill_level: float 0-100, weight_kg: float)
    """
    if previous_fill_level is None:
        fill_level = round(random.uniform(0, 100), 1)
    else:
        # 5% chance a collection truck just emptied this bin
        if previous_fill_level > 75 and random.random() < 0.15:
            fill_level = round(random.uniform(0, 10), 1)
        else:
            # Normal gradual increase, with small chance of going down a bit
            # (compaction, or sensor noise)
            delta = random.uniform(-1.5, 6.0)
            fill_level = previous_fill_level + delta
            fill_level = max(0, min(100, round(fill_level, 1)))

    # Weight roughly correlates with fill level but has its own noise
    # (different waste types have different densities)
    weight_kg = (fill_level / 100) * capacity_kg + random.uniform(-2.5, 2.5)
    weight_kg = round(max(0, weight_kg), 1)

    return fill_level, weight_kg


def generate_random_reading_independent():
    """
    Pure random reading with NO memory of previous state -- used the very
    first time a bin is read, or for quick demo/testing purposes.
    """
    fill_level = round(random.uniform(0, 100), 1)
    weight_kg = round((fill_level / 100) * 80 + random.uniform(-3, 3), 1)
    return fill_level, max(0, weight_kg)
