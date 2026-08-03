"""
test_phase3_analytics.py
pytest coverage for Phase 3 Analytics Dashboard backend APIs:
  /dashboard_stats, /mode_accuracy, /accuracy_trend
"""

import sys, os, json, pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backtest-service"))

import importlib
main    = importlib.import_module("main")
accuracy_mod = importlib.import_module("accuracy")
client  = TestClient(main.app)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_predictions(*records):
    """Build a list of prediction dicts for mocking load_predictions().

    OPEN trades use datetime.now() as TrackedAt so check_prediction()
    does not auto-expire them (ExpiryDays=5, so any past date > 5 days
    ago would be classified EXPIRED, not OPEN).
    """
    from datetime import datetime, timezone
    now_iso  = datetime.now(timezone.utc).isoformat()

    defaults = {
        "EntryPrice": 100.0, "Target": 105.0, "StopLoss": 97.0,
        "Mode": "INTRADAY", "Confidence": 70,
        "TrackedAt":   now_iso,
        "LastChecked": now_iso,
        "ResolvedAt": None, "ExpiryDays": 5,
    }
    result = []
    for r in records:
        item = {**defaults, **r}
        result.append(item)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 1. /dashboard_stats
# ─────────────────────────────────────────────────────────────────────────────

class TestDashboardStats:

    def test_empty_history_returns_zeros(self):
        with patch.object(accuracy_mod, "load_predictions", return_value=[]):
            res = client.get("/dashboard_stats")
        assert res.status_code == 200
        data = res.json()
        assert data["Total"]    == 0
        assert data["Wins"]     == 0
        assert data["Losses"]   == 0
        assert data["Open"]     == 0
        assert data["Accuracy"] == 0.0

    def test_all_required_keys_present(self):
        with patch.object(accuracy_mod, "load_predictions", return_value=[]):
            res = client.get("/dashboard_stats")
        data = res.json()
        for key in ("Total", "Wins", "Losses", "Open", "Expired", "Accuracy"):
            assert key in data, f"Missing key: {key}"

    def test_win_loss_counts_are_correct(self):
        preds = _make_predictions(
            {"Stock": "A", "Status": "WIN",  "ResolvedAt": "2026-01-02T00:00:00+00:00"},
            {"Stock": "B", "Status": "WIN",  "ResolvedAt": "2026-01-03T00:00:00+00:00"},
            {"Stock": "C", "Status": "LOSS", "ResolvedAt": "2026-01-04T00:00:00+00:00"},
            {"Stock": "D", "Status": "OPEN", "ResolvedAt": None},
        )
        with patch.object(accuracy_mod, "load_predictions", return_value=preds):
            res = client.get("/dashboard_stats")
        data = res.json()
        assert data["Wins"]   == 2
        assert data["Losses"] == 1
        assert data["Open"]   == 1
        assert data["Total"]  == 4

    def test_accuracy_calculation(self):
        preds = _make_predictions(
            {"Stock": "A", "Status": "WIN",  "ResolvedAt": "2026-01-02T00:00:00+00:00"},
            {"Stock": "B", "Status": "WIN",  "ResolvedAt": "2026-01-03T00:00:00+00:00"},
            {"Stock": "C", "Status": "LOSS", "ResolvedAt": "2026-01-04T00:00:00+00:00"},
        )
        with patch.object(accuracy_mod, "load_predictions", return_value=preds):
            res = client.get("/dashboard_stats")
        data = res.json()
        # 2 wins / 3 closed = 66.67%
        assert abs(data["Accuracy"] - 66.67) < 0.1

    def test_expired_trades_counted_separately(self):
        preds = _make_predictions(
            {"Stock": "E", "Status": "EXPIRED", "ResolvedAt": "2026-01-05T00:00:00+00:00"},
        )
        with patch.object(accuracy_mod, "load_predictions", return_value=preds):
            res = client.get("/dashboard_stats")
        data = res.json()
        assert data["Expired"] == 1
        assert data["Wins"]    == 0


# ─────────────────────────────────────────────────────────────────────────────
# 2. /mode_accuracy
# ─────────────────────────────────────────────────────────────────────────────

