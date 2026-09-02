import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { NotificationChannel, NotificationLogPage } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { StatusChip } from '@/components/ui/status-chip'
import { Pagination } from '@/components/ui/pagination'
import { NotificationChannelDialog } from '@/components/NotificationChannelDialog'

const LOGS_PAGE_SIZE = 20

function ChannelRow({ channel }: { channel: NotificationChannel }) {
  const queryClient = useQueryClient()
  const [testTo, setTestTo] = useState('')
  const [showLogs, setShowLogs] = useState(false)
  const [logsPage, setLogsPage] = useState(1)

  const { data: logs } = useQuery({
    queryKey: ['notification-logs', channel.id, logsPage],
    queryFn: async () =>
      (
        await api.get<NotificationLogPage>(`/notification-channels/${channel.id}/logs`, {
          params: { limit: LOGS_PAGE_SIZE, offset: (logsPage - 1) * LOGS_PAGE_SIZE },
        })
      ).data,
    enabled: showLogs,
  })

  const totalPages = Math.max(1, Math.ceil((logs?.total ?? 0) / LOGS_PAGE_SIZE))

  const testMutation = useMutation({
    mutationFn: async () => api.post(`/notification-channels/${channel.id}/test`, { to: testTo }),
    onSuccess: () => {
      setLogsPage(1)
      queryClient.invalidateQueries({ queryKey: ['notification-logs', channel.id] })
      setShowLogs(true)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async () => api.delete(`/notification-channels/${channel.id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notification-channels'] }),
  })

  return (
    <div className="rounded-md border border-slate-800 p-4">
      <div className="flex items-center justify-between">
        <div>
          <span className="text-sm text-slate-100">{channel.name}</span>
          <Badge className="ml-2" variant="info">
            {channel.type}
          </Badge>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            if (confirm(`¿Eliminar el canal "${channel.name}"?`)) deleteMutation.mutate()
          }}
        >
          Eliminar
        </Button>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <Input
          placeholder={channel.type === 'email' ? 'destinatario@pj.gob.pe' : 'destinatario (chat id / número)'}
          value={testTo}
          onChange={(e) => setTestTo(e.target.value)}
          className="max-w-xs"
        />
        <Button size="sm" disabled={!testTo || testMutation.isPending} onClick={() => testMutation.mutate()}>
          {testMutation.isPending ? 'Enviando…' : 'Enviar prueba'}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setShowLogs((v) => !v)}>
          Historial{logs && logs.total > 0 ? ` (${logs.total})` : ''}
        </Button>
      </div>
      {showLogs && logs && logs.items.length > 0 && (
        <>
          <div className="mt-3 flex flex-col gap-1">
            {logs.items.map((log) => (
              <p key={log.id} className="flex items-center gap-1.5 text-xs text-slate-500">
                {new Date(log.sent_at).toLocaleString()}
                <StatusChip tone={log.status === 'sent' ? 'ok' : 'critical'}>{log.status.toUpperCase()}</StatusChip>
                {log.error_message && `— ${log.error_message}`}
              </p>
            ))}
          </div>
          {totalPages > 1 && (
            <div className="mt-3">
              <Pagination page={logsPage} totalPages={totalPages} onPageChange={setLogsPage} />
            </div>
          )}
        </>
      )}
      {showLogs && logs && logs.items.length === 0 && (
        <p className="mt-3 text-xs text-slate-500">Sin envíos registrados todavía.</p>
      )}
    </div>
  )
}

export function NotificationsPage() {
  const { data: channels } = useQuery({
    queryKey: ['notification-channels'],
    queryFn: async () => (await api.get<NotificationChannel[]>('/notification-channels')).data,
  })

  const weeklyReportMutation = useMutation({
    mutationFn: async () => api.post('/notification-channels/weekly-report/trigger'),
  })

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-base font-medium text-slate-200">Notificaciones</h2>
        <NotificationChannelDialog trigger={<Button size="sm">+ Nuevo canal</Button>} />
      </div>

      <div className="mb-6 flex items-center justify-between rounded-md border border-slate-800 p-4">
        <div>
          <p className="text-sm text-slate-100">Reporte semanal</p>
          <p className="text-xs text-slate-500">
            Se envía solo cada lunes 08:00 (hora de Lima). Usa este botón para probarlo sin esperar.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {weeklyReportMutation.isSuccess && <span className="text-xs text-emerald-400">Enviado</span>}
          {weeklyReportMutation.isError && <span className="text-xs text-red-400">Falló el envío</span>}
          <Button
            variant="outline"
            size="sm"
            disabled={weeklyReportMutation.isPending}
            onClick={() => weeklyReportMutation.mutate()}
          >
            {weeklyReportMutation.isPending ? 'Enviando…' : 'Enviar ahora'}
          </Button>
        </div>
      </div>

      {channels && channels.length === 0 && <p className="text-sm text-slate-500">Sin canales configurados.</p>}

      <div className="flex flex-col gap-4">
        {channels?.map((channel) => (
          <ChannelRow key={channel.id} channel={channel} />
        ))}
      </div>
    </div>
  )
}
