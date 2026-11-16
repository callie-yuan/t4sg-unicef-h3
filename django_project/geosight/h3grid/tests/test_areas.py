# coding=utf-8
"""
GeoSight is UNICEF's geospatial web-based business intelligence platform.

Contact : geosight-no-reply@unicef.org

.. note:: This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.

"""
__date__ = '15/11/2026'
__copyright__ = ('Copyright 2023, Unicef')

import json
from datetime import date
from unittest import mock

import h3
from django.core.exceptions import ValidationError
from django.urls import reverse

from core.models.profile import ROLES
from core.tests.base_tests import APITestCase
from core.tests.model_factories import create_user
from geosight.data.tests.model_factories import (
    DashboardF, IndicatorF, IndicatorValueF
)
from geosight.h3grid.clipping import cells_in_aoi, parse_aoi
from geosight.h3grid.models import (
    H3ProjectArea, H3ReferenceLayer, H3ReferenceLayerConfig
)
from geosight.permission.models.factory import PERMISSIONS

RES = 7
# Small area for the layer, another one for the project
LAYER_WKT = 'POLYGON((44.4 3.4, 44.6 3.4, 44.6 3.6, 44.4 3.6, 44.4 3.4))'
PROJECT_WKT = 'POLYGON((46 5, 47 5, 47 6, 46 6, 46 5))'
LAYER_CELL = h3.latlng_to_cell(3.5, 44.5, RES)
PROJECT_CELL = h3.latlng_to_cell(5.5, 46.5, RES)
OUTSIDE_CELL = h3.latlng_to_cell(0, 0, RES)
VALUES = {LAYER_CELL: 1, PROJECT_CELL: 2, OUTSIDE_CELL: 3}


