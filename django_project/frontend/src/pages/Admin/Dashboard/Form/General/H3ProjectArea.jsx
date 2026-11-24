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
   H3 PROJECT AREA
   The project's own area, used instead of its H3 layer's area.
   The change is kept in the project data (h3_area_change) and saved with
   the project's Save button (see saveProjectArea).
   ========================================================================== */

import React, { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Actions } from "../../../../../store/dashboard";
import { DjangoRequests } from "../../../../../Requests";
import AreaInput from "../../../../../components/AreaInput";
import { ThemeButton } from "../../../../../components/Elements/Button";

const EMPTY_AREA = { mode: "paste", text: "", country_codes: [] };
const COUNTRIES_URL = "/api/v1/h3/countries/";

export const H3AreaUrls = {
  project: (slug) => `/api/v1/h3/projects/${encodeURIComponent(slug)}/area/`,
  layer: (identifier) => `/api/v1/h3/layers/${identifier}/area/`,
};

const isBlank = (area) =>
  !area ||
  (area.mode === "countries"
    ? !area.country_codes?.length
    : !area.text?.trim());

/**
 * Save the area change of a project, after the project itself is saved.
 * @param {string} slug Project slug.
 * @param {object|null} change {action: "set", area} or {action: "clear"}.
 * @returns {Promise} Resolves when there is nothing to save or it is saved.
 */
export function saveProjectArea(slug, change) {
  if (!change) {
    return Promise.resolve(null);
  }
  const url = H3AreaUrls.project(slug);
  return change.action === "clear"
    ? DjangoRequests.delete(url)
    : DjangoRequests.put(url, { area: change.area });
}

/** Readable message of a failed area request. */
export function areaErrorMessage(error) {
  const data = error?.response?.data;
  const message = data?.area ?? data?.detail ?? error?.message;
  return Array.isArray(message) ? message.join(" ") : "" + message;
}

/** Area section of an H3 project. */
export default function H3ProjectArea({ referenceLayer }) {
  const dispatch = useDispatch();
  const projectData = useSelector((state) => state.dashboard.data);
  const change = projectData.h3_area_change ?? null;
  // Saved projects have an id; new ones get their area after the first save
  const slug = projectData.id ? projectData.slug : null;

  const [saved, setSaved] = useState(null);
  const [layerHasArea, setLayerHasArea] = useState(null);
  const [value, setValue] = useState(EMPTY_AREA);
  const [error, setError] = useState("");

  /** Saved area of the project; again after a save clears the change. */
  useEffect(() => {
    if (!slug || change) {
      return;
    }
    let cancelled = false;
    DjangoRequests.get(H3AreaUrls.project(slug))
      .then(({ data }) => {
        if (cancelled) return;
        setSaved(data.area);
        setValue(data.area ?? EMPTY_AREA);
        setError("");
      })
      .catch((requestError) => {
        if (!cancelled) setError(areaErrorMessage(requestError));
      });
    return () => {
      cancelled = true;
    };
  }, [slug, !change]);

  /** Whether the chosen layer has its own area. */
  useEffect(() => {
    setLayerHasArea(null);
    if (!referenceLayer?.identifier) {
      return;
    }
    let cancelled = false;
    DjangoRequests.get(H3AreaUrls.layer(referenceLayer.identifier))
      .then(({ data }) => {
        if (!cancelled) setLayerHasArea(!!data.has_area);
      })
      .catch((requestError) => {
        if (!cancelled) setError(areaErrorMessage(requestError));
      });
    return () => {
      cancelled = true;
    };
  }, [referenceLayer?.identifier]);

  /** Keep the change in the project data, so Save saves it. */
  const onChange = (area) => {
    setValue(area);
    let newChange = null;
    if (!isBlank(area)) {
      newChange = { action: "set", area: area };
    } else if (saved) {
      newChange = { action: "clear" };
    }
    if (JSON.stringify(newChange) !== JSON.stringify(change)) {
      dispatch(Actions.Dashboard.updateProps({ h3_area_change: newChange }));
    }
  };

  const hasCustomArea =
    change?.action === "set" || (!!saved && change?.action !== "clear");
  const inEffect = hasCustomArea
    ? "Custom area for this project"
    : layerHasArea === null
      ? "Loading…"
      : layerHasArea
        ? "Using the layer's area"
        : "No area";

  return (
    <div className="BasicFormSection H3ProjectArea">
      <label className="form-label">Project area</label>
      <div className="H3ProjectAreaInEffect" role="status">
        <b>{inEffect}</b>
        {change ? " (not saved yet)" : ""}
      </div>
      <AreaInput
        value={value}
        onChange={onChange}
        countriesUrl={COUNTRIES_URL}
        error={error}
      />
      <span className="form-helptext">
        Only this project uses this area. Leave it blank to use the layer's
        area.
      </span>
      {hasCustomArea ? (
        <div>
          <ThemeButton
            variant="Basic Reverse"
            onClick={() => onChange(EMPTY_AREA)}
          >
            Clear custom area
          </ThemeButton>
        </div>
      ) : null}
    </div>
  );
}
