"""
Tests for SupabaseClient (src/data/supabase_client.py).

Covers:
- get_scoring_config: normal return, None data, exception logging
- save_daily_picks_batch: batch save with market_type, delete_existing, error collection
- save_stock_scores: market_type inclusion/exclusion in upsert data
- get_unreviewed_batch: returns unreviewed batch, fallback on missing column
"""

import logging
import pytest
from unittest.mock import MagicMock, patch, call

from src.data.supabase_client import DailyPick, StockScore, SupabaseClient


# ─── Helpers ──────────────────────────────────────────────────


def _make_mock_config():
    """Create a mock config with supabase URL and keys."""
    mock_config = MagicMock()
    mock_config.supabase.url = "https://fake.supabase.co"
    mock_config.supabase.service_role_key = "fake-service-role-key"
    mock_config.supabase.anon_key = "fake-anon-key"
    return mock_config


def _build_client(mock_create_client, mock_config):
    """
    Instantiate SupabaseClient with mocked dependencies.
    Returns (client, mock_supabase_inner) where mock_supabase_inner
    is the mock returned by create_client (i.e. self._client).
    """
    mock_supabase_inner = MagicMock()
    mock_create_client.return_value = mock_supabase_inner

    client = SupabaseClient()

    mock_create_client.assert_called_once_with(
        "https://fake.supabase.co",
        "fake-service-role-key",
    )
    return client, mock_supabase_inner


def _make_daily_pick(**overrides):
    """Create a DailyPick with sensible defaults."""
    defaults = dict(
        batch_date="2025-06-01",
        symbols=["AAPL", "MSFT"],
        pick_count=2,
        market_regime="normal",
        strategy_mode="conservative",
        status="generated",
        market_type="us",
    )
    defaults.update(overrides)
    return DailyPick(**defaults)


def _make_stock_score(**overrides):
    """Create a StockScore with sensible defaults."""
    defaults = dict(
        batch_date="2025-06-01",
        symbol="AAPL",
        strategy_mode="conservative",
        trend_score=80,
        momentum_score=75,
        value_score=70,
        sentiment_score=65,
        composite_score=73,
        percentile_rank=85,
        reasoning="Strong fundamentals",
        price_at_time=190.50,
        market_regime_at_time="normal",
    )
    defaults.update(overrides)
    return StockScore(**defaults)


# ============================================================
# get_scoring_config
# ============================================================


@patch("src.data.supabase_client.config")
@patch("src.data.supabase_client.create_client")
class TestGetScoringConfig:
    """Tests for SupabaseClient.get_scoring_config()."""

    def test_returns_config_dict(self, mock_create_client, mock_config_module):
        """Normal path: single() returns a valid config dict."""
        mock_config_module.supabase = _make_mock_config().supabase
        client, mock_sb = _build_client(mock_create_client, mock_config_module)

        expected = {"threshold": 60.0, "max_picks": 5}
        mock_sb.table.return_value.select.return_value.eq.return_value \
            .single.return_value.execute.return_value.data = expected

        result = client.get_scoring_config("conservative")

        assert result == expected
        mock_sb.table.assert_called_with("scoring_config")

    def test_returns_empty_dict_when_data_is_none(
        self, mock_create_client, mock_config_module
    ):
        """When single() returns None data, return empty dict."""
        mock_config_module.supabase = _make_mock_config().supabase
        client, mock_sb = _build_client(mock_create_client, mock_config_module)

        mock_sb.table.return_value.select.return_value.eq.return_value \
            .single.return_value.execute.return_value.data = None

        result = client.get_scoring_config("aggressive")

        assert result == {}

    def test_exception_logs_debug_and_returns_empty(
        self, mock_create_client, mock_config_module
    ):
        """
        When single().execute() raises (e.g. no row found),
        the method should log via logger.debug and return {}.
        """
        mock_config_module.supabase = _make_mock_config().supabase
        client, mock_sb = _build_client(mock_create_client, mock_config_module)

        mock_sb.table.return_value.select.return_value.eq.return_value \
            .single.return_value.execute.side_effect = Exception("No rows")

        # Patch the logger used inside supabase_client module.
        # The module uses a bare `logger` name which is defined at module scope.
        with patch("src.data.supabase_client.logger", create=True) as mock_logger:
            result = client.get_scoring_config("conservative")

            assert result == {}
            mock_logger.debug.assert_called_once()
            logged_msg = mock_logger.debug.call_args[0][0]
            assert "No scoring_config for conservative" in logged_msg
            assert "No rows" in logged_msg


# ============================================================
# save_daily_picks_batch
# ============================================================


