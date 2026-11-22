"""Create and edit H3 reference layers from the Reference Datasets screen."""

import json

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from geosight.georepo.request.request import (
    GeorepoEntityDoesNotExist, GeorepoRequestError,
    GeorepoUrlDoesNotExist,
)
from geosight.h3grid.clipping import parse_aoi
from geosight.h3grid.models import H3ReferenceLayer, H3ReferenceLayerConfig
from geosight.h3grid.validation import H3Error
from geosight.permission.models.resource.reference_layer_view import (
    ReferenceLayerViewPermission,
)


def layer_data(layer):
    """Return the fields needed by the H3 edit screen."""
    config = layer.h3_config
    return {
        'identifier': layer.identifier,
        'name': layer.name,
        'default_resolution': config.default_resolution,
        'min_resolution': config.min_resolution,
        'max_resolution': config.max_resolution,
        'area': {
            'mode': 'countries' if config.clip_countries else 'paste',
            'text': '' if config.clip_countries else (config.clip_geometry or ''),
            'country_codes': config.clip_countries,
        },
    }


def validate_layer_data(data):
    """Validate form values and resolve the selected area before saving."""
    errors = {}
    name = data.get('name')
    if not isinstance(name, str) or not name.strip():
        errors['name'] = ['Name is required.']
    elif len(name.strip()) > 256:
        errors['name'] = ['Name must be 256 characters or fewer.']

    resolutions = {}
    for field in ('min_resolution', 'default_resolution', 'max_resolution'):
        value = data.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 15:
            errors[field] = ['Enter a whole number from 0 to 15.']
        else:
            resolutions[field] = value
    if len(resolutions) == 3 and not (
        resolutions['min_resolution'] <= resolutions['default_resolution']
        <= resolutions['max_resolution']
    ):
        errors['default_resolution'] = [
            'Default resolution must be between minimum and maximum.'
        ]

    area = data.get('area')
    if not isinstance(area, dict) or area.get('mode') not in ('paste', 'countries'):
        errors['area'] = ['Choose Paste or Countries.']
        area = {}

    geometry = None
    codes = []
    if area.get('mode') == 'paste':
        text = area.get('text', '')
        if not isinstance(text, str):
            errors['area'] = ['Paste WKT or GeoJSON text.']
        elif text.strip():
            try:
                geometry = parse_aoi(text).wkt
            except H3Error as error:
                errors['area'] = [str(error)]
    elif area.get('mode') == 'countries':
        selected = area.get('country_codes')
        if not isinstance(selected, list) or not selected or any(
            not isinstance(code, str) or not code.strip() for code in selected
        ):
            errors['area'] = ['Choose at least one country.']
        else:
            codes = list(dict.fromkeys(code.strip() for code in selected))
            # Part C supplies this service using GeoSight's GeoRepo client.
            try:
                from geosight.h3grid.api_georepo import get_combined_country_outline
                outline = get_combined_country_outline(codes)
                if not isinstance(outline, str):
                    outline = json.dumps(outline) if isinstance(outline, dict) else outline.wkt
                geometry = parse_aoi(outline).wkt
            except ImportError as error:
                errors['area'] = [f'Country service is unavailable: {error}']
            except (H3Error, GeorepoRequestError,
                    GeorepoEntityDoesNotExist, GeorepoUrlDoesNotExist,
                    LookupError,
                    ValueError, TypeError) as error:
                errors['area'] = [str(error)]

    if errors:
        raise ValidationError(errors)
    return name.strip(), resolutions, geometry, codes


class H3LayerListAPI(APIView):
    """Create an H3 reference layer."""

    def post(self, request):
        """Create a layer and its config as one transaction."""
        if not request.user.is_authenticated or not request.user.profile.is_admin:
            raise PermissionDenied()
        name, resolutions, geometry, codes = validate_layer_data(request.data)
        with transaction.atomic():
            layer = H3ReferenceLayer.objects.create(
                identifier=H3ReferenceLayer.get_uuid(), name=name,
                creator=request.user,
            )
            config = H3ReferenceLayerConfig(
                reference_layer=layer, clip_geometry=geometry,
                clip_countries=codes, **resolutions
            )
            config.full_clean()
            config.save()
            ReferenceLayerViewPermission.objects.get_or_create(obj=layer)
        return Response(layer_data(layer), status=201)


class H3LayerDetailAPI(APIView):
    """Read or edit a single H3 reference layer."""

    def get_layer(self, request, identifier, edit=False):
        """Look up an H3 layer and check its resource permission."""
        if not request.user.is_authenticated or not request.user.profile.is_admin:
            raise PermissionDenied()
        layer = get_object_or_404(H3ReferenceLayer, identifier=identifier)
        permission, _ = ReferenceLayerViewPermission.objects.get_or_create(obj=layer)
        allowed = permission.has_edit_perm(request.user) if edit else permission.has_read_perm(request.user)
        if not allowed:
            raise PermissionDenied()
        return layer

    def get(self, request, identifier):
        """Return the values used to populate the H3 form."""
        return Response(layer_data(self.get_layer(request, identifier)))

    def put(self, request, identifier):
        """Update the layer and its config as one transaction."""
        layer = self.get_layer(request, identifier, edit=True)
        name, resolutions, geometry, codes = validate_layer_data(request.data)
        with transaction.atomic():
            layer.name = name
            layer.save()
            config, _ = H3ReferenceLayerConfig.objects.get_or_create(
                reference_layer=layer, defaults=resolutions
            )
            for field, value in resolutions.items():
                setattr(config, field, value)
            config.clip_geometry = geometry
            config.clip_countries = codes
            try:
                config.full_clean()
            except DjangoValidationError as error:
                raise ValidationError(error.message_dict if hasattr(error, 'message_dict') else error.messages)
            config.save()
        return Response(layer_data(layer))
