import { AlertTriangle, Bell, CheckCheck, Info, XCircle } from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { InAppNotification, NotificationSeverity } from '@/types'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'

const severityMeta: Record<NotificationSeverity, { icon: typeof Info; className: string }> = {
  critical: { icon: XCircle, className: 'text-red-400' },
  warning: { icon: AlertTriangle, className: 'text-amber-400' },
  info: { icon: Info, className: 'text-sky-400' },
}

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const minutes = Math.floor(diffMs / 60_000)
  if (minutes < 1) return 'ahora'
  if (minutes < 60) return `hace ${minutes} min`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `hace ${hours} h`
  const days = Math.floor(hours / 24)
  return `hace ${days} d`
}

export function NotificationBell() {
  const queryClient = useQueryClient()

  const { data: unreadCount } = useQuery({
    queryKey: ['notifications-unread-count'],
    queryFn: async () => (await api.get<{ count: number }>('/in-app-notifications/unread-count')).data.count,
    refetchInterval: 30_000,
  })

  const { data: notifications } = useQuery({
    queryKey: ['notifications-list'],
    queryFn: async () => (await api.get<InAppNotification[]>('/in-app-notifications', { params: { limit: 20 } })).data,
    refetchInterval: 30_000,
  })

  const markRead = useMutation({
    mutationFn: async (id: string) => api.post(`/in-app-notifications/${id}/read`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications-unread-count'] })
      queryClient.invalidateQueries({ queryKey: ['notifications-list'] })
    },
  })

  const markAllRead = useMutation({
    mutationFn: async () => api.post('/in-app-notifications/read-all'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications-unread-count'] })
      queryClient.invalidateQueries({ queryKey: ['notifications-list'] })
    },
  })

  const hasUnread = (unreadCount ?? 0) > 0

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="relative flex h-8 w-8 items-center justify-center rounded-md text-slate-300 transition-colors hover:bg-slate-800 hover:text-slate-100">
          <Bell className="h-4.5 w-4.5" />
          {hasUnread && (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold text-white">
              {(unreadCount ?? 0) > 9 ? '9+' : unreadCount}
            </span>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-96 max-h-[28rem] overflow-y-auto p-0">
        <div className="flex items-center justify-between px-3 py-2.5">
          <DropdownMenuLabel className="px-0 py-0 text-sm font-medium text-slate-200">Notificaciones</DropdownMenuLabel>
          {hasUnread && (
            <button
              onClick={() => markAllRead.mutate()}
              className="flex items-center gap-1 text-xs text-amber-400 hover:text-amber-300"
            >
              <CheckCheck className="h-3.5 w-3.5" />
              Marcar todas leídas
            </button>
          )}
        </div>
        <DropdownMenuSeparator className="my-0" />
        {(!notifications || notifications.length === 0) && (
          <p className="px-3 py-6 text-center text-sm text-slate-500">Sin notificaciones</p>
        )}
        {notifications?.map((n) => {
          const meta = severityMeta[n.severity]
          const Icon = meta.icon
          const isUnread = !n.read_at
          return (
            <DropdownMenuItem
              key={n.id}
              onSelect={(e) => {
                e.preventDefault()
                if (isUnread) markRead.mutate(n.id)
              }}
              className={cn('flex-col items-start gap-1 whitespace-normal py-2.5', isUnread && 'bg-slate-800/40')}
            >
              <div className="flex w-full items-start gap-2">
                <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', meta.className)} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-100">{n.title}</p>
                  <p className="mt-0.5 text-xs text-slate-400">{n.message}</p>
                  <p className="mt-1 text-[11px] text-slate-500">{timeAgo(n.created_at)}</p>
                </div>
                {isUnread && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-amber-500" />}
              </div>
            </DropdownMenuItem>
          )
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