@patch("src.data.supabase_client.config")
@patch("src.data.supabase_client.create_client")
class TestSaveDailyPicksBatch:
    """Tests for SupabaseClient.save_daily_picks_batch()."""

    def test_empty_list_returns_empty(
        self, mock_create_client, mock_config_module
    ):
        """Passing an empty list returns ([], []) immediately."""
        mock_config_module.supabase = _make_mock_config().supabase
        client, _ = _build_client(mock_create_client, mock_config_module)

        saved, errors = client.save_daily_picks_batch([])

        assert saved == []
        assert errors == []

    def test_saves_picks_with_market_type(
        self, mock_create_client, mock_config_module
    ):
        """Batch save with market_type='us' passes through to save_daily_picks."""
        mock_config_module.supabase = _make_mock_config().supabase
        client, mock_sb = _build_client(mock_create_client, mock_config_module)

        pick1 = _make_daily_pick(strategy_mode="conservative", market_type="us")
        pick2 = _make_daily_pick(strategy_mode="aggressive", market_type="us")

        # Mock delete (delete_existing=True by default)
        mock_sb.table.return_value.delete.return_value.eq.return_value \
            .in_.return_value.execute.return_value.data = []

        # Mock upsert for each save_daily_picks call
        saved_record_1 = {"id": "1", "strategy_mode": "conservative"}
        saved_record_2 = {"id": "2", "strategy_mode": "aggressive"}
        mock_sb.table.return_value.upsert.return_value.execute.return_value \
            .data = [saved_record_1]

        # We need to return different data for successive calls
        mock_sb.table.return_value.upsert.return_value.execute.side_effect = [
            MagicMock(data=[saved_record_1]),
            MagicMock(data=[saved_record_2]),
        ]

        with patch("src.data.supabase_client.logger", create=True):
            saved, errors = client.save_daily_picks_batch([pick1, pick2])

        assert len(saved) == 2
        assert errors == []
        assert saved[0] == saved_record_1
        assert saved[1] == saved_record_2

    def test_delete_existing_false_skips_deletion(
        self, mock_create_client, mock_config_module
    ):
        """When delete_existing=False, delete_daily_picks_for_date is not called."""
        mock_config_module.supabase = _make_mock_config().supabase
        client, mock_sb = _build_client(mock_create_client, mock_config_module)

        pick = _make_daily_pick()
        saved_record = {"id": "1", "strategy_mode": "conservative"}
        mock_sb.table.return_value.upsert.return_value.execute.return_value \
            .data = [saved_record]

        with patch.object(client, "delete_daily_picks_for_date") as mock_delete:
            saved, errors = client.save_daily_picks_batch(
                [pick], delete_existing=False
            )

            mock_delete.assert_not_called()
            assert len(saved) == 1
            assert errors == []

    def test_delete_existing_true_calls_delete(
        self, mock_create_client, mock_config_module
    ):
        """When delete_existing=True, delete_daily_picks_for_date is called."""
        mock_config_module.supabase = _make_mock_config().supabase
        client, mock_sb = _build_client(mock_create_client, mock_config_module)

        pick = _make_daily_pick(strategy_mode="conservative")
        saved_record = {"id": "1", "strategy_mode": "conservative"}
        mock_sb.table.return_value.upsert.return_value.execute.return_value \
            .data = [saved_record]

        with patch.object(client, "delete_daily_picks_for_date") as mock_delete, \
             patch("src.data.supabase_client.logger", create=True):
            mock_delete.return_value = 1

            saved, errors = client.save_daily_picks_batch(
                [pick], delete_existing=True
            )

            mock_delete.assert_called_once_with("2025-06-01", ["conservative"])
            assert len(saved) == 1
            assert errors == []

    def test_error_in_save_collected(
        self, mock_create_client, mock_config_module
    ):
        """Errors during individual pick saves are collected, not raised."""
        mock_config_module.supabase = _make_mock_config().supabase
        client, mock_sb = _build_client(mock_create_client, mock_config_module)

        pick = _make_daily_pick(strategy_mode="aggressive")

        # Mock delete to succeed
        mock_sb.table.return_value.delete.return_value.eq.return_value \
            .in_.return_value.execute.return_value.data = []

        # Make upsert raise
        mock_sb.table.return_value.upsert.return_value.execute.side_effect = \
            Exception("DB connection lost")

        with patch("src.data.supabase_client.logger", create=True):
            saved, errors = client.save_daily_picks_batch([pick])

        assert saved == []
        assert len(errors) == 1
        assert "aggressive" in errors[0]
        assert "DB connection lost" in errors[0]

    def test_error_in_delete_collected_but_save_continues(
        self, mock_create_client, mock_config_module
    ):
        """If deletion fails, error is collected but saves still proceed."""
        mock_config_module.supabase = _make_mock_config().supabase
        client, mock_sb = _build_client(mock_create_client, mock_config_module)

        pick = _make_daily_pick()
        saved_record = {"id": "1", "strategy_mode": "conservative"}
        mock_sb.table.return_value.upsert.return_value.execute.return_value \
            .data = [saved_record]

        with patch.object(
            client, "delete_daily_picks_for_date",
            side_effect=Exception("Delete failed"),
        ), patch("src.data.supabase_client.logger", create=True):
            saved, errors = client.save_daily_picks_batch([pick])

        # Delete error is collected
        assert len(errors) == 1
        assert "delete" in errors[0].lower()
        # But save still proceeded
        assert len(saved) == 1


