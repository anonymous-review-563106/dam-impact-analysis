"""
Utilities for parsing inputs into appropriate formats.
"""

import csv
import datetime
import json
from io import StringIO

import ee
import pandas as pd
import streamlit as st

from .earth_engine_auth import initialize_earth_engine

initialize_earth_engine()


def upload_points_to_ee(file: StringIO, widget_prefix="") -> ee.FeatureCollection | None:
    """
    Modified parser to include widget_prefix and autodetect header
    """
    if not file:
        return None

    try:
        if file.name.endswith(".csv"):
            file.seek(0)

            # Handle delimiter selection
            delimiter = detect_csv_delimiter(widget_prefix)

            # Detect headers and process CSV
            has_header = detect_csv_header(file)
            df = process_csv_to_dataframe(file, delimiter, has_header)

            # Handle coordinate column selection
            longitude_col, latitude_col = display_coordinate_column_selectors(df, widget_prefix)

            # Year selection with warnings
            selected_date = display_year_selector_with_warning(widget_prefix)

            if st.button("Confirm and Process Data", key=f"{widget_prefix}_process_data_button"):
                standardized_features = csv_to_ee_features(df, longitude_col, latitude_col, selected_date)
                feature_collection = ee.FeatureCollection(standardized_features)
                st.success("CSV successfully uploaded and standardized. Preview the data on the map below.")
                return feature_collection

        elif file.name.endswith(".geojson"):
            geojson = load_and_validate_geojson(file)
            if geojson is None:
                return None

            # Year selection with warnings
            selected_date = display_year_selector_with_warning(widget_prefix, "_geojson")

            if st.button("Confirm and Process GeoJSON", key=f"{widget_prefix}_geojson_process_button"):
                features = create_ee_features_from_geojson(geojson, selected_date)
                feature_collection = ee.FeatureCollection(features)
                st.success("GeoJSON successfully uploaded and converted.")
                return feature_collection

        else:
            st.error("Unsupported file format. Please upload a CSV or GeoJSON file.")
            return None

    except Exception as e:  # pylint: disable=broad-except
        st.error(f"An error occurred while processing the file: {e}")
        return None


def upload_waterway_to_ee(file, widget_prefix="Waterway"):
    """
    Upload a user-provided waterway dataset (GeoJSON) and convert to an
    Earth Engine FeatureCollection.
    Expected geometry types: LineString / MultiLineString (polygons also allowed).
    """
    if not file:
        return None
    try:
        if file.name.lower().endswith((".geojson", ".json")):
            geojson = load_and_validate_geojson(file)
            if geojson is None:
                return None
            geom_types = {
                f.get("geometry", {}).get("type")
                for f in geojson.get("features", [])
                if f.get("geometry") is not None
            }
            if geom_types and not geom_types.intersection(
                {"LineString", "MultiLineString", "Polygon", "MultiPolygon"}
            ):
                st.warning(
                    f"Uploaded GeoJSON has geometry types {geom_types}, "
                    "which may not be ideal as a waterway map."
                )
            if st.button(
                "Confirm and Process Waterway",
                key=f"{widget_prefix}_process_waterway_button",
            ):
                features = create_ee_features_from_geojson(geojson)
                feature_collection = ee.FeatureCollection(features)
                st.success("Custom waterway dataset successfully uploaded and converted.")
                return feature_collection
        else:
            st.error("Unsupported file format. Please upload a GeoJSON file for waterways.")
            return None
    except Exception as e:  # pylint: disable=broad-except
        st.error(f"An error occurred while processing the waterway file: {e}")
        return None


