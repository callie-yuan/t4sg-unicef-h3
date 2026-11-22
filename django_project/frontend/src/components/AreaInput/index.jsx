import React, { useEffect, useState } from 'react';
import { DjangoRequests } from '../../Requests';

import './style.scss';

/** Controlled area selector shared by layer and future project forms. */
export default function AreaInput({ value, onChange, countriesUrl, error }) {
  const [query, setQuery] = useState('');
  const [countries, setCountries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    if (value.mode !== 'countries' || countries.length) return;
    let active = true;
    setLoading(true);
    DjangoRequests.get(countriesUrl).then(({ data }) => {
      if (!active) return;
      const items = Array.isArray(data) ? data : data.results;
      if (!Array.isArray(items)) throw new Error('Invalid country list.');
      setCountries(items);
      setLoadError('');
    }).catch((requestError) => {
      if (active) setLoadError(
        requestError.response?.data?.detail || requestError.message || 'Could not load countries.'
      );
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [value.mode, countriesUrl, countries.length]);

  const codes = value.country_codes || [];
  const matches = countries.filter((country) =>
    `${country.name} ${country.code}`.toLowerCase().includes(query.toLowerCase())
  );

  return <fieldset className='AreaInput'>
    <legend>Area</legend>
    <label>
      <input type='radio' name='area-mode' checked={value.mode === 'paste'}
        onChange={() => onChange({ mode: 'paste', text: '', country_codes: [] })} />
      Paste WKT or GeoJSON
    </label>
    <label>
      <input type='radio' name='area-mode' checked={value.mode === 'countries'}
        onChange={() => onChange({ mode: 'countries', text: '', country_codes: [] })} />
      Countries (GeoRepo)
    </label>
    {value.mode === 'paste' ? <div>
      <textarea aria-label='WKT or GeoJSON area' rows={8}
        placeholder='POLYGON((...)) or GeoJSON Polygon / MultiPolygon'
        value={value.text || ''}
        onChange={(event) => onChange({ mode: 'paste', text: event.target.value, country_codes: [] })} />
      <p>Leave blank for no clipping. Use a Polygon or MultiPolygon in WKT or GeoJSON.</p>
    </div> : <div>
      <input aria-label='Search countries' type='search' value={query}
        onChange={(event) => setQuery(event.target.value)} placeholder='Search countries' />
      {loading && <p>Loading countries…</p>}
      {loadError && <p role='alert'>{loadError}</p>}
      <div className='AreaInputCountries'>
        {matches.map((country) => <label key={country.code}>
          <input type='checkbox' checked={codes.includes(country.code)}
            onChange={() => onChange({
              mode: 'countries', text: '',
              country_codes: codes.includes(country.code)
                ? codes.filter((code) => code !== country.code)
                : [...codes, country.code]
            })} />
          {country.name} ({country.code})
        </label>)}
      </div>
      {!!codes.length && <p>Selected: {codes.join(', ')}</p>}
    </div>}
    {error && <p className='AreaInputError' role='alert'>{Array.isArray(error) ? error.join(' ') : error}</p>}
  </fieldset>;
}
