import math
import pytest
import ee
import pandas as pd
import streamlit as st
from unittest.mock import patch

from service.constants import AppConstants
from service.parser import (
    clean_coordinate,
    csv_to_ee_features,
    extract_coordinates_df,
)
from service.validation import (
    validate_dam_waterway_distance,
    generate_validation_report,
)
from service.negative_sampling import (
    sample_negative_points,
    prepare_hydro,
    sampling_ring,
    waterways_in_sampling_area,
)
from service.visualize_trends import (
    add_elevation_band,
    add_landsat_lst_et,
    compute_all_metrics_lst_et,
    s2_export_for_visual,
)
from pages.analyze_impacts import (
    create_buffers,
)
from service.earth_engine_auth import initialize_earth_engine
from service.session_state import SessionStateManager


@pytest.fixture(scope="session", autouse=True)
def init_ee():
    """Initialize Earth Engine once for all tests"""
    initialize_earth_engine()


@pytest.fixture
def mock_streamlit():
    """Mock streamlit for functions that use st.session_state"""
    with patch('streamlit.session_state', {}) as mock_state:
        SessionStateManager.initialize()
        yield mock_state


def test_clean_coordinate():
    assert clean_coordinate("45.5°N") == 45.5
    assert clean_coordinate("-122.3W") == -122.3
    assert clean_coordinate("45,5") == 45.5
    assert clean_coordinate("invalid") is None


def test_csv_to_ee_features():
    """Test the actual csv_to_ee_features function from parser.py"""
    df = pd.DataFrame({
        'longitude': [-122.5, -122.6],
        'latitude': [45.5, 45.6]
    })

    features = csv_to_ee_features(df, 'longitude', 'latitude', '2020-07-01')
    fc = ee.FeatureCollection(features)

    assert fc.size().getInfo() == 2
    first_feature = fc.first()
    assert first_feature.geometry().type().getInfo() == "Point"
    assert first_feature.get("date").getInfo() == "2020-07-01"


def test_extract_coordinates_df():
    """Test extract_coordinates_df from parser.py"""
    # Create test dam data with Point_geo property
    dam_fc = ee.FeatureCollection([
        ee.Feature(
            ee.Geometry.Point([-123.0, 44.0]),
            {
                "id_property": "P1",
                "Point_geo": {"type": "Point", "coordinates": [-123.0, 44.0]}
            }
        ),
        ee.Feature(
            ee.Geometry.Point([-123.1, 44.1]),
            {
                "id_property": "P2",
                "Point_geo": {"type": "Point", "coordinates": [-123.1, 44.1]}
            }
        )
    ])

    df = extract_coordinates_df(dam_fc)

    assert len(df) == 2
    assert 'id_property' in df.columns
    assert 'longitude' in df.columns
    assert 'latitude' in df.columns
    assert df.loc[0, 'id_property'] == 'P1'
    assert df.loc[0, 'longitude'] == -123.0


def test_validate_dam_waterway_distance():
    """Test the actual validate_dam_waterway_distance function"""
    # Create test dams and waterway
    dam_fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([-123.0, 44.05]), {"date": "2020-07-01"}),
        ee.Feature(ee.Geometry.Point([-123.1, 44.15]), {"date": "2020-07-01"})
    ])

    waterway = ee.FeatureCollection("projects/sat-io/open-datasets/NHD/NHD_OR/NHDFlowline")
    waterway = waterway.filterBounds(dam_fc.geometry().bounds())

    results = validate_dam_waterway_distance(dam_fc, waterway, max_distance=500)

    # Check structure of results
    assert 'valid_dams' in results
    assert 'invalid_dams' in results
    assert 'valid_count' in results
    assert 'invalid_count' in results

    # Verify it's actually checking distances
    total = results['total_dams'].getInfo()
    valid = results['valid_count'].getInfo()
    invalid = results['invalid_count'].getInfo()
    assert total == valid + invalid


