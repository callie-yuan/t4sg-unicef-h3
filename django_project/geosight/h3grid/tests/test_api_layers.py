"""Focused tests for H3 layer management from Reference Datasets."""

import json
import sys
from types import ModuleType
from unittest import mock

from django.urls import reverse

from core.models.profile import ROLES
from core.tests.base_tests import APITestCase
from core.tests.model_factories import create_user
from geosight.georepo.request.request import GeorepoRequestError
from geosight.h3grid.models import H3ReferenceLayer, H3ReferenceLayerConfig
from geosight.reference_dataset.models.reference_dataset import ReferenceDataset


WKT = 'POLYGON((44 3, 45 3, 45 4, 44 4, 44 3))'


class H3LayerApiTest(APITestCase):
    """Create, edit, and validate H3 layers without changing local datasets."""

    def setUp(self):
        """Set up users, URLs, and a valid payload."""
        self.admin = create_user(ROLES.SUPER_ADMIN.name)
        self.viewer = create_user(ROLES.VIEWER.name)
        self.url = reverse('h3-layer-list')
        self.payload = {
            'name': 'Somalia H3', 'min_resolution': 5,
            'default_resolution': 7, 'max_resolution': 9,
            'area': {'mode': 'paste', 'text': WKT},
        }

    def post(self, payload=None, user=None):
        """Submit a JSON create request."""
        self.client.force_login(user or self.admin)
        return self.client.post(
            self.url, json.dumps(payload or self.payload),
            content_type='application/json'
        )

    def test_create_and_edit_pasted_area(self):
        """Save settings and replace the area while preserving H3 flags."""
        response = self.post()
        self.assertEqual(response.status_code, 201)
        identifier = response.json()['identifier']
        layer = H3ReferenceLayer.objects.get(identifier=identifier)
        self.assertTrue(layer.is_h3)
        self.assertFalse(layer.in_georepo)
        self.assertFalse(ReferenceDataset.objects.filter(pk=layer.pk).exists())
        self.assertEqual(layer.h3_config.clip_countries, [])
        self.assertEqual(layer.h3_config.default_resolution, 7)

        detail = reverse('h3-layer-detail', args=[identifier])
        self.assertEqual(self.client.get(detail).status_code, 200)
        payload = {**self.payload, 'name': 'Updated',
                   'area': {'mode': 'paste', 'text': ''}}
        response = self.client.put(
            detail, json.dumps(payload), content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        layer.refresh_from_db()
        self.assertEqual(layer.name, 'Updated')
        self.assertIsNone(H3ReferenceLayerConfig.objects.get(
            reference_layer=layer
        ).clip_geometry)

    def test_country_area_uses_part_c_outline_once_at_save(self):
        """Persist codes and the outline returned by Part C's service."""
        service = ModuleType('geosight.h3grid.api_georepo')
        service.get_combined_country_outline = mock.Mock(return_value=WKT)
        payload = {**self.payload, 'area': {
            'mode': 'countries', 'country_codes': ['SOM', 'SOM']
        }}
        with mock.patch.dict(sys.modules, {'geosight.h3grid.api_georepo': service}):
            response = self.post(payload)
        self.assertEqual(response.status_code, 201)
        service.get_combined_country_outline.assert_called_once_with(['SOM'])
        config = H3ReferenceLayer.objects.get(
            identifier=response.json()['identifier']
        ).h3_config
        self.assertEqual(config.clip_countries, ['SOM'])
        self.assertTrue(config.clip_geometry.startswith('POLYGON'))

        detail = reverse('h3-layer-detail', args=[response.json()['identifier']])
        self.client.force_login(self.admin)
        response = self.client.put(
            detail, json.dumps(self.payload), content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        config.refresh_from_db()
        self.assertEqual(config.clip_countries, [])
        self.assertTrue(config.clip_geometry.startswith('POLYGON'))

    def test_validation_and_permissions(self):
        """Reject invalid area, resolution order, and non-admin writes."""
        bad = {**self.payload, 'area': {
            'mode': 'paste', 'text': 'POINT(0 0)'
        }, 'default_resolution': 12}
        response = self.post(bad)
        self.assertEqual(response.status_code, 400)
        self.assertIn('area', response.json())
        self.assertIn('default_resolution', response.json())
        self.assertEqual(H3ReferenceLayer.objects.count(), 0)
        self.assertEqual(self.post(user=self.viewer).status_code, 403)

    def test_country_service_error_is_shown_as_area_error(self):
        """GeoRepo failure returns a useful error and does not save a layer."""
        service = ModuleType('geosight.h3grid.api_georepo')
        service.get_combined_country_outline = mock.Mock(
            side_effect=GeorepoRequestError('GeoRepo is unavailable')
        )
        payload = {**self.payload, 'area': {
            'mode': 'countries', 'country_codes': ['SOM']
        }}
        with mock.patch.dict(sys.modules, {'geosight.h3grid.api_georepo': service}):
            response = self.post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('GeoRepo is unavailable', response.json()['area'][0])
        self.assertEqual(H3ReferenceLayer.objects.count(), 0)
