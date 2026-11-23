"""
GeoSight is UNICEF's geospatial web-based business intelligence platform.

Contact : geosight-no-reply@unicef.org

.. note:: This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.

"""

import json

import h3
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.db.models import OuterRef, Subquery
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ParseError, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from geosight.data.models.dashboard import Dashboard
from geosight.data.models.indicator import Indicator, IndicatorValue
from geosight.h3grid.clipping import SRID, cells_in_aoi, parse_aoi
from geosight.h3grid.models import H3ReferenceLayer

H3_CELL_REGEX = r'^8[0-9a-f]{14}$'
H3_MIN_RESOLUTION = 0
H3_MAX_RESOLUTION = 15
H3_MAX_AREA_CELLS = 50000
EQUAL_AREA_SRID = 6933


def h3_values(indicator):
    """Return the indicator values whose geom_id is an H3 cell"""
    return IndicatorValue.objects.filter(
        indicator=indicator, geom_id__regex=H3_CELL_REGEX
    )


def estimate_area_cells(aoi, resolution):
    """Return roughly how many cells of a resolution cover the area."""
    area_km2 = aoi.transform(EQUAL_AREA_SRID, clone=True).area / 1e6
    return area_km2 / h3.average_hexagon_area(resolution, 'km^2')


def area_cells(aoi, resolution):
    """Return the cells whose center is inside the area.

    :return: Cell IDs, or None if there are more than H3_MAX_AREA_CELLS.
    :rtype: list or None
    """
    # Refuse huge areas before listing their cells
    if estimate_area_cells(aoi, resolution) > 2 * H3_MAX_AREA_CELLS:
        return None
    cells = h3.h3shape_to_cells(
        h3.geo_to_h3shape(json.loads(aoi.geojson)), resolution
    )
    if len(cells) > H3_MAX_AREA_CELLS:
        return None
    return cells


def too_many_cells(aoi, resolution):
    """Return a 400 saying the area is too big for the resolution."""
    coarser = resolution - 1
    while coarser > H3_MIN_RESOLUTION and (
            estimate_area_cells(aoi, coarser) > H3_MAX_AREA_CELLS
    ):
        coarser -= 1
    return HttpResponseBadRequest(
        f'The area has more than {H3_MAX_AREA_CELLS} cells at resolution '
        f'{resolution}. Use a coarser resolution, e.g. {max(coarser, 0)}, '
        f'or a smaller bbox'
    )


def parse_bbox(text):
    """Return ?bbox=west,south,east,north as a tuple of floats.

    :raises ValueError: If it isn't 4 numbers forming a lng/lat box.
    """
    try:
        west, south, east, north = [float(part) for part in text.split(',')]
    except ValueError:
        raise ValueError('bbox must be west,south,east,north')
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError(
            'bbox must be west,south,east,north in degrees, '
            'with west < east and south < north'
        )
    return west, south, east, north


def in_bbox(cell, bbox):
    """Return whether the cell's center is inside the box, edge included."""
    lat, lng = h3.cell_to_latlng(cell)
    west, south, east, north = bbox
    return west <= lng <= east and south <= lat <= north


def clip_to_bbox(aoi, bbox):
    """Return the part of the area inside the box, or None if nothing."""
    box = Polygon.from_bbox(bbox)
    box.srid = SRID
    part = aoi.intersection(box)
    parts = part if part.geom_type in (
        'MultiPolygon', 'GeometryCollection'
    ) else [part]
    # A box touching the area only along an edge leaves lines or points
    polygons = [
        geometry for geometry in parts
        if geometry.geom_type == 'Polygon' and not geometry.empty
    ]
    if not polygons:
        return None
    if len(polygons) == 1:
        return polygons[0]
    return MultiPolygon(polygons, srid=SRID)


def with_empty_cells(values, cells):
    """Add {geom_id, value: None} for the cells without a value."""
    have_value = {v['geom_id'] for v in values}
    return values + [
        {'geom_id': cell, 'value': None}
        for cell in sorted(cells) if cell not in have_value
    ]