def upload_non_dam_points_to_ee(file: StringIO, dam_date=None, widget_prefix=""):
    """
    Handles CSV and GeoJSON uploads for non-dam points, using the date from dam data.
    """
    if not file:
        return None

    # Get date from context
    dam_date = get_dam_date_from_context(dam_date, st.session_state)

    try:
        if file.name.endswith(".csv"):
            file.seek(0)

            # Handle delimiter selection
            delimiter = detect_csv_delimiter(widget_prefix, "_nondam")

            # Detect headers and process CSV
            has_header = detect_csv_header(file)
            df = process_csv_to_dataframe(file, delimiter, has_header)

            # Handle coordinate column selection
            longitude_col, latitude_col = display_coordinate_column_selectors(df, widget_prefix, "_nondam")

            if st.button("Confirm and Process Data", key=f"{widget_prefix}_nondam_process_data_button"):
                standardized_features = csv_to_ee_features(df, longitude_col, latitude_col, dam_date)
                feature_collection = ee.FeatureCollection(standardized_features)
                return feature_collection

        elif file.name.endswith(".geojson"):
            geojson = load_and_validate_geojson(file)
            if geojson is None:
                return None

            if st.button("Confirm and Process GeoJSON", key=f"{widget_prefix}_nondam_geojson_process_button"):
                features = create_ee_features_from_geojson(geojson, dam_date)
                feature_collection = ee.FeatureCollection(features)
                st.success("Non-dam points GeoJSON successfully uploaded and converted.")
                return feature_collection

        else:
            st.error("Unsupported file format. Please upload a CSV or GeoJSON file.")
            return None

    except Exception as e:  # pylint: disable=broad-except
        st.error(f"An error occurred while processing the file: {e}")
        return None


def detect_csv_delimiter(widget_prefix, suffix=""):
    """Handle CSV delimiter selection UI and return chosen delimiter"""
    delimiter_display = {",": "Comma (,)", ";": "Semicolon (;)", "\t": "Tab (\\t)"}
    delimiter_key = st.selectbox(
        "Select delimiter used in CSV:",
        list(delimiter_display.values()),
        index=0,
        key=f"{widget_prefix}{suffix}_delimiter_selectbox",
    )
    return [k for k, v in delimiter_display.items() if v == delimiter_key][0]


def detect_csv_header(file):
    """Use csv.Sniffer to detect if CSV has headers, return boolean"""
    sample = file.read(1024)
    try:
        sample_str = sample.decode("utf-8")
    except AttributeError:
        sample_str = sample  # already a string

    sniffer = csv.Sniffer()
    has_header = sniffer.has_header(sample_str)
    file.seek(0)  # Reset pointer
    return has_header


def process_csv_to_dataframe(file, delimiter, has_header):
    """Read CSV into DataFrame with proper headers"""
    if has_header:
        df = pd.read_csv(file, delimiter=delimiter, header=0, encoding="utf-8")
    else:
        df = pd.read_csv(file, delimiter=delimiter, header=None, encoding="utf-8")
        df.columns = [f"column{i}" for i in range(len(df.columns))]

    st.write("**Preview of the uploaded file:**")
    st.dataframe(df.head(5))
    return df


def auto_select_coordinate_columns(df):
    """Return default indices for lat/lon columns based on column names"""
    columns_lower = [col.lower() for col in df.columns]

    if "longitude" in columns_lower:
        default_longitude = list(df.columns).index(df.columns[columns_lower.index("longitude")])
    else:
        default_longitude = 0

    if "latitude" in columns_lower:
        default_latitude = list(df.columns).index(df.columns[columns_lower.index("latitude")])
    else:
        default_latitude = 1 if len(df.columns) > 1 else 0

    return default_longitude, default_latitude


def display_coordinate_column_selectors(df, widget_prefix, suffix=""):
    """Show lat/lon column selectboxes and return selected column names"""
    default_longitude, default_latitude = auto_select_coordinate_columns(df)

    longitude_col = st.selectbox(
        "Select the **Longitude** column:",
        options=df.columns,
        index=default_longitude,
        key=f"{widget_prefix}{suffix}_longitude_selectbox",
    )
    latitude_col = st.selectbox(
        "Select the **Latitude** column:",
        options=df.columns,
        index=default_latitude,
        key=f"{widget_prefix}{suffix}_latitude_selectbox",
    )

    return longitude_col, latitude_col


def load_and_validate_geojson(file):
    """Load and validate GeoJSON structure, return parsed data or None"""
    file.seek(0)
    try:
        geojson = json.load(file)
    except json.JSONDecodeError:
        st.error("Invalid GeoJSON file format.")
        return None

    if "features" not in geojson or not isinstance(geojson["features"], list):
        st.error("Invalid GeoJSON format: missing 'features' key.")
        return None

    return geojson


def create_ee_feature_from_row(row, longitude_col, latitude_col, date, extra_props=None):
    """Create EE feature from DataFrame row with coordinate cleaning"""
    longitude = clean_coordinate(row[longitude_col])
    latitude = clean_coordinate(row[latitude_col])
    if longitude is None or latitude is None:
        return None

    properties = {"date": date}
    if extra_props:
        properties.update(extra_props)

    return ee.Feature(ee.Geometry.Point([longitude, latitude]), properties)


