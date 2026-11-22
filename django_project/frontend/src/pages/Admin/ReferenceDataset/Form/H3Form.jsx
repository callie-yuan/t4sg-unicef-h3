import React, { useState } from 'react';
import Admin, { pageNames } from '../../index';
import { SaveButton } from '../../../../components/Elements/Button';
import AreaInput from '../../../../components/AreaInput';
import { DjangoRequests } from '../../../../Requests';

function fieldError(errors, name) {
  const value = errors[name];
  return value ? <p className='H3FormError' role='alert'>
    {Array.isArray(value) ? value.join(' ') : value}
  </p> : null;
}

/** Standalone H3 form; local reference datasets retain their existing form. */
export default function H3Form() {
  const [name, setName] = useState(initialData.name || '');
  const [minResolution, setMinResolution] = useState(initialData.min_resolution ?? 0);
  const [defaultResolution, setDefaultResolution] = useState(initialData.default_resolution ?? 7);
  const [maxResolution, setMaxResolution] = useState(initialData.max_resolution ?? 15);
  const [area, setArea] = useState(initialData.area || {
    mode: 'paste', text: '', country_codes: []
  });
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);

  async function save(event) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setErrors({});
    const payload = {
      name: name.trim(),
      min_resolution: Number(minResolution),
      default_resolution: Number(defaultResolution),
      max_resolution: Number(maxResolution),
      area,
    };
    try {
      const response = initialData.identifier
        ? await DjangoRequests.put(
          urls.api.h3Detail.replace(DEFAULT_UUID, initialData.identifier), payload
        )
        : await DjangoRequests.post(urls.api.h3Create, payload);
      window.location.assign(
        urls.api.h3Edit.replace(DEFAULT_UUID, response.data.identifier) + '?success=true'
      );
    } catch (error) {
      const data = error.response?.data;
      setErrors(data && typeof data === 'object' && !Array.isArray(data)
        ? { ...data, non_field_errors: data.non_field_errors || data.detail }
        : { non_field_errors: ['Could not save the H3 layer.'] });
      setSaving(false);
    }
  }

  return <Admin minifySideNavigation={true} pageName={pageNames.ReferenceLayerView}
    rightHeader={<SaveButton type='submit' form='H3LayerForm' variant='primary'
      text={saving ? 'Saving…' : 'Submit'} disabled={saving} />}>
    <form id='H3LayerForm' className='H3LayerForm' onSubmit={save}>
      {new URLSearchParams(window.location.search).has('success') &&
        <p role='status'>Saved.</p>}
      {fieldError(errors, 'non_field_errors')}
      <label htmlFor='h3-name'>Name</label>
      <input id='h3-name' value={name} maxLength={256} required
        onChange={(event) => setName(event.target.value)} />
      {fieldError(errors, 'name')}
      <div className='H3ResolutionFields'>
        {[
          ['Minimum resolution', minResolution, setMinResolution, 'min_resolution'],
          ['Default resolution', defaultResolution, setDefaultResolution, 'default_resolution'],
          ['Maximum resolution', maxResolution, setMaxResolution, 'max_resolution'],
        ].map(([label, value, setter, key]) => <label key={key}>
          {label}
          <input type='number' min={0} max={15} step={1} required value={value}
            onChange={(event) => setter(event.target.value)} />
          {fieldError(errors, key)}
        </label>)}
      </div>
      <AreaInput value={area} onChange={setArea}
        countriesUrl={urls.api.h3Countries} error={errors.area} />
    </form>
  </Admin>;
}
