"""
Validation for dam locations and generation of reports and visualization.
"""

from typing import Dict

import ee
import geemap.foliumap as geemap
import streamlit as st


def validate_dam_waterway_distance(
    dam_collection: ee.FeatureCollection, waterway_fc: ee.FeatureCollection, max_distance: float = 100
) -> Dict:
    """
    Validate if dam locations are near waterways

    Args:
        dam_collection: Collection of dam locations
        waterway_fc: Collection of waterway features
        max_distance: Maximum allowed distance in meters

    Returns:
        Dictionary containing validation results
    """
    try:
        # Function to calculate distance to nearest waterway for each dam
        def calculate_distance(dam_feature):
            dam_geom = dam_feature.geometry()
            # Create a buffer around the dam point
            dam_buffer = dam_geom.buffer(max_distance)
            # Find waterways that intersect with the buffer
            nearby_waterways = waterway_fc.filterBounds(dam_buffer)

            # Calculate distance to each nearby waterway
            def get_distance(waterway):
                distance = dam_geom.distance(waterway.geometry())
                return waterway.set("distance", distance)

            # Get distances and find minimum
            distances = nearby_waterways.map(get_distance)
            min_distance = ee.Algorithms.If(
                distances.size().gt(0),
                distances.sort("distance").first().get("distance"),
                ee.Number(999999),  # Large number for dams with no nearby waterways
            )

            # Set both distance and validation status
            return dam_feature.set(
                {"distance_to_waterway": min_distance, "distance_valid": ee.Number(min_distance).lte(max_distance)}
            )

        # Add distance to all dams
        dams_with_distance = dam_collection.map(calculate_distance)

        # Split into valid and invalid dams
        valid_dams = dams_with_distance.filter(ee.Filter.eq("distance_valid", 1))
        invalid_dams = dams_with_distance.filter(ee.Filter.eq("distance_valid", 0))

        # Get invalid dams info with index
        invalid_dams_info = invalid_dams.map(
            lambda f: ee.Feature(
                f.geometry(), {"distance": f.get("distance_to_waterway"), "coordinates": f.geometry().coordinates()}
            )
        )

        return {
            "valid_dams": valid_dams,
            "invalid_dams": invalid_dams,
            "invalid_dams_info": invalid_dams_info,
            "total_dams": dam_collection.size(),
            "valid_count": valid_dams.size(),
            "invalid_count": invalid_dams.size(),
        }
    except Exception as e:
        st.error(f"Error in distance validation: {str(e)}")
        raise


def check_waterway_intersection(dam_collection: ee.FeatureCollection, waterway_fc: ee.FeatureCollection) -> Dict:
    """
    Check if dams intersect with waterways
    """
    try:
        # Check each dam for intersection
        def check_intersection(feature):
            point = feature.geometry()
            # Create a small buffer around the dam point (10 meters)
            buffered_point = point.buffer(10)
            # Check if the buffered point intersects with any waterways
            intersects = waterway_fc.filterBounds(buffered_point).size().gt(0)
            # Set intersection status and validation status
            return feature.set({"intersects_waterway": intersects, "intersection_valid": ee.Number(intersects)})

        # Add intersection status to all dams
        dams_with_intersection = dam_collection.map(check_intersection)

        # Get intersecting dams
        intersecting_dams = dams_with_intersection.filter(ee.Filter.eq("intersection_valid", 1))

        return {"intersecting_dams": intersecting_dams, "intersecting_count": intersecting_dams.size()}
    except Exception as e:
        st.error(f"Error in intersection validation: {str(e)}")
        raise


def resolve_validation_summary(validation_results: Dict) -> Dict:
    """
    Resolve the lazy validation results into plain Python values in ONE round-trip.

    The values returned by validate_dam_waterway_distance are unevaluated Earth Engine
    objects, so every separate .getInfo() re-runs the whole dam-to-waterway distance
    computation server-side. Bundling them into a single ee.Dictionary evaluates the
    shared graph once. Only each invalid dam's coordinates are needed downstream, so
    those are fetched as a plain array rather than a whole FeatureCollection.

    Returns:
        dict with valid_count, invalid_count, total_dams, invalid_coords
    """
    return ee.Dictionary(
        {
            "valid_count": validation_results["valid_count"],
            "invalid_count": validation_results["invalid_count"],
            "total_dams": validation_results["total_dams"],
            "invalid_coords": validation_results["invalid_dams_info"].aggregate_array("coordinates"),
        }
    ).getInfo()


def generate_validation_report(validation_results: Dict, summary: Dict = None) -> str:
    """
    Generate a human-readable validation report

    Args:
        validation_results: Dictionary containing validation results
        summary: Optional pre-resolved summary from resolve_validation_summary(). Pass
            it to avoid re-running the distance computation.

    Returns:
        Formatted report text
    """
    try:
        report = []

        if "valid_count" in validation_results and "invalid_count" in validation_results:
            if summary is None:
                summary = resolve_validation_summary(validation_results)

            valid_count = summary["valid_count"]
            invalid_count = summary["invalid_count"]
            total_dams = summary["total_dams"]

            report.append(f"Total dams: {total_dams}")
            report.append(f"Valid dams: {valid_count}")
            report.append(f"Invalid dams: {invalid_count}")

            if valid_count == 0:
                report.append("\nNo valid dam locations found. All dams failed validation.")
            elif invalid_count == 0:
                report.append("\nAll dams are valid!")
            else:
                report.append(f"\nFound {invalid_count} dams that are too far from waterways:")
                for i, coords in enumerate(summary["invalid_coords"], 1):
                    report.append(f"- Point #{i}, Location: [{coords[0]:.6f}, {coords[1]:.6f}]")

        return "\n".join(report)
    except Exception as e:  # pylint: disable=broad-except
        st.error(f"Error generating validation report: {str(e)}")
        return "Error generating validation report."


def visualize_validation_results(
    dam_collection: ee.FeatureCollection, waterway_fc: ee.FeatureCollection, validation_results: Dict
) -> geemap.Map:
    """
    Create a map visualization of validation results

    Args:
        dam_collection: Collection of dam locations
        waterway_fc: Collection of waterway features
        validation_results: Dictionary containing validation results

    Returns:
        Map object with validation visualization
    """
    try:
        # Create a new map
        map_obj = geemap.Map()
        map_obj.add_basemap("SATELLITE")

        # Add waterway layer
        map_obj.addLayer(waterway_fc, {"color": "blue", "width": 2}, "Waterways")

        # Add valid dams in green
        if "valid_dams" in validation_results:
            valid_dams = validation_results["valid_dams"]
            map_obj.addLayer(valid_dams, {"color": "green", "pointSize": 5}, "Valid Dams")

        # Add invalid dams in red
        if "invalid_dams" in validation_results:
            invalid_dams = validation_results["invalid_dams"]
            map_obj.addLayer(invalid_dams, {"color": "red", "pointSize": 5}, "Invalid Dams")

        # Center the map on the dam collection
        map_obj.centerObject(dam_collection)

        return map_obj
    except Exception as e:
        st.error(f"Error creating validation map: {str(e)}")
        raise