def csv_to_ee_features(df, longitude_col, latitude_col, date):
    """Convert DataFrame to list of EE features"""

    def standardize_feature(row):
        return create_ee_feature_from_row(row, longitude_col, latitude_col, date)

    return list(filter(None, df.apply(standardize_feature, axis=1).tolist()))


def create_ee_features_from_geojson(geojson, date):
    """Convert GeoJSON features to Earth Engine features with given date"""
    features = []
    for i, feature_obj in enumerate(geojson["features"]):
        try:
            geom = feature_obj.get("geometry")
            props = feature_obj.get("properties", {"id": i})
            props["date"] = date
            features.append(ee.Feature(ee.Geometry(geom), props))
        except Exception as e:  # pylint: disable=broad-except
            st.warning(f"Skipped feature {i} due to an error: {e}")

    return features


def display_year_selector_with_warning(widget_prefix, suffix=""):
    """Show year selector and ET data warnings, return selected date"""
    _max_year = max(datetime.date.today().year, 2026)
    selected_year = st.selectbox(
        "Select a year:", list(range(2017, _max_year + 1)), index=3, key=f"{widget_prefix}{suffix}_year_selectbox"
    )
    st.caption(
        "This is the year your dam locations are analyzed against: satellite imagery is "
        "drawn from within six months of 1 July of this year. You are not locked in — in "
        "Step 6 you can optionally run a multi-year analysis to compare several years."
    )
    selected_date = f"{selected_year}-07-01"

    if selected_year >= datetime.date.today().year:
        st.warning("You may proceed to next steps, but ET for the most recent months may not be published yet.")

    return selected_date


def get_dam_date_from_context(dam_date, session_state):
    """Get date from various sources with fallback logic"""
    if dam_date is not None:
        return dam_date

    if "selected_date" in session_state:
        return session_state.selected_date

    if "Dam_data" in session_state and session_state.Dam_data:
        try:
            first_feature = ee.Feature(session_state.Dam_data.first())
            dam_date = first_feature.get("date").getInfo()
            if dam_date:
                return dam_date
        except Exception:  # pylint: disable=broad-except
            pass

    st.warning("No dam data date found, using default date: 2020-07-01")
    return "2020-07-01"


def clean_coordinate(value) -> float | None:
    """Cleans and converts a coordinate value into a valid float."""
    try:
        value = str(value).strip().replace("°", "").replace(",", ".")
        value = value.replace("N", "").replace("S", "").replace("E", "").replace("W", "")
        return float(value)
    except ValueError:
        return None


def extract_coordinates_df(dam_data):
    """
    Extract coordinates from Dam_data and create a DataFrame with id_property and coordinates

    Args:
        dam_data: Earth Engine Feature Collection containing dam data

    Returns:
        DataFrame with id_property, longitude, and latitude columns
    """
    try:
        # Get features from Dam_data
        dam_features = dam_data.getInfo()["features"]

        coords_data = []
        for i, feature in enumerate(dam_features):
            try:
                props = feature["properties"]
                id_prop = props.get("id_property")

                if not id_prop:
                    st.warning(f"Feature {i} missing id_property")
                    continue

                # Extract coordinates from Point_geo
                if "Point_geo" in props:
                    point_geo = props["Point_geo"]

                    if isinstance(point_geo, dict) and "coordinates" in point_geo:
                        coords = point_geo["coordinates"]
                        if isinstance(coords, list) and len(coords) >= 2:
                            coords_data.append({"id_property": id_prop, "longitude": coords[0], "latitude": coords[1]})
                        else:
                            st.warning(f"Invalid coordinates format for feature {i}: {coords}")
                    else:
                        st.warning(f"Point_geo missing coordinates for feature {i}")
                else:
                    st.warning(f"No Point_geo found for feature {i}")

            except Exception as e:
                st.warning(f"Error processing feature {i}: {str(e)}")
                continue

        # Create DataFrame from coordinates data
        coords_df = pd.DataFrame(coords_data)

        return coords_df
    except Exception as e:
        st.warning(f"Could not extract coordinates: {str(e)}")
        return pd.DataFrame(columns=["id_property", "longitude", "latitude"])
