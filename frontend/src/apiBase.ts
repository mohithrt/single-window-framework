const configuredApiOrigin = (import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/+$/, '')

/** Build an API URL for local Vite proxying or a separately hosted production API. */
export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${configuredApiOrigin}${normalizedPath}`
}
