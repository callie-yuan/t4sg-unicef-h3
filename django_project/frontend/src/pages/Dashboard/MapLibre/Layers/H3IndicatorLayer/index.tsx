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
   Renders nothing when the indicator has no H3 values.
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
  resolutions: (indicatorId: number) =>
    `/api/v1/indicators/${indicatorId}/h3/resolutions/`,
  values: (indicatorId: number, resolution: number) =>
    `/api/v1/indicators/${indicatorId}/h3/values/?resolution=${resolution}`,
};

/** Popup content for a clicked hexagon */
const renderPopup = (cell: H3Value) => {
  const escape = (text: string) =>
    text.replace(/[&<>"']/g, (char) => `&#${char.charCodeAt(0)};`);
  return (
    `<div class="maplibregl-popup-content-main">` +
    `<b>H3 ID:</b> ${escape(String(cell.geom_id))}<br/>` +
    `<b>Value:</b> ${escape(String(cell.value))}` +
    `</div>`
  );
};

export interface Props {
  mapId: number;
  map: maplibregl.Map;
  indicatorLayer: IndicatorLayer;
}

export default function H3IndicatorLayer({
  mapId,
  map,
  indicatorLayer,
}: Props) {
  // @ts-ignore
  const indicators = useSelector((state) => state.dashboard.data?.indicators);
  // @ts-ignore
  const indicatorShow = useSelector((state) => state.map?.indicatorShow);
  const transparency = useSelector(
    // @ts-ignore
    (state) => state.map?.transparency?.indicatorLayer,
  );

  const [resolutions, setResolutions] = useState<number[]>([]);
  const [resolution, setResolution] = useState<number | null>(null);
  const [values, setValues] = useState<H3Value[]>([]);

  // deck.gl overlay owned by this layer. ReferenceLayer replaces all layers
  // on the shared overlay, so H3 hexagons need their own.
  const overlay = useRef<MapboxOverlay | null>(null);
  const layerId = `h3-indicator-layer-${mapId}`;

  // Only single-indicator layers can have H3 values
  const indicatorId =
    indicatorLayer?.indicators?.length === 1
      ? indicatorLayer.indicators[0].id
      : null;

  /** Fetch the resolutions that have H3 values */
  useEffect(() => {
    setResolutions([]);
    setResolution(null);
    if (!indicatorId) {
      return;
    }
    const mock = mockSize();
    if (mock) {
      const mocked = mockResolutions(mock);
      setResolutions(mocked);
      setResolution(mocked[0]);
      return;
    }
    let cancelled = false;
    axiosRequest
      .get(H3Urls.resolutions(indicatorId))
      .then((response) => {
        if (cancelled) return;
        const fetched: number[] = response.data ?? [];
        setResolutions(fetched);
        setResolution(fetched.length ? fetched[0] : null);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [indicatorId]);

  /** Fetch the values of the selected resolution */
  useEffect(() => {
    setValues([]);
    if (!indicatorId || resolution === null) {
      return;
    }
    const mock = mockSize();
    if (mock) {
      setValues(mockValues(mock, resolution));
      return;
    }
    let cancelled = false;
    axiosRequest
      .get(H3Urls.values(indicatorId, resolution))
      .then((response) => {
        if (!cancelled) setValues(response.data ?? []);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [indicatorId, resolution]);

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
    const deckgl = new MapboxOverlay({ interleaved: true, layers: [] });
    map.addControl(deckgl as unknown as maplibregl.IControl);
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
      map.off("click", onClick);
      map.removeControl(deckgl as unknown as maplibregl.IControl);
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

  /** Resolution picker, only when there is more than one resolution */
  const wrapper = document.getElementById(`map-${mapId}-wrapper`);
  if (!wrapper || resolutions.length < 2 || !indicatorShow) {
    return null;
  }
  return createPortal(
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
    </div>,
    wrapper,
  );
}
