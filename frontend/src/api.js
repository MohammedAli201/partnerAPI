export async function previewDraft(kind, draft, signal) {
  const endpoint = kind === 'partner' ? '/api/public/enquiries/preview' : '/api/public/support/preview';
  const csrf = document.cookie.split('; ').find((value) => value.startsWith('csrf_token='));
  const headers = { 'Content-Type': 'application/json' };
  if (csrf) headers['X-CSRF-Token'] = decodeURIComponent(csrf.slice('csrf_token='.length));
  const response = await fetch(endpoint, { method: 'POST', credentials: 'same-origin', headers, body: JSON.stringify(draft), signal });
  const result = await response.json();
  if (!response.ok || result.mode !== 'preview' || result.sent !== false || result.stored !== false) {
    throw new Error('Preview validation failed');
  }
  return result;
}

export function createLatestRequester(fetcher = fetch) {
  let generation = 0;
  let controller;
  return async (url) => {
    const current = ++generation;
    controller?.abort();
    controller = new AbortController();
    try {
      const response = await fetcher(url, { signal: controller.signal, credentials: 'same-origin' });
      const data = await response.json();
      if (current !== generation) return null;
      if (!response.ok) throw new Error('Request unavailable');
      return data;
    } catch (error) {
      if (current !== generation || error.name === 'AbortError') return null;
      throw error;
    }
  };
}

export function validateDraft(kind, data, copy) {
  const errors = {};
  const ranges = kind === 'partner' ? { company: [2, 160], name: [2, 100], email: [5, 254], website: [8, 500], countries: [2, 200], message: [10, 2000] } : { name: [2, 100], email: [5, 254], message: [10, 2000] };
  for (const [key, [min, max]] of Object.entries(ranges)) {
    const value = String(data[key] || '').trim();
    if (!value) errors[key] = copy.required;
    else if (value.length < min || value.length > max) errors[key] = copy.validation_error;
  }
  if (data.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email.trim())) errors.email = copy.invalid_email;
  if (kind === 'partner') {
    try { const url = new URL(data.website); if (!['https:', 'http:'].includes(url.protocol) || !url.hostname || url.username || url.password) throw Error(); } catch { errors.website = copy.invalid_website; }
    if (!['under_1000', '1000_10000', '10001_50000', 'over_50000'].includes(data.volume)) errors.volume = copy.required;
    if (!Array.isArray(data.methods) || !data.methods.length || data.methods.some((value) => !['mobile_wallet', 'other'].includes(value))) errors.methods = copy.select_method;
  } else if (!['delivery', 'details', 'other'].includes(data.topic)) errors.topic = copy.required;
  return errors;
}