def test_generate_validation_report():
    """Test generate_validation_report function"""
    # Create mock validation results
    mock_results = {
        'valid_count': ee.Number(2),
        'invalid_count': ee.Number(1),
        'total_dams': ee.Number(3),
        'invalid_dams_info': ee.FeatureCollection([
            ee.Feature(None, {
                'distance': 150,
                'coordinates': [-123.5, 44.5]
            })
        ])
    }

    report = generate_validation_report(mock_results)

    assert "Total dams: 3" in report
    assert "Valid dams: 2" in report
    assert "Invalid dams: 1" in report
    assert "-123.5" in report  # Check coordinates are in report


def test_prepare_hydro():
    """Test prepare_hydro function from negative_sampling.py"""
    # Small waterway feature collection
    waterway = ee.FeatureCollection("projects/sat-io/open-datasets/NHD/NHD_OR/NHDFlowline").limit(10)

    hydro_raster = prepare_hydro(waterway)

    # Check it returns an image
    assert isinstance(hydro_raster, ee.Image)
    # Check it has the hydro_mask band
    bands = hydro_raster.bandNames().getInfo()
    assert 'hydro_mask' in bands


def test_waterways_in_sampling_area_finds_stream_outside_dam_bounding_box():
    """A stream beside a tight cluster of dams is found, though it misses their bounding box.

    Regression: three dams in a north-south line just west of a stream have a bounding
    box the stream never crosses, so "No waterway data found" was reported even though
    the stream is well inside the sampling radius.
    """
    stream = ee.FeatureCollection([ee.Feature(ee.Geometry.LineString([[-123.0, 44.0], [-123.0, 44.01]]))])
    dams = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([-123.001, lat])) for lat in (44.004, 44.005, 44.006)
    ])  # ~80 m west of the stream

    assert stream.filterBounds(dams.geometry().bounds()).size().getInfo() == 0
    assert waterways_in_sampling_area(stream, sampling_ring(dams, 30, 1000)).size().getInfo() == 1


def test_waterways_in_sampling_area_single_dam():
    """One dam has a zero-area bounding box; its sampling area must still find waterways."""
    stream = ee.FeatureCollection([ee.Feature(ee.Geometry.LineString([[-123.0, 44.0], [-123.0, 44.01]]))])
    dams = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([-123.001, 44.005]))])
    assert waterways_in_sampling_area(stream, sampling_ring(dams, 30, 1000)).size().getInfo() == 1


def test_sampling_ring_spans_inner_to_outer_radius_from_each_dam():
    """The ring is 30-1000 m from the dam, not 30-1030 m (inner radius added twice)."""
    dam = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([-123.0, 44.0]))])
    area = sampling_ring(dam, inner_radius=30, outer_radius=1000).area(1).getInfo()
    expected = math.pi * (1000**2 - 30**2)  # the old ring was ~6% larger
    assert area == pytest.approx(expected, rel=0.005)


def test_waterways_in_sampling_area_uses_outer_radius_from_dam():
    """A stream 950 m from the dam is used; one 1050 m away is not."""
    metres_per_degree_lon = 111_320 * math.cos(math.radians(44.0))
    dam = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([-123.0, 44.0]))])

    def stream_at(metres):
        lon = -123.0 + metres / metres_per_degree_lon
        return ee.FeatureCollection([ee.Feature(ee.Geometry.LineString([[lon, 43.99], [lon, 44.01]]))])

    assert waterways_in_sampling_area(stream_at(950), sampling_ring(dam, 30, 1000)).size().getInfo() == 1
    assert waterways_in_sampling_area(stream_at(1050), sampling_ring(dam, 30, 1000)).size().getInfo() == 0


