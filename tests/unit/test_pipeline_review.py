"""
Tests for shared pipeline review functions (src/pipeline/review.py).

Covers:
- get_current_price: market-aware price fetching (Finnhub + yfinance for US, yfinance-only for JP)
- calculate_all_returns: return calculation with mock price_fetcher, was_picked logic, rate_limit_sleep
- log_return_summary: logging for error results, valid results, missed opportunities
"""
import pytest
from unittest.mock import MagicMock, patch, call

from src.pipeline.market_config import MarketConfig, US_MARKET, JP_MARKET
from src.pipeline.review import get_current_price, calculate_all_returns, log_return_summary


# ============================================================
# get_current_price Tests
# ============================================================


class TestGetCurrentPrice:
    """Tests for get_current_price."""

    def test_us_market_uses_finnhub_first(self):
        """US market (use_finnhub=True) tries Finnhub first and returns its price."""
        finnhub = MagicMock()
        yf_client = MagicMock()
        quote = MagicMock()
        quote.current_price = 150.0
        finnhub.get_quote.return_value = quote

        result = get_current_price("AAPL", US_MARKET, finnhub=finnhub, yf_client=yf_client)

        assert result == 150.0
        finnhub.get_quote.assert_called_once_with("AAPL")
        yf_client.get_quote.assert_not_called()

    def test_us_market_falls_back_to_yfinance_when_finnhub_fails(self):
        """US market falls back to yfinance when Finnhub raises an exception."""
        finnhub = MagicMock()
        finnhub.get_quote.side_effect = Exception("Finnhub API error")
        yf_client = MagicMock()
        yf_quote = MagicMock()
        yf_quote.current_price = 148.5
        yf_client.get_quote.return_value = yf_quote

        result = get_current_price("AAPL", US_MARKET, finnhub=finnhub, yf_client=yf_client)

        assert result == 148.5
        finnhub.get_quote.assert_called_once_with("AAPL")
        yf_client.get_quote.assert_called_once_with("AAPL")

    def test_us_market_falls_back_to_yfinance_when_finnhub_returns_zero(self):
        """US market falls back to yfinance when Finnhub returns price of 0."""
        finnhub = MagicMock()
        quote = MagicMock()
        quote.current_price = 0
        finnhub.get_quote.return_value = quote
        yf_client = MagicMock()
        yf_quote = MagicMock()
        yf_quote.current_price = 148.5
        yf_client.get_quote.return_value = yf_quote

        result = get_current_price("AAPL", US_MARKET, finnhub=finnhub, yf_client=yf_client)

        assert result == 148.5

    def test_us_market_falls_back_to_yfinance_when_finnhub_returns_none(self):
        """US market falls back to yfinance when Finnhub quote.current_price is None."""
        finnhub = MagicMock()
        quote = MagicMock()
        quote.current_price = None
        finnhub.get_quote.return_value = quote
        yf_client = MagicMock()
        yf_quote = MagicMock()
        yf_quote.current_price = 200.0
        yf_client.get_quote.return_value = yf_quote

        result = get_current_price("MSFT", US_MARKET, finnhub=finnhub, yf_client=yf_client)

        assert result == 200.0

    def test_jp_market_uses_yfinance_only(self):
        """JP market (use_finnhub=False) skips Finnhub and uses yfinance only."""
        finnhub = MagicMock()
        yf_client = MagicMock()
        yf_quote = MagicMock()
        yf_quote.current_price = 3500.0
        yf_client.get_quote.return_value = yf_quote

        result = get_current_price("7203.T", JP_MARKET, finnhub=finnhub, yf_client=yf_client)

        assert result == 3500.0
        finnhub.get_quote.assert_not_called()
        yf_client.get_quote.assert_called_once_with("7203.T")

    def test_jp_market_without_finnhub_client(self):
        """JP market works without a finnhub client being passed."""
        yf_client = MagicMock()
        yf_quote = MagicMock()
        yf_quote.current_price = 3500.0
        yf_client.get_quote.return_value = yf_quote

        result = get_current_price("7203.T", JP_MARKET, finnhub=None, yf_client=yf_client)

        assert result == 3500.0

    def test_both_fail_returns_none(self):
        """Returns None when both Finnhub and yfinance fail."""
        finnhub = MagicMock()
        finnhub.get_quote.side_effect = Exception("Finnhub down")
        yf_client = MagicMock()
        yf_client.get_quote.side_effect = Exception("yfinance down")

        result = get_current_price("AAPL", US_MARKET, finnhub=finnhub, yf_client=yf_client)

        assert result is None

    def test_no_clients_returns_none(self):
        """Returns None when no clients are provided."""
        result = get_current_price("AAPL", US_MARKET, finnhub=None, yf_client=None)

        assert result is None

    def test_yfinance_returns_none_quote(self):
        """Returns None when yfinance returns None for the quote object."""
        yf_client = MagicMock()
        yf_client.get_quote.return_value = None

        result = get_current_price("7203.T", JP_MARKET, yf_client=yf_client)

        assert result is None

    def test_yfinance_returns_zero_price(self):
        """Returns None when yfinance returns a price of 0."""
        yf_client = MagicMock()
        yf_quote = MagicMock()
        yf_quote.current_price = 0
        yf_client.get_quote.return_value = yf_quote

        result = get_current_price("BAD", JP_MARKET, yf_client=yf_client)

        assert result is None


