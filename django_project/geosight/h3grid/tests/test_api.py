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

from django.urls import reverse

from core.models.profile import ROLES
from core.tests.base_tests import APITestCase
from core.tests.model_factories import create_user
from geosight.data.tests.model_factories import IndicatorF, IndicatorValueF

RES_6 = ['862a1072fffffff', '862a1073fffffff']
RES_7 = ['872a10720ffffff', '872a10721ffffff']
OLD, LATEST = date(2026, 1, 1), date(2026, 2, 1)


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
        """An explicit date selects that date's values"""
        response = self.assertRequestGetView(
            f'{self.values_url}?resolution=7&date={OLD.isoformat()}',
            200, user=self.admin
        )
        self.assertEqual(
            response.json(), [{'geom_id': RES_7[0], 'value': 99}]
        )

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
