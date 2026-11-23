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
   H3 INDICATOR LAYER
   Draws an indicator's H3 values as hexagons, straight from the H3 cell IDs.
   Mounted for H3 projects; draws hexagons when the indicator has H3 values.
   The resolution follows the zoom in Auto mode (see zoomResolution.tsx), and
   only the hexagons around the view are requested. What is on screen is
   shared in the dashboard store (h3Map), for widgets and others.
   ========================================================================== */

import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useDispatch, useSelector } from "react-redux";
import maplibregl from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox/typed";
import { H3HexagonLayer } from "@deck.gl/geo-layers/typed";
import axiosRequest from "../../../../../utils/Request";
import { UpdateStyleData } from "../../../../../utils/indicatorData";
import {
  createDynamicStyle,
  dynamicStyleTypes,
  returnLayerStyleConfig,
  returnNoDataStyle,
} from "../../../../../utils/Style";
import { hexToRGBList } from "../../../../../utils/main";
import { NO_DATA_RULE } from "../../../../Admin/Style/Form/StyleRules";
import { addStandalonePopup } from "../../utils";
import { IndicatorLayer } from "../../../../../types/IndicatorLayer";
import type { RootState } from "../../../../../store/dashboard/reducers";
import H3MapActions from "../../../../../store/dashboard/reducers/h3Map/actions";
import {
  H3Bbox,
  selectH3Map,
} from "../../../../../store/dashboard/reducers/h3Map";
import { mockResolutions, mockSize, mockValues } from "./mock";
import { autoResolution, bboxContains, padBbox } from "./zoomResolution";

// Wait this long after the map stops moving before switching resolution
const SETTLE_MS = 300;
// Request this share of the view's size more on each side, so small pans
// don't need a new request
const VIEW_PADDING = 0.25;
const WORLD_BBOX: H3Bbox = [-180, -85, 180, 85];

/** One row of GET /api/v1/indicators/<id>/h3/values/ */
export interface H3Value {
  geom_id: string;
  // null for a cell of the area without a value (include_empty)
  value: number | null;
}

interface StyledH3Value extends H3Value {
  color: number[];
}

const hasValue = (row: H3Value) =>
  row.value !== null && row.value !== undefined;

/** Query of the area filters: the project and the reference layer */
const areaQuery = (referenceLayerId: string, projectId: number | null) =>
  `reference_layer=${encodeURIComponent(referenceLayerId)}` +
  (projectId ? `&project=${projectId}` : "");

const H3Urls = {
  resolutions: (
    indicatorId: number,
    referenceLayerId: string,
    projectId: number | null,
  ) =>
    `/api/v1/indicators/${indicatorId}/h3/resolutions/?` +
    areaQuery(referenceLayerId, projectId),
  values: (
    indicatorId: number,
    resolution: number,
    referenceLayerId: string,
    projectId: number | null,
    date: string | null,
    includeEmpty: boolean,
    bbox: H3Bbox,
  ) =>
    `/api/v1/indicators/${indicatorId}/h3/values/?resolution=${resolution}&` +
    areaQuery(referenceLayerId, projectId) +
    (date ? `&date=${encodeURIComponent(date)}` : "") +
    (includeEmpty ? "&include_empty=true" : "") +
    `&bbox=${bbox.map((part) => part.toFixed(5)).join(",")}`,
};

/** Log a failed request with the server's message */
const logRequestError = (what: string, error: any) => {
  console.error(
    `H3 layer: ${what} request failed`,
    error?.response?.data ?? error?.message ?? error,
  );
};

