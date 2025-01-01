"""
Constants and default values for the app.
"""


# pylint: disable=too-few-public-methods
class AppConstants:
    """simple container for constants and default values"""

    # Buffer settings
    DEFAULT_BUFFER_RADIUS = 150
    MIN_BUFFER_RADIUS = 1
    BUFFER_STEP = 1

    # Elevation band settings
    DEFAULT_ELEVATION_DISTANCE = 3
    ELEVATION_STEP = 1
    ELEVATION_DISTANCE_SUB = 10

    # Validation settings
    DEFAULT_MAX_DISTANCE = 50
    MIN_MAX_DISTANCE = 0
    DISTANCE_STEP = 10

    # Negative sampling
    DEFAULT_INNER_RADIUS = 300
    DEFAULT_OUTER_RADIUS = 500
    SAMPLING_SCALE = 10
    RADIUS_STEP = 50

    # Processing settings.
    # Earth Engine's per-request compute budget falls off a cliff for this pipeline:
    # measured on a 2017 run, 6+ points per request took 143-177s (at the timeout
    # boundary) while 5 or fewer took 9-21s. Keeping batches small is both faster
    # overall and what stops "Computation timed out" errors.
    BATCH_SIZE = 4
    MAX_RETRIES = 3
    RETRY_BACKOFF_SECONDS = 2

    # Locations x years x months computed beyond which we warn that a run is large
    # (720 = 60 location-years of full-year data). Past roughly this much work, a
    # Streamlit session may not stay connected long enough to finish, and results are
    # lost when it drops.
    LARGE_RUN_POINT_MONTHS = 720

    # UI settings
    MAP_WIDTH = 800
    MAP_HEIGHT = 600
    LARGE_MAP_WIDTH = 1200
    LARGE_MAP_HEIGHT = 700

    # Date formatting
    DEFAULT_DATE_SUFFIX = "-07-01"
    DATE_FORMAT = "YYYY"
    FORMATTED_DATE_FORMAT = "YYYYMMdd"

    # Session state defaults
    SESSION_DEFAULTS = {
        # Data collections
        "Positive_collection": None,
        "Dam_data": None,
        "Full_positive": None,
        "selected_waterway": None,
        "Merged_collection": None,
        "validation_results": None,
        "validation_summary": None,
        "analysis_coverage_warning": None,
        "analysis_mode": None,
        "analysis_point_count": None,
        "analysis_label": None,
        "df_lst": None,
        "fig": None,
        "plot_years": None,
        "plot_months": None,
        # Configuration
        "buffer_radius": DEFAULT_BUFFER_RADIUS,
        # Boolean flags
        "validation_complete": False,
        "use_all_dams": True,
        "show_non_dam_section": False,
        "buffer_complete": False,
        "dataset_loaded": False,
        "buffers_created": False,
        "visualization_complete": False,
        # Workflow state
        "validation_step": "initial",
    }

    STATE_CODES = {
        "Alabama": "AL",
        "Alaska": "AK",
        "Arizona": "AZ",
        "Arkansas": "AR",
        "California": "CA",
        "Colorado": "CO",
        "Connecticut": "CT",
        "Delaware": "DE",
        "Florida": "FL",
        "Georgia": "GA",
        "Hawaii": "HI",
        "Idaho": "ID",
        "Illinois": "IL",
        "Indiana": "IN",
        "Iowa": "IA",
        "Kansas": "KS",
        "Kentucky": "KY",
        "Louisiana": "LA",
        "Maine": "ME",
        "Maryland": "MD",
        "Massachusetts": "MA",
        "Michigan": "MI",
        "Minnesota": "MN",
        "Mississippi": "MS",
        "Missouri": "MO",
        "Montana": "MT",
        "Nebraska": "NE",
        "Nevada": "NV",
        "New Hampshire": "NH",
        "New Jersey": "NJ",
        "New Mexico": "NM",
        "New York": "NY",
        "North Carolina": "NC",
        "North Dakota": "ND",
        "Ohio": "OH",
        "Oklahoma": "OK",
        "Oregon": "OR",
        "Pennsylvania": "PA",
        "Rhode Island": "RI",
        "South Carolina": "SC",
        "South Dakota": "SD",
        "Tennessee": "TN",
        "Texas": "TX",
        "Utah": "UT",
        "Vermont": "VT",
        "Virginia": "VA",
        "Washington": "WA",
        "West Virginia": "WV",
        "Wisconsin": "WI",
        "Wyoming": "WY",
    }