# ============================================================
# save_stock_scores
# ============================================================


@patch("src.data.supabase_client.config")
@patch("src.data.supabase_client.create_client")
class TestSaveStockScores:
    """Tests for SupabaseClient.save_stock_scores()."""

    def test_includes_market_type_when_set(
        self, mock_create_client, mock_config_module
    ):
        """When StockScore.market_type is set, it should appear in upsert data."""
        mock_config_module.supabase = _make_mock_config().supabase
        client, mock_sb = _build_client(mock_create_client, mock_config_module)

        score = _make_stock_score(market_type="us")
        mock_sb.table.return_value.upsert.return_value.execute.return_value \
            .data = [{"symbol": "AAPL"}]

        client.save_stock_scores([score])

        # Inspect the data passed to upsert
        upsert_call = mock_sb.table.return_value.upsert
        upsert_call.assert_called_once()
        upsert_data = upsert_call.call_args[0][0]

        assert len(upsert_data) == 1
        assert upsert_data[0]["market_type"] == "us"
        assert upsert_data[0]["symbol"] == "AAPL"

    def test_excludes_market_type_when_none(
        self, mock_create_client, mock_config_module
    ):
        """When StockScore.market_type is None, key should not be in upsert data."""
        mock_config_module.supabase = _make_mock_config().supabase
        client, mock_sb = _build_client(mock_create_client, mock_config_module)

        score = _make_stock_score(market_type=None)
        mock_sb.table.return_value.upsert.return_value.execute.return_value \
            .data = [{"symbol": "AAPL"}]

        client.save_stock_scores([score])

        upsert_data = mock_sb.table.return_value.upsert.call_args[0][0]
        assert "market_type" not in upsert_data[0]

    def test_v2_scores_included_when_present(
        self, mock_create_client, mock_config_module
    ):
        """V2 score fields are included and cast to int when present."""
        mock_config_module.supabase = _make_mock_config().supabase
        client, mock_sb = _build_client(mock_create_client, mock_config_module)

        score = _make_stock_score(
            momentum_12_1_score=88,
            breakout_score=72,
            catalyst_score=60,
            risk_adjusted_score=55,
        )
        mock_sb.table.return_value.upsert.return_value.execute.return_value \
            .data = [{"symbol": "AAPL"}]

        client.save_stock_scores([score])

        upsert_data = mock_sb.table.return_value.upsert.call_args[0][0]
        record = upsert_data[0]
        assert record["momentum_12_1_score"] == 88
        assert record["breakout_score"] == 72
        assert record["catalyst_score"] == 60
        assert record["risk_adjusted_score"] == 55

    def test_v2_scores_none_when_absent(
        self, mock_create_client, mock_config_module
    ):
        """V2 score fields are None when not set on StockScore."""
        mock_config_module.supabase = _make_mock_config().supabase
        client, mock_sb = _build_client(mock_create_client, mock_config_module)

        score = _make_stock_score()  # no V2 overrides
        mock_sb.table.return_value.upsert.return_value.execute.return_value \
            .data = [{"symbol": "AAPL"}]

        client.save_stock_scores([score])

        upsert_data = mock_sb.table.return_value.upsert.call_args[0][0]
        record = upsert_data[0]
        assert record["momentum_12_1_score"] is None
        assert record["breakout_score"] is None
        assert record["catalyst_score"] is None
        assert record["risk_adjusted_score"] is None

    def test_multiple_scores_batched(
        self, mock_create_client, mock_config_module
    ):
        """Multiple StockScores are batched into a single upsert call."""
        mock_config_module.supabase = _make_mock_config().supabase
        client, mock_sb = _build_client(mock_create_client, mock_config_module)

        scores = [
            _make_stock_score(symbol="AAPL"),
            _make_stock_score(symbol="MSFT", composite_score=80),
        ]
        mock_sb.table.return_value.upsert.return_value.execute.return_value \
            .data = [{"symbol": "AAPL"}, {"symbol": "MSFT"}]

        result = client.save_stock_scores(scores)

        upsert_data = mock_sb.table.return_value.upsert.call_args[0][0]
        assert len(upsert_data) == 2
        assert upsert_data[0]["symbol"] == "AAPL"
        assert upsert_data[1]["symbol"] == "MSFT"
        assert len(result) == 2

    def test_returns_empty_list_when_no_data(
        self, mock_create_client, mock_config_module
    ):
        """Returns empty list when upsert returns no data."""
        mock_config_module.supabase = _make_mock_config().supabase
        client, mock_sb = _build_client(mock_create_client, mock_config_module)

        score = _make_stock_score()
        mock_sb.table.return_value.upsert.return_value.execute.return_value \
            .data = []

        result = client.save_stock_scores([score])

        assert result == []

    def test_upsert_conflict_key(
        self, mock_create_client, mock_config_module
    ):
        """Upsert is called with the correct on_conflict key."""
        mock_config_module.supabase = _make_mock_config().supabase
        client, mock_sb = _build_client(mock_create_client, mock_config_module)

        score = _make_stock_score()
        mock_sb.table.return_value.upsert.return_value.execute.return_value \
            .data = []

        client.save_stock_scores([score])

        upsert_kwargs = mock_sb.table.return_value.upsert.call_args[1]
        assert upsert_kwargs["on_conflict"] == "batch_date,symbol,strategy_mode"


