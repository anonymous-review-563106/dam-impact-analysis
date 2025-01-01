import pandas as pd

from pages.analyze_impacts import describe_month_gaps


def _alaska_like():
    """Two locations, Feb-Nov only; LST missing Feb, Mar, Nov; no ET column."""
    rows = []
    for loc in ("A", "B"):
        for m in range(2, 12):
            rows.append({"id_property": loc, "Image_month": m, "NDVI": 0.5, "NDWI_Green": -0.1,
                         "LST": None if m in (2, 3, 11) else 10.0})
    return pd.DataFrame(rows)


def test_reports_gaps_per_metric_and_missing_et():
    note = describe_month_gaps(_alaska_like(), range(1, 13))
    assert "NDVI, NDWI Green in Jan, Dec" in note
    assert "LST (°C) in Jan, Feb, Mar, Nov, Dec" in note
    assert "No ET data" in note and "contiguous US" in note


def test_only_selected_months_are_checked():
    df = _alaska_like()
    df["ET"] = 50.0
    assert describe_month_gaps(df, [6, 7, 8]) is None
