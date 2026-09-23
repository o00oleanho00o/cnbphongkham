import files from 'virtual:dc-files';

export { files };

export const docUrl = (file: string) => `${import.meta.env.BASE_URL}${encodeURIComponent(file)}`;

export const displayName = (file: string) => file.replace(/\.dc\.html$/, '');

export function fileFromHash() {
  let wanted = '';
  try {
    wanted = decodeURIComponent(window.location.hash.slice(1));
  } catch {
    wanted = '';
  }
  return files.includes(wanted) ? wanted : (files[0] ?? '');
}
