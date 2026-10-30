# coding=utf-8
"""
GeoSight is UNICEF's geospatial web-based business intelligence platform.

Contact : geosight-no-reply@unicef.org

.. note:: This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.

"""
__author__ = 'irwan@kartoza.com'
__date__ = '13/06/2023'
__copyright__ = ('Copyright 2023, Unicef')

from django.db.models import Q
from drf_yasg.utils import swagger_auto_schema

from core.api_utils import common_api_params, ApiParams
from core.permissions import (
    RoleContributorAuthenticationPermission,
    RoleCreatorAuthenticationPermission
)
from geosight.data.api.v1.base import BaseApiV1Resource
from geosight.h3grid.models import H3ReferenceLayer
from geosight.permission.models.resource.reference_layer_view import (
    ReferenceLayerViewPermission
)
from geosight.reference_dataset.api.v1.api_utils import (
    ApiTag as ReferenceApiTag,
    ApiParams as ReferenceApiParams,
)
from geosight.reference_dataset.models.reference_dataset import (
    ReferenceDataset
)
from geosight.reference_dataset.serializer.reference_dataset import (
    ReferenceDatasetSerializer
)


class ReferenceDatasetViewSet(BaseApiV1Resource):
    """Reference Dataset view set."""

    model_class = ReferenceDataset
    serializer_class = ReferenceDatasetSerializer
    extra_exclude_fields = ['id']
    lookup_field = 'identifier'
    lookup_value_regex = '[0-9A-Fa-f]{8}(-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}'
    http_method_names = ['get', 'delete']
    non_filtered_keys = BaseApiV1Resource.non_filtered_keys + ['include_h3']

    @property
    def queryset(self):
        """
        Return the queryset, with H3 reference layers when requested.

        Local reference datasets exclude H3 layers. The list adds them
        only with `include_h3=true`; detail always resolves them so a
        selected H3 layer can be loaded.
        """
        query = super().queryset
        if self.action == 'retrieve':
            return ReferenceDataset._base_manager.filter(in_georepo=False)
        if (
                self.action == 'list' and
                self.request.GET.get('include_h3') == 'true'
        ):
            h3 = H3ReferenceLayer.permissions.list(self.request.user)
            return ReferenceDataset._base_manager.filter(
                Q(id__in=query.values('id')) | Q(id__in=h3.values('id'))
            )
        return query

    def get_permissions(self):
        """Get the permissions based on the action."""
        if self.action in ['create', 'destroy']:
            permission_classes = [RoleCreatorAuthenticationPermission]
        elif self.action in ['update', 'partial_update']:
            permission_classes = [RoleContributorAuthenticationPermission]
        else:
            permission_classes = []
        return [permission() for permission in permission_classes]

    @swagger_auto_schema(
        operation_id='reference-datasets-list',
        tags=[ReferenceApiTag.REFERENCE_DATASET],
        manual_parameters=[
            *common_api_params,
            ApiParams.NAME_CONTAINS,
            ReferenceApiParams.IDENTIFIER
        ],
        operation_description=(
                'Return list of accessed reference dataset for the user.'
        )
    )
    def list(self, request, *args, **kwargs):
        """List of reference-dataset."""
        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id='reference-datasets-detail',
        tags=[ReferenceApiTag.REFERENCE_DATASET],
        manual_parameters=[],
        operation_description='Return detailed of reference dataset.'
    )
    def retrieve(self, request, identifier=None):
        """
        Return detailed of reference-dataset.

        For H3 layers, also returns `h3_config` (default, min and max
        resolution), so the project editor can show a layer's settings.

        :param request: The HTTP request.
        :type request: Request
        :param identifier: Identifier of the reference dataset.
        :type identifier: str
        :return: The serialized reference dataset.
        :rtype: Response
        """
        h3_layer = H3ReferenceLayer.objects.filter(
            identifier=identifier
        ).first()
        if h3_layer:
            # H3 layers may have no permission row yet. post_save is sent
            # with the proxy class, so the ReferenceLayerView receiver that
            # creates it does not run for them.
            ReferenceLayerViewPermission.objects.get_or_create(obj=h3_layer)

        response = super().retrieve(request, identifier=identifier)
        if h3_layer:
            config = getattr(h3_layer, 'h3_config', None)
            response.data['h3_config'] = {
                'default_resolution': config.default_resolution,
                'min_resolution': config.min_resolution,
                'max_resolution': config.max_resolution
            } if config else None
        return response

    @swagger_auto_schema(
        operation_id='reference-datasets-detail-delete',
        tags=[ReferenceApiTag.REFERENCE_DATASET],
        manual_parameters=[],
        operation_description='Delete a reference dataset.'
    )
    def destroy(self, request, identifier=None):
        """Destroy an object."""
        return super().destroy(request, id=identifier)
