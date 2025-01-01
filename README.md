# Beaver Impacts Tool: Developer Guide

A Streamlit web app that quantifies the environmental impact of beaver dams by comparing
satellite-derived metrics (NDVI, NDWI, Land Surface Temperature, Evapotranspiration) at dam
sites versus nearby non-dam control sites, over the course of a year. All geospatial
computation runs on **Google Earth Engine (GEE)**; the app is a UI that orchestrates GEE calls.

## Table of Contents
1. [Local Setup](#local-setup)
2. [Architecture Overview](#architecture-overview)
3. [Code Structure](#code-structure)
4. [Earth Engine Authentication](#earth-engine-authentication)
5. [The Six-Step Workflow](#the-six-step-workflow)
6. [Data Processing Pipeline](#data-processing-pipeline)
7. [Batch Processing](#batch-processing)
8. [Adding New Features](#adding-new-features)

## Local Setup

Install dependencies (a virtual environment is recommended):
```commandline
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Authenticate with Google Earth Engine (opens a browser to grant permission):
```commandline
earthengine authenticate
```

Create a Google Cloud project (note its **project id**, which can differ from the name) at
https://console.cloud.google.com/, then enable the Earth Engine API for it
(https://console.cloud.google.com/apis/library/earthengine.googleapis.com) and register it
with Earth Engine (https://code.earthengine.google.com/register).

Copy the config template and add your project id:
```commandline
cp config.yaml.example config.yaml
```

Run the app (defaults to http://localhost:8501):
```commandline
streamlit run app.py
```

## Architecture Overview

Built on:
- **Streamlit** — web interface and per-session state
- **Google Earth Engine** — satellite imagery access and geospatial computation
- **geemap** — bridges Earth Engine results into pandas / maps
- **Pandas / NumPy** — data manipulation
- **Seaborn / Matplotlib** — plotting

The app is a step-by-step wizard. Data flows between steps as lazy `ee.FeatureCollection`
objects held in `st.session_state`; nothing is actually computed on Earth Engine until the
final step calls `.getInfo()` / `geemap.ee_to_df()`.

## Code Structure

```
beaver-app-st/
├── app.py                        # Entry point: Streamlit multi-page navigation
├── pages/
│   └── analyze_impacts.py        # The entire 6-step analysis workflow
├── service/                      # Stateless libraries of functions
│   ├── earth_engine_auth.py      # Centralized GEE initialization (imported everywhere)
│   ├── constants.py              # AppConstants: defaults, session-state schema, state codes
│   ├── session_state.py          # SessionStateManager: all st.session_state access
│   ├── parser.py                 # Parse uploaded CSV/GeoJSON into ee.FeatureCollections
│   ├── validation.py             # Validate dams are near waterways; build reports/maps
│   ├── negative_sampling.py      # Generate non-dam control points
│   ├── load_datasets.py          # Load NHD flowline collections per US state
│   ├── visualize_trends.py       # The GEE analysis core (imagery, LST/ET, metric reducers)
│   └── error_handling.py         # Decorators/context managers for user-friendly errors
├── assets/                       # Static images used by the About page
├── config.yaml.example           # Template for the local Earth Engine project id
├── Dockerfile                    # Python 3.9 + GDAL + gcloud; runs streamlit on :8501
└── requirements.txt
```

## Earth Engine Authentication

All authentication is centralized in `service/earth_engine_auth.py`. Nearly every `service/`
module calls `initialize_earth_engine()` at **import time**, so importing them (including in
tests) triggers GEE auth — there is no fully offline path.

Two auth modes:
- **Deployment** — service-account credentials read from `st.secrets["gcp_service_account"]`;
  the project is taken from that same secret's `project_id`.
- **Local development** — falls back to user credentials via `ee.Authenticate()`, using the
  `project_id` from your `config.yaml` (copied from `config.yaml.example`). `config.yaml` is
  gitignored.

## The Six-Step Workflow

`pages/analyze_impacts.py` renders six expandable steps, each gated on the previous step's
completion flag (`step1_complete` … `step6_complete`, managed by `SessionStateManager`):

1. **Upload Dam Locations** — CSV or GeoJSON of dam/BDA coordinates (`render_step1`,
   `process_dam_upload` → `parser.upload_points_to_ee`). At least two locations are required.
2. **Select Waterway** — pick an NHD dataset by US state (`load_datasets.load_nhd_collections`),
   choose WWF Free-Flowing Rivers, or upload/point to your own GEE asset (`render_step2`).
3. **Validate Dam Locations** — flag dams too far from any waterway
   (`validation.validate_dam_waterway_distance`, default threshold `DEFAULT_MAX_DISTANCE` = 50m);
   continue with or without the invalid ones (`render_step3`).
4. **Upload or Generate Non-Dam Locations** — upload negatives, or auto-sample them in a ring
   around the dams (`negative_sampling.prepare_hydro` + `sample_negative_points`, inner/outer
   radius default `DEFAULT_INNER_RADIUS`/`DEFAULT_OUTER_RADIUS` = 300m/500m) (`render_step4`).
5. **Create Buffers** — choose the analysis buffer radius (`DEFAULT_BUFFER_RADIUS` = 150m) and
   the elevation distance (`DEFAULT_ELEVATION_DISTANCE` = 3m); buffers are built and
   elevation-masked (`create_buffers`, `render_step5`).
6. **Visualize Trends** — run the pipeline and plot monthly means with 95% confidence
   intervals; download figures and a CSV (`analyze_combined_effects`, `render_step6`).
   Optionally compare multiple years: the pipeline is re-run per selected year (points
   re-dated to July 1 of that year) and yearly averages over the selected months are
   plotted per metric (`analyze_multiple_years`).

## Data Processing Pipeline

The analysis in step 6 transforms points into metrics via these stages
(all in `service/visualize_trends.py` unless noted):

1. **Standardize points** — each dam/non-dam point is assigned an id and a survey date, and
   buffered with an elevation mask in `add_dam_buffer_and_standardize_date`
   (`pages/analyze_impacts.py`). Each point keeps its own survey date, so multi-year inputs
   are carried through as per-point `Survey_Date`.
2. **Elevation masking** — `add_elevation_band(image, elev_dist)` restricts the buffer to
   pixels within the chosen elevation distance of the point's base elevation.
3. **Imagery acquisition** — `s2_export_for_visual` selects Sentinel-2 imagery in a ±6-month
   window around each point's survey date, applies the QA60 cloud mask
   (`add_cloud_mask_band` / `apply_cloud_mask`), renames bands to
   `S2_Blue/Green/Red/NIR`, and reduces to one **monthly median** image per calendar month
   (`get_monthly_median`).
4. **LST & ET augmentation** — `add_landsat_lst_et` attaches Land Surface Temperature (derived
   from synchronous Landsat 8 thermal data via an NDVI-based emissivity) and monthly
   Evapotranspiration (OpenET `et_ensemble_mad`). Missing data is masked out, not filled with
   a sentinel value.
5. **Metric reduction** — `compute_all_metrics_lst_et` computes, per image/buffer:
   NDVI = `normalizedDifference(S2_NIR, S2_Red)`, NDWI_Green =
   `normalizedDifference(S2_Green, S2_NIR)`, plus mean LST and ET. NDVI/NDWI are reported
   as-is, including legitimately negative values.
6. **DataFrame & plots** (`pages/analyze_impacts.py`) — results are converted with
   `geemap.ee_to_df`, concatenated across batches, labeled Dam vs Non-dam, and plotted as
   monthly time series; `create_export_dataframe` builds the downloadable CSV.

> Note on Evapotranspiration: OpenET does not cover the eastern half of the US or all years,
> so ET may be absent for some locations/dates — the app omits the ET plot in that case.

## Batch Processing

Earth Engine imposes memory limits, so step 6 processes dams in batches of
`AppConstants.BATCH_SIZE` (30). Each batch is run through the full pipeline independently and
the resulting DataFrames are concatenated:

```python
total_count = dam_data.size().getInfo()
batch_size = AppConstants.BATCH_SIZE
num_batches = (total_count + batch_size - 1) // batch_size

for i in range(num_batches):
    dam_batch_fc = ee.FeatureCollection(dam_data.toList(batch_size, i * batch_size))
    # ... run pipeline on dam_batch_fc, append results ...
```

Per-batch failures are caught and skipped rather than aborting the whole run. When editing the
analysis loop, preserve the batching.

## Adding New Features

- **New GEE processing** — add functions to the appropriate `service/` module. Any module
  that uses `ee` must call `initialize_earth_engine()` at module top, matching the existing files.
- **New UI** — follow the `render_stepN` pattern; read/write workflow data only through
  `SessionStateManager`, and add any new defaults to `AppConstants.SESSION_DEFAULTS`.
- **New metric** — add it to `compute_all_metrics_lst_et` and to the plotting/export code in
  `pages/analyze_impacts.py`.
- **Errors** — wrap risky UI/processing in the helpers from `service/error_handling.py`
  (`handle_processing_errors`, `safe_processing`, `safe_expander`) so failures surface as
  friendly messages and expanders don't nest illegally.
