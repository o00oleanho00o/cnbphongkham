import files from 'virtual:dc-files';

export { files };

export const docUrl = (file: string) => `${import.meta.env.BASE_URL}${encodeURIComponent(file)}`;

export const displayName = (file: string) => file.replace(/\.dc\.html$/, '');

// The web canvases come as a pair: the old web ("Web cũ", the default) and the Next.js-only screens ("Màn mới").
// When the canvas folder holds both, the toolbar shows one dropdown instead of two tabs; "Cả hai" loads both side by side.
export const WEB_OLD = 'Pema Web.dc.html';
export const WEB_NEW = 'Pema Web (Next.js).dc.html';
export const BOTH_HASH = 'both';
export const hasWebPair = files.includes(WEB_OLD) && files.includes(WEB_NEW);
export type WebSource = 'old' | 'new' | 'both';

function wantedFromHash() {
  try {
    return decodeURIComponent(window.location.hash.slice(1));
  } catch {
    return '';
  }
}

export function fileFromHash() {
  const wanted = wantedFromHash();
  if (hasWebPair && wanted === BOTH_HASH) return WEB_OLD;
  if (files.includes(wanted)) return wanted;
  return hasWebPair ? WEB_OLD : (files[0] ?? '');
}

/** True for the hash `#both`: the two web canvases side by side. */
export const bothFromHash = () => hasWebPair && wantedFromHash() === BOTH_HASH;