def test_sample_negative_points():
    """Test sample_negative_points function"""
    positive_fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([-123.021055, 44.080697]), {"date": "2020-07-01"}),
        ee.Feature(ee.Geometry.Point([-123.001068, 44.079008]), {"date": "2020-07-01"}),
        ee.Feature(ee.Geometry.Point([-122.976106, 44.084595]), {"date": "2020-07-01"})
    ])

    waterway = ee.FeatureCollection("projects/sat-io/open-datasets/NHD/NHD_OR/NHDFlowline")
    waterway = waterway.filterBounds(positive_fc.geometry().bounds().buffer(1000))

    hydro_raster = prepare_hydro(waterway)

    negative_fc = sample_negative_points(
        positive_fc,
        hydro_raster,
        ring_area=sampling_ring(positive_fc, inner_radius=300, outer_radius=500),
        sampling_scale=10
    )

    size = negative_fc.size().getInfo()
    assert size > 0
    # Should generate approximately same number as positive (may vary)
    assert abs(size - positive_fc.size().getInfo()) < 1


def test_create_buffers(mock_streamlit):
    """Test the actual create_buffers function from analyze_impacts.py"""
    merged_fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([-123.021055, 44.080697]), {
            "Dam": "positive",
            "date": "2020-07-01",
            "id_property": "P1"
        }),
        ee.Feature(ee.Geometry.Point([-122.976106, 44.084595]), {
            "Dam": "negative",
            "date": "2020-07-01",
            "id_property": "N1"
        })
    ])

    st.session_state['Merged_collection'] = merged_fc
    st.session_state['Positive_collection'] = merged_fc.filter(ee.Filter.eq('Dam', 'positive'))

    result = create_buffers(buffer_radius=150)

    assert result is not None
    # Check geometry type changed to Polygon
    first = result.first()
    assert first.geometry().type().getInfo() == "Polygon"

    # Check properties are preserved
    props = first.propertyNames().getInfo()
    assert 'Dam' in props
    assert 'Survey_Date' in props
    assert 'id_property' in props
    assert 'Point_geo' in props


def test_date_standardization_by_create_buffers():
    """Test Survey_Date handling in buffer creation"""
    merged_fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([-123.0, 44.0]), {
            "Dam": "positive",
            "date": "2020-07-01",
            "id_property": "P1"
        })
    ])

    st.session_state['Merged_collection'] = merged_fc
    st.session_state['Positive_collection'] = merged_fc

    result = create_buffers(150)
    first = result.first()

    # Check Survey_Date is set
    survey_date = first.get('Survey_Date').getInfo()
    assert survey_date is not None

    # Check formatted date
    damdate = first.get('Damdate').getInfo()
    assert 'DamDate_' in damdate
    assert '20200701' in damdate


def test_s2_export_for_visual():
    """Test s2_export_for_visual function"""
    # Create small buffered collection
    dam_fc = ee.FeatureCollection([
        ee.Feature(
            ee.Geometry.Point([-123.0, 44.05]).buffer(150),
            {
                "Dam": "positive",
                "Survey_Date": "2020-07-01",
                "id_property": "P1",
                "Point_geo": ee.Geometry.Point([-123.0, 44.05])
            }
        )
    ])

    image_collection = s2_export_for_visual(dam_fc, add_elevation_band, AppConstants.DEFAULT_ELEVATION_DISTANCE)

    # Check it returns ImageCollection
    assert isinstance(image_collection, ee.ImageCollection)
    size = image_collection.size().getInfo()
    assert size > 0  # Should have some images


def test_s2_export_for_visual_months():
    """Only the requested months are computed; omitting months computes all 12"""
    dam_fc = ee.FeatureCollection([
        ee.Feature(
            ee.Geometry.Point([-123.0, 44.05]).buffer(150),
            {
                "Dam": "positive",
                "Survey_Date": "2020-07-01",
                "id_property": "P1",
                "Point_geo": ee.Geometry.Point([-123.0, 44.05])
            }
        )
    ])

    subset = s2_export_for_visual(
        dam_fc, add_elevation_band, AppConstants.DEFAULT_ELEVATION_DISTANCE, months=[6, 7]
    )
    assert sorted(subset.aggregate_array("Image_month").getInfo()) == [6, 7]

    full = s2_export_for_visual(dam_fc, add_elevation_band, AppConstants.DEFAULT_ELEVATION_DISTANCE)
    assert full.size().getInfo() == 12


