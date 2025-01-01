"""Summary statistics for the trend figures.

Locations are the unit of analysis: intervals describe how much locations differ, so
they reflect how well the dam vs non-dam averages are known rather than seasonality.
"""

import math

import numpy as np
from scipy import stats


def t_interval(values, confidence=0.95):
    """Confidence interval for the mean of ``values`` using the t-distribution.

    Returns (low, high). NaNs are ignored; a single value gives a zero-width interval
    and no values give (nan, nan).
    """
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    n = arr.size
    if n == 0:
        return float("nan"), float("nan")

    mean = float(arr.mean())
    if n == 1:
        return mean, mean

    half = stats.t.ppf((1 + confidence) / 2, df=n - 1) * arr.std(ddof=1) / math.sqrt(n)
    return mean - float(half), mean + float(half)


def location_means(df, metric, months, id_col="id_property"):
    """Average ``metric`` over ``months`` for each location, skipping missing values."""
    selected = df[df["Image_month"].isin(months)]
    return selected.groupby(id_col)[metric].mean().dropna()


def missing_months_by_metric(df, months, metrics, id_col="id_property"):
    """Months in which at least one location has no value, per metric.

    A month counts as missing for a location whether its row is absent (no imagery at
    all) or the metric is null (e.g. no usable Landsat for LST). Metrics with no gaps
    are omitted, so an empty dict means complete coverage.
    """
    locations = df[id_col].nunique()
    gaps = {}
    for metric in metrics:
        if metric in df.columns:
            present = df.dropna(subset=[metric]).groupby("Image_month")[id_col].nunique()
        else:
            present = {}
        missing = [m for m in sorted(months) if present.get(m, 0) < locations]
        if missing:
            gaps[metric] = missing
    return gaps
