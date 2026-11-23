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

/**
 * H3_MAP reducer
 * What each map shows of the H3 layer, so the rest of the dashboard
 * (e.g. widgets) can read it. Keyed by map id; 0 is the main map.
 */

export const H3_MAP_ACTION_NAME = "H3_MAP";
export const H3_MAP_ACTION_TYPE_UPDATE = "H3_MAP/UPDATE";
export const H3_MAP_ACTION_TYPE_REMOVE = "H3_MAP/REMOVE";

export const MAIN_MAP_ID = 0;

/** [west, south, east, north] in degrees */
export type H3Bbox = [number, number, number, number];

export interface H3MapState {
  /** "auto" follows the zoom, "manual" keeps the dropdown's choice */
  mode: "auto" | "manual";
  /** Resolution being shown or requested */
  selectedResolution: number | null;
  /** Resolution of the hexagons on screen; lags while new ones load */
  resolution: number | null;
  /** Resolutions with data, inside the layer's min and max */
  resolutions: number[];
  indicatorId: number | null;
  zoom: number | null;
  /** Visible part of the map */
  bbox: H3Bbox | null;
}

export const initialH3MapState: H3MapState = {
  mode: "auto",
  selectedResolution: null,
  resolution: null,
  resolutions: [],
  indicatorId: null,
  zoom: null,
  bbox: null,
};

export type H3MapsState = Record<number, H3MapState>;

export default function h3MapReducer(state: H3MapsState = {}, action: any) {
  if (action.name !== H3_MAP_ACTION_NAME) return state;
  switch (action.type) {
    case H3_MAP_ACTION_TYPE_UPDATE: {
      const current = state[action.mapId] ?? initialH3MapState;
      const changed = Object.keys(action.payload).some(
        (key) =>
          JSON.stringify(current[key as keyof H3MapState]) !==
          JSON.stringify(action.payload[key]),
      );
      if (!changed) return state;
      return {
        ...state,
        [action.mapId]: { ...current, ...action.payload },
      };
    }
    case H3_MAP_ACTION_TYPE_REMOVE: {
      if (!(action.mapId in state)) return state;
      const { [action.mapId]: _, ...rest } = state;
      return rest;
    }
  }
  return state;
}

/** H3 state of a map, or null when it has no H3 layer */
export const selectH3Map =
  (mapId: number = MAIN_MAP_ID) =>
  (state: { h3Map: H3MapsState }): H3MapState | null =>
    state.h3Map[mapId] ?? null;
