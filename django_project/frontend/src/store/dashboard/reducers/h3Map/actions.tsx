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

import {
  H3_MAP_ACTION_NAME,
  H3_MAP_ACTION_TYPE_REMOVE,
  H3_MAP_ACTION_TYPE_UPDATE,
  H3MapState,
} from "./index";

/** Merge fields into a map's H3 state */
export const update = (mapId: number, payload: Partial<H3MapState>) => ({
  name: H3_MAP_ACTION_NAME,
  type: H3_MAP_ACTION_TYPE_UPDATE,
  mapId,
  payload,
});

/** Forget a map's H3 state */
export const remove = (mapId: number) => ({
  name: H3_MAP_ACTION_NAME,
  type: H3_MAP_ACTION_TYPE_REMOVE,
  mapId,
});

export default {
  update,
  remove,
};