class TestModeAccuracy:

    def test_empty_history_returns_empty_dict(self):
        with patch.object(accuracy_mod, "load_predictions", return_value=[]):
            res = client.get("/mode_accuracy")
        assert res.status_code == 200
        assert res.json() == {}

    def test_intraday_and_swing_separated(self):
        preds = _make_predictions(
            {"Stock": "A", "Mode": "INTRADAY", "Status": "WIN",  "ResolvedAt": "2026-01-02T00:00:00+00:00"},
            {"Stock": "B", "Mode": "INTRADAY", "Status": "LOSS", "ResolvedAt": "2026-01-03T00:00:00+00:00"},
            {"Stock": "C", "Mode": "SWING",    "Status": "WIN",  "ResolvedAt": "2026-01-04T00:00:00+00:00"},
            {"Stock": "D", "Mode": "SWING",    "Status": "WIN",  "ResolvedAt": "2026-01-05T00:00:00+00:00"},
        )
        with patch.object(accuracy_mod, "load_predictions", return_value=preds):
            res = client.get("/mode_accuracy")
        data = res.json()
        assert "INTRADAY" in data
        assert "SWING"    in data
        assert data["INTRADAY"]["Wins"]   == 1
        assert data["INTRADAY"]["Losses"] == 1
        assert data["SWING"]["Wins"]      == 2
        assert data["SWING"]["Losses"]    == 0

    def test_mode_accuracy_percentage(self):
        preds = _make_predictions(
            {"Stock": "A", "Mode": "INTRADAY", "Status": "WIN",  "ResolvedAt": "2026-01-02T00:00:00+00:00"},
            {"Stock": "B", "Mode": "INTRADAY", "Status": "WIN",  "ResolvedAt": "2026-01-03T00:00:00+00:00"},
            {"Stock": "C", "Mode": "INTRADAY", "Status": "WIN",  "ResolvedAt": "2026-01-04T00:00:00+00:00"},
            {"Stock": "D", "Mode": "INTRADAY", "Status": "LOSS", "ResolvedAt": "2026-01-05T00:00:00+00:00"},
        )
        with patch.object(accuracy_mod, "load_predictions", return_value=preds):
            res = client.get("/mode_accuracy")
        data = res.json()
        # 3 wins / 4 closed = 75%
        assert abs(data["INTRADAY"]["Accuracy"] - 75.0) < 0.1

    def test_mode_accuracy_keys_present(self):
        preds = _make_predictions(
            {"Stock": "A", "Mode": "SWING", "Status": "WIN", "ResolvedAt": "2026-01-02T00:00:00+00:00"},
        )
        with patch.object(accuracy_mod, "load_predictions", return_value=preds):
            res = client.get("/mode_accuracy")
        data = res.json()
        for key in ("Wins", "Losses", "Open", "Expired", "Total", "Accuracy"):
            assert key in data["SWING"], f"Missing key in mode result: {key}"

    def test_open_trades_not_counted_in_accuracy(self):
        preds = _make_predictions(
            {"Stock": "A", "Mode": "INTRADAY", "Status": "WIN",  "ResolvedAt": "2026-01-02T00:00:00+00:00"},
            {"Stock": "B", "Mode": "INTRADAY", "Status": "OPEN", "ResolvedAt": None},
        )
        with patch.object(accuracy_mod, "load_predictions", return_value=preds):
            res = client.get("/mode_accuracy")
        data = res.json()
        # Accuracy should be 100% (1 win / 1 closed), OPEN not counted
        assert data["INTRADAY"]["Accuracy"] == 100.0
        assert data["INTRADAY"]["Open"]     == 1


# ─────────────────────────────────────────────────────────────────────────────
# 3. /accuracy_trend
# ─────────────────────────────────────────────────────────────────────────────

