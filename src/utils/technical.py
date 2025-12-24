"""Technical analysis utilities."""


def calculate_rsi(prices: list[float], period: int = 14) -> float:
    """
    Calculate RSI (Relative Strength Index) for a price series.

    Args:
        prices: List of closing prices (oldest to newest)
        period: RSI period (default 14)

    Returns:
        RSI value between 0 and 100
    """
    if len(prices) < period + 1:
        return 50.0  # Neutral when insufficient data

    gains = []
    losses = []

    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi
