# coding=utf-8
"""
GeoSight is UNICEF's geospatial web-based business intelligence platform.

Contact : geosight-no-reply@unicef.org

.. note:: This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.

"""
__date__ = '23/11/2026'
__copyright__ = ('Copyright 2026, Unicef')

import json

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from geosight.data.models.dashboard import Dashboard
from geosight.georepo.request.request import (
    GeorepoEntityDoesNotExist, GeorepoRequestError, GeorepoUrlDoesNotExist,
)
from geosight.h3grid.clipping import parse_aoi
from geosight.h3grid.models import H3ProjectArea, H3ReferenceLayer
from geosight.h3grid.validation import H3Error
from geosight.permission.models.resource.reference_layer_view import (
    ReferenceLayerViewPermission,
)

IN_EFFECT_PROJECT = 'project'
IN_EFFECT_LAYER = 'layer'
IN_EFFECT_NONE = 'none'


def has_text(text):
    """Return True when an area text is not blank."""
    return bool(text and text.strip())


def layer_has_area(layer):
    """Return True when an H3 layer has its own area."""
    config = getattr(layer, 'h3_config', None) if layer else None
    return bool(config and has_text(config.clip_geometry))


def area_data(area):
    """Return a project area in the shape used by the area input."""
    if not area or not has_text(area.clip_geometry):
        return None
    return {
        'mode': 'countries' if area.clip_countries else 'paste',
        'text': '' if area.clip_countries else area.clip_geometry,
        'country_codes': area.clip_countries,
    }


def pasted_area(text):
    """Return the WKT of a pasted WKT/GeoJSON area."""
    if not isinstance(text, str) or not text.strip():
        raise ValidationError({
            'area': ['Paste an area, or clear it to use the layer area.']
        })
    try:
        return parse_aoi(text).wkt
    except H3Error as error:
        raise ValidationError({'area': [str(error)]})


def countries_area(codes):
    """Return the WKT outline of countries, from GeoRepo.

    It uses the same GeoRepo outline service as the layer area.
    """
    if not isinstance(codes, list) or not codes or any(
            not isinstance(code, str) or not code.strip() for code in codes
    ):
        raise ValidationError({'area': ['Choose at least one country.']})
    codes = list(dict.fromkeys(code.strip() for code in codes))
    try:
        from geosight.h3grid.api_georepo import get_combined_country_outline
        outline = get_combined_country_outline(codes)
        if not isinstance(outline, str):
            outline = (
                json.dumps(outline) if isinstance(outline, dict)
                else outline.wkt
            )
        return parse_aoi(outline).wkt, codes
    except ImportError as error:
        raise ValidationError(
            {'area': [f'Country service is unavailable: {error}']}
        )
    except (
            H3Error, GeorepoRequestError, GeorepoEntityDoesNotExist,
            GeorepoUrlDoesNotExist, LookupError, ValueError, TypeError
    ) as error:
        raise ValidationError({'area': [str(error)]})


def validate_area(area):
    """Check the area from the request and return (geometry, codes).

    The area is the value of the area input: a pasted WKT/GeoJSON, or
    countries whose outline comes from GeoRepo (same as the layer area).
    """
    if not isinstance(area, dict) or (
            area.get('mode') not in ('paste', 'countries')
    ):
        raise ValidationError({'area': ['Choose Paste or Countries.']})
    if area['mode'] == 'paste':
        return pasted_area(area.get('text')), []
    return countries_area(area.get('country_codes'))


class H3ProjectAreaAPI(APIView):
    """Get, set or clear the area of a project on an H3 layer.

    Anyone who can edit the project can set or clear its area.
    """

    def get_project(self, request, slug, edit=False):
        """Return the project, checking the read or edit permission."""
        if not request.user.is_authenticated:
            raise PermissionDenied()
        project = get_object_or_404(Dashboard, slug=slug)
        permission = project.permission
        allowed = (
            permission.has_edit_perm(request.user) if edit
            else permission.has_read_perm(request.user)
        )
        if not allowed:
            raise PermissionDenied(
                'You do not have permission to change this project'
                if edit else
                'You do not have permission to access this project'
            )
        return project

    def response(self, project):
        """Return the project area and which area is in effect."""
        area = area_data(getattr(project, 'h3_area', None))
        layer = project.reference_layer
        is_h3 = bool(layer and layer.is_h3)
        if area and is_h3:
            in_effect = IN_EFFECT_PROJECT
        elif is_h3 and layer_has_area(layer):
            in_effect = IN_EFFECT_LAYER
        else:
            in_effect = IN_EFFECT_NONE
        return Response({
            'area': area,
            'layer_has_area': is_h3 and layer_has_area(layer),
            'in_effect': in_effect,
        })

    def get(self, request, slug):
        """Return the project area."""
        return self.response(self.get_project(request, slug))

    def put(self, request, slug):
        """Set the project area."""
        project = self.get_project(request, slug, edit=True)
        layer = project.reference_layer
        if not (layer and layer.is_h3):
            raise ValidationError({
                'area': ['Only projects on an H3 layer can have an area.']
            })
        geometry, codes = validate_area(request.data.get('area'))
        H3ProjectArea.objects.update_or_create(
            project=project,
            defaults={'clip_geometry': geometry, 'clip_countries': codes}
        )
        # Fresh copy, so the area relation isn't cached
        return self.response(Dashboard.objects.get(pk=project.pk))

    def delete(self, request, slug):
        """Clear the project area, so the layer area is used again."""
        project = self.get_project(request, slug, edit=True)
        H3ProjectArea.objects.filter(project=project).delete()
        # Fresh copy, so the area relation isn't cached
        return self.response(Dashboard.objects.get(pk=project.pk))


class H3LayerAreaAPI(APIView):
    """Say if an H3 layer has its own area.

    Used by the project editor before the project is saved.
    """

    def get(self, request, identifier):
        """Return whether the layer has an area."""
        if not request.user.is_authenticated:
            raise PermissionDenied()
        layer = get_object_or_404(H3ReferenceLayer, identifier=identifier)
        permission, _ = ReferenceLayerViewPermission.objects.get_or_create(
            obj=layer
        )
        if not permission.has_read_perm(request.user):
            raise PermissionDenied()
        return Response({'has_area': layer_has_area(layer)})
