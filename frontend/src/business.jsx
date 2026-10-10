import { createContext, useContext } from 'react';

export const BusinessContext = createContext(null);
export const useBusiness = () => useContext(BusinessContext);
export function useLink() {
  const { lang } = useBusiness();
  return (path) => {
    if (!path.startsWith('/')) return path;
    const url = new URL(path, window.location.origin);
    url.searchParams.set('lang', lang);
    return url.pathname + url.search + url.hash;
  };
}
