"""
Functions for visualizing trends.
Sentinel-2 Dam Imagery Processing Module.

This module provides functions for extracting and processing Sentinel-2 imagery around dam locations with
 elevation-based masking.
"""

import ee

from .earth_engine_auth import initialize_earth_engine
from service.constants import AppConstants

initialize_earth_engine()


def add_cloud_mask_band(image):
    """
    Add bands for cloud mask where 1 is clear and 0 is cloudy pixels.
    Args:
        image: an image with bits for clouds and cirrus.
    Returns: image with additional bands
    """
    qa = image.select("QA60")

    # Bits 10 and 11 are clouds and cirrus, respectively.
    cloud_bit_mask = 1 << 10
    cirrus_bit_mask = 1 << 11

    # Both flags should be set to zero, indicating clear conditions.
    cloud_mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
    # Create a band with values 1 (clear) and 0 (cloudy or cirrus) and convert from byte to Uint16
    cloud_mask_band = cloud_mask.rename("cloudMask").toUint16()

    return image.addBands(cloud_mask_band)


def add_acquisition_date(image):
    """
    Add acquisition date metadata to image.
    Args:
        image: an image.
    Returns: image with acquisition date metadata added.
    """
    date = ee.Date(image.get("system:time_start"))
    return image.set("acquisition_date", date)


def rename_bands(s2_cloud_band):
    """Change band names"""
    old_band_names = ["B2", "B3", "B4", "B8", "cloudMask"]
    new_band_names = ["S2_Blue", "S2_Green", "S2_Red", "S2_NIR", "S2_Binary_cloudMask"]

    s2_named_bands = s2_cloud_band.map(lambda image: image.select(old_band_names).rename(new_band_names))
    return s2_named_bands


def apply_cloud_mask(image):
    """
    Mask out cloudy pixels (where cloudMask = 0) for relevant bands
    """
    cloud_mask = image.select("S2_Binary_cloudMask")
    return image.updateMask(cloud_mask).select(["S2_Blue", "S2_Green", "S2_Red", "S2_NIR"])


def get_monthly_median(collection, months=None):
    """
    Get the median of the images from each month

    ``months`` limits which calendar months are computed (default: all 12). Each month
    only uses its own imagery, so skipping months doesn't change the others' values.

    Months with no images are dropped. Sentinel-2 has none in high-latitude winter
    (e.g. January and December in western Alaska), and taking the date of a missing
    first image would fail the whole request.
    """
    months = ee.List(list(months)) if months else ee.List.sequence(1, 12)

    def get_month_image(month):
        monthly_images = collection.filter(ee.Filter.calendarRange(month, month, "month"))
        first = monthly_images.first()
        image_date = ee.Date(first.get("system:time_start"))
        image_month = image_date.get("month")
        image_year = image_date.get("year")
        median = monthly_images.median().set("Image_month", image_month).set("Image_year", image_year)
        # Lazy: the date lookup above is only evaluated for months that have images.
        return ee.Algorithms.If(monthly_images.size().gt(0), median, None)

    monthly_images_list = months.map(get_month_image, True)  # dropNulls
    monthly_images_collection = ee.ImageCollection.fromImages(monthly_images_list)
    return monthly_images_collection


def add_elevation_band(image, elev_dist):

    dataset = ee.ImageCollection("USGS/3DEP/10m_collection")

    filtered_collection = dataset.filterBounds(image.geometry())
    filtered_mosaic = filtered_collection.mosaic()

    elevation_select = filtered_mosaic.select("elevation")
    elevation = ee.Image(elevation_select)

    # Extract sample area from elevation
    point_geom = image.get("DamGeo")
    buffered_area = image.get("boxArea")
    dam_status = image.get("DamStatus")
    dam_id = image.get("damId")
    # Extract elevation of dam location
    point_elevation = ee.Number(elevation.sample(point_geom, 10).first().get("elevation"))

    elevation_clipped = elevation.clip(buffered_area)

    # Create elevation radius around point to sample from
    point_plus = point_elevation.add(elev_dist)
    point_minus = point_elevation.subtract(AppConstants.ELEVATION_DISTANCE_SUB)
    elevation_masked = (
        elevation_clipped.where(elevation_clipped.lt(point_minus), 0)
        .where(elevation_clipped.gt(point_minus), 1)
        .where(elevation_clipped.gt(point_plus), 0)
    )
    elevation_masked2 = elevation_masked.updateMask(elevation_masked.eq(1))

    # Add bands, create new "id" property to name the file, and clip the images to the ROI.
    # id_property is carried through as well: _extract_metadata reads it, and without it
    # the metrics DataFrame loses the column and the CSV export has to fall back to
    # matching coordinates by row order.
    full_image = (
        image.set("Dam_id", dam_id)
        .set("id_property", dam_id)
        .set("Dam_status", dam_status)
        .set("Area", buffered_area)
        .clip(buffered_area)
    )
    full_image2 = full_image.addBands(elevation_masked2)

    return full_image2


