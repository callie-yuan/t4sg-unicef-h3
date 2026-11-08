"""
GeoSight is UNICEF's geospatial web-based business intelligence platform.

Contact : geosight-no-reply@unicef.org

.. note:: This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.

"""

from django.db.models import OuterRef, Subquery
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from geosight.data.models.indicator import Indicator, IndicatorValue
from geosight.h3grid.clipping import cells_in_aoi, parse_aoi
from geosight.h3grid.models import H3ReferenceLayer

H3_CELL_REGEX = r'^8[0-9a-f]{14}$'
H3_MIN_RESOLUTION = 0
H3_MAX_RESOLUTION = 15


def h3_values(indicator):
    """Return the indicator values whose geom_id is an H3 cell"""
    return IndicatorValue.objects.filter(
        indicator=indicator, geom_id__regex=H3_CELL_REGEX
    )


class _H3IndicatorAPI(APIView):
    """Base H3 indicator API"""

    def get_aoi(self, request):
        """Return the clip area of ?reference_layer=<identifier>, or None.

        None means no filtering: no parameter, or the layer has no clip.
        """
        identifier = request.GET.get('reference_layer')
        if not identifier:
            return None
        layer = H3ReferenceLayer.objects.filter(identifier=identifier).first()
        if layer is None:
            raise Http404('H3 reference layer not found')
        config = getattr(layer, 'h3_config', None)
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
                return Response([])
            values = query.filter(date=date)
        values = list(values.values('geom_id', 'value'))
        if aoi is not None:
            kept = set(cells_in_aoi([v['geom_id'] for v in values], aoi))
            values = [v for v in values if v['geom_id'] in kept]
        return Response(values)