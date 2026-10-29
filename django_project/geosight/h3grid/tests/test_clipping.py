"""Tests for parsing an area of interest and clipping H3 cells to it"""

import json
from unittest import TestCase

import h3

from geosight.h3grid.clipping import cells_in_aoi, parse_aoi
from geosight.h3grid.validation import H3Error


def rectangle(west, south, east, north):
    """GeoJSON Polygon geometry for a lng/lat rectangle"""
    return {
        'type': 'Polygon',
        'coordinates': [[
            [west, south], [east, south], [east, north],
            [west, north], [west, south],
        ]],
    }


# Rectangle in central/southern Somalia
SOMALIA_RECT = rectangle(44.0, 3.0, 45.0, 4.0)
SOMALIA_WKT = 'POLYGON((44 3, 45 3, 45 4, 44 4, 44 3))'


class ParseAoiTest(TestCase):
    """Check every pasted format parses, and bad input is rejected."""

    def test_formats_parse_to_same_shape(self):
        feature = {'type': 'Feature', 'properties': {}, 'geometry': SOMALIA_RECT}
        collection = {'type': 'FeatureCollection', 'features': [feature]}
        texts = {
            'wkt': SOMALIA_WKT,
            'geometry': json.dumps(SOMALIA_RECT),
            'feature': json.dumps(feature),
            'feature collection': json.dumps(collection),
        }
        expected = parse_aoi(SOMALIA_WKT)
        for name, text in texts.items():
            with self.subTest(format=name):
                aoi = parse_aoi(f'\n  {text}  \n')
                self.assertEqual(aoi.geom_type, 'Polygon')
                self.assertEqual(aoi.srid, 4326)
                self.assertTrue(aoi.equals(expected))

    def test_multipolygon(self):
        wkt = (
            'MULTIPOLYGON(((44 3, 45 3, 45 4, 44 4, 44 3)),'
            '((46 5, 47 5, 47 6, 46 6, 46 5)))'
        )
        aoi = parse_aoi(wkt)
        self.assertEqual(aoi.geom_type, 'MultiPolygon')
        self.assertEqual(aoi.srid, 4326)

    def test_feature_collection_of_several_polygons(self):
        collection = {
            'type': 'FeatureCollection',
            'features': [
                {'type': 'Feature', 'geometry': SOMALIA_RECT},
                {'type': 'Feature', 'geometry': rectangle(46, 5, 47, 6)},
            ],
        }
        aoi = parse_aoi(json.dumps(collection))
        self.assertEqual(aoi.geom_type, 'MultiPolygon')
        self.assertEqual(len(aoi), 2)

    def test_bad_inputs(self):
        bad = {
            'none': None,
            'empty': '',
            'spaces': '   ',
            'unreadable text': 'not a shape',
            'broken json': '{"type": "Polygon", ',
            'point': 'POINT(45 2)',
            'line': 'LINESTRING(44 3, 45 4)',
            'geojson point': json.dumps(
                {'type': 'Point', 'coordinates': [45, 2]}
            ),
            'self-intersecting': 'POLYGON((44 3, 45 4, 45 3, 44 4, 44 3))',
            'empty polygon': 'POLYGON EMPTY',
            'feature without geometry': json.dumps(
                {'type': 'Feature', 'geometry': None}
            ),
            'empty feature collection': json.dumps(
                {'type': 'FeatureCollection', 'features': []}
            ),
            'feature collection with a point': json.dumps({
                'type': 'FeatureCollection',
                'features': [
                    {'type': 'Feature', 'geometry': SOMALIA_RECT},
                    {'type': 'Feature', 'geometry': {
                        'type': 'Point', 'coordinates': [45, 2]
                    }},
                ],
            }),
        }
        for name, text in bad.items():
            with self.subTest(input=name):
                with self.assertRaises(H3Error) as context:
                    parse_aoi(text)
                self.assertTrue(str(context.exception))


class CellsInAoiTest(TestCase):
    """Check cells are kept by their center, never cut."""

    resolution = 6

    def test_matches_h3_polyfill(self):
        aoi = parse_aoi(SOMALIA_WKT)
        expected = h3.geo_to_cells(
            h3.geo_to_h3shape(SOMALIA_RECT), self.resolution
        )
        # Candidates cover a larger area than the rectangle
        candidates = h3.geo_to_cells(
            h3.geo_to_h3shape(rectangle(43.5, 2.5, 45.5, 4.5)),
            self.resolution,
        )
        far_cell = h3.latlng_to_cell(0, 0, self.resolution)

        kept = cells_in_aoi(list(candidates) + [far_cell], aoi)

        self.assertTrue(expected)
        self.assertEqual(sorted(kept), sorted(expected))
        self.assertNotIn(far_cell, kept)

    def test_keeps_cell_with_center_on_edge(self):
        cell = h3.latlng_to_cell(3.5, 44.5, self.resolution)
        lat, lng = h3.cell_to_latlng(cell)
        # Rectangle whose west edge runs through the cell center
        aoi = parse_aoi(json.dumps(rectangle(lng, lat - 1, lng + 1, lat + 1)))

        self.assertEqual(cells_in_aoi([cell], aoi), [cell])