class _H3IndicatorAPI(APIView):
    """Base H3 indicator API"""

    def get_project(self, request):
        """Return the project of ?project=<id>, or None."""
        project_id = request.GET.get('project')
        if not project_id:
            return None
        if not project_id.isdigit():
            raise ParseError('project must be an integer id')
        project = get_object_or_404(Dashboard, pk=project_id)
        readable = Dashboard.permissions.read(request.user)
        if not readable.filter(pk=project.pk).exists():
            raise PermissionDenied(
                'You do not have permission to access this project'
            )
        return project

    def get_aoi(self, request):
        """Return the area that applies to the request, or None.

        The project's area (?project=<id>) comes first. Otherwise the
        clip of the layer (?reference_layer=<identifier>, or else the
        project's reference layer). None means no filtering.
        """
        project = self.get_project(request)
        area = getattr(project, 'h3_area', None) if project else None
        if area and area.clip_geometry and area.clip_geometry.strip():
            return parse_aoi(area.clip_geometry)

        identifier = request.GET.get('reference_layer')
        if identifier:
            layer = H3ReferenceLayer.objects.filter(
                identifier=identifier
            ).first()
            if layer is None:
                raise Http404('H3 reference layer not found')
        elif project:
            layer = project.reference_layer
        else:
            return None
        config = getattr(layer, 'h3_config', None) if layer else None
        text = config.clip_geometry if config else None
        if not text or not text.strip():
            return None
        return parse_aoi(text)

    def get_indicator(self, request, pk):
        indicator = get_object_or_404(Indicator, pk=pk)
        readable = Indicator.permissions.read_data(request.user)
        if not readable.filter(pk=indicator.pk).exists():
            raise PermissionDenied(
                'You do not have permission to access this indicator'
            )
        return indicator


class H3IndicatorResolutionsAPI(_H3IndicatorAPI):
    """Return H3 resolutions (admin levels) of an indicator sorted"""

    def get(self, request, pk):
        indicator = self.get_indicator(request, pk)
        aoi = self.get_aoi(request)
        values = h3_values(indicator)
        levels = list(
            values.values_list('admin_level', flat=True)
            .distinct().order_by('admin_level')
        )
        if aoi is not None:
            levels = [
                level for level in levels
                if cells_in_aoi(
                    values.filter(admin_level=level)
                    .values_list('geom_id', flat=True).distinct(),
                    aoi
                )
            ]
        return Response(levels)


class H3IndicatorValuesAPI(_H3IndicatorAPI):
    """Return H3 cell values for a resolution and optional as-of date."""

    def get(self, request, pk):
        indicator = self.get_indicator(request, pk)
        aoi = self.get_aoi(request)
        try:
            resolution = int(request.GET.get('resolution'))
        except (TypeError, ValueError):
            resolution = None
        if resolution is None or not (
                H3_MIN_RESOLUTION <= resolution <= H3_MAX_RESOLUTION
        ):
            return HttpResponseBadRequest(
                f'resolution must be an integer between '
                f'{H3_MIN_RESOLUTION} and {H3_MAX_RESOLUTION}'
            )
        # Only the cells in view, when a box is given
        bbox = request.GET.get('bbox')
        if bbox:
            try:
                bbox = parse_bbox(bbox)
            except ValueError as error:
                return HttpResponseBadRequest(str(error))
        # Cells of the area without a value, only when asked for
        cells = []
        include_empty = request.GET.get('include_empty', '').lower()
        if include_empty in ('true', '1') and aoi is not None:
            empty_area = clip_to_bbox(aoi, bbox) if bbox else aoi
            if empty_area is not None:
                cells = area_cells(empty_area, resolution)
                if cells is None:
                    return too_many_cells(empty_area, resolution)
        query = h3_values(indicator).filter(admin_level=resolution)

        date = request.GET.get('date')
        if date:
            date = parse_date(date)
            if not date:
                return HttpResponseBadRequest('date must be YYYY-MM-DD')
            query = query.filter(date__lte=date)
            latest_cell_value = (
                query.filter(geom_id=OuterRef('geom_id'))
                .order_by('-date', '-pk').values('pk')[:1]
            )
            values = query.filter(pk=Subquery(latest_cell_value))
        else:
            date = (
                query.order_by('-date').values_list('date', flat=True).first()
            )
            if date is None:
                return Response(with_empty_cells([], cells))
            values = query.filter(date=date)
        values = list(values.values('geom_id', 'value'))
        if bbox:
            values = [v for v in values if in_bbox(v['geom_id'], bbox)]
        if aoi is not None:
            kept = set(cells_in_aoi([v['geom_id'] for v in values], aoi))
            values = [v for v in values if v['geom_id'] in kept]
        return Response(with_empty_cells(values, cells))