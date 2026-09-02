export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i++
  }
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

export function formatUptime(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

export function formatMbps(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${value.toFixed(value >= 10 ? 0 : 2)} Mbps`
}

export function formatMBps(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${value.toFixed(value >= 10 ? 0 : 2)} MB/s`
}

/** Inverse of timeAgo — "en 2h 14min" style countdown to a future timestamp, used by
 * MaintenancePage for "empieza en…"/"termina en…". A past timestamp reads as "ahora". */
export function timeUntil(iso: string | null | undefined): string {
  if (!iso) return '—'
  const seconds = Math.floor((new Date(iso).getTime() - Date.now()) / 1000)
  if (seconds <= 0) return 'ahora'
  if (seconds < 60) return `en ${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `en ${minutes} min`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `en ${hours}h ${minutes % 60}min`
  return `en ${Math.floor(hours / 24)} d`
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return 'nunca'
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 5) return 'ahora mismo'
  if (seconds < 60) return `hace ${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `hace ${minutes} min`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `hace ${hours} h`
  return `hace ${Math.floor(hours / 24)} d`
}
