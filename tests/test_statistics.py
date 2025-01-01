import math

import pandas as pd
import pytest

from service.statistics import location_means, missing_months_by_metric, t_interval


def test_t_interval_known_values():
    # mean 3, sample SD sqrt(2.5), n 5, t(0.975, 4) = 2.7764
    low, high = t_interval([1, 2, 3, 4, 5])
    half = 2.776445 * math.sqrt(2.5) / math.sqrt(5)
    assert low == pytest.approx(3 - half, rel=1e-5)
    assert high == pytest.approx(3 + half, rel=1e-5)


def test_t_interval_ignores_nan():
    assert t_interval([1, 2, 3, 4, 5, float("nan")]) == pytest.approx(t_interval([1, 2, 3, 4, 5]))


def test_t_interval_single_value_has_no_width():
    assert t_interval([2.5]) == (2.5, 2.5)


def test_t_interval_empty_is_nan():
    low, high = t_interval([])
    assert math.isnan(low) and math.isnan(high)


def test_location_means_averages_selected_months_per_location():
    df = pd.DataFrame(
        {
            "id_property": ["A", "A", "A", "B", "B", "B"],
            "Image_month": [6, 7, 8, 6, 7, 8],
            "NDVI": [0.2, 0.4, 0.9, 0.5, 0.7, 0.0],
        }
    )
    means = location_means(df, "NDVI", [6, 7])
    assert means.to_dict() == pytest.approx({"A": 0.3, "B": 0.6})


def test_location_means_skips_missing_values():
    df = pd.DataFrame(
        {
            "id_property": ["A", "A", "B"],
            "Image_month": [6, 7, 6],
            "NDVI": [0.2, None, None],
        }
    )
    assert location_means(df, "NDVI", [6, 7]).to_dict() == {"A": 0.2}


def test_missing_months_by_metric_reports_absent_rows_and_null_values():
    # A has no row for month 3 at all; B's LST is null in month 2; ET never present.
    df = pd.DataFrame(
        {
            "id_property": ["A", "A", "B", "B", "B"],
            "Image_month": [1, 2, 1, 2, 3],
            "NDVI": [0.1, 0.2, 0.3, 0.4, 0.5],
            "LST": [1.0, 2.0, 3.0, None, 5.0],
        }
    )
    gaps = missing_months_by_metric(df, [1, 2, 3], ["NDVI", "LST", "ET"])
    assert gaps == {"NDVI": [3], "LST": [2, 3], "ET": [1, 2, 3]}


def test_missing_months_by_metric_complete_data_has_no_gaps():
    df = pd.DataFrame({"id_property": ["A", "B"], "Image_month": [6, 6], "NDVI": [0.1, 0.2]})
    assert missing_months_by_metric(df, [6], ["NDVI"]) == {}
