"""
Functions for negative sampling of dam locations for comparative analyses.
"""

import ee


def deduplicate_locations(orig_set):
    """Merge close points, take centroids, and return unique feature collection."""
    buffer_distance = 10  # Adjust based on your criteria
    buffered_points = orig_set.map(lambda point: point.buffer(buffer_distance))
    union_of_buffers = buffered_points.union()
    simplified_union = union_of_buffers.geometry().simplify(buffer_distance / 2)
    centroids = simplified_union.geometries().map(lambda geom: ee.Feature(ee.Geometry(geom).centroid()))
    return ee.FeatureCollection(centroids)


def sampling_ring(positive_dams, inner_radius, outer_radius):
    """Area negatives are drawn from: within outer_radius of a dam, but not within inner_radius.

    Both radii are measured from the dams themselves, so the ring for inner 30 m /
    outer 1000 m spans 30-1000 m from each dam.
    """
    inner = positive_dams.map(lambda pt: pt.buffer(inner_radius, 1)).geometry().dissolve(1)
    outer = positive_dams.map(lambda pt: pt.buffer(outer_radius, 1)).geometry().dissolve(1)
    return outer.difference(inner, 1)


def waterways_in_sampling_area(waterway_fc, ring_area):
    """Waterways negatives can be drawn from: those crossing the sampling ring.

    Using the ring itself, rather than a box around the dams, keeps every stream within
    reach. A box around a tight or single-file cluster of dams beside a stream can miss
    the stream entirely, and a single dam's box has no area at all.
    """
    return waterway_fc.filterBounds(ring_area)


def prepare_hydro(waterway_fc) -> ee.Image:
    """
    Convert a lines/polygons FeatureCollection (hydro) to a raster image
    for sampling, with 'hydro_mask' band = 1 where waterway is present.
    """
    # Paint the features onto an empty image
    base = ee.Image(0).int()
    hydro_raster = base.paint(waterway_fc, 1, 1)

    # Focal max to fill small gaps (optional). Adjust radius/iterations as needed
    filled_image = hydro_raster.focal_max(radius=2, units="meters", iterations=8)
    hydro_raster = filled_image.gt(0).rename(["hydro_mask"])

    return hydro_raster


def sample_negative_points(positive_dams, hydro_raster, ring_area, sampling_scale):
    """
    Create negative points by sampling hydroRaster where hydro_mask == 1, within
    ring_area (see sampling_ring) - the same ring used to select the waterways.
    """
    # Clip hydroRaster to that ring
    clipped_hydro = hydro_raster.clip(ring_area)

    # Sample the same number of negatives as positives
    num_points = positive_dams.size()

    # Use stratifiedSample, specifying classBand='hydro_mask'
    samples = clipped_hydro.stratifiedSample(
        numPoints=num_points, classBand="hydro_mask", region=ring_area, scale=sampling_scale, seed=42, geometries=True
    )

    # Filter only where hydro_mask == 1
    negative_points = samples.filter(ee.Filter.eq("hydro_mask", 1))
    return negative_points
