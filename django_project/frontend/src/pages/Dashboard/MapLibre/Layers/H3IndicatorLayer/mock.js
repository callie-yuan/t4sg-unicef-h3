/**
 * GeoSight is UNICEF's geospatial web-based business intelligence platform.
 *
 * Contact : geosight-no-reply@unicef.org
 *
 * .. note:: This program is free software; you can redistribute it and/or modify
 *     it under the terms of the GNU Affero General Public License as published by
 *     the Free Software Foundation; either version 3 of the License, or
 *     (at your option) any later version.
 *
 * __date__ = '25/10/2026'
 * __copyright__ = ('Copyright 2026, Unicef')
 */

/* ==========================================================================
   H3 MOCK DATA (development only)
   Enabled with the `h3_mock` URL parameter:
     ?h3_mock=1      -> mock.json (resolutions 5 and 7 around Mogadishu)
     ?h3_mock=10000  -> N generated cells at resolution 7, for performance tests
   ========================================================================== */

// h3-js is installed as a dependency of @deck.gl/geo-layers (H3HexagonLayer).
import { geoToH3, h3ToGeo, kRing } from "h3-js";
import mockData from "./mock.json";

const MOCK_CENTER = [2.0469, 45.3182]; // Mogadishu [lat, lng]
const GENERATED_RESOLUTION = 7;

/** Number from the `h3_mock` URL parameter, or null when mock is off. */
export function mockSize() {
  const param = new URLSearchParams(window.location.search).get("h3_mock");
  const size = parseInt(param);
  return isNaN(size) || size < 1 ? null : size;
}

/** Mock of GET /api/v1/indicators/<id>/h3/resolutions/ */
export function mockResolutions(size) {
  return size === 1 ? mockData.resolutions : [GENERATED_RESOLUTION];
}

/** Mock of GET /api/v1/indicators/<id>/h3/values/?resolution=N */
export function mockValues(size, resolution) {
  if (size === 1) {
    return mockData.values[resolution] ?? [];
  }
  // Smallest ring around the center that holds `size` cells.
  const k = Math.ceil((-3 + Math.sqrt(9 + 12 * (size - 1))) / 6);
  const center = geoToH3(MOCK_CENTER[0], MOCK_CENTER[1], resolution);
  return kRing(center, k)
    .slice(0, size)
    .map((cell) => {
      const [lat, lng] = h3ToGeo(cell);
      return {
        geom_id: cell,
        value: 50 + 40 * Math.sin(lat * 9) * Math.cos(lng * 7),
      };
    });
}
