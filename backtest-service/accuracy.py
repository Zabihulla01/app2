import json
import os
from datetime import datetime, timezone

# ── Storage path ────────────────────────────────────────────────────────────
# /data is the volume mount defined in docker-compose.yml.
# Falls back to a local path so the service still works outside Docker.
FILE_PATH = "/data/prediction_history.json"

DEFAULT_EXPIRY_DAYS = 5   # trades older than this are auto-expired


# ── Helpers ─────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _days_since(iso_ts: str) -> float:
    """Return fractional days between an ISO timestamp and now."""
    try:
        dt = datetime.fromisoformat(iso_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return delta.total_seconds() / 86400.0
    except Exception:
        return 0.0


# ── Persistence ─────────────────────────────────────────────────────────────

def load_predictions() -> list:
    """Load all predictions from disk.  Returns [] on any error."""
    if not os.path.exists(FILE_PATH):
        return []
    try:
        with open(FILE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save_predictions(data: list) -> None:
    """Persist predictions to disk, keeping at most 1000 records."""
    if len(data) > 1000:
        data = data[-1000:]
    os.makedirs(os.path.dirname(FILE_PATH), exist_ok=True)
    with open(FILE_PATH, "w") as f:
        json.dump(data, f, indent=4)


# ── Track a new prediction ───────────────────────────────────────────────────

def save_prediction(prediction: dict) -> bool:
    """
    Persist a new prediction.

    New fields added (Phase 1):
      Status       – "OPEN" initially
      TrackedAt    – UTC ISO timestamp when first tracked
      LastChecked  – UTC ISO timestamp of the last status evaluation
      ResolvedAt   – UTC ISO timestamp when WIN/LOSS/EXPIRED, else null
      ExpiryDays   – max days before an OPEN trade is marked EXPIRED

    Returns False if the stock is already being tracked (duplicate guard).
    """
    data = load_predictions()

    # Duplicate guard – one open trade per stock
    for item in data:
        if (
            item.get("Stock") == prediction.get("Stock")
            and item.get("Status", "OPEN") == "OPEN"
        ):
            return False

    now = _now_iso()
    compact = {
        "Stock":      prediction["Stock"],
        "EntryPrice": prediction["EntryPrice"],
        "Target":     prediction["Target"],
        "StopLoss":   prediction["StopLoss"],
        "Mode":       prediction.get("Mode", "INTRADAY"),
        "Confidence": prediction.get("Confidence", 0),
        # ── Phase 1 new fields ──
        "Status":      "OPEN",
        "TrackedAt":   now,
        "LastChecked": now,
        "ResolvedAt":  None,
        "ExpiryDays":  DEFAULT_EXPIRY_DAYS,
    }

    data.append(compact)
    _save_predictions(data)
    return True


# ── Status evaluation (NO Yahoo Finance) ────────────────────────────────────

def check_prediction(prediction: dict) -> str:
    """
    Return the current status of a prediction using its persisted Status field.

    Rules (evaluated in order):
      1. Already resolved (WIN / LOSS / EXPIRED) → return persisted status.
      2. Older than ExpiryDays              → EXPIRED.
      3. Otherwise                          → OPEN.

    Yahoo Finance is intentionally NOT called here.
    Status is updated externally via /monitor or manual resolve.
    """
    persisted = prediction.get("Status", "OPEN")

    # Already closed – honour persisted value
    if persisted in ("WIN", "LOSS", "EXPIRED"):
        return persisted

    # Auto-expire based on age
    tracked_at = prediction.get("TrackedAt")
    expiry_days = prediction.get("ExpiryDays", DEFAULT_EXPIRY_DAYS)
    if tracked_at and _days_since(tracked_at) > expiry_days:
        return "EXPIRED"

    return "OPEN"


# ── Accuracy calculation (uses persisted Status only) ────────────────────────

def calculate_accuracy() -> dict:
    """
    Compute accuracy statistics from persisted Status fields.
    Does NOT call Yahoo Finance or any external service.
    """
    predictions = load_predictions()

    wins        = 0
    losses      = 0
    open_count  = 0
    expired     = 0

    for item in predictions:
        status = check_prediction(item)

        if status == "WIN":
            wins += 1
        elif status == "LOSS":
            losses += 1
        elif status == "EXPIRED":
            expired += 1
        else:
            open_count += 1

    total_closed = wins + losses
    accuracy = 0.0
    if total_closed > 0:
        accuracy = round((wins / total_closed) * 100, 2)

    return {
        "Accuracy": accuracy,
        "Wins":     wins,
        "Losses":   losses,
        "Open":     open_count,
        "Expired":  expired,
        "Total":    len(predictions),
    }


# ── Monitor: resolve trades from live price supplied by caller ───────────────

def resolve_prediction(stock: str, current_price: float) -> dict:
    """
    Evaluate a single tracked prediction against a supplied current_price and
    persist the updated Status.  Caller is responsible for fetching the price.

    Returns the updated prediction dict, or None if not found.
    """
    data = load_predictions()
    updated = None

    for item in data:
        if item.get("Stock") != stock:
            continue
        if item.get("Status", "OPEN") not in ("OPEN",):
            # Already resolved – nothing to do
            return item

        now = _now_iso()
        item["LastChecked"] = now

        if current_price >= item["Target"]:
            item["Status"]     = "WIN"
            item["ResolvedAt"] = now
        elif current_price <= item["StopLoss"]:
            item["Status"]     = "LOSS"
            item["ResolvedAt"] = now
        else:
            # Check expiry
            tracked_at   = item.get("TrackedAt")
            expiry_days  = item.get("ExpiryDays", DEFAULT_EXPIRY_DAYS)
            if tracked_at and _days_since(tracked_at) > expiry_days:
                item["Status"]     = "EXPIRED"
                item["ResolvedAt"] = now

        updated = item
        break

    if updated is not None:
        _save_predictions(data)

    return updated


# ── Open trades helper ───────────────────────────────────────────────────────

def get_open_trades() -> list:
    """Return all predictions whose Status is OPEN."""
    return [p for p in load_predictions() if check_prediction(p) == "OPEN"]


# ── Delete all prediction history ───────────────────────────────────────────

def clear_predictions() -> bool:
    """Wipe prediction_history.json.  Returns True on success."""
    try:
        _save_predictions([])
        return True
    except Exception:
        return False


# ── Phase 3: Mode-level accuracy ─────────────────────────────────────────────

def get_mode_accuracy() -> dict:
    """
    Break accuracy down by trading mode (INTRADAY / SWING).
    Returns per-mode win/loss counts and accuracy percentages.
    """
    predictions = load_predictions()

    modes: dict = {}

    for item in predictions:
        mode   = item.get("Mode", "INTRADAY")
        status = check_prediction(item)

        if mode not in modes:
            modes[mode] = {"wins": 0, "losses": 0, "open": 0, "expired": 0}

        if status == "WIN":
            modes[mode]["wins"] += 1
        elif status == "LOSS":
            modes[mode]["losses"] += 1
        elif status == "EXPIRED":
            modes[mode]["expired"] += 1
        else:
            modes[mode]["open"] += 1

    result = {}
    for mode, counts in modes.items():
        closed   = counts["wins"] + counts["losses"]
        accuracy = round((counts["wins"] / closed) * 100, 2) if closed > 0 else 0.0
        result[mode] = {
            "Wins":     counts["wins"],
            "Losses":   counts["losses"],
            "Open":     counts["open"],
            "Expired":  counts["expired"],
            "Total":    counts["wins"] + counts["losses"] + counts["open"] + counts["expired"],
            "Accuracy": accuracy,
        }

    return result


# ── Phase 3: Accuracy trend timeline ─────────────────────────────────────────

def get_accuracy_trend(limit: int = 20) -> dict:
    """
    Return the last `limit` resolved (WIN/LOSS) predictions in chronological
    order together with a running-accuracy timeline.

    Running accuracy at position i = wins_so_far / (i + 1) * 100.
    """
    predictions = load_predictions()

    # Collect only resolved (WIN/LOSS) predictions, sorted by ResolvedAt
    resolved = [
        p for p in predictions
        if p.get("Status") in ("WIN", "LOSS") and p.get("ResolvedAt")
    ]

    # Sort by ResolvedAt ascending, then take the last `limit`
    resolved.sort(key=lambda p: p.get("ResolvedAt", ""))
    recent = resolved[-limit:]

    timeline   = []
    running_wins = 0

    for idx, p in enumerate(recent):
        if p["Status"] == "WIN":
            running_wins += 1
        running_acc = round((running_wins / (idx + 1)) * 100, 2)

        timeline.append({
            "index":          idx + 1,
            "Stock":          p["Stock"],
            "Status":         p["Status"],
            "Mode":           p.get("Mode", "INTRADAY"),
            "ResolvedAt":     p.get("ResolvedAt", ""),
            "RunningAccuracy": running_acc,
        })

    final_accuracy = round((running_wins / len(recent)) * 100, 2) if recent else 0.0

    return {
        "Timeline":       timeline,
        "FinalAccuracy":  final_accuracy,
        "ResolvedCount":  len(recent),
    }
