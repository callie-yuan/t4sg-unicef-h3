# coding=utf-8
"""
GeoSight is UNICEF's geospatial web-based business intelligence platform.

Contact : geosight-no-reply@unicef.org

.. note:: This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.

"""
__author__ = 'andrewleblanc187@gmail.com'
__date__ = '24/10/2026'
__copyright__ = ('Copyright 2023, Unicef')

from datetime import date
from unittest import mock

import h3
from django.urls import reverse

from core.models.profile import ROLES
from core.tests.base_tests import APITestCase
from core.tests.model_factories import create_user
from geosight.data.tests.model_factories import IndicatorF, IndicatorValueF
from geosight.h3grid.models import H3ReferenceLayer, H3ReferenceLayerConfig

RES_6 = ['862a1072fffffff', '862a1073fffffff']
RES_7 = ['872a10720ffffff', '872a10721ffffff']
OLD, LATEST = date(2026, 1, 1), date(2026, 2, 1)

# Two cells far apart, a box around the first, and an area around both
NEAR = h3.latlng_to_cell(3.5, 44.5, 7)
FAR = h3.latlng_to_cell(5.5, 46.5, 7)
NEAR_BBOX = '44.4,3.4,44.6,3.6'
BOTH_WKT = 'POLYGON((44 3, 47 3, 47 6, 44 6, 44 3))'


class H3IndicatorApiTest(APITestCase):
    """Tests for the H3 indicator resolutions and values APIs."""

    def setUp(self):
        """Create an indicator with H3 rows and one non-H3 row."""
        self.admin = create_user(ROLES.SUPER_ADMIN.name)
        self.viewer = create_user(ROLES.VIEWER.name)
        self.indicator = IndicatorF()
        for i, geom_id in enumerate(RES_6):
            self._value(geom_id, 6, i, LATEST)
        for i, geom_id in enumerate(RES_7):
            self._value(geom_id, 7, 10 + i, LATEST)
        self._value(RES_7[0], 7, 99, OLD)
        self._value('SOM_0012_V1', 2, 5, LATEST)

        self.resolutions_url = reverse(
            'h3-indicator-resolutions', args=[self.indicator.id]
        )
        self.values_url = reverse(
            'h3-indicator-values', args=[self.indicator.id]
        )

    def _value(self, geom_id, admin_level, value, value_date):
        """Create an indicator value."""
        IndicatorValueF(
            indicator=self.indicator, geom_id=geom_id,
            admin_level=admin_level, value=value, date=value_date
        )

    def test_resolutions_only_h3_sorted(self):
        """Non-H3 geom ids are ignored and resolutions are sorted"""
        response = self.assertRequestGetView(
            self.resolutions_url, 200, user=self.admin
        )
        self.assertEqual(response.json(), [6, 7])

    def test_values_by_resolution_defaults_to_latest(self):
        """Only the requested resolution at the latest date is returned"""
        response = self.assertRequestGetView(
            f'{self.values_url}?resolution=7', 200, user=self.admin
        )
        self.assertCountEqual(
            response.json(),
            [
                {'geom_id': RES_7[0], 'value': 10},
                {'geom_id': RES_7[1], 'value': 11},
            ]
        )

    def test_values_with_date(self):
        """An explicit date selects each cell's latest value by that date."""
        response = self.assertRequestGetView(
            f'{self.values_url}?resolution=7&date={OLD.isoformat()}',
            200, user=self.admin
        )
        self.assertEqual(
            response.json(), [{'geom_id': RES_7[0], 'value': 99}]
        )

    def test_values_with_date_use_latest_value_per_cell(self):
        """As-of dates use each cell's most recent earlier value."""
        indicator = IndicatorF()
        values_url = reverse('h3-indicator-values', args=[indicator.id])
        for geom_id, value in [(RES_7[0], 20), (RES_7[1], 21)]:
            IndicatorValueF(
                indicator=indicator, geom_id=geom_id, admin_level=7,
                value=value, date=date(2020, 1, 1)
            )
        IndicatorValueF(
            indicator=indicator, geom_id=RES_7[0], admin_level=7,
            value=25, date=date(2025, 1, 1)
        )

        for as_of_date, expected in [
            ('2022-06-01', [
                {'geom_id': RES_7[0], 'value': 20},
                {'geom_id': RES_7[1], 'value': 21},
            ]),
            ('2026-01-01', [
                {'geom_id': RES_7[0], 'value': 25},
                {'geom_id': RES_7[1], 'value': 21},
            ]),
            ('2019-01-01', []),
        ]:
            with self.subTest(as_of_date=as_of_date):
                response = self.assertRequestGetView(
                    f'{values_url}?resolution=7&date={as_of_date}',
                    200, user=self.admin
                )
                self.assertCountEqual(response.json(), expected)

    def test_values_no_data_for_resolution(self):
        """A resolution without H3 rows returns an empty list"""
        response = self.assertRequestGetView(
            f'{self.values_url}?resolution=8', 200, user=self.admin
        )
        self.assertEqual(response.json(), [])

    def test_bad_resolution(self):
        """Missing, non numeric or out of range resolution returns 400"""
        for query in ['', '?resolution=abc', '?resolution=16',
                      '?resolution=-1']:
            self.assertRequestGetView(
                f'{self.values_url}{query}', 400, user=self.admin
            )

    def test_bad_date(self):
        """A malformed date returns 400"""
        self.assertRequestGetView(
            f'{self.values_url}?resolution=7&date=nope', 400, user=self.admin
        )

    def test_unknown_indicator(self):
        """Unknown indicator returns 404"""
        for name in ['h3-indicator-resolutions', 'h3-indicator-values']:
            self.assertRequestGetView(
                reverse(name, args=[999999]) + '?resolution=7',
                404, user=self.admin
            )

    def test_no_access_matches_existing_endpoint(self):
        """A user without access gets the same code as the existing API"""
        existing = self.assertRequestGetView(
            reverse('indicator_data-list', args=[self.indicator.id]),
            403, user=self.viewer
        )
        for url in [self.resolutions_url, f'{self.values_url}?resolution=7']:
            response = self.assertRequestGetView(
                url, existing.status_code, user=self.viewer
            )
            self.assertEqual(response.status_code, existing.status_code)