class H3AreaApiTest(APITestCase):
    """Tests for which area the H3 APIs apply."""

    def setUp(self):
        """Create an indicator, a clipped H3 layer and a project."""
        self.admin = create_user(ROLES.SUPER_ADMIN.name)
        self.viewer = create_user(ROLES.VIEWER.name)
        self.indicator = IndicatorF()
        for geom_id, value in VALUES.items():
            IndicatorValueF(
                indicator=self.indicator, geom_id=geom_id, admin_level=RES,
                value=value, date=date(2026, 1, 1)
            )
        # Resolution 6 has a value only outside both areas
        IndicatorValueF(
            indicator=self.indicator, geom_id=h3.latlng_to_cell(0, 0, 6),
            admin_level=6, value=4, date=date(2026, 1, 1)
        )

        self.layer = H3ReferenceLayer.objects.create(
            identifier='h3-area-test', name='H3 area layer'
        )
        H3ReferenceLayerConfig.objects.create(
            reference_layer=self.layer, min_resolution=5,
            default_resolution=RES, max_resolution=9,
            clip_geometry=LAYER_WKT
        )
        self.project = DashboardF(reference_layer=self.layer)
        self.project_area = H3ProjectArea.objects.create(
            project=self.project, clip_geometry=PROJECT_WKT,
            clip_countries=['SOM']
        )

        self.resolutions_url = reverse(
            'h3-indicator-resolutions', args=[self.indicator.id]
        )
        self.values_url = reverse(
            'h3-indicator-values', args=[self.indicator.id]
        )

    def get_values(self, query='', code=200, user=None):
        """Return the response of /values/ at RES."""
        return self.assertRequestGetView(
            f'{self.values_url}?resolution={RES}{query}',
            code, user=user or self.admin
        )

    def cells(self, query=''):
        """Return {geom_id: value} of /values/ at RES."""
        return {
            row['geom_id']: row['value']
            for row in self.get_values(query).json()
        }

    def test_precedence(self):
        """Project area, then layer area, then no area."""
        other_project = DashboardF()
        layer = f'&reference_layer={self.layer.identifier}'
        cases = {
            'no parameters': ('', VALUES),
            'layer': (layer, {LAYER_CELL: 1}),
            'project area beats layer': (
                f'&project={self.project.id}{layer}', {PROJECT_CELL: 2}
            ),
            'project area': (
                f'&project={self.project.id}', {PROJECT_CELL: 2}
            ),
            'project without area uses the layer given': (
                f'&project={other_project.id}{layer}', {LAYER_CELL: 1}
            ),
            'project without area or H3 layer': (
                f'&project={other_project.id}', VALUES
            ),
        }
        for name, (query, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.cells(query), expected)

    def test_project_without_area_uses_its_layer(self):
        """A project with no area falls back to its own H3 layer's clip."""
        self.project_area.delete()
        self.assertEqual(
            self.cells(f'&project={self.project.id}'), {LAYER_CELL: 1}
        )

    def test_blank_project_area_is_ignored(self):
        """A project area with blank geometry counts as no area."""
        self.project_area.clip_geometry = '  '
        self.project_area.save()
        self.assertEqual(
            self.cells(f'&project={self.project.id}'), {LAYER_CELL: 1}
        )

    def test_resolutions_use_project_area(self):
        """Resolutions with no cells in the active area are dropped."""
        cases = {
            '': [6, 7],
            f'?project={self.project.id}': [7],
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                response = self.assertRequestGetView(
                    f'{self.resolutions_url}{query}', 200, user=self.admin
                )
                self.assertEqual(response.json(), expected)

    def test_permissions(self):
        """Indicator and project read permissions are both required."""
        query = f'&project={self.project.id}'
        # No access to the indicator
        self.get_values(query, 403, user=self.viewer)

        self.indicator.permission.update_user_permission(
            self.viewer, PERMISSIONS.READ_DATA.name
        )
        self.get_values('', 200, user=self.viewer)
        # Can read the indicator, but not the project
        self.project.permission.public_permission = PERMISSIONS.NONE.name
        self.project.permission.organization_permission = (
            PERMISSIONS.NONE.name
        )
        self.project.permission.save()
        for url in [
            f'{self.resolutions_url}?project={self.project.id}',
            f'{self.values_url}?resolution={RES}{query}',
        ]:
            self.assertRequestGetView(url, 403, user=self.viewer)

        self.project.permission.update_user_permission(
            self.viewer, PERMISSIONS.READ.name
        )
        response = self.get_values(query, 200, user=self.viewer)
        self.assertEqual(
            response.json(), [{'geom_id': PROJECT_CELL, 'value': 2}]
        )

    def test_bad_project(self):
        """Unknown project is 404, a non-numeric one is 400."""
        self.get_values('&project=999999', 404)
        self.get_values('&project=abc', 400)

    def test_include_empty_only_returns_cells_inside_area(self):
        """Empty cells are the area's cells, with value null."""
        layer = f'&reference_layer={self.layer.identifier}'
        cells = self.cells(f'{layer}&include_empty=true')
        area_cells = h3.h3shape_to_cells(
            h3.geo_to_h3shape(json.loads(parse_aoi(LAYER_WKT).geojson)), RES
        )

        self.assertGreater(len(cells), 1)
        self.assertEqual(set(cells), set(area_cells))
        self.assertEqual(
            sorted(cells_in_aoi(cells, parse_aoi(LAYER_WKT))), sorted(cells)
        )
        self.assertEqual(cells.pop(LAYER_CELL), 1)
        self.assertEqual(set(cells.values()), {None})

    def test_include_empty_uses_project_area(self):
        """With a project area, empty cells come from that area."""
        cells = self.cells(f'&project={self.project.id}&include_empty=true')
        self.assertEqual(cells[PROJECT_CELL], 2)
        self.assertNotIn(LAYER_CELL, cells)
        self.assertEqual(
            sorted(cells_in_aoi(cells, parse_aoi(PROJECT_WKT))), sorted(cells)
        )

    def test_include_empty_without_area_changes_nothing(self):
        """Without an area there are no empty cells to add."""
        for query in ['&include_empty=true', '&include_empty=false']:
            with self.subTest(query=query):
                self.assertEqual(self.cells(query), VALUES)
        self.assertEqual(
            self.cells(
                f'&reference_layer={self.layer.identifier}'
                '&include_empty=false'
            ),
            {LAYER_CELL: 1}
        )

    def test_cell_limit(self):
        """Too many cells in the area is a 400 suggesting a coarser res."""
        query = f'&reference_layer={self.layer.identifier}&include_empty=true'
        # 10 is refused from the estimate, 60 after listing the cells
        for limit in [10, 60]:
            with self.subTest(limit=limit), mock.patch(
                    'geosight.h3grid.api.H3_MAX_AREA_CELLS', limit
            ):
                response = self.get_values(query, 400)
                self.assertIn(b'coarser resolution', response.content)
        # Without include_empty the limit doesn't apply
        with mock.patch('geosight.h3grid.api.H3_MAX_AREA_CELLS', 10):
            self.get_values(f'&reference_layer={self.layer.identifier}')


class H3ProjectAreaModelTest(APITestCase):
    """Tests for the project area model."""

    def test_clean(self):
        """Blank or polygon areas pass, others fail."""
        project = DashboardF()
        for text in [None, '', PROJECT_WKT]:
            with self.subTest(text=text):
                H3ProjectArea(project=project, clip_geometry=text).full_clean()
        for text in ['POINT(45 2)', 'not a shape']:
            with self.subTest(text=text):
                with self.assertRaises(ValidationError):
                    H3ProjectArea(
                        project=project, clip_geometry=text
                    ).full_clean()
