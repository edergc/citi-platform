import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, Play, RotateCw, Square } from 'lucide-react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import type { ServiceAction, ServiceActionLog } from '@/types'

const actionLabels: Record<ServiceAction, string> = {
  start: 'Iniciar',
  stop: 'Detener',
  restart: 'Reiniciar',
  force_restart: 'Reinicio forzado',
}

export function ServiceActions({ serviceId }: { serviceId: string }) {
  const [lastLog, setLastLog] = useState<ServiceActionLog | null>(null)
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: async (action: ServiceAction) =>
      (await api.post<ServiceActionLog>(`/services/${serviceId}/actions`, { action })).data,
    onSuccess: (data) => {
      setLastLog(data)
      queryClient.invalidateQueries({ queryKey: ['services'] })
    },
  })

  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          title="Iniciar"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate('start')}
        >
          <Play className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          title="Detener"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate('stop')}
        >
          <Square className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          title="Reiniciar"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate('restart')}
        >
          <RotateCw className="h-3.5 w-3.5" />
        </Button>
      </div>

      {mutation.isPending && (
        <span className="flex items-center gap-1 text-xs text-sky-400">
          <Loader2 className="h-3 w-3 animate-spin" />
          Ejecutando {actionLabels[mutation.variables as ServiceAction].toLowerCase()}… (hasta 20s)
        </span>
      )}

      {!mutation.isPending && lastLog && (
        <span
          className={
            'text-xs ' +
            (lastLog.status === 'success'
              ? 'text-emerald-400'
              : lastLog.status === 'failed'
                ? 'text-red-400'
                : 'text-slate-500')
          }
        >
          {actionLabels[lastLog.action]}:{' '}
          {lastLog.status === 'success' && 'completado'}
          {lastLog.status === 'failed' && `falló${lastLog.output ? ` — ${lastLog.output}` : ''}`}
          {lastLog.status === 'pending' && 'pendiente del Agente CITI'}
        </span>
      )}
    </div>
  )
}