class TestAccuracyTrend:

    def test_empty_history_returns_empty_timeline(self):
        with patch.object(accuracy_mod, "load_predictions", return_value=[]):
            res = client.get("/accuracy_trend")
        assert res.status_code == 200
        data = res.json()
        assert data["Timeline"]       == []
        assert data["ResolvedCount"]  == 0
        assert data["FinalAccuracy"]  == 0.0

    def test_all_required_keys_present(self):
        with patch.object(accuracy_mod, "load_predictions", return_value=[]):
            res = client.get("/accuracy_trend")
        data = res.json()
        for key in ("Timeline", "FinalAccuracy", "ResolvedCount"):
            assert key in data, f"Missing key: {key}"

    def test_only_resolved_trades_in_timeline(self):
        preds = _make_predictions(
            {"Stock": "A", "Status": "WIN",  "ResolvedAt": "2026-01-02T00:00:00+00:00"},
            {"Stock": "B", "Status": "OPEN", "ResolvedAt": None},
            {"Stock": "C", "Status": "LOSS", "ResolvedAt": "2026-01-03T00:00:00+00:00"},
        )
        with patch.object(accuracy_mod, "load_predictions", return_value=preds):
            res = client.get("/accuracy_trend")
        data = res.json()
        assert data["ResolvedCount"] == 2
        for entry in data["Timeline"]:
            assert entry["Status"] in ("WIN", "LOSS")

    def test_running_accuracy_is_correct(self):
        preds = _make_predictions(
            {"Stock": "A", "Status": "WIN",  "ResolvedAt": "2026-01-01T00:00:00+00:00"},
            {"Stock": "B", "Status": "WIN",  "ResolvedAt": "2026-01-02T00:00:00+00:00"},
            {"Stock": "C", "Status": "LOSS", "ResolvedAt": "2026-01-03T00:00:00+00:00"},
            {"Stock": "D", "Status": "WIN",  "ResolvedAt": "2026-01-04T00:00:00+00:00"},
        )
        with patch.object(accuracy_mod, "load_predictions", return_value=preds):
            res = client.get("/accuracy_trend")
        data = res.json()
        tl = data["Timeline"]
        # index 0: 1/1 = 100%
        assert tl[0]["RunningAccuracy"] == 100.0
        # index 1: 2/2 = 100%
        assert tl[1]["RunningAccuracy"] == 100.0
        # index 2: 2/3 = 66.67%
        assert abs(tl[2]["RunningAccuracy"] - 66.67) < 0.1
        # index 3: 3/4 = 75%
        assert abs(tl[3]["RunningAccuracy"] - 75.0) < 0.1

    def test_timeline_limit_respected(self):
        # 30 WIN predictions
        preds = _make_predictions(*[
            {"Stock": f"S{i}", "Status": "WIN",
             "ResolvedAt": f"2026-01-{i+1:02d}T00:00:00+00:00"}
            for i in range(30)
        ])
        with patch.object(accuracy_mod, "load_predictions", return_value=preds):
            res = client.get("/accuracy_trend?limit=10")
        data = res.json()
        assert data["ResolvedCount"] == 10
        assert len(data["Timeline"]) == 10

    def test_default_limit_is_20(self):
        preds = _make_predictions(*[
            {"Stock": f"S{i}", "Status": "WIN",
             "ResolvedAt": f"2026-01-{i+1:02d}T00:00:00+00:00"}
            for i in range(25)
        ])
        with patch.object(accuracy_mod, "load_predictions", return_value=preds):
            res = client.get("/accuracy_trend")
        data = res.json()
        assert data["ResolvedCount"] == 20

    def test_timeline_entries_have_required_keys(self):
        preds = _make_predictions(
            {"Stock": "A", "Status": "WIN", "ResolvedAt": "2026-01-01T00:00:00+00:00"},
        )
        with patch.object(accuracy_mod, "load_predictions", return_value=preds):
            res = client.get("/accuracy_trend")
        entry = res.json()["Timeline"][0]
        for key in ("index", "Stock", "Status", "Mode", "ResolvedAt", "RunningAccuracy"):
            assert key in entry, f"Missing key in timeline entry: {key}"

    def test_limit_clamped_to_valid_range(self):
        """limit=0 and limit=9999 should both be clamped to 20."""
        with patch.object(accuracy_mod, "load_predictions", return_value=[]):
            res0    = client.get("/accuracy_trend?limit=0")
            res9999 = client.get("/accuracy_trend?limit=9999")
        assert res0.status_code    == 200
        assert res9999.status_code == 200

    def test_expired_trades_excluded_from_timeline(self):
        preds = _make_predictions(
            {"Stock": "A", "Status": "WIN",     "ResolvedAt": "2026-01-01T00:00:00+00:00"},
            {"Stock": "B", "Status": "EXPIRED", "ResolvedAt": "2026-01-02T00:00:00+00:00"},
        )
        with patch.object(accuracy_mod, "load_predictions", return_value=preds):
            res = client.get("/accuracy_trend")
        data = res.json()
        # EXPIRED should not appear in the timeline
        statuses = [e["Status"] for e in data["Timeline"]]
        assert "EXPIRED" not in statuses
        assert data["ResolvedCount"] == 1