def s2_export_for_visual(dam_collection, elevation_function, elevation_dist=None, months=None) -> ee.ImageCollection:
    """Apply the required transformations and filtration to the images"""

    def extract_pixels(box):
        image_date = ee.Date(box.get("Survey_Date"))
        start_date = image_date.advance(-6, "month").format("YYYY-MM-dd")
        end_date = image_date.advance(6, "month").format("YYYY-MM-dd")

        box_area = box.geometry()
        dam_id = box.get("id_property")
        dam_status = box.get("Dam")
        dam_geo = box.get("Point_geo")
        s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        filtered_collection = s2.filterDate(start_date, end_date).filterBounds(box_area)

        # Define the dataset
        s2_cloud_band = filtered_collection.map(add_cloud_mask_band)
        s2_named_bands = rename_bands(s2_cloud_band)
        s2_cloud_masked = s2_named_bands.map(apply_cloud_mask)
        s2_cloud_filter = s2_cloud_masked.map(add_acquisition_date)
        filtered_collection_bands = get_monthly_median(s2_cloud_filter, months)

        # Set metadata to each image
        filtered_collection_bands = filtered_collection_bands.map(
            lambda img: img.set("DamGeo", dam_geo)
            .set("boxArea", box_area)
            .set("damId", dam_id)
            .set("DamStatus", dam_status)
        )

        # Apply elevation_function
        filtered_collection_bands = filtered_collection_bands.map(
            lambda img: elevation_function(img, elevation_dist)
        )

        return filtered_collection_bands

    imagery_collections = dam_collection.map(extract_pixels).flatten()
    return ee.ImageCollection(imagery_collections)


def _add_cloud_coverage_to_id(image: ee.Image) -> ee.Image:
    """Add cloud coverage percentage to the image identifier."""
    first_id: ee.ComputedObject = image.get("First_id")
    cloud_coverage: ee.ComputedObject = image.get("Cloud_coverage")
    return image.set("Full_id", ee.String(first_id).cat("_Cloud_").cat(cloud_coverage))


def add_landsat_lst_et(s2_image):
    """Adds robust Landsat LST and OpenET ET bands to a Sentinel-2 image."""

    year = ee.Number(s2_image.get("Image_year"))
    month = ee.Number(s2_image.get("Image_month"))
    start_date = ee.Date.fromYMD(year, month, 1)
    end_date = start_date.advance(1, "month")

    box_area = s2_image.geometry()

    # STEP 1: PROCESS LANDSAT FOR LST
    def apply_scale_factors(image):
        optical_bands = image.select("SR_B.").multiply(0.0000275).add(-0.2)
        thermal_bands = image.select("ST_B.*").multiply(0.00341802).add(149.0)
        return image.addBands(optical_bands, overwrite=True).addBands(thermal_bands, overwrite=True)

    def cloud_mask(image):
        qa = image.select("QA_PIXEL")
        mask = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 5).eq(0))
        return image.updateMask(mask)

    lc08 = ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").filterDate(start_date, end_date).filterBounds(box_area)
    lc09 = ee.ImageCollection("LANDSAT/LC09/C02/T1_L2").filterDate(start_date, end_date).filterBounds(box_area)
    landsat_col = lc08.merge(lc09).map(apply_scale_factors).map(cloud_mask)

    def add_ndvi_stats(img):
        """
        Add NDVI stats as properties for filtering
        """
        ndvi = img.normalizedDifference(["SR_B5", "SR_B4"]).rename("NDVI")
        d = ndvi.reduceRegion(reducer=ee.Reducer.minMax(), geometry=box_area, scale=30, maxPixels=1e13)
        # Store only if we actually got values
        return img.setMulti(ee.Dictionary(d))

    landsat_col = landsat_col.map(add_ndvi_stats)

    filtered_col = landsat_col.filter(ee.Filter.notNull(["NDVI_min", "NDVI_max"]))
    collection_size = filtered_col.size()

    def lst_from_image(img):
        ndvi = img.normalizedDifference(["SR_B5", "SR_B4"]).rename("NDVI")
        d = ee.Dictionary(ndvi.reduceRegion(reducer=ee.Reducer.minMax(), geometry=box_area, scale=30, maxPixels=1e13))

        has_min = d.contains("NDVI_min")
        has_max = d.contains("NDVI_max")

        # Python EE: no And/Or; do nested If to compute "has_both"
        has_both = ee.Algorithms.If(has_min, ee.Algorithms.If(has_max, True, False), False)

        ndvi_min = ee.Number(ee.Algorithms.If(has_min, d.get("NDVI_min"), 0))
        ndvi_max = ee.Number(ee.Algorithms.If(has_max, d.get("NDVI_max"), 1))

        # If we have both stats, check real range; otherwise treat as zero-range (invalid)
        zero_range = ee.Algorithms.If(has_both, ndvi_max.subtract(ndvi_min).abs().lt(1e-6), True)

        fv = ee.Image(
            ee.Algorithms.If(
                zero_range,
                # fully masked placeholder so downstream math stays valid
                ee.Image.constant(0).toFloat().selfMask(),
                ndvi.subtract(ndvi_min).divide(ndvi_max.subtract(ndvi_min)).pow(2),
            )
        ).rename("FV")

        em = fv.multiply(0.004).add(0.986).rename("EM")
        tb = img.select("ST_B10").rename("TB")

        lst = tb.expression("(TB / (1 + (0.00115 * (TB / 1.438)) * log(em))) - 273.15", {"TB": tb, "em": em}).rename(
            "LST"
        )

        return lst.updateMask(fv.mask())

    lst_image = ee.Image(
        ee.Algorithms.If(
            filtered_col.size().eq(0),
            # no valid Landsat → masked LST image (no bogus 99s)
            ee.Image.constant(0).toFloat().selfMask().rename("LST").clip(box_area),
            ee.Algorithms.If(
                filtered_col.size().eq(1),
                lst_from_image(filtered_col.first()).clip(box_area),
                lst_from_image(filtered_col.median()).clip(box_area),
            ),
        )
    )
    # STEP 2: PROCESS OPENET ET DATA
    et_collection = (
        # OpenET ensemble v2.1. Replaces v2_0, which stopped at 2024-12 and had no data
        # for much of the eastern US. Same et_ensemble_mad band; still updated monthly
        # (1999-10 onwards). Contiguous US only - no Alaska or Hawaii.
        ee.ImageCollection("projects/openet/assets/ensemble/conus/gridmet/monthly/v2_1")
        .filterDate(start_date, end_date)
        .filterBounds(box_area)
    )

    et_monthly = et_collection.mean().select("et_ensemble_mad").rename("ET")
    et_final = ee.Image(
        ee.Algorithms.If(
            et_collection.size().eq(0),
            ee.Image.constant(0).toFloat().selfMask().rename("ET").clip(box_area),
            et_monthly.clip(box_area),
        )
    )

    # STEP 3: ADD BANDS BACK TO SENTINEL-2 IMAGE
    return s2_image.addBands(lst_image).addBands(et_final).set("landsat_collection_size", collection_size)


