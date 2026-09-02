import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { AlertEvent, CriticalConnectivityAlert } from '@/types'

export interface UnifiedCriticalAlert {
  id: string
  kind: 'threshold' | 'connectivity'
  title: string
  subtitle: string
  occurredAt: string
  serverId: string | null
}

// Shared by CriticalAlertBanner and CriticalAlertModal so both read from the same two
// cached queries instead of firing everything twice, and so "acknowledge" behaves
// identically everywhere it appears. Merges two otherwise-separate alert pipelines into
// one list: threshold breaches (AlertRule/AlertEvent, has an explicit
// open/acknowledged/resolved lifecycle) and server connectivity criticals
// (InAppNotification — see list_active_connectivity_alerts in the backend for why
// "currently offline + unread" stands in for "open" there, since that model has no
// resolved/acknowledged concept of its own).
export function useCriticalAlerts() {
  const queryClient = useQueryClient()

  const { data: thresholdEvents } = useQuery({
    queryKey: ['alert-rules', 'events', 'critical-banner'],
    queryFn: async () =>
      (
        await api.get<AlertEvent[]>('/alert-rules/events', {
          params: { status_filter: 'open', severity_filter: 'critical', limit: 300 },
        })
      ).data,
    refetchInterval: 30000,
  })

  const { data: connectivityAlerts } = useQuery({
    queryKey: ['servers', 'critical-connectivity-alerts'],
    queryFn: async () => (await api.get<CriticalConnectivityAlert[]>('/servers/critical-connectivity-alerts')).data,
    refetchInterval: 30000,
  })

  const unacknowledgedThresholds = (thresholdEvents ?? []).filter((e) => !e.acknowledged_at)

  const items: UnifiedCriticalAlert[] = [
    ...unacknowledgedThresholds.map(
      (e): UnifiedCriticalAlert => ({
        id: e.id,
        kind: 'threshold',
        title: e.rule_name,
        subtitle: [e.hostname, e.site_name].filter(Boolean).join(' · ') || 'Regla global',
        occurredAt: e.triggered_at,
        serverId: e.server_id,
      }),
    ),
    ...(connectivityAlerts ?? []).map(
      (a): UnifiedCriticalAlert => ({
        id: a.id,
        kind: 'connectivity',
        title: `Servidor desconectado: ${a.hostname}`,
        subtitle: a.site_name ?? '',
        occurredAt: a.occurred_at,
        serverId: a.server_id,
      }),
    ),
  ].sort((a, b) => new Date(b.occurredAt).getTime() - new Date(a.occurredAt).getTime())

  function invalidateAll() {
    queryClient.invalidateQueries({ queryKey: ['alert-rules', 'events'] })
    queryClient.invalidateQueries({ queryKey: ['servers', 'critical-connectivity-alerts'] })
    queryClient.invalidateQueries({ queryKey: ['in-app-notifications'] })
  }

  function acknowledgeRequest(item: Pick<UnifiedCriticalAlert, 'id' | 'kind'>) {
    return item.kind === 'threshold'
      ? api.post(`/alert-rules/events/${item.id}/acknowledge`)
      : api.post(`/in-app-notifications/${item.id}/read`)
  }

  const acknowledgeOne = useMutation({
    mutationFn: acknowledgeRequest,
    onSuccess: invalidateAll,
  })

  const acknowledgeAll = useMutation({
    mutationFn: (targets: UnifiedCriticalAlert[]) => Promise.all(targets.map(acknowledgeRequest)),
    onSuccess: invalidateAll,
  })

  return {
    items,
    acknowledgeOne,
    acknowledgeAll,
    isAcknowledging: acknowledgeOne.isPending || acknowledgeAll.isPending,
  }
}
