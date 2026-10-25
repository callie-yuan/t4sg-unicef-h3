# coding=utf-8
"""
GeoSight is UNICEF's geospatial web-based business intelligence platform.

Contact : geosight-no-reply@unicef.org

.. note:: This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.

"""
__author__ = 'adiress@college.harvard.edu'
__date__ = '24/10/2026'
__copyright__ = ('Copyright 2023, Unicef')

import os

from django.core.files import File

from core.settings.utils import ABS_PATH
from geosight.data.models.indicator import IndicatorValue
from geosight.h3grid.models import H3ReferenceLayer
from geosight.importer.importers.base.indicator_value import (
    AdminLevelType, IndicatorDataType, ImporterTimeDataType
)
from geosight.importer.models import Importer, ImportType, InputFormat
from geosight.importer.models.log import LogStatus
from geosight.importer.tests.importers._base import (
    BaseIndicatorValueImporterTest
)

# H3 cells used in the test spreadsheets
CELL_RES7_A = '877a6e42cffffff'
CELL_RES7_B = '877a6e552ffffff'
CELL_RES7_C = '877a6e421ffffff'
CELL_RES6 = '867a6e42fffffff'


def data_file(name):
    """Return the path of a test spreadsheet."""
    return ABS_PATH('geosight', 'h3grid', 'tests', 'data', name)


class H3ImportTest(BaseIndicatorValueImporterTest):
    """Import H3 cell IDs through the Excel Long importer."""

    def setUp(self):
        """Create an H3 reference layer and an importer that uses it."""
        super().setUp()
        self.h3_layer = H3ReferenceLayer.objects.create(
            identifier='h3-import-test', name='H3 import test'
        )
        self.importer = Importer.objects.create(
            import_type=ImportType.INDICATOR_VALUE,
            input_format=InputFormat.EXCEL_LONG,
            reference_layer=self.h3_layer
        )
        self.attributes = {
            'sheet_name': 'Sheet 1',
            'row_number_for_header': 1,
            'key_administration_code': 'h3_id',
            'indicator_data_type': IndicatorDataType.BY_VALUE,
            'indicator_data_value': self.indicator_2.id,
            'admin_level_type': AdminLevelType.BY_VALUE,
            'admin_level_value': 1,
            'key_value': 'value',
            'date_time_data_type': ImporterTimeDataType.BY_VALUE,
            'date_time_data_value': '2010-01-01'
        }

    def run_import(self, filename, attributes=None):
        """Run the importer with a test spreadsheet and return its log."""
        with open(data_file(filename), 'rb') as _file:
            self.importer.save_attributes(
                {**self.attributes, **(attributes or {})},
                {'file': File(_file, name=os.path.basename(_file.name))}
            )
        self.importer.run()
        return self.importer.importerlog_set.all().last()

    def test_valid_rows_saved_and_bad_row_reported(self):
        """3 valid rows are stored and the bad row's number is reported."""
        log = self.run_import('h3_long.xlsx')

        values = IndicatorValue.objects.filter(indicator=self.indicator_2)
        self.assertEqual(values.count(), 3)
        self.assertEqual(
            dict(values.values_list('geom_id', 'admin_level')),
            {CELL_RES7_A: 7, CELL_RES7_B: 7, CELL_RES6: 6}
        )

        # The bad row (row 4) is in the error summary
        self.assertEqual(log.status, LogStatus.SUCCESS)
        self.assertIn('Row 4', log.note)

    def test_reimport_creates_no_duplicates(self):
        """Importing the same file twice keeps one value per cell."""
        self.run_import('h3_long.xlsx')
        self.run_import('h3_long.xlsx')
        self.assertEqual(
            IndicatorValue.objects.filter(
                indicator=self.indicator_2
            ).count(),
            3
        )

    def test_multi_indicator_shortcode_column(self):
        """Each row is stored under the indicator from its shortcode."""
        self.run_import(
            'h3_long_multi_indicator.xlsx', {
                'indicator_data_type': IndicatorDataType.DATA_DRIVEN,
                'indicator_data_field': 'indicator_shortcode',
                'indicator_data_value': None
            }
        )
        self.assertEqual(
            set(
                IndicatorValue.objects.filter(
                    indicator=self.indicator_1
                ).values_list('geom_id', flat=True)
            ),
            {CELL_RES7_A, CELL_RES7_C}
        )
        self.assertEqual(
            set(
                IndicatorValue.objects.filter(
                    indicator=self.indicator_2
                ).values_list('geom_id', flat=True)
            ),
            {CELL_RES7_A, CELL_RES6}
        )
