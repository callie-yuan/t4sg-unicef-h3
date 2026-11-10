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
  returnLayerStyleConfig,
  returnNoDataStyle,
} from "../../../../../utils/Style";
import { hexToRGBList } from "../../../../../utils/main";
import { addStandalonePopup } from "../../utils";
import { IndicatorLayer } from "../../../../../types/IndicatorLayer";
import type { RootState } from "../../../../../store/dashboard/reducers";
import { mockResolutions, mockSize, mockValues } from "./mock";

/** One row of GET /api/v1/indicators/<id>/h3/values/ */
export interface H3Value {
  geom_id: string;
  value: number;
}

interface StyledH3Value extends H3Value {
  color: number[];
}

const H3Urls = {
  resolutions: (indicatorId: number, referenceLayerId: string) =>
    `/api/v1/indicators/${indicatorId}/h3/resolutions/?reference_layer=${encodeURIComponent(referenceLayerId)}`,
  values: (
    indicatorId: number,
    resolution: number,
    referenceLayerId: string,
    date: string | null,
  ) =>
    `/api/v1/indicators/${indicatorId}/h3/values/?resolution=${resolution}&reference_layer=${encodeURIComponent(referenceLayerId)}` +
    (date ? `&date=${encodeURIComponent(date)}` : ""),
};

/** Popup content for a clicked hexagon */
// django_project/frontend/src/pages/Dashboard/MapLibre/Layers/H3IndicatorLayer/index.tsx
const renderPopup = (cell: H3Value & { title?: string; date?: string | null; resolution?: number | null }) => {
  const escape = (text: string) =>
    text.replace(/[&<>"']/g, (char) => `&#${char.charCodeAt(0)};`);
  const value = Number.isFinite(cell.value) ? cell.value.toLocaleString() : String(cell.value);
  return (
    `<div class="maplibregl-popup-content-main" style="background:#fff;color:#333;padding:8px 12px;border-radius:4px;box-shadow:0 1px 4px rgba(0,0,0,.3);min-width:170px">` +
    `<div class="maplibregl-popup-content-main">` +
    `<div style="font-weight:600;margin-bottom:4px">${escape(cell.title ?? "H3 cell")}</div>` +
    `<div style="font-size:20px;line-height:1.2">${escape(value)}</div>` +
    `<div style="color:#666;font-size:11px;margin-top:6px">` +
    (cell.date ? `as of ${escape(cell.date)} | ` : "") +
    `resolution ${cell.resolution ?? ""}<br/>` +
    `<span style="font-family:monospace">${escape(String(cell.geom_id))}</span>` +
    `</div></div>`
  );
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
}

export default function H3IndicatorLayer({
  mapId,
  map,
  indicatorLayer,
  referenceLayer,
}: Props) {
  // @ts-ignore
  const indicators = useSelector((state) => state.dashboard.data?.indicators);
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

  // Click handler is created once (effect on [map]); read live values through a ref
  const popupMeta = useRef<{
    title?: string;
    date: string | null;
    resolution: number | null;
  }>({ date: null, resolution: null });
  popupMeta.current = {
    title: indicatorLayer?.name,
    date: selectedDate,
    resolution,
  };

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
    defaultResolution,
    minResolution,
    maxResolution,
  ]);
  const valuesKey = JSON.stringify([
    indicatorId,
    resolution,
    referenceLayerId,
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
      .get(H3Urls.resolutions(indicatorId, referenceLayerId))
      .then((response) => {
        if (cancelled) return;
        const fetched = configuredResolutions(response.data ?? []);
        setResolutions(fetched);
        setResolution(initialResolution(fetched));
        setLoadedResolutionsKey(resolutionsKey);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [
    indicatorId,
    referenceLayerId,
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
    axiosRequest
      .get(
        H3Urls.values(indicatorId, resolution, referenceLayerId, selectedDate),
      )
      .then((response) => {
        if (cancelled) return;
        setValues(response.data ?? []);
        setLoadedValuesKey(valuesKey);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [indicatorId, resolution, referenceLayerId, selectedDate]);

  /** Color each cell with the indicator's style rules */
  const styledValues: StyledH3Value[] = useMemo(() => {
    if (!values.length) {
      return [];
    }
    const config = returnLayerStyleConfig(indicatorLayer, indicators ?? []);
    const noDataStyle = returnNoDataStyle(indicatorLayer, indicators ?? []);
    // Dynamic styles are grouped by admin level; use the resolution for it.
    const rows = UpdateStyleData(
      values.map((row) => ({ ...row, admin_level: resolution })),
      config,
    );
    return rows
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
      const object = { ...picked.object, ...popupMeta.current };
      setTimeout(() =>
        addStandalonePopup(map, e.lngLat, renderPopup, object as any, null),
      );
    };
    map.on("click", onClick);
    return () => {
      map.off("click", onClick);
      deckgl.onRemove();
      container.remove();
      overlay.current = null;
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
  const noH3Data =
    (loadedResolutionsKey === resolutionsKey && resolutions.length === 0) ||
    (loadedValuesKey === valuesKey && values.length === 0);
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
