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
 * __date__ = '23/11/2026'
 * __copyright__ = ('Copyright 2026, Unicef')
 */

/* ==========================================================================
   ZOOM -> H3 RESOLUTION
   Auto mode keeps hexagons about TARGET_HEX_PX wide on screen. Each finer
   resolution is ~2.65x smaller and each zoom level 2x bigger, so the
   resolution goes up by one about every 1.4 zoom levels.

   Hexagon width (flat side to flat side) = sqrt(3) * average edge length:
     res 3: 104 km   res 4: 39 km   res 5: 15 km   res 6: 5.6 km
     res 7: 2.1 km   res 8: 0.8 km  res 9: 0.3 km

   All of Somalia fills the map around zoom 5, where res 5 hexagons are
   ~7 px wide -> res 5. A city (~zoom 11) would ideally be res 9, so with
   data only up to res 7 it shows res 7.
   ========================================================================== */

import { edgeLength } from "h3-js";
import type { H3Bbox } from "../../../../../store/dashboard/reducers/h3Map";

/** Wanted on-screen hexagon width, in pixels */
export const TARGET_HEX_PX = 8;

const EARTH_CIRCUMFERENCE_M = 40075016.686;
// MapLibre zoom levels are based on 512 px tiles
const TILE_SIZE_PX = 512;

/** Meters per pixel at a zoom level and latitude */
export const metersPerPixel = (zoom: number, latitude: number) =>
  (EARTH_CIRCUMFERENCE_M * Math.cos((latitude * Math.PI) / 180)) /
  (TILE_SIZE_PX * Math.pow(2, zoom));

/** On-screen width of an average hexagon, in pixels */
export const hexWidthPx = (
  resolution: number,
  zoom: number,
  latitude: number,
) =>
  (Math.sqrt(3) * edgeLength(resolution, "m")) / metersPerPixel(zoom, latitude);

/**
 * Pick the resolution whose hexagons are closest to TARGET_HEX_PX wide,
 * from the given resolutions (those with data, inside the layer's min/max).
 * Sizes are compared on a log scale, so 4 px and 16 px are equally far
 * from 8 px. Ties go to the coarser resolution (fewer cells).
 */
export function autoResolution(
  resolutions: number[],
  zoom: number,
  latitude: number,
): number | null {
  let best: number | null = null;
  let bestDistance = Infinity;
  [...resolutions]
    .sort((a, b) => a - b)
    .forEach((resolution) => {
      const distance = Math.abs(
        Math.log(hexWidthPx(resolution, zoom, latitude) / TARGET_HEX_PX),
      );
      if (distance < bestDistance - 1e-9) {
        best = resolution;
        bestDistance = distance;
      }
    });
  return best;
}

/** Grow a box by a share of its size on each side, within lng/lat limits */
export const padBbox = ([west, south, east, north]: H3Bbox, share: number) => {
  const padX = (east - west) * share;
  const padY = (north - south) * share;
  return [
    Math.max(-180, west - padX),
    Math.max(-85, south - padY),
    Math.min(180, east + padX),
    Math.min(85, north + padY),
  ] as H3Bbox;
};

/** Whether the outer box contains the inner box */
export const bboxContains = (outer: H3Bbox, inner: H3Bbox) =>
  outer[0] <= inner[0] &&
  outer[1] <= inner[1] &&
  outer[2] >= inner[2] &&
  outer[3] >= inner[3];
