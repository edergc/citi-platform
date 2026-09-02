// Disconnect notifications written after the "motivo" feature shipped embed a
// "Motivo: ...." segment (see _disconnect_reason in backend/app/api/v1/agents.py) —
// extract it for display instead of showing the whole sentence. Older disconnect events
// (before this shipped) won't match, so callers should treat null as "not recorded",
// not as an error.
const MOTIVO_RE = /Motivo: (.+?)\.\s*(?:Los servicios|$)/

export function extractMotivo(message: string): string | null {
  const match = MOTIVO_RE.exec(message)
  return match ? match[1] : null
}
