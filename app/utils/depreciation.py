"""
Depreciation calculation utility.

Supports:
  - Straight-line depreciation
  - Declining (reducing) balance depreciation

Usage:
    from utils.depreciation import calculate_straight_line, calculate_declining_balance,
                                   calculate_current_value, get_depreciation_schedule
"""

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP


def _years_elapsed(purchase_date_str: str) -> float:
    """Return fractional years elapsed since purchase_date_str (YYYY-MM-DD)."""
    try:
        if isinstance(purchase_date_str, (date, datetime)):
            purchase = purchase_date_str if isinstance(purchase_date_str, date) else purchase_date_str.date()
        else:
            purchase = date.fromisoformat(str(purchase_date_str))
        today = date.today()
        delta_days = (today - purchase).days
        return max(delta_days / 365.25, 0)
    except (ValueError, TypeError):
        return 0.0


def calculate_straight_line(
    cost: float,
    salvage_value: float = 0.0,
    useful_life_years: int = 5,
) -> dict:
    """
    Straight-line depreciation schedule.

    Args:
        cost: Original purchase price.
        salvage_value: Residual value at end of life.
        useful_life_years: Expected lifespan in years.

    Returns:
        dict with keys: method, annual_depreciation, salvage_value, schedule
    """
    cost = float(cost)
    salvage_value = float(salvage_value)
    useful_life_years = max(int(useful_life_years), 1)

    depreciable_amount = max(cost - salvage_value, 0)
    annual_dep = depreciable_amount / useful_life_years

    schedule = []
    book_value = cost
    for year in range(1, useful_life_years + 1):
        dep_this_year = min(annual_dep, book_value - salvage_value)
        dep_this_year = max(dep_this_year, 0)
        book_value = max(book_value - dep_this_year, salvage_value)
        schedule.append({
            "year": year,
            "depreciation": round(dep_this_year, 2),
            "book_value": round(book_value, 2),
            "accumulated_depreciation": round(cost - book_value, 2),
        })

    return {
        "method": "straight_line",
        "cost": round(cost, 2),
        "salvage_value": round(salvage_value, 2),
        "useful_life_years": useful_life_years,
        "annual_depreciation": round(annual_dep, 2),
        "total_depreciation": round(depreciable_amount, 2),
        "schedule": schedule,
    }


def calculate_declining_balance(
    cost: float,
    rate_percent: float = 20.0,
    useful_life_years: int = 5,
) -> dict:
    """
    Declining (reducing) balance depreciation schedule.

    Args:
        cost: Original purchase price.
        rate_percent: Annual depreciation rate as a percentage (e.g. 20 for 20%).
        useful_life_years: Number of years to show in schedule.

    Returns:
        dict with keys: method, rate_percent, schedule
    """
    cost = float(cost)
    rate = float(rate_percent) / 100.0
    useful_life_years = max(int(useful_life_years), 1)

    schedule = []
    book_value = cost
    total_depreciated = 0.0

    for year in range(1, useful_life_years + 1):
        dep_this_year = book_value * rate
        book_value = max(book_value - dep_this_year, 0)
        total_depreciated += dep_this_year
        schedule.append({
            "year": year,
            "depreciation": round(dep_this_year, 2),
            "book_value": round(book_value, 2),
            "accumulated_depreciation": round(total_depreciated, 2),
        })

    return {
        "method": "declining_balance",
        "cost": round(cost, 2),
        "rate_percent": round(rate_percent, 2),
        "useful_life_years": useful_life_years,
        "total_depreciation": round(total_depreciated, 2),
        "schedule": schedule,
    }


def calculate_current_value(
    cost: float,
    purchase_date_str,
    method: str = "straight_line",
    useful_life_years: int = 5,
    salvage_value: float = 0.0,
    rate_percent: float = 20.0,
) -> float:
    """
    Calculate current book value of an asset based on years elapsed.

    Args:
        cost: Original purchase price.
        purchase_date_str: Purchase date as 'YYYY-MM-DD' string or date object.
        method: 'straight_line' or 'declining_balance'.
        useful_life_years: Expected lifespan in years.
        salvage_value: Residual value (straight-line only).
        rate_percent: Annual rate % (declining balance only).

    Returns:
        Current book value as float.
    """
    cost = float(cost)
    years = _years_elapsed(purchase_date_str)
    whole_years = int(years)

    if method == "straight_line":
        salvage_value = float(salvage_value)
        annual_dep = (cost - salvage_value) / max(useful_life_years, 1)
        total_dep = annual_dep * min(whole_years, useful_life_years)
        return round(max(cost - total_dep, salvage_value), 2)

    elif method == "declining_balance":
        rate = float(rate_percent) / 100.0
        book_value = cost
        for _ in range(min(whole_years, useful_life_years)):
            book_value = book_value * (1 - rate)
        return round(max(book_value, 0), 2)

    # Unknown method — return cost unchanged
    return round(cost, 2)


def get_depreciation_schedule(asset: dict, method: str = "straight_line") -> dict:
    """
    Generate a full depreciation schedule for an asset dict.

    Args:
        asset: Dict with keys: purchase_price, purchase_date, depreciation_rate,
               and optionally: useful_life_years, salvage_value.
        method: 'straight_line' or 'declining_balance'.

    Returns:
        dict with schedule, current_value, and years_elapsed.
    """
    cost = float(asset.get("purchase_price") or 0)
    purchase_date = asset.get("purchase_date")
    rate_percent = float(asset.get("depreciation_rate") or 20)
    useful_life_years = int(asset.get("useful_life_years") or 5)
    salvage_value = float(asset.get("salvage_value") or 0)

    if cost <= 0:
        return {
            "error": "Asset has no purchase price",
            "schedule": [],
            "current_value": 0,
            "years_elapsed": 0,
        }

    years_elapsed = round(_years_elapsed(purchase_date), 2)

    if method == "straight_line":
        result = calculate_straight_line(cost, salvage_value, useful_life_years)
    else:
        result = calculate_declining_balance(cost, rate_percent, useful_life_years)

    current_value = calculate_current_value(
        cost=cost,
        purchase_date_str=purchase_date,
        method=method,
        useful_life_years=useful_life_years,
        salvage_value=salvage_value,
        rate_percent=rate_percent,
    )

    result["years_elapsed"] = years_elapsed
    result["current_value"] = current_value
    result["purchase_date"] = str(purchase_date) if purchase_date else None

    return result