# ============================================================
# get_unreviewed_batch
# ============================================================


@patch("src.data.supabase_client.config")
@patch("src.data.supabase_client.create_client")
class TestGetUnreviewedBatch:
    """Tests for SupabaseClient.get_unreviewed_batch()."""

    def test_returns_unreviewed_batch(
        self, mock_create_client, mock_config_module
    ):
        """Normal path: returns the first unreviewed batch."""
        mock_config_module.supabase = _make_mock_config().supabase
        client, mock_sb = _build_client(mock_create_client, mock_config_module)

        expected = {
            "id": "uuid-123",
            "batch_date": "2025-06-01",
            "symbols": ["AAPL", "MSFT"],
            "pick_count": 2,
        }
        mock_sb.table.return_value.select.return_value \
            .eq.return_value.eq.return_value \
            .is_.return_value.order.return_value \
            .limit.return_value.execute.return_value.data = [expected]

        result = client.get_unreviewed_batch("conservative")

        assert result == expected
        mock_sb.table.assert_called_with("daily_picks")

    def test_returns_none_when_no_unreviewed(
        self, mock_create_client, mock_config_module
    ):
        """Returns None when there are no unreviewed batches."""
        mock_config_module.supabase = _make_mock_config().supabase
        client, mock_sb = _build_client(mock_create_client, mock_config_module)

        mock_sb.table.return_value.select.return_value \
            .eq.return_value.eq.return_value \
            .is_.return_value.order.return_value \
            .limit.return_value.execute.return_value.data = []

        result = client.get_unreviewed_batch("aggressive")

        assert result is None

    def test_fallback_when_reviewed_at_column_missing(
        self, mock_create_client, mock_config_module
    ):
        """
        If reviewed_at column doesn't exist (migration not applied),
        falls back to latest batch without the is_() filter.
        """
        mock_config_module.supabase = _make_mock_config().supabase
        client, mock_sb = _build_client(mock_create_client, mock_config_module)

        # First call (with is_ filter) raises because column doesn't exist
        column_error = Exception(
            'column "reviewed_at" does not exist'
        )
        mock_sb.table.return_value.select.return_value \
            .eq.return_value.eq.return_value \
            .is_.return_value.order.return_value \
            .limit.return_value.execute.side_effect = column_error

        # Fallback call (without is_ filter) succeeds
        fallback_result = {
            "id": "uuid-456",
            "batch_date": "2025-06-01",
            "symbols": ["GOOG"],
            "pick_count": 1,
        }
        mock_sb.table.return_value.select.return_value \
            .eq.return_value.eq.return_value \
            .order.return_value \
            .limit.return_value.execute.return_value.data = [fallback_result]

        result = client.get_unreviewed_batch("conservative")

        assert result == fallback_result

    def test_non_column_error_is_reraised(
        self, mock_create_client, mock_config_module
    ):
        """Non-column-related exceptions should be re-raised."""
        mock_config_module.supabase = _make_mock_config().supabase
        client, mock_sb = _build_client(mock_create_client, mock_config_module)

        mock_sb.table.return_value.select.return_value \
            .eq.return_value.eq.return_value \
            .is_.return_value.order.return_value \
            .limit.return_value.execute.side_effect = \
            Exception("Network timeout")

        with pytest.raises(Exception, match="Network timeout"):
            client.get_unreviewed_batch("conservative")
