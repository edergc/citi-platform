import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { AlertRule, AlertRuleInput, Server } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { ErrorMessage } from '@/components/ui/error-message'

const GLOBAL_SCOPE = '__global__'

const emptyForm: AlertRuleInput = {
  name: '',
  scope_type: 'server',
  scope_id: null,
  metric: 'ram_percent',
  metric_target: null,
  condition: 'gte',
  threshold: 90,
  severity: 'warning',
  custom_message: null,
  cooldown_minutes: 30,
  enabled: true,
}

const conditionLabel: Record<AlertRuleInput['condition'], string> = {
  gt: 'mayor que (>)',
  gte: 'mayor o igual que (≥)',
  lt: 'menor que (<)',
  lte: 'menor o igual que (≤)',
  eq: 'igual a (=)',
}

export function AlertRuleFormDialog({ rule, trigger }: { rule?: AlertRule; trigger: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<AlertRuleInput>(emptyForm)
  const [error, setError] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const isEdit = !!rule

  const { data: servers } = useQuery({
    queryKey: ['servers'],
    queryFn: async () => (await api.get<Server[]>('/servers')).data,
    enabled: open,
  })

  useEffect(() => {
    if (!open) return
    setError(null)
    setForm(
      rule
        ? {
            name: rule.name,
            scope_type: rule.scope_type,
            scope_id: rule.scope_id,
            metric: rule.metric,
            metric_target: rule.metric_target,
            condition: rule.condition,
            threshold: rule.threshold,
            severity: rule.severity,
            custom_message: rule.custom_message,
            cooldown_minutes: rule.cooldown_minutes,
            enabled: rule.enabled,
          }
        : emptyForm,
    )
  }, [open, rule])

  const mutation = useMutation({
    mutationFn: async () => {
      const payload = { ...form, custom_message: form.custom_message || null, metric_target: form.metric_target || null }
      if (isEdit) return api.patch(`/alert-rules/${rule!.id}`, payload)
      return api.post('/alert-rules', payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert-rules'] })
      setOpen(false)
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'No se pudo guardar la regla de alerta.')
    },
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    mutation.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Editar regla de alerta' : 'Nueva regla de alerta'}</DialogTitle>
          <DialogDescription>Define un umbral de CPU/RAM/disco y qué mensaje enviar cuando se supere.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rule-name">Nombre</Label>
            <Input
              id="rule-name"
              required
              placeholder="Ej: Disco D con poco espacio"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Alcance</Label>
            <Select
              value={form.scope_id ?? GLOBAL_SCOPE}
              onValueChange={(v) => setForm((f) => ({ ...f, scope_id: v === GLOBAL_SCOPE ? null : v }))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={GLOBAL_SCOPE}>Todos los servidores</SelectItem>
                {servers?.map((server) => (
                  <SelectItem key={server.id} value={server.id}>
                    {server.hostname}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label>Métrica</Label>
              <Select
                value={form.metric}
                onValueChange={(v) => {
                  const metric = v as AlertRuleInput['metric']
                  setForm((f) => ({
                    ...f,
                    metric,
                    metric_target: null,
                    // No es intuitivo pedirle a alguien "condición ≥ umbral" para algo
                    // binario como "¿se cae o no?" — se fija automáticamente para que
                    // el admin solo elija la severidad y el mensaje.
                    ...(metric === 'network_reachable' ? { condition: 'eq' as const, threshold: 0 } : {}),
                  }))
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ram_percent">RAM</SelectItem>
                  <SelectItem value="cpu_percent">CPU</SelectItem>
                  <SelectItem value="disk_percent_used">Disco</SelectItem>
                  <SelectItem value="network_reachable">Red: sin respuesta</SelectItem>
                  <SelectItem value="network_latency_ms">Red: latencia</SelectItem>
                  <SelectItem value="network_loss_percent">Red: pérdida al destino</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {form.metric === 'disk_percent_used' && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="rule-mount">Disco (vacío = el más lleno)</Label>
                <Input
                  id="rule-mount"
                  placeholder="Ej: D:\"
                  value={form.metric_target ?? ''}
                  onChange={(e) => setForm((f) => ({ ...f, metric_target: e.target.value }))}
                />
              </div>
            )}
          </div>

          {form.metric === 'network_reachable' ? (
            <p className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2 text-xs text-slate-400">
              Se activa cuando el último sondeo de red de este servidor no logra llegar a Core.
            </p>
          ) : (
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <Label>Condición</Label>
                <Select
                  value={form.condition}
                  onValueChange={(v) => setForm((f) => ({ ...f, condition: v as AlertRuleInput['condition'] }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(conditionLabel).map(([value, label]) => (
                      <SelectItem key={value} value={value}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="rule-threshold">Umbral {form.metric === 'network_latency_ms' ? '(ms)' : '(%)'}</Label>
                <Input
                  id="rule-threshold"
                  type="number"
                  step="0.1"
                  required
                  value={form.threshold}
                  onChange={(e) => setForm((f) => ({ ...f, threshold: Number(e.target.value) }))}
                />
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label>Severidad</Label>
              <Select
                value={form.severity}
                onValueChange={(v) => setForm((f) => ({ ...f, severity: v as AlertRuleInput['severity'] }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="info">Informativo</SelectItem>
                  <SelectItem value="warning">Advertencia</SelectItem>
                  <SelectItem value="critical">Crítico</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="rule-cooldown">Espera entre avisos (min)</Label>
              <Input
                id="rule-cooldown"
                type="number"
                min={1}
                required
                value={form.cooldown_minutes}
                onChange={(e) => setForm((f) => ({ ...f, cooldown_minutes: Number(e.target.value) }))}
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rule-message">Mensaje personalizado (opcional)</Label>
            <Textarea
              id="rule-message"
              placeholder="Ej: El disco {mount} de {hostname} está por llenarse ({value}% usado)."
              value={form.custom_message ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, custom_message: e.target.value }))}
            />
            <p className="text-xs text-slate-500">
              Puedes usar <code>{'{hostname}'}</code>, <code>{'{value}'}</code>, <code>{'{mount}'}</code> y{' '}
              <code>{'{threshold}'}</code>. Si lo dejas vacío, se usa un mensaje genérico.
            </p>
          </div>

          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
              className="h-4 w-4 rounded border-slate-700 bg-slate-900"
            />
            Regla activa
          </label>

          {error && <ErrorMessage>{error}</ErrorMessage>}
          <DialogFooter>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? 'Guardando…' : 'Guardar'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
