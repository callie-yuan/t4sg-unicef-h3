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
   ========================================================================== */

import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useSelector } from "react-redux";
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
import { mockResolutions, mockSize, mockValues } from "./mock";

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
  ) =>
    `/api/v1/indicators/${indicatorId}/h3/values/?resolution=${resolution}&` +
    areaQuery(referenceLayerId, projectId) +
    (date ? `&date=${encodeURIComponent(date)}` : "") +
    (includeEmpty ? "&include_empty=true" : ""),
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

  const [resolutions, setResolutions] = useState<number[]>([]);
  const [resolution, setResolution] = useState<number | null>(null);
  const [values, setValues] = useState<H3Value[]>([]);
  const [loadedResolutionsKey, setLoadedResolutionsKey] = useState<
    string | null
  >(null);
  const [loadedValuesKey, setLoadedValuesKey] = useState<string | null>(null);

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
  const valuesKey = JSON.stringify([
    indicatorId,
    resolution,
    referenceLayerId,
    projectId,
    selectedDate,
  ]);

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

  /** Fetch the resolutions that have H3 values */
  useEffect(() => {
    setResolutions([]);
    setResolution(null);
    if (!indicatorId || !referenceLayerId) {
      return;
    }
    const mock = mockSize();
    if (mock) {
      const mocked = configuredResolutions(mockResolutions(mock));
      setResolutions(mocked);
      setResolution(initialResolution(mocked));
      setLoadedResolutionsKey(resolutionsKey);
      return;
    }
    let cancelled = false;
    axiosRequest
      .get(H3Urls.resolutions(indicatorId, referenceLayerId, projectId))
      .then((response) => {
        if (cancelled) return;
        const fetched = configuredResolutions(response.data ?? []);
        setResolutions(fetched);
        setResolution(initialResolution(fetched));
        setLoadedResolutionsKey(resolutionsKey);
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

  /** Fetch the values of the selected resolution */
  useEffect(() => {
    setValues([]);
    if (!indicatorId || !referenceLayerId || resolution === null) {
      return;
    }
    const mock = mockSize();
    if (mock) {
      setValues(mockValues(mock, resolution));
      setLoadedValuesKey(valuesKey);
      return;
    }
    let cancelled = false;
    const request = (includeEmpty: boolean) =>
      axiosRequest.get(
        H3Urls.values(
          indicatorId,
          resolution,
          referenceLayerId,
          projectId,
          selectedDate,
          includeEmpty,
        ),
      );
    // Ask for the empty cells of the area too. The API refuses that when
    // the area has too many cells at this resolution, so then draw only the
    // cells with values.
    request(true)
      .catch((error) => {
        if (cancelled || error?.response?.status !== 400) throw error;
        logRequestError("empty cells", error);
        return request(false);
      })
      .then((response) => {
        if (cancelled) return;
        setValues(response.data ?? []);
        setLoadedValuesKey(valuesKey);
      })
      .catch((error) => {
        if (!cancelled) logRequestError("values", error);
      });
    return () => {
      cancelled = true;
    };
  }, [indicatorId, resolution, referenceLayerId, projectId, selectedDate]);

  /** Color each cell with the indicator's style rules */
  const styledValues: StyledH3Value[] = useMemo(() => {
    if (!values.length) {
      return [];
    }
    const config = returnLayerStyleConfig(indicatorLayer, indicators ?? []);
    const noDataStyle = returnNoDataStyle(indicatorLayer, indicators ?? []);
    // Dynamic styles are grouped by admin level; use the resolution for it.
    // Empty cells skip the rules (null would match "x>=0") and get no-data.
    const rows = UpdateStyleData(
      values
        .filter(hasValue)
        .map((row) => ({ ...row, admin_level: resolution })),
      config,
    );
    const emptyRows = values.filter((row) => !hasValue(row));
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
  }, [values, indicatorLayer, indicators, resolution]);

  const noResolutions =
    loadedResolutionsKey === resolutionsKey && resolutions.length === 0;
  const valuesLoaded = loadedValuesKey === valuesKey;

  /** Legend: the classes of the resolution and date on screen */
  const legendRules = useMemo(() => {
    if (!noResolutions && !valuesLoaded) {
      return null;
    }
    const config = returnLayerStyleConfig(indicatorLayer, indicators ?? []);
    const rows = noResolutions
      ? []
      : values
          .filter(hasValue)
          .map((row) => ({ ...row, admin_level: resolution }));
    return h3LegendRules(config, rows, resolution);
  }, [
    noResolutions,
    valuesLoaded,
    values,
    indicatorLayer,
    indicators,
    resolution,
  ]);

  useEffect(() => {
    onLegendRules?.(legendRules);
  }, [legendRules]);

  useEffect(() => () => onLegendRules?.(null), []);

  /** Create the overlay */
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
    return () => {
      overlay.current = null;
      // The map may already be removed (e.g. leaving the page), so each step
      // must not stop the others.
      try {
        map.off("click", onClick);
      } catch (error) {
        console.warn("H3 layer: could not remove the click handler", error);
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
  const noH3Data = noResolutions || (valuesLoaded && !values.some(hasValue));
  if (!noH3Data && resolutions.length < 2) {
    return null;
  }
  return createPortal(
    <>
      {noH3Data && (
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
          }}
        >
          No H3 data for this indicator
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
              value={resolution ?? ""}
              onChange={(evt) => setResolution(parseInt(evt.target.value))}
            >
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
