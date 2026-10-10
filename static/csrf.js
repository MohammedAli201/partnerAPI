// Preserve existing fetch calls while attaching the server-issued session CSRF token.
(() => {
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    const target = new URL(typeof input === 'string' ? input : input.url, location.href);
    const method = (init.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    if (target.origin === location.origin && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
      const token = document.cookie.split('; ').find(v => v.startsWith('csrf_token='));
      const headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined));
      if (token) headers.set('X-CSRF-Token', decodeURIComponent(token.slice('csrf_token='.length)));
      init = { ...init, headers };
    }
    return originalFetch(input, init);
  };
})();
