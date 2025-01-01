"""
Utilities for loading external datasets such as National Hydrography Dataset (NHD).
"""

from typing import List

import ee

from service.constants import AppConstants
from service.earth_engine_auth import initialize_earth_engine

initialize_earth_engine()


def load_nhd_collections(state_names: List[str]) -> List[ee.FeatureCollection]:
    """
    Load NHD collections per state.
    """
    nhd_collections = []
    for state in state_names:
        state_code = AppConstants.STATE_CODES.get(state)
        if state_code:
            nhd_dataset = ee.FeatureCollection(f"projects/sat-io/open-datasets/NHD/NHD_{state_code}/NHDFlowline")
            nhd_collections.append(nhd_dataset)
    return nhd_collections
