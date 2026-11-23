"""Reference Datasets page shell for H3 layer creation and editing."""

import json

from django import forms
from django.shortcuts import get_object_or_404, reverse

from frontend.views.admin._base import AdminBaseView
from geosight.h3grid.api_layers import layer_data
from geosight.h3grid.models import H3ReferenceLayer
from geosight.permission.access import (
    RoleLocalDatasetManagerRequiredMixin, edit_permission_resource,
)
from geosight.permission.models.resource.reference_layer_view import (
    ReferenceLayerViewPermission,
)


class H3LayerFormView(RoleLocalDatasetManagerRequiredMixin, AdminBaseView):
    """Render the H3 branch of the existing Reference Datasets form bundle."""

    template_name = 'reference_dataset/admin/form.html'

    @property
    def page_title(self):
        """Return the browser tab title."""
        return 'H3 Reference Layer'

    @property
    def content_title(self):
        """Return a link back to Reference Datasets."""
        return (
            f'<a href="{reverse("admin-reference-dataset-list-view")}">'
            'Reference Datasets</a> <span>></span> H3 layer'
        )

    def get_context_data(self, **kwargs):
        """Pass initial H3 values to the React form without a local dataset form."""
        context = super().get_context_data(**kwargs)
        identifier = self.kwargs.get('identifier')
        initial = {}
        if identifier:
            layer = get_object_or_404(H3ReferenceLayer, identifier=identifier)
            permission, _ = ReferenceLayerViewPermission.objects.get_or_create(
                obj=layer
            )
            edit_permission_resource(layer, self.request.user)
            initial = layer_data(layer)
        context.update({
            'is_h3': True,
            'form': forms.Form(),
            'h3_initial': json.dumps(initial).replace('<', '\\u003c'),
        })
        return context