# ============================================================
# calculate_all_returns Tests
# ============================================================


class TestCalculateAllReturns:
    """Tests for calculate_all_returns."""

    def _make_market_config(self, strategies=None, rate_limit_sleep=0.0):
        """Create a MarketConfig for testing with zero sleep by default."""
        return MarketConfig(
            v1_strategy_mode=(strategies or ["conservative", "aggressive"])[0],
            v2_strategy_mode=(strategies or ["conservative", "aggressive"])[1],
            market_type="us",
            benchmark_symbol="SPY",
            use_finnhub=True,
            rate_limit_sleep=rate_limit_sleep,
        )

    def _mock_supabase_scores(self, supabase, scores_by_strategy):
        """Set up mock supabase to return stock_scores for each strategy.

        Args:
            scores_by_strategy: dict mapping strategy_mode -> list of score dicts
        """
        def table_side_effect(table_name):
            mock_table = MagicMock()
            if table_name == "stock_scores":
                def select_side_effect(*args):
                    mock_select = MagicMock()
                    def eq_batch_date(field, value):
                        mock_eq1 = MagicMock()
                        def eq_strategy(field2, value2):
                            mock_eq2 = MagicMock()
                            mock_result = MagicMock()
                            mock_result.data = scores_by_strategy.get(value2, [])
                            mock_eq2.execute.return_value = mock_result
                            return mock_eq2
                        mock_eq1.eq = eq_strategy
                        return mock_eq1
                    mock_select.eq = eq_batch_date
                    return mock_select
                mock_table.select = select_side_effect
            elif table_name == "daily_picks":
                def select_side_effect(*args):
                    mock_select = MagicMock()
                    def eq_batch_date(field, value):
                        mock_eq1 = MagicMock()
                        def eq_strategy(field2, value2):
                            mock_eq2 = MagicMock()
                            mock_result = MagicMock()
                            mock_result.data = []
                            mock_eq2.execute.return_value = mock_result
                            return mock_eq2
                        mock_eq1.eq = eq_strategy
                        return mock_eq1
                    mock_select.eq = eq_batch_date
                    return mock_select
                mock_table.select = select_side_effect
            return mock_table
        supabase._client.table = table_side_effect

    def _mock_supabase_with_picks(self, supabase, scores_by_strategy, picks_by_strategy):
        """Set up mock supabase with both scores and picks data."""
        def table_side_effect(table_name):
            mock_table = MagicMock()
            if table_name == "stock_scores":
                def select_side_effect(*args):
                    mock_select = MagicMock()
                    def eq_batch_date(field, value):
                        mock_eq1 = MagicMock()
                        def eq_strategy(field2, value2):
                            mock_eq2 = MagicMock()
                            mock_result = MagicMock()
                            mock_result.data = scores_by_strategy.get(value2, [])
                            mock_eq2.execute.return_value = mock_result
                            return mock_eq2
                        mock_eq1.eq = eq_strategy
                        return mock_eq1
                    mock_select.eq = eq_batch_date
                    return mock_select
                mock_table.select = select_side_effect
            elif table_name == "daily_picks":
                def select_side_effect(*args):
                    mock_select = MagicMock()
                    def eq_batch_date(field, value):
                        mock_eq1 = MagicMock()
                        def eq_strategy(field2, value2):
                            mock_eq2 = MagicMock()
                            mock_result = MagicMock()
                            symbols = picks_by_strategy.get(value2)
                            if symbols is not None:
                                mock_result.data = [{"symbols": symbols}]
                            else:
                                mock_result.data = []
                            mock_eq2.execute.return_value = mock_result
                            return mock_eq2
                        mock_eq1.eq = eq_strategy
                        return mock_eq1
                    mock_select.eq = eq_batch_date
                    return mock_select
                mock_table.select = select_side_effect
            return mock_table
        supabase._client.table = table_side_effect

    def test_returns_error_when_no_scores_found(self):
        """Returns error dict when no scores exist for the check date."""
        supabase = MagicMock()
        config = self._make_market_config()
        self._mock_supabase_scores(supabase, {})

        price_fetcher = MagicMock()
        result = calculate_all_returns(price_fetcher, supabase, config, days_ago=5)

        assert "error" in result
        assert result["error"] == "No scores found"
        price_fetcher.assert_not_called()

    def test_calculates_return_correctly(self):
        """Verifies return percentage calculation: ((current - original) / original) * 100."""
        supabase = MagicMock()
        config = self._make_market_config()
        scores = {
            "conservative": [
                {
                    "symbol": "AAPL",
                    "strategy_mode": "conservative",
                    "price_at_time": 100.0,
                    "composite_score": 80,
                }
            ],
            "aggressive": [],
        }
        self._mock_supabase_scores(supabase, scores)
        supabase.bulk_update_returns = MagicMock(return_value=1)

        price_fetcher = MagicMock(return_value=110.0)
        result = calculate_all_returns(price_fetcher, supabase, config, days_ago=5)

        assert result["successful"] == 1
        assert result["failed"] == 0
        assert result["total_stocks"] == 1
        # Not picked (no picks data), so should be in not_picked_returns
        assert len(result["not_picked_returns"]) == 1
        assert result["not_picked_returns"][0]["return_pct"] == 10.0
        assert result["not_picked_returns"][0]["symbol"] == "AAPL"

    def test_was_picked_logic(self):
        """Stocks appearing in daily_picks are marked as picked in results."""
        supabase = MagicMock()
        config = self._make_market_config()
        scores = {
            "conservative": [
                {
                    "symbol": "AAPL",
                    "strategy_mode": "conservative",
                    "price_at_time": 100.0,
                    "composite_score": 85,
                },
                {
                    "symbol": "MSFT",
                    "strategy_mode": "conservative",
                    "price_at_time": 200.0,
                    "composite_score": 70,
                },
            ],
            "aggressive": [],
        }
        picks = {"conservative": ["AAPL"]}
        self._mock_supabase_with_picks(supabase, scores, picks)
        supabase.bulk_update_returns = MagicMock(return_value=2)

        price_fetcher = MagicMock(return_value=110.0)
        result = calculate_all_returns(price_fetcher, supabase, config, days_ago=5)

        assert result["successful"] == 2
        assert len(result["picked_returns"]) == 1
        assert result["picked_returns"][0]["symbol"] == "AAPL"
        assert len(result["not_picked_returns"]) == 1
        assert result["not_picked_returns"][0]["symbol"] == "MSFT"

    def test_missed_opportunities_detected(self):
        """Stocks not picked with return >= 3.0% are flagged as missed opportunities."""
        supabase = MagicMock()
        config = self._make_market_config()
        scores = {
            "conservative": [
                {
                    "symbol": "TSLA",
                    "strategy_mode": "conservative",
                    "price_at_time": 100.0,
                    "composite_score": 60,
                },
            ],
            "aggressive": [],
        }
        self._mock_supabase_scores(supabase, scores)
        supabase.bulk_update_returns = MagicMock(return_value=1)

        # 5% return >= 3% threshold
        price_fetcher = MagicMock(return_value=105.0)
        result = calculate_all_returns(price_fetcher, supabase, config, days_ago=5)

        assert len(result["missed_opportunities"]) == 1
        assert result["missed_opportunities"][0]["symbol"] == "TSLA"
        assert result["missed_opportunities"][0]["return_pct"] == 5.0

    def test_not_missed_when_return_below_threshold(self):
        """Stocks not picked with return < 3.0% are NOT flagged as missed opportunities."""
        supabase = MagicMock()
        config = self._make_market_config()
        scores = {
            "conservative": [
                {
                    "symbol": "IBM",
                    "strategy_mode": "conservative",
                    "price_at_time": 100.0,
                    "composite_score": 50,
                },
            ],
            "aggressive": [],
        }
        self._mock_supabase_scores(supabase, scores)
        supabase.bulk_update_returns = MagicMock(return_value=1)

        # 2% return < 3% threshold
        price_fetcher = MagicMock(return_value=102.0)
        result = calculate_all_returns(price_fetcher, supabase, config, days_ago=5)

        assert len(result["missed_opportunities"]) == 0
        assert len(result["not_picked_returns"]) == 1

    @patch("src.pipeline.review.time.sleep")
    def test_rate_limit_sleep_called(self, mock_sleep):
        """Verifies time.sleep is called with market_config.rate_limit_sleep for each stock."""
        supabase = MagicMock()
        config = self._make_market_config(rate_limit_sleep=0.5)
        scores = {
            "conservative": [
                {
                    "symbol": "AAPL",
                    "strategy_mode": "conservative",
                    "price_at_time": 100.0,
                    "composite_score": 80,
                },
                {
                    "symbol": "MSFT",
                    "strategy_mode": "conservative",
                    "price_at_time": 200.0,
                    "composite_score": 75,
                },
            ],
            "aggressive": [],
        }
        self._mock_supabase_scores(supabase, scores)
        supabase.bulk_update_returns = MagicMock(return_value=2)

        price_fetcher = MagicMock(return_value=110.0)
        calculate_all_returns(price_fetcher, supabase, config, days_ago=5)

        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(0.5)

    def test_skips_stock_with_zero_original_price(self):
        """Stocks with price_at_time <= 0 are skipped and counted as failed."""
        supabase = MagicMock()
        config = self._make_market_config()
        scores = {
            "conservative": [
                {
                    "symbol": "BAD",
                    "strategy_mode": "conservative",
                    "price_at_time": 0,
                    "composite_score": 50,
                },
            ],
            "aggressive": [],
        }
        self._mock_supabase_scores(supabase, scores)

        price_fetcher = MagicMock()
        result = calculate_all_returns(price_fetcher, supabase, config, days_ago=5)

        assert result["failed"] == 1
        assert result["successful"] == 0
        price_fetcher.assert_not_called()

    def test_skips_stock_when_price_fetcher_returns_none(self):
        """Stocks for which price_fetcher returns None are counted as failed."""
        supabase = MagicMock()
        config = self._make_market_config()
        scores = {
            "conservative": [
                {
                    "symbol": "DEAD",
                    "strategy_mode": "conservative",
                    "price_at_time": 100.0,
                    "composite_score": 50,
                },
            ],
            "aggressive": [],
        }
        self._mock_supabase_scores(supabase, scores)

        price_fetcher = MagicMock(return_value=None)
        result = calculate_all_returns(price_fetcher, supabase, config, days_ago=5)

        assert result["failed"] == 1
        assert result["successful"] == 0

    def test_return_field_1d_sets_correct_keys(self):
        """When return_field='1d', update entry uses return_1d and price_1d keys."""
        supabase = MagicMock()
        config = self._make_market_config()
        scores = {
            "conservative": [
                {
                    "symbol": "AAPL",
                    "strategy_mode": "conservative",
                    "price_at_time": 100.0,
                    "composite_score": 80,
                },
            ],
            "aggressive": [],
        }
        self._mock_supabase_scores(supabase, scores)
        supabase.bulk_update_returns = MagicMock(return_value=1)

        price_fetcher = MagicMock(return_value=105.0)
        calculate_all_returns(price_fetcher, supabase, config, days_ago=1, return_field="1d")

        # Check the update entry passed to bulk_update_returns
        update_call = supabase.bulk_update_returns.call_args[0][0]
        assert len(update_call) == 1
        entry = update_call[0]
        assert "return_1d" in entry
        assert "price_1d" in entry
        assert entry["return_1d"] == 5.0
        assert entry["price_1d"] == 105.0
        assert "return_5d" not in entry
        assert "price_5d" not in entry

    def test_return_field_5d_sets_correct_keys(self):
        """When return_field='5d', update entry uses return_5d and price_5d keys."""
        supabase = MagicMock()
        config = self._make_market_config()
        scores = {
            "conservative": [
                {
                    "symbol": "AAPL",
                    "strategy_mode": "conservative",
                    "price_at_time": 100.0,
                    "composite_score": 80,
                },
            ],
            "aggressive": [],
        }
        self._mock_supabase_scores(supabase, scores)
        supabase.bulk_update_returns = MagicMock(return_value=1)

        price_fetcher = MagicMock(return_value=110.0)
        calculate_all_returns(price_fetcher, supabase, config, days_ago=5, return_field="5d")

        update_call = supabase.bulk_update_returns.call_args[0][0]
        entry = update_call[0]
        assert "return_5d" in entry
        assert "price_5d" in entry
        assert entry["return_5d"] == 10.0
        assert entry["price_5d"] == 110.0

    def test_bulk_update_called_with_updates(self):
        """Verifies bulk_update_returns is called when there are successful updates."""
        supabase = MagicMock()
        config = self._make_market_config()
        scores = {
            "conservative": [
                {
                    "symbol": "AAPL",
                    "strategy_mode": "conservative",
                    "price_at_time": 100.0,
                    "composite_score": 80,
                },
            ],
            "aggressive": [],
        }
        self._mock_supabase_scores(supabase, scores)
        supabase.bulk_update_returns = MagicMock(return_value=1)

        price_fetcher = MagicMock(return_value=110.0)
        calculate_all_returns(price_fetcher, supabase, config, days_ago=5)

        supabase.bulk_update_returns.assert_called_once()

    def test_bulk_update_not_called_when_all_fail(self):
        """Verifies bulk_update_returns is NOT called when all stocks fail."""
        supabase = MagicMock()
        config = self._make_market_config()
        scores = {
            "conservative": [
                {
                    "symbol": "BAD",
                    "strategy_mode": "conservative",
                    "price_at_time": 0,
                    "composite_score": 50,
                },
            ],
            "aggressive": [],
        }
        self._mock_supabase_scores(supabase, scores)
        supabase.bulk_update_returns = MagicMock()

        price_fetcher = MagicMock()
        calculate_all_returns(price_fetcher, supabase, config, days_ago=5)

        supabase.bulk_update_returns.assert_not_called()

    def test_multiple_strategies_combined(self):
        """Scores from both strategies are combined in results."""
        supabase = MagicMock()
        config = self._make_market_config()
        scores = {
            "conservative": [
                {
                    "symbol": "AAPL",
                    "strategy_mode": "conservative",
                    "price_at_time": 100.0,
                    "composite_score": 80,
                },
            ],
            "aggressive": [
                {
                    "symbol": "TSLA",
                    "strategy_mode": "aggressive",
                    "price_at_time": 200.0,
                    "composite_score": 90,
                },
            ],
        }
        self._mock_supabase_scores(supabase, scores)
        supabase.bulk_update_returns = MagicMock(return_value=2)

        price_fetcher = MagicMock(return_value=220.0)
        result = calculate_all_returns(price_fetcher, supabase, config, days_ago=5)

        assert result["total_stocks"] == 2
        assert result["successful"] == 2

    def test_negative_return_calculation(self):
        """Verifies correct negative return when current price is below original."""
        supabase = MagicMock()
        config = self._make_market_config()
        scores = {
            "conservative": [
                {
                    "symbol": "LOSE",
                    "strategy_mode": "conservative",
                    "price_at_time": 100.0,
                    "composite_score": 60,
                },
            ],
            "aggressive": [],
        }
        self._mock_supabase_scores(supabase, scores)
        supabase.bulk_update_returns = MagicMock(return_value=1)

        price_fetcher = MagicMock(return_value=90.0)
        result = calculate_all_returns(price_fetcher, supabase, config, days_ago=5)

        assert result["not_picked_returns"][0]["return_pct"] == -10.0


