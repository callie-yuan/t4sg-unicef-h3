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
from datetime import date

import h3
from django.urls import reverse

from core.models.profile import ROLES
from core.tests.base_tests import APITestCase
from core.tests.model_factories import create_user
from geosight.data.tests.model_factories import (
    DashboardF, IndicatorF, IndicatorValueF
)
from geosight.h3grid.models import (
    H3ProjectArea, H3ReferenceLayer, H3ReferenceLayerConfig
)
from geosight.permission.models.factory import PERMISSIONS

RES = 7
LAYER_WKT = 'POLYGON((44.4 3.4, 44.6 3.4, 44.6 3.6, 44.4 3.6, 44.4 3.4))'
PROJECT_WKT = 'POLYGON((46 5, 47 5, 47 6, 46 6, 46 5))'
LAYER_CELL = h3.latlng_to_cell(3.5, 44.5, RES)
PROJECT_CELL = h3.latlng_to_cell(5.5, 46.5, RES)


class H3ProjectAreaApiTest(APITestCase):
    """Set and clear a project's own area from the project editor."""

    def setUp(self):
        """Create an H3 layer with an area, two projects and users."""
        self.admin = create_user(ROLES.SUPER_ADMIN.name)
        # Not admins: one can edit the project, one can only view it
        self.editor = create_user(ROLES.CREATOR.name)
        self.viewer = create_user(ROLES.VIEWER.name)

        self.layer = H3ReferenceLayer.objects.create(
            identifier='5b8a6c1e-7f0e-4a55-9a43-1d6f1c0e9a01',
            name='H3 layer'
        )
        H3ReferenceLayerConfig.objects.create(
            reference_layer=self.layer, min_resolution=5,
            default_resolution=RES, max_resolution=9,
            clip_geometry=LAYER_WKT
        )
        self.project = DashboardF(reference_layer=self.layer)
        self.other_project = DashboardF(reference_layer=self.layer)
        self.project.permission.update_user_permission(
            self.editor, PERMISSIONS.WRITE.name
        )
        self.project.permission.update_user_permission(
            self.viewer, PERMISSIONS.READ.name
        )

        self.indicator = IndicatorF()
        for cell, value in [(LAYER_CELL, 1), (PROJECT_CELL, 2)]:
            IndicatorValueF(
                indicator=self.indicator, geom_id=cell, admin_level=RES,
                value=value, date=date(2026, 1, 1)
            )

    def url(self, project=None):
        """Return the area URL of a project."""
        return reverse(
            'h3-project-area', args=[(project or self.project).slug]
        )

    def put(self, area, user, project=None):
        """Set an area as a user."""
        self.client.force_login(user)
        return self.client.put(
            self.url(project), json.dumps({'area': area}),
            content_type='application/json'
        )

    def delete(self, user, project=None):
        """Clear the area as a user."""
        self.client.force_login(user)
        return self.client.delete(self.url(project))

    def cells(self, project):
        """Return the cells the map gets for a project."""
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse('h3-indicator-values', args=[self.indicator.id]),
            {'resolution': RES, 'project': project.id,
             'reference_layer': self.layer.identifier}
        )
        self.assertEqual(response.status_code, 200)
        return {row['geom_id'] for row in response.json()}

    def test_editor_can_set_and_clear(self):
        """A non-admin editor sets the area, then clears it."""
        response = self.put(
            {'mode': 'paste', 'text': PROJECT_WKT}, self.editor
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['in_effect'], 'project')
        self.assertEqual(response.json()['area']['mode'], 'paste')
        self.assertTrue(
            H3ProjectArea.objects.filter(project=self.project).exists()
        )
        # Saved as WKT, readable again by the area input
        self.assertTrue(
            response.json()['area']['text'].startswith('POLYGON')
        )

        response = self.delete(self.editor)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['area'])
        self.assertFalse(
            H3ProjectArea.objects.filter(project=self.project).exists()
        )

    def test_viewer_cannot_set_or_clear(self):
        """A viewer can read the area but not change it."""
        H3ProjectArea.objects.create(
            project=self.project, clip_geometry=PROJECT_WKT
        )
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.url()).status_code, 200)
        self.assertEqual(
            self.put({'mode': 'paste', 'text': LAYER_WKT}, self.viewer)
            .status_code, 403
        )
        self.assertEqual(self.delete(self.viewer).status_code, 403)
        self.assertEqual(
            H3ProjectArea.objects.get(project=self.project).clip_geometry,
            PROJECT_WKT
        )

    def test_invalid_shape_is_rejected(self):
        """Bad shapes get a readable message and nothing is saved."""
        for text in ['not a shape', 'POINT(45 2)', '   ']:
            with self.subTest(text=text):
                response = self.put(
                    {'mode': 'paste', 'text': text}, self.editor
                )
                self.assertEqual(response.status_code, 400)
                message = response.json()['area'][0]
                self.assertIsInstance(message, str)
                self.assertTrue(message)
        self.assertFalse(
            H3ProjectArea.objects.filter(project=self.project).exists()
        )

    def test_hexagons_follow_the_project_area(self):
        """The project's own area clips its hexagons.

        Clearing it goes back to the layer's area, and another project on
        the same layer is unchanged.
        """
        self.assertEqual(self.cells(self.project), {LAYER_CELL})

        self.put({'mode': 'paste', 'text': PROJECT_WKT}, self.editor)
        self.assertEqual(self.cells(self.project), {PROJECT_CELL})
        self.assertEqual(self.cells(self.other_project), {LAYER_CELL})

        response = self.delete(self.editor)
        self.assertEqual(response.json()['in_effect'], 'layer')
        self.assertEqual(self.cells(self.project), {LAYER_CELL})

    def test_in_effect(self):
        """The API says which area is in effect."""
        self.client.force_login(self.viewer)
        self.assertEqual(
            self.client.get(self.url()).json()['in_effect'], 'layer'
        )
        config = self.layer.h3_config
        config.clip_geometry = ''
        config.save()
        self.assertEqual(
            self.client.get(self.url()).json()['in_effect'], 'none'
        )
        layer_url = reverse('h3-layer-area', args=[self.layer.identifier])
        self.assertEqual(
            self.client.get(layer_url).json(), {'has_area': False}
        )

    def test_non_h3_project(self):
        """Non-H3 projects can't get an area and are left as they were."""
        project = DashboardF()
        project.permission.update_user_permission(
            self.editor, PERMISSIONS.WRITE.name
        )
        response = self.put(
            {'mode': 'paste', 'text': PROJECT_WKT}, self.editor, project
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            H3ProjectArea.objects.filter(project=project).exists()
        )
        self.client.force_login(self.editor)
        self.assertEqual(
            self.client.get(self.url(project)).json(),
            {'area': None, 'layer_has_area': False, 'in_effect': 'none'}
        )

    def test_unknown_project(self):
        """Unknown projects are 404."""
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(
                reverse('h3-project-area', args=['no-such-project'])
            ).status_code, 404
        )