def compute_all_metrics_lst_et(image) -> ee.Feature:
    """
    Returns an ee.Feature containing mean NDVI, NDWI_Green, LST, and ET
    for the geometry of interest.
    """
    # Get geometry from elevation band
    elevation_mask = image.select("elevation")
    geometry = elevation_mask.geometry()

    # Compute indices
    ndvi, ndwi_green = _compute_indices(image)

    # Prepare bands for reduction
    bands = {"NDVI": ndvi, "NDWI_Green": ndwi_green, "LST": image.select("LST"), "ET": image.select("ET")}

    # Reduce all bands over geometry, restricted to the elevation band
    reduced_values = _reduce_bands_by_mask(bands, mask=elevation_mask, geometry=geometry)

    # Extract metadata and combine with metrics
    metadata = _extract_metadata(image)
    combined_metrics = {**metadata, **reduced_values}

    return ee.Feature(None, ee.Dictionary(combined_metrics))


def _compute_indices(image):
    """Helper function to compute NDVI and NDWI_Green indices."""
    ndvi = image.normalizedDifference(["S2_NIR", "S2_Red"]).rename("NDVI")
    ndwi_green = image.normalizedDifference(["S2_Green", "S2_NIR"]).rename("NDWI_Green")
    return ndvi, ndwi_green


def _extract_metadata(image):
    """Helper function to extract common metadata from image."""
    return {
        "Image_month": image.get("Image_month"),
        "Image_year": image.get("Image_year"),
        "Dam_status": image.get("Dam_status"),
        "id_property": image.get("id_property"),
    }


def _reduce_bands_by_mask(bands, mask=None, geometry=None):
    """
    Helper function to reduce bands with optional mask over geometry.
    Uses appropriate scale for each band type:
    - 10m for Sentinel-2 derived indices (NDVI, NDWI_Green)
    - 30m for Landsat derived bands (LST, ET)

    Args:
        bands: dict mapping band names to ee.Image bands
        mask: optional ee.Image mask to apply
        geometry: geometry for reduction

    Returns:
        dict of reduced values
    """
    results = {}

    # Define appropriate scales for each band type
    scale_map = {
        "NDVI": 10,  # Sentinel-2 derived
        "NDWI_Green": 10,  # Sentinel-2 derived
        "LST": 30,  # Landsat derived
        "ET": 30,  # Landsat derived
    }

    for band_name, band in bands.items():
        if mask is not None:
            masked_band = band.updateMask(mask)
        else:
            masked_band = band

        # Use appropriate scale for this band type
        scale = scale_map.get(band_name, 30)  # Default to 30m if unknown

        reduced_value = masked_band.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=geometry, scale=scale, maxPixels=1e13
        ).get(band.bandNames().get(0))

        results[band_name] = reduced_value

    return results