# ============================================================
# log_return_summary Tests
# ============================================================


class TestLogReturnSummary:
    """Tests for log_return_summary."""

    def test_logs_warning_on_error_results(self, caplog):
        """When results contain an error key, logs a warning and returns early."""
        import logging
        with caplog.at_level(logging.WARNING, logger="src.pipeline.review"):
            log_return_summary({"error": "No scores found", "date": "2025-01-01"})

        assert any("No data for" in record.message for record in caplog.records)

    def test_logs_summary_for_valid_results(self, caplog):
        """Logs summary info for valid results with picked and not_picked stocks."""
        import logging
        results = {
            "successful": 10,
            "picked_returns": [
                {"symbol": "AAPL", "score": 80, "return_pct": 5.0},
                {"symbol": "MSFT", "score": 75, "return_pct": 3.0},
            ],
            "not_picked_returns": [
                {"symbol": "IBM", "score": 50, "return_pct": 1.0},
            ],
            "missed_opportunities": [],
        }

        with caplog.at_level(logging.INFO, logger="src.pipeline.review"):
            log_return_summary(results, label="5-day")

        messages = [r.message for r in caplog.records]
        assert any("5-day results summary" in m for m in messages)
        assert any("Total reviewed: 10" in m for m in messages)
        assert any("Picked stocks: 2" in m for m in messages)
        assert any("Not picked: 1" in m for m in messages)
        assert any("MISSED OPPORTUNITIES: 0" in m for m in messages)

    def test_logs_missed_opportunities_warning(self, caplog):
        """When missed opportunities exist, logs them as warnings with details."""
        import logging
        results = {
            "successful": 5,
            "picked_returns": [],
            "not_picked_returns": [
                {"symbol": "TSLA", "score": 65, "return_pct": 8.5},
                {"symbol": "NVDA", "score": 70, "return_pct": 12.3},
            ],
            "missed_opportunities": [
                {"symbol": "TSLA", "score": 65, "return_pct": 8.5},
                {"symbol": "NVDA", "score": 70, "return_pct": 12.3},
            ],
        }

        with caplog.at_level(logging.WARNING, logger="src.pipeline.review"):
            log_return_summary(results, label="5-day")

        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("MISSED OPPORTUNITIES DETECTED" in m for m in warning_messages)
        assert any("TSLA" in m for m in warning_messages)
        assert any("NVDA" in m for m in warning_messages)

    def test_missed_opportunities_limited_to_five(self, caplog):
        """Only the first 5 missed opportunities are logged."""
        import logging
        missed = [
            {"symbol": f"SYM{i}", "score": 60 + i, "return_pct": 5.0 + i}
            for i in range(8)
        ]
        results = {
            "successful": 10,
            "picked_returns": [],
            "not_picked_returns": missed,
            "missed_opportunities": missed,
        }

        with caplog.at_level(logging.WARNING, logger="src.pipeline.review"):
            log_return_summary(results, label="1-day")

        # Count how many missed symbol lines appear (each has "Score=" in the message)
        symbol_warnings = [
            r.message for r in caplog.records
            if "Score=" in r.message and r.levelno >= logging.WARNING
        ]
        assert len(symbol_warnings) == 5

    def test_custom_label(self, caplog):
        """The label parameter is used in the summary log."""
        import logging
        results = {
            "successful": 3,
            "picked_returns": [],
            "not_picked_returns": [],
            "missed_opportunities": [],
        }

        with caplog.at_level(logging.INFO, logger="src.pipeline.review"):
            log_return_summary(results, label="1-day")

        messages = [r.message for r in caplog.records]
        assert any("1-day results summary" in m for m in messages)

    def test_empty_results_no_crash(self, caplog):
        """Handles results with empty lists gracefully."""
        import logging
        results = {
            "successful": 0,
            "picked_returns": [],
            "not_picked_returns": [],
            "missed_opportunities": [],
        }

        with caplog.at_level(logging.INFO, logger="src.pipeline.review"):
            log_return_summary(results)

        messages = [r.message for r in caplog.records]
        assert any("Total reviewed: 0" in m for m in messages)
