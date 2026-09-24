export function getLmBasePath(): string {
  const { pathname } = window.location;
  return pathname.endsWith('/') ? pathname.slice(0, -1) : pathname;
}

export function lmApiUrl(path: string): string {
  return `${getLmBasePath()}${path}`;
}
