"""
optimization/predictor.py
---------------------------
Bonus feature: Basic AI prediction of a bin's FUTURE fill level using
linear regression over its recent historical readings.

WHY LINEAR REGRESSION (and not a heavier ML model)?
-----------------------------------------------------
Bin fill-level over short time windows is roughly linear (waste
accumulates at a fairly steady rate between collections), so a simple
ordinary-least-squares fit (y = mx + c) gives a useful, explainable
"time until full" estimate without needing scikit-learn, TensorFlow, or
any heavy dependency -- just pure Python math. This keeps the project
beginner-friendly while still demonstrating a genuine predictive feature
that could be swapped for a more sophisticated model (e.g. Prophet, an
LSTM, or scikit-learn's LinearRegression) later without changing the
function's interface.
"""

from datetime import datetime, timedelta


def _to_minutes_since_epoch(timestamp_str):
    """Convert an ISO timestamp string to minutes since epoch (float)."""
    dt = datetime.fromisoformat(timestamp_str)
    return dt.timestamp() / 60.0


def linear_regression(x_values, y_values):
    """
    Compute simple ordinary-least-squares linear regression.
    Returns (slope, intercept) such that y ≈ slope * x + intercept.
    """
    n = len(x_values)
    if n < 2:
        return 0.0, (y_values[0] if y_values else 0.0)

    mean_x = sum(x_values) / n
    mean_y = sum(y_values) / n

    numerator = sum((x_values[i] - mean_x) * (y_values[i] - mean_y) for i in range(n))
    denominator = sum((x_values[i] - mean_x) ** 2 for i in range(n))

    if denominator == 0:
        return 0.0, mean_y

    slope = numerator / denominator
    intercept = mean_y - slope * mean_x
    return slope, intercept


def predict_fill_level(history, hours_ahead=6):
    """
    Given a bin's reading history (list of dicts with 'timestamp' and
    'fill_level', oldest first), fit a linear trend on the most recent
    readings and predict the fill level `hours_ahead` hours from now.

    Also estimates "time until full" (when predicted fill level would
    cross 100%), which is highly actionable for proactive collection
    planning.

    Returns dict:
    {
        "current_level": float,
        "predicted_level": float,      # clamped 0-100
        "trend": "rising" | "falling" | "stable",
        "hours_until_full": float | None,
        "confidence": "low" | "medium" | "high"
    }
    """
    if not history or len(history) < 2:
        current = history[-1]["fill_level"] if history else 0
        return {
            "current_level": current,
            "predicted_level": current,
            "trend": "stable",
            "hours_until_full": None,
            "confidence": "low"
        }

    # Use only the most recent readings since the last "collection event"
    # (a sharp drop in fill level) so the regression reflects the CURRENT
    # filling cycle, not a sawtooth average across multiple cycles.
    recent = history[-1]
    cycle_data = [recent]
    for reading in reversed(history[:-1]):
        if reading["fill_level"] > cycle_data[-1]["fill_level"] + 15:
            # A big drop going backwards in time means a collection
            # happened right after this point -> stop here
            break
        cycle_data.append(reading)
    cycle_data.reverse()

    if len(cycle_data) < 2:
        cycle_data = history[-min(6, len(history)):]

    x_values = [_to_minutes_since_epoch(r["timestamp"]) for r in cycle_data]
    y_values = [r["fill_level"] for r in cycle_data]

    # Normalize x to start at 0 for numerical stability
    x0 = x_values[0]
    x_values = [x - x0 for x in x_values]

    slope, intercept = linear_regression(x_values, y_values)

    current_level = y_values[-1]
    future_x = x_values[-1] + (hours_ahead * 60)  # hours -> minutes
    predicted_level = slope * future_x + intercept
    predicted_level = max(0, min(100, round(predicted_level, 1)))

    # Trend classification
    if slope > 0.02:
        trend = "rising"
    elif slope < -0.02:
        trend = "falling"
    else:
        trend = "stable"

    # Time until full (only meaningful if rising)
    hours_until_full = None
    if slope > 0.001 and current_level < 100:
        minutes_until_full = (100 - intercept) / slope - x_values[-1]
        if minutes_until_full > 0:
            hours_until_full = round(minutes_until_full / 60, 1)

    confidence = "high" if len(cycle_data) >= 5 else ("medium" if len(cycle_data) >= 3 else "low")

    return {
        "current_level": current_level,
        "predicted_level": predicted_level,
        "trend": trend,
        "hours_until_full": hours_until_full,
        "confidence": confidence
    }