class H3ValuesBboxApiTest(APITestCase):
    """Tests for ?bbox= on the H3 values API."""

    def setUp(self):
        """Create an indicator with two far apart cells, and a clip area."""
        self.admin = create_user(ROLES.SUPER_ADMIN.name)
        self.indicator = IndicatorF()
        for geom_id, value in [(NEAR, 1), (FAR, 2)]:
            IndicatorValueF(
                indicator=self.indicator, geom_id=geom_id, admin_level=7,
                value=value, date=LATEST
            )
        self.layer = H3ReferenceLayer.objects.create(
            identifier='h3-bbox-test', name='H3 bbox layer'
        )
        H3ReferenceLayerConfig.objects.create(
            reference_layer=self.layer, min_resolution=5,
            default_resolution=7, max_resolution=9, clip_geometry=BOTH_WKT
        )
        self.values_url = reverse(
            'h3-indicator-values', args=[self.indicator.id]
        ) + '?resolution=7'
        self.area = f'&reference_layer={self.layer.identifier}'

    def cells(self, query):
        """Return {geom_id: value} of the values API."""
        response = self.assertRequestGetView(
            f'{self.values_url}{query}', 200, user=self.admin
        )
        return {row['geom_id']: row['value'] for row in response.json()}

    def test_bbox_returns_only_cells_in_view(self):
        """Only cells whose center is in the box, with or without an area."""
        self.assertEqual(self.cells(''), {NEAR: 1, FAR: 2})
        for query in [f'&bbox={NEAR_BBOX}', f'&bbox={NEAR_BBOX}{self.area}']:
            with self.subTest(query=query):
                self.assertEqual(self.cells(query), {NEAR: 1})

    def test_bad_bbox(self):
        """A bbox that isn't west,south,east,north in degrees is a 400."""
        for bbox in ['abc', '44,3,45', '44,3,45,4,5', '45,3,44,4',
                     '44,4,45,3', '-181,3,45,4', '44,-91,45,4']:
            with self.subTest(bbox=bbox):
                self.assertRequestGetView(
                    f'{self.values_url}&bbox={bbox}', 400, user=self.admin
                )

    def test_bbox_include_empty_only_cells_in_view_and_area(self):
        """Empty cells come from the part of the area inside the box."""
        cells = self.cells(f'&bbox={NEAR_BBOX}{self.area}&include_empty=true')
        bbox = [float(part) for part in NEAR_BBOX.split(',')]

        self.assertGreater(len(cells), 1)
        self.assertEqual(cells.pop(NEAR), 1)
        self.assertNotIn(FAR, cells)
        self.assertEqual(set(cells.values()), {None})
        for cell in cells:
            lat, lng = h3.cell_to_latlng(cell)
            self.assertTrue(bbox[0] <= lng <= bbox[2])
            self.assertTrue(bbox[1] <= lat <= bbox[3])

    def test_bbox_avoids_the_cell_limit(self):
        """The whole area is over the limit, the part in view is not."""
        query = f'{self.area}&include_empty=true'
        with mock.patch('geosight.h3grid.api.H3_MAX_AREA_CELLS', 1000):
            self.assertRequestGetView(
                f'{self.values_url}{query}', 400, user=self.admin
            )
            self.cells(f'{query}&bbox={NEAR_BBOX}')

    def test_bbox_outside_area(self):
        """A box outside the area returns no cells, not even empty ones."""
        self.assertEqual(
            self.cells(f'&bbox=10,10,11,11{self.area}&include_empty=true'),
            {}
        )
