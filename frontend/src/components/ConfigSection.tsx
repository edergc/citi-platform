import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ConfigEntry, ConfigEntryHistoryEntry, Service } from '@/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ConfigEntryDialog } from '@/components/ConfigEntryDialog'

function ConfigEntryHistoryRow({ entryId }: { entryId: string }) {
  const { data: history } = useQuery({
    queryKey: ['config-entry-history', entryId],
    queryFn: async () => (await api.get<ConfigEntryHistoryEntry[]>(`/config-entries/${entryId}/history`)).data,
  })

  if (!history || history.length === 0) {
    return <p className="px-4 pb-2 text-xs text-slate-500">Sin cambios anteriores.</p>
  }

  return (
    <div className="px-4 pb-2">
      {history.map((h) => (
        <p key={h.id} className="text-xs text-slate-500">
          {new Date(h.changed_at).toLocaleString()} — valor anterior: <span className="font-mono">{h.previous_value ?? '—'}</span>
        </p>
      ))}
    </div>
  )
}

function ConfigEntryRow({ entry, serviceId }: { entry: ConfigEntry; serviceId: string }) {
  const [showHistory, setShowHistory] = useState(false)
  const queryClient = useQueryClient()

  const deleteMutation = useMutation({
    mutationFn: async () => api.delete(`/config-entries/${entry.id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['config-entries', serviceId] }),
  })

  return (
    <div className="border-b border-slate-800/60 last:border-0">
      <div className="flex items-center justify-between gap-4 py-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm text-slate-200">{entry.key}</span>
            {entry.is_secret && <Badge variant="warning">secreto</Badge>}
            <span className="text-xs text-slate-500">v{entry.version}</span>
          </div>
          <p className="truncate font-mono text-xs text-slate-400">{entry.value ?? '—'}</p>
          {entry.description && <p className="text-xs text-slate-500">{entry.description}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button variant="ghost" size="sm" onClick={() => setShowHistory((v) => !v)}>
            Historial
          </Button>
          <ConfigEntryDialog serviceId={serviceId} entry={entry} trigger={<Button variant="ghost" size="sm">Editar</Button>} />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              if (confirm(`¿Eliminar la variable "${entry.key}"?`)) deleteMutation.mutate()
            }}
          >
            Eliminar
          </Button>
        </div>
      </div>
      {showHistory && <ConfigEntryHistoryRow entryId={entry.id} />}
    </div>
  )
}

export function ConfigSection({ services }: { services: Service[] }) {
  return (
    <div>
      <h3 className="mb-4 text-base font-medium text-slate-200">Centro de Configuración</h3>
      <div className="flex flex-col gap-6">
        {services.map((service) => <ServiceConfigBlock key={service.id} service={service} />)}
      </div>
    </div>
  )
}

function ServiceConfigBlock({ service }: { service: Service }) {
  const { data: entries } = useQuery({
    queryKey: ['config-entries', service.id],
    queryFn: async () => (await api.get<ConfigEntry[]>('/config-entries', { params: { service_id: service.id } })).data,
  })

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <p className="text-sm font-medium text-slate-300">{service.name}</p>
        <ConfigEntryDialog
          serviceId={service.id}
          trigger={
            <Button variant="outline" size="sm">
              + Nueva variable
            </Button>
          }
        />
      </div>
      {entries && entries.length === 0 && <p className="text-xs text-slate-500">Sin variables configuradas.</p>}
      {entries && entries.length > 0 && (
        <div className="rounded-md border border-slate-800 px-4">
          {entries.map((entry) => (
            <ConfigEntryRow key={entry.id} entry={entry} serviceId={service.id} />
          ))}
        </div>
      )}
    </div>
  )
}