/** Popup content for a clicked hexagon */
const renderPopup = (cell: H3Value) => {
  const escape = (text: string) =>
    text.replace(/[&<>"']/g, (char) => `&#${char.charCodeAt(0)};`);
  return (
    `<div class="maplibregl-popup-content-main">` +
    `<b>H3 ID:</b> ${escape(String(cell.geom_id))}<br/>` +
    `<b>Value:</b> ${hasValue(cell) ? escape(String(cell.value)) : "No data"}` +
    `</div>`
  );
};

/**
 * Legend rules of the H3 layer, built like GeoSight's indicatorLayerStyle:
 * the classes of the resolution on screen, then the no-data rule.
 */
const h3LegendRules = (config: any, rows: any[], resolution: number | null) => {
  let style = config.style;
  if (dynamicStyleTypes.includes(config.style_type)) {
    // Classes are keyed by admin level, which is the resolution for H3
    const dynamic = createDynamicStyle(
      rows,
      config.style_type,
      config.style_config,
      config.style_data,
    ) as unknown as Record<string, any[]>;
    const classes = (dynamic[String(resolution)] ?? []).filter(
      (rule: any) => rule.name !== NO_DATA_RULE,
    );
    classes.reverse();
    style = [...classes, ...dynamic["NoData"]];
  }
  return (style ?? []).filter((rule: any) => rule.active);
};

export interface H3ReferenceLayer {
  identifier?: string;
  is_h3?: boolean;
  h3_config?: {
    default_resolution: number;
    min_resolution: number;
    max_resolution: number;
  };
}

export interface Props {
  mapId: number;
  map: maplibregl.Map;
  indicatorLayer: IndicatorLayer;
  referenceLayer?: H3ReferenceLayer;
  /** Receives the legend rules; null while loading */
  onLegendRules?: (rules: any[] | null) => void;
}

export default function H3IndicatorLayer({
  mapId,
  map,
  indicatorLayer,
  referenceLayer,
  onLegendRules,
}: Props) {
  const dispatch = useDispatch();
  // @ts-ignore
  const indicators = useSelector((state) => state.dashboard.data?.indicators);
  // @ts-ignore
  const projectId = useSelector((state) => state.dashboard.data?.id) ?? null;
  // @ts-ignore
  const indicatorShow = useSelector((state) => state.map?.indicatorShow);
  const transparency = useSelector(
    // @ts-ignore
    (state) => state.map?.transparency?.indicatorLayer,
  );
  const selectedDate = useSelector((state: RootState) =>
    state.selectedGlobalTime.max
      ? state.selectedGlobalTime.max.split("T")[0]
      : null,
  );

  // Shared H3 state of this map (store: h3Map)
  const h3Map = useSelector(selectH3Map(mapId));
  const mode = h3Map?.mode ?? "auto";
  const selectedResolution = h3Map?.selectedResolution ?? null;
  const resolutions = h3Map?.resolutions ?? [];
  const zoom = h3Map?.zoom ?? null;
  const viewBbox = h3Map?.bbox ?? null;
  const viewLatitude = viewBbox ? (viewBbox[1] + viewBbox[3]) / 2 : 0;
  const updateH3Map = (payload: Parameters<typeof H3MapActions.update>[1]) =>
    dispatch(H3MapActions.update(mapId, payload));

  const [loadedResolutionsKey, setLoadedResolutionsKey] = useState<
    string | null
  >(null);
  // Hexagons on screen, kept until the next ones arrive
  const [loaded, setLoaded] = useState<{
    key: string;
    resolution: number;
    values: H3Value[];
    bbox: H3Bbox;
  } | null>(null);
  const loadedRef = useRef(loaded);
  loadedRef.current = loaded;
  // Request in flight, so a pan inside its box doesn't restart it
  const pendingRef = useRef<{
    key: string;
    bbox: H3Bbox;
    cancelled: boolean;
  } | null>(null);

  // Use an overlaid deck.gl instance. Interleaved overlays share the map's
  // deck instance, so removing this overlay would finalize ReferenceLayer's.
  const overlay = useRef<MapboxOverlay | null>(null);
  const layerId = `h3-indicator-layer-${mapId}`;

  // Only single-indicator layers can have H3 values
  const indicatorId =
    indicatorLayer?.indicators?.length === 1
      ? indicatorLayer.indicators[0].id
      : null;
  const referenceLayerId = referenceLayer?.identifier;
  const {
    default_resolution: defaultResolution,
    min_resolution: minResolution,
    max_resolution: maxResolution,
  } = referenceLayer?.h3_config ?? {};
  const resolutionsKey = JSON.stringify([
    indicatorId,
    referenceLayerId,
    projectId,
    defaultResolution,
    minResolution,
    maxResolution,
  ]);
  // In Auto mode, take the resolution straight from the view, so a new view
  // is requested with its own resolution, never with the previous one
  const wantedResolution =
    mode === "auto" && zoom !== null && resolutions.length
      ? autoResolution(resolutions, zoom, viewLatitude)
      : selectedResolution;
  // Everything a request depends on except the box
  const valuesKey = JSON.stringify([
    indicatorId,
    wantedResolution,
    referenceLayerId,
    projectId,
    selectedDate,
  ]);
  const shownResolution = loaded?.resolution ?? null;
  const shownValues = loaded?.values ?? [];

  const configuredResolutions = (available: number[]): number[] =>
    available
      .filter(
        (res) =>
          (minResolution === undefined || res >= minResolution) &&
          (maxResolution === undefined || res <= maxResolution),
      )
      .sort((a, b) => a - b);

  const initialResolution = (available: number[]): number | null =>
    defaultResolution === undefined
      ? (available[0] ?? null)
      : available.reduce<number | null>(
          (closest, res) =>
            closest === null ||
            Math.abs(res - defaultResolution) <
              Math.abs(closest - defaultResolution)
              ? res
              : closest,
          null,
        );

  /** Resolution to show from the available ones, for the current mode */
  const pickResolution = (available: number[]): number | null => {
    if (mode === "auto" && zoom !== null) {
      return autoResolution(available, zoom, viewLatitude);
    }
    if (
      mode === "manual" &&
      selectedResolution !== null &&
      available.includes(selectedResolution)
    ) {
      return selectedResolution;
    }
    return initialResolution(available);
  };

  /** Fetch the resolutions that have H3 values */
  useEffect(() => {
    updateH3Map({
      indicatorId,
      resolutions: [],
      selectedResolution: null,
    });
    if (!indicatorId || !referenceLayerId) {
      return;
    }
    const loadResolutions = (available: number[]) => {
      const fetched = configuredResolutions(available);
      updateH3Map({
        resolutions: fetched,
        selectedResolution: pickResolution(fetched),
      });
      setLoadedResolutionsKey(resolutionsKey);
    };
    const mock = mockSize();
    if (mock) {
      loadResolutions(mockResolutions(mock));
      return;
    }
    let cancelled = false;
    axiosRequest
      .get(H3Urls.resolutions(indicatorId, referenceLayerId, projectId))
      .then((response) => {
        if (!cancelled) loadResolutions(response.data ?? []);
      })
      .catch((error) => {
        if (!cancelled) logRequestError("resolutions", error);
      });
    return () => {
      cancelled = true;
    };
  }, [
    indicatorId,
    referenceLayerId,
    projectId,
    defaultResolution,
    minResolution,
    maxResolution,
  ]);

  /** Auto mode: pick the resolution from the zoom, once the map settles */
  useEffect(() => {
    if (mode !== "auto" || !resolutions.length || zoom === null) {
      return;
    }
    const next = autoResolution(resolutions, zoom, viewLatitude);
    if (next !== selectedResolution) {
      updateH3Map({ selectedResolution: next });
    }
  }, [mode, zoom, viewLatitude, resolutions]);

  /**
   * Fetch the values of the selected resolution around the view.
   * Nothing is requested when the hexagons on screen (or on their way)
   * already have this resolution and date and cover the view.
   */
  useEffect(() => {
    if (!indicatorId || !referenceLayerId || wantedResolution === null) {
      if (pendingRef.current) pendingRef.current.cancelled = true;
      pendingRef.current = null;
      setLoaded(null);
      return;
    }
    const covers = (request: { key: string; bbox: H3Bbox } | null) =>
      request?.key === valuesKey &&
      (!viewBbox || bboxContains(request.bbox, viewBbox));
    if (covers(pendingRef.current)) {
      return;
    }
    if (pendingRef.current) pendingRef.current.cancelled = true;
    pendingRef.current = null;
    if (covers(loadedRef.current)) {
      return;
    }
    const mock = mockSize();
    if (mock) {
      setLoaded({
        key: valuesKey,
        resolution: wantedResolution,
        values: mockValues(mock, wantedResolution),
        bbox: WORLD_BBOX,
      });
      return;
    }
    // Wait for the map to report what it shows
    if (!viewBbox) {
      return;
    }
    const pending = {
      key: valuesKey,
      bbox: padBbox(viewBbox, VIEW_PADDING),
      cancelled: false,
    };
    pendingRef.current = pending;
    const resolution = wantedResolution;
    const request = (includeEmpty: boolean) =>
      axiosRequest.get(
        H3Urls.values(
          indicatorId,
          resolution,
          referenceLayerId,
          projectId,
          selectedDate,
          includeEmpty,
          pending.bbox,
        ),
      );
    // Ask for the empty cells of the area too. The API refuses that when
    // the area has too many cells at this resolution, so then draw only the
    // cells with values.
    request(true)
      .catch((error) => {
        if (pending.cancelled || error?.response?.status !== 400) throw error;
        logRequestError("empty cells", error);
        return request(false);
      })
      .then((response) => {
        if (pending.cancelled) return;
        pendingRef.current = null;
        setLoaded({
          key: pending.key,
          resolution,
          values: response.data ?? [],
          bbox: pending.bbox,
        });
      })
      .catch((error) => {
        if (pending.cancelled) return;
        pendingRef.current = null;
        logRequestError("values", error);
      });
  }, [
    indicatorId,
    wantedResolution,
    referenceLayerId,
    projectId,
    selectedDate,
    viewBbox,
  ]);

  /** Share the resolution on screen */
  useEffect(() => {
    updateH3Map({ resolution: shownResolution });
  }, [shownResolution]);

  /** Forget this map's H3 state when the layer goes away */
  useEffect(
    () => () => {
      if (pendingRef.current) pendingRef.current.cancelled = true;
      dispatch(H3MapActions.remove(mapId));
    },
    [],
  );

  /** Color each cell with the indicator's style rules */
  const styledValues: StyledH3Value[] = useMemo(() => {
    if (!shownValues.length) {
      return [];
    }
    const config = returnLayerStyleConfig(indicatorLayer, indicators ?? []);
    const noDataStyle = returnNoDataStyle(indicatorLayer, indicators ?? []);
    // Dynamic styles are grouped by admin level; use the resolution for it.
    // Empty cells skip the rules (null would match "x>=0") and get no-data.
    const rows = UpdateStyleData(
      shownValues
        .filter(hasValue)
        .map((row) => ({ ...row, admin_level: shownResolution })),
      config,
    );
    const emptyRows = shownValues.filter((row) => !hasValue(row));
    return [...emptyRows, ...rows]
      .map((row: any) => {
        const color = row.style?.color ?? noDataStyle?.color;
        if (!color) return null;
        return {
          geom_id: row.geom_id,
          value: row.value,
          color: hexToRGBList(color, 255),
        };
      })
      .filter(Boolean);
  }, [shownValues, indicatorLayer, indicators, shownResolution]);

  const noResolutions =
    loadedResolutionsKey === resolutionsKey && resolutions.length === 0;
  const valuesLoaded = loaded?.key === valuesKey;

  /** Legend: the classes of the hexagons on screen */
  const legendRules = useMemo(() => {
    if (!noResolutions && !loaded) {
      return null;
    }
    const config = returnLayerStyleConfig(indicatorLayer, indicators ?? []);
    const rows = noResolutions
      ? []
      : shownValues
          .filter(hasValue)
          .map((row) => ({ ...row, admin_level: shownResolution }));
    return h3LegendRules(config, rows, shownResolution);
  }, [
    noResolutions,
    loaded,
    shownValues,
    indicatorLayer,
    indicators,
    shownResolution,
  ]);

  useEffect(() => {
    onLegendRules?.(legendRules);
  }, [legendRules]);

  useEffect(() => () => onLegendRules?.(null), []);

  /** Create the overlay, and report the view once the map settles */
  useEffect(() => {
    if (!map) {
      return;
    }
    const deckgl = new MapboxOverlay({ interleaved: false, layers: [] });
    // Keep the independent canvas with the map, below popups and controls.
    const container = deckgl.onAdd(
      map as unknown as Parameters<MapboxOverlay["onAdd"]>[0],
    );
    map.getCanvasContainer().appendChild(container);
    overlay.current = deckgl;

    // GeoSight popups find clicked features with queryRenderedFeatures, which
    // can't see deck.gl layers. Pick the hexagon here and open the popup on
    // the next tick, so it replaces the region popup opened by the same click.
    const onClick = (e: maplibregl.MapMouseEvent) => {
      const picked = deckgl.pickObject({
        x: e.point.x,
        y: e.point.y,
        layerIds: [layerId],
      });
      if (!picked?.object) return;
      setTimeout(() =>
        addStandalonePopup(map, e.lngLat, renderPopup, picked.object, null),
      );
    };
    map.on("click", onClick);

    const reportView = () => {
      const bounds = map.getBounds();
      updateH3Map({
        zoom: map.getZoom(),
        bbox: padBbox(
          [
            bounds.getWest(),
            bounds.getSouth(),
            bounds.getEast(),
            bounds.getNorth(),
          ],
          0,
        ),
      });
    };
    let settleTimer: ReturnType<typeof setTimeout> | undefined;
    const onMoveEnd = () => {
      clearTimeout(settleTimer);
      settleTimer = setTimeout(reportView, SETTLE_MS);
    };
    // A new move cancels a pending report, so only settled views count
    const onMoveStart = () => clearTimeout(settleTimer);
    map.on("moveend", onMoveEnd);
    map.on("movestart", onMoveStart);
    // First report also waits, as the project may still fly to its extent
    onMoveEnd();

    return () => {
      overlay.current = null;
      clearTimeout(settleTimer);
      // The map may already be removed (e.g. leaving the page), so each step
      // must not stop the others.
      try {
        map.off("click", onClick);
        map.off("moveend", onMoveEnd);
        map.off("movestart", onMoveStart);
      } catch (error) {
        console.warn("H3 layer: could not remove the map handlers", error);
      }
      try {
        deckgl.onRemove();
      } catch (error) {
        console.warn("H3 layer: could not remove the overlay", error);
      }
      container.remove();
    };
  }, [map]);

  /** Render hexagons */
  useEffect(() => {
    if (!overlay.current) {
      return;
    }
    if (!styledValues.length || !indicatorShow) {
      overlay.current.setProps({ layers: [] });
      return;
    }
    overlay.current.setProps({
      layers: [
        new H3HexagonLayer<StyledH3Value>({
          id: layerId,
          data: styledValues,
          getHexagon: (d) => d.geom_id,
          getFillColor: (d) => d.color as [number, number, number, number],
          extruded: false,
          stroked: true,
          getLineColor: [255, 255, 255, 120],
          lineWidthMinPixels: 0.5,
          opacity: (transparency ?? 100) / 100,
          pickable: true,
        }),
      ],
    });
  }, [map, styledValues, indicatorShow, transparency]);

  /** Show an empty state and the resolution picker over the map. */
  const wrapper = document.getElementById(`map-${mapId}-wrapper`);
  if (!wrapper || !indicatorShow) {
    return null;
  }
  // Empty cells alone (include_empty) still mean there is no data
  const noDataInView = valuesLoaded && !shownValues.some(hasValue);
  const noDataMessage = noResolutions
    ? "No H3 data for this indicator"
    : noDataInView
      ? "No H3 data in this view"
      : null;
  if (!noDataMessage && resolutions.length < 2) {
    return null;
  }
  return createPortal(
    <>
      {noDataMessage && (
        <div
          role="status"
          style={{
            position: "absolute",
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            zIndex: 2,
            background: "white",
            padding: "8px 12px",
            borderRadius: 4,
            boxShadow: "0 1px 4px rgba(0, 0, 0, 0.3)",
            pointerEvents: "none",
          }}
        >
          {noDataMessage}
        </div>
      )}
      {resolutions.length > 1 && (
        <div
          className="H3ResolutionSelector"
          style={{
            position: "absolute",
            top: 10,
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 2,
            background: "white",
            padding: "4px 8px",
            borderRadius: 4,
            fontSize: 12,
            boxShadow: "0 1px 4px rgba(0, 0, 0, 0.3)",
          }}
        >
          <label>
            H3 resolution{" "}
            <select
              value={mode === "auto" ? "auto" : (selectedResolution ?? "")}
              onChange={(evt) =>
                evt.target.value === "auto"
                  ? updateH3Map({ mode: "auto" })
                  : updateH3Map({
                      mode: "manual",
                      selectedResolution: parseInt(evt.target.value),
                    })
              }
            >
              <option value="auto">
                Auto (follows zoom)
                {mode === "auto" && shownResolution !== null
                  ? `: ${shownResolution}`
                  : ""}
              </option>
              {resolutions.map((res) => (
                <option key={res} value={res}>
                  {res}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
    </>,
    wrapper,
  );
}