def test_s2_export_for_visual_skips_months_without_imagery():
    """Months with no Sentinel-2 images are dropped instead of failing the whole run.

    Regression: on the Seward Peninsula, Alaska, there is no Sentinel-2 imagery in
    January or December, which used to fail every batch with "Element.get: Parameter
    'object' is required and may not be null".
    """
    point = ee.Geometry.Point([-164.8, 65.19])
    dam_fc = ee.FeatureCollection([
        ee.Feature(
            point.buffer(150),
            {"Dam": "positive", "Survey_Date": "2020-07-01", "id_property": "AK1", "Point_geo": point},
        )
    ])

    ic = s2_export_for_visual(dam_fc, add_elevation_band, AppConstants.DEFAULT_ELEVATION_DISTANCE)
    assert sorted(ic.aggregate_array("Image_month").getInfo()) == list(range(2, 12))


def test_add_landsat_lst_et():
    """Test add_landsat_lst_et adds LST and ET bands"""
    # Create a simple S2 image with required properties
    dam_fc = ee.FeatureCollection([
        ee.Feature(
            ee.Geometry.Point([-123.0, 44.05]).buffer(150),
            {
                "Dam": "positive",
                "Survey_Date": "2020-07-01",
                "id_property": "P1",
                "Point_geo": ee.Geometry.Point([-123.0, 44.05])
            }
        )
    ])

    ic = s2_export_for_visual(dam_fc, add_elevation_band, AppConstants.DEFAULT_ELEVATION_DISTANCE).limit(1)
    first_image = ic.first()

    result = add_landsat_lst_et(first_image)

    # Check bands were added
    bands = result.bandNames().getInfo()
    assert 'LST' in bands
    assert 'ET' in bands


def test_compute_all_metrics_lst_et():
    """Test compute_all_metrics_lst_et returns feature with metrics"""
    dam_fc = ee.FeatureCollection([
        ee.Feature(
            ee.Geometry.Point([-123.0, 44.05]).buffer(150),
            {
                "Dam": "positive",
                "Survey_Date": "2020-07-01",
                "id_property": "P1",
                "Point_geo": ee.Geometry.Point([-123.0, 44.05])
            }
        )
    ])

    ic = s2_export_for_visual(dam_fc, add_elevation_band, AppConstants.DEFAULT_ELEVATION_DISTANCE).limit(1)
    ic_with_bands = ic.map(add_landsat_lst_et)

    # Apply metrics computation
    results_fc = ic_with_bands.map(compute_all_metrics_lst_et)

    first_result = results_fc.first()
    props = first_result.propertyNames().getInfo()

    # Check expected properties exist
    assert 'NDVI' in props
    assert 'NDWI_Green' in props
    assert 'LST' in props
    assert 'ET' in props
    assert 'Image_month' in props
    assert 'Dam_status' in props


def test_end_to_end_small_dataset(mock_streamlit):
    """Integration test with 2 points through key functions"""
    # Setup
    dam_coords = [[-123.0, 44.05], [-123.05, 44.06]]
    dam_fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point(coord), {"date": "2020-07-01"})
        for coord in dam_coords
    ])

    # Load waterway
    waterway = ee.FeatureCollection("projects/sat-io/open-datasets/NHD/NHD_OR/NHDFlowline")
    waterway = waterway.filterBounds(dam_fc.geometry().bounds())

    # Validate
    validation = validate_dam_waterway_distance(dam_fc, waterway, max_distance=500)
    assert validation['valid_count'].getInfo() > 0

    # Generate negatives
    hydro_raster = prepare_hydro(waterway)
    negatives = sample_negative_points(dam_fc, hydro_raster, sampling_ring(dam_fc, 300, 500), 10)
    assert negatives.size().getInfo() > 0