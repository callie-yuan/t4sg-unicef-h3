"""Parse a pasted area of interest (AOI) and clip H3 cells to it."""

import json

import h3
from django.contrib.gis.gdal.error import GDALException
from django.contrib.gis.geos import GEOSException, GEOSGeometry, Point

from geosight.h3grid.validation import H3Error

SRID = 4326
POLYGON_TYPES = ('Polygon', 'MultiPolygon')


def _read_geometry(text):
    """Return a GEOS geometry from WKT/EWKT text or a GeoJSON geometry.

    :param text: WKT/EWKT text, GeoJSON geometry text, or a geometry dict.
    :type text: str or dict
    :return: Geometry in srid 4326.
    :rtype: GEOSGeometry
    :raises H3Error: If the text can't be read as a geometry.
    """
    try:
        if isinstance(text, dict):
            text = json.dumps(text)
        geometry = GEOSGeometry(text)
    except (GDALException, GEOSException, ValueError, TypeError) as error:
        raise H3Error(
            'Could not read the area. Paste a WKT POLYGON/MULTIPOLYGON '
            f'or GeoJSON polygon ({error})'
        )
    if geometry.srid is None:
        geometry.srid = SRID
    elif geometry.srid != SRID:
        geometry.transform(SRID)
    return geometry


def _check_polygon(geometry):
    """Check that a geometry is a valid, non-empty polygon.

    :param geometry: Geometry to check.
    :type geometry: GEOSGeometry
    :return: The same geometry.
    :rtype: GEOSGeometry
    :raises H3Error: If it isn't a valid, non-empty Polygon/MultiPolygon.
    """
    if geometry.geom_type not in POLYGON_TYPES:
        raise H3Error(
            f'The area must be a Polygon or MultiPolygon, '
            f'not a {geometry.geom_type}'
        )
    if geometry.empty:
        raise H3Error('The area is empty')
    if not geometry.valid:
        raise H3Error(
            f'The area is not a valid polygon ({geometry.valid_reason}). '
            f'Check that its edges do not cross each other'
        )
    return geometry


def _geojson_geometries(data):
    """Return the geometries in a GeoJSON geometry/Feature/Collection.

    :param data: Parsed GeoJSON.
    :type data: dict
    :return: GeoJSON geometry dicts.
    :rtype: list
    :raises H3Error: If a Feature or FeatureCollection has no geometry.
    """
    if not isinstance(data, dict):
        raise H3Error('GeoJSON must be an object with a "type"')
    geojson_type = data.get('type')
    if geojson_type == 'FeatureCollection':
        features = data.get('features') or []
        if not features:
            raise H3Error('The FeatureCollection has no features')
        geometries = []
        for feature in features:
            geometries.extend(_geojson_geometries(feature))
        return geometries
    if geojson_type == 'Feature':
        if not data.get('geometry'):
            raise H3Error('The Feature has no geometry')
        return [data['geometry']]
    return [data]


def parse_aoi(text) -> GEOSGeometry:
    """Return the pasted area as one valid Polygon/MultiPolygon.

    Accepts WKT POLYGON/MULTIPOLYGON, or GeoJSON as a bare geometry,
    a Feature, or a FeatureCollection of polygons.

    :param text: Text the admin pasted.
    :type text: str
    :return: The area in srid 4326.
    :rtype: GEOSGeometry
    :raises H3Error: With a message saying what to fix, if not usable.
    """
    if not isinstance(text, str) or not text.strip():
        raise H3Error('No area given. Paste a WKT or GeoJSON polygon')
    text = text.strip()

    if text.startswith('{'):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise H3Error(f'Could not read the GeoJSON ({error.msg})')
        parts = [
            _check_polygon(_read_geometry(geometry))
            for geometry in _geojson_geometries(data)
        ]
        aoi = parts[0]
        for part in parts[1:]:
            aoi = aoi.union(part)
    else:
        aoi = _check_polygon(_read_geometry(text))

    aoi.srid = SRID
    return aoi


def cells_in_aoi(cells, aoi):
    """Return the cells whose center is inside the area, edge included.

    :param cells: H3 cell IDs.
    :type cells: iterable
    :param aoi: Area from parse_aoi.
    :type aoi: GEOSGeometry
    :return: Kept cell IDs, in input order.
    :rtype: list
    """
    prepared = aoi.prepared
    kept = []
    for cell in cells:
        lat, lng = h3.cell_to_latlng(cell)
        if prepared.covers(Point(lng, lat, srid=SRID)):
            kept.append(cell)
    return kept
