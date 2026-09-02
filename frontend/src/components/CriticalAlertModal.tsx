import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertOctagon, WifiOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { timeAgo } from '@/lib/format'
import { useCriticalAlerts, type UnifiedCriticalAlert } from '@/lib/useCriticalAlerts'

const SESSION_KEY = 'citi-critical-alert-modal-shown'

export function CriticalAlertModal() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const { items, acknowledgeOne, acknowledgeAll, isAcknowledging } = useCriticalAlerts()

  // Pops up once per browser tab session (sessionStorage survives a page reload but not
  // closing the tab) — not on every refetch, so it doesn't interrupt someone mid-task
  // every 30s just because the list is still non-empty.
  useEffect(() => {
    if (items.length > 0 && sessionStorage.getItem(SESSION_KEY) !== '1') {
      setOpen(true)
      sessionStorage.setItem(SESSION_KEY, '1')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items.length > 0])

  if (items.length === 0) return null

  function goTo(item: UnifiedCriticalAlert) {
    setOpen(false)
    if (item.kind === 'connectivity' && item.serverId) {
      navigate(`/connectivity/${item.serverId}`)
    } else if (item.serverId) {
      navigate(`/servers/${item.serverId}`)
    } else {
      navigate('/alerts?severity=critical')
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-md border-red-800 bg-gradient-to-b from-red-950/50 via-red-950/20 to-slate-900">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertOctagon className="h-4.5 w-4.5 text-red-400" />
            {items.length === 1 ? '1 alerta crítica sin reconocer' : `${items.length} alertas críticas sin reconocer`}
          </DialogTitle>
          <DialogDescription>Requieren atención antes de continuar con lo demás.</DialogDescription>
        </DialogHeader>

        <div className="flex max-h-72 flex-col gap-2 overflow-y-auto">
          {items.slice(0, 8).map((item) => (
            <div
              key={`${item.kind}:${item.id}`}
              className="flex items-center justify-between gap-3 rounded-md border border-red-900/50 bg-red-950/30 px-3 py-2"
            >
              <button className="min-w-0 flex-1 text-left" onClick={() => goTo(item)}>
                <p className="flex items-center gap-1.5 truncate text-sm text-slate-100">
                  {item.kind === 'connectivity' && <WifiOff className="h-3.5 w-3.5 shrink-0 text-red-400" />}
                  {item.title}
                </p>
                <p className="truncate text-xs text-slate-500">
                  {item.subtitle} · {timeAgo(item.occurredAt)}
                </p>
              </button>
              <Button size="sm" variant="outline" disabled={isAcknowledging} onClick={() => acknowledgeOne.mutate(item)}>
                Reconocer
              </Button>
            </div>
          ))}
          {items.length > 8 && <p className="text-xs text-slate-500">+{items.length - 8} más.</p>}
        </div>

        <DialogFooter className="sm:justify-between">
          <Button variant="outline" disabled={isAcknowledging} onClick={() => acknowledgeAll.mutate(items)}>
            {acknowledgeAll.isPending ? 'Reconociendo…' : 'Reconocer todas'}
          </Button>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cerrar
            </Button>
            <Button onClick={() => goTo(items[0])}>Revisar</Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
