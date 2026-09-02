import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Wrench } from 'lucide-react'
import { api } from '@/lib/api'
import type { MaintenanceWindow } from '@/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { TableSkeleton } from '@/components/ui/skeleton'
import { ErrorMessage } from '@/components/ui/error-message'
import { MaintenanceWindowFormDialog } from '@/components/MaintenanceWindowFormDialog'
import { HexagonStat, HexagonLegend } from '@/components/ui/hexagon-stat'
import { cn } from '@/lib/utils'
import { timeAgo, timeUntil } from '@/lib/format'

function scopeDestination(window: MaintenanceWindow): string | null {
  return window.scope_type === 'server' ? `/servers/${window.scope_id}` : null
}

function WindowCard({ window, borderClass, muted }: { window: MaintenanceWindow; borderClass: string; muted?: boolean }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const dest = scopeDestination(window)

  const cancel = useMutation({
    mutationFn: async () => api.post(`/maintenance-windows/${window.id}/cancel`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['maintenance-windows'] })
      queryClient.invalidateQueries({ queryKey: ['servers'] })
    },
  })

  return (
    <div
      className={cn(
        'flex flex-col gap-2 rounded-lg border border-l-4 border-slate-800 bg-slate-900/60 px-4 py-3 sm:flex-row sm:items-center sm:justify-between',
        borderClass,
        muted && 'opacity-60',
      )}
    >
      <div className={cn('flex min-w-0 flex-1 flex-col gap-1', dest && 'cursor-pointer')} onClick={() => dest && navigate(dest)}>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="maintenance">{window.scope_type === 'server' ? 'Servidor' : 'Sede'}</Badge>
          <span className="text-sm font-medium text-slate-100">{window.scope_label}</span>
          <span className="text-sm text-slate-400">— {window.reason}</span>
        </div>
        <p className="text-xs text-slate-500">
          {new Date(window.starts_at).toLocaleString()} → {new Date(window.ends_at).toLocaleString()}
          {window.created_by_name && ` · programada por ${window.created_by_name}`}
          {window.description && ` · ${window.description}`}
        </p>
      </div>

      <div className="flex shrink-0 items-center gap-2" onClick={(e) => e.stopPropagation()}>
        <span className="text-xs text-slate-500">
          {window.status === 'active' && `Termina ${timeUntil(window.ends_at)}`}
          {window.status === 'scheduled' && `Empieza ${timeUntil(window.starts_at)}`}
          {window.status === 'ended' && `Terminó ${timeAgo(window.ends_at)}`}
          {window.status === 'cancelled' && `Cancelada ${timeAgo(window.cancelled_at)}`}
        </span>
        {(window.status === 'active' || window.status === 'scheduled') && (
          <>
            <MaintenanceWindowFormDialog
              window={window}
              trigger={
                <Button size="sm" variant="outline">
                  Editar
                </Button>
              }
            />
            <Button size="sm" variant="outline" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
              {cancel.isPending ? 'Cancelando…' : 'Cancelar'}
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

function Section({ title, windows, borderClass, muted, emptyLabel }: {
  title: string
  windows: MaintenanceWindow[]
  borderClass: string
  muted?: boolean
  emptyLabel: string
}) {
  return (
    <div className="mb-6">
      <h3 className="mb-2 text-sm font-medium text-slate-300">
        {title} <span className="text-slate-500">({windows.length})</span>
      </h3>
      {windows.length === 0 ? (
        <p className="text-sm text-slate-500">{emptyLabel}</p>
      ) : (
        <div className="flex flex-col gap-2">
          {windows.map((w) => (
            <WindowCard key={w.id} window={w} borderClass={borderClass} muted={muted} />
          ))}
        </div>
      )}
    </div>
  )
}

export function MaintenancePage() {
  const { data: windows, isLoading, isError } = useQuery({
    queryKey: ['maintenance-windows'],
    queryFn: async () => (await api.get<MaintenanceWindow[]>('/maintenance-windows', { params: { limit: 200 } })).data,
    refetchInterval: 30000,
  })

  const active = (windows ?? []).filter((w) => w.status === 'active')
  const scheduled = (windows ?? [])
    .filter((w) => w.status === 'scheduled')
    .sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime())
  const finished = (windows ?? [])
    .filter((w) => w.status === 'ended' || w.status === 'cancelled')
    .slice(0, 20)

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-semibold text-slate-100">
            <Wrench className="h-5 w-5 text-violet-400" />
            Mantenimiento
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Programa ventanas para trabajos planificados — mientras están activas, se silencian las notificaciones (correo y
            campanita) del servidor o sede afectado, sin perder el historial de alertas.
          </p>
        </div>
        <MaintenanceWindowFormDialog
          trigger={
            <Button>
              <Plus className="h-4 w-4" />
              Programar mantenimiento
            </Button>
          }
        />
      </div>

      <Card className="mb-6">
        <CardContent className="flex flex-wrap items-center gap-6 py-5">
          <HexagonStat
            segments={[
              { value: active.length, color: '#a78bfa', label: 'Activas ahora' },
              { value: scheduled.length, color: '#38bdf8', label: 'Programadas' },
              { value: finished.length, color: '#64748b', label: 'Finalizadas recientes' },
            ]}
          />
          <HexagonLegend
            segments={[
              { value: active.length, color: '#a78bfa', label: 'Activas ahora' },
              { value: scheduled.length, color: '#38bdf8', label: 'Programadas' },
              { value: finished.length, color: '#64748b', label: 'Finalizadas recientes' },
            ]}
          />
        </CardContent>
      </Card>

      {isLoading && <TableSkeleton rows={4} cols={5} />}
      {isError && <ErrorMessage>No se pudo cargar las ventanas de mantenimiento.</ErrorMessage>}

      {windows && (
        <>
          <Section title="Activas" windows={active} borderClass="border-l-violet-400" emptyLabel="Ningún servidor o sede está en mantenimiento ahora mismo." />
          <Section title="Programadas" windows={scheduled} borderClass="border-l-slate-600" emptyLabel="No hay ventanas programadas a futuro." />
          <Section title="Finalizadas" windows={finished} borderClass="border-l-slate-800" muted emptyLabel="Sin historial reciente." />
        </>
      )}
    </div>
  )
}
