import { useState, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { NotificationChannelType } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { ErrorMessage } from '@/components/ui/error-message'

const configFieldsByType: Record<NotificationChannelType, { key: string; label: string; type?: string }[]> = {
  email: [
    { key: 'smtp_host', label: 'Host SMTP' },
    { key: 'smtp_port', label: 'Puerto', type: 'number' },
    { key: 'smtp_user', label: 'Usuario (opcional)' },
    { key: 'smtp_password', label: 'Contraseña (opcional)', type: 'password' },
    { key: 'from_address', label: 'Dirección remitente' },
    { key: 'from_name', label: 'Nombre remitente (opcional)' },
  ],
  telegram: [
    { key: 'bot_token', label: 'Bot Token', type: 'password' },
    { key: 'chat_id', label: 'Chat ID por defecto (opcional)' },
  ],
  teams: [{ key: 'webhook_url', label: 'Webhook URL' }],
  whatsapp: [
    { key: 'api_url', label: 'API URL' },
    { key: 'token', label: 'Token', type: 'password' },
  ],
}

export function NotificationChannelDialog({ trigger }: { trigger: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [type, setType] = useState<NotificationChannelType>('email')
  const [config, setConfig] = useState<Record<string, string>>({})
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: async () => api.post('/notification-channels', { name, type, config, enabled: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notification-channels'] })
      setOpen(false)
      setName('')
      setConfig({})
    },
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    mutation.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuevo canal de notificación</DialogTitle>
          <DialogDescription>La configuración se guarda cifrada.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="channel-name">Nombre</Label>
            <Input id="channel-name" required value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Tipo</Label>
            <Select
              value={type}
              onValueChange={(v) => {
                setType(v as NotificationChannelType)
                setConfig({})
              }}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="email">Email</SelectItem>
                <SelectItem value="telegram">Telegram</SelectItem>
                <SelectItem value="teams">Microsoft Teams</SelectItem>
                <SelectItem value="whatsapp">WhatsApp</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {configFieldsByType[type].map((field) => (
            <div key={field.key} className="flex flex-col gap-1.5">
              <Label htmlFor={field.key}>{field.label}</Label>
              <Input
                id={field.key}
                type={field.type ?? 'text'}
                value={config[field.key] ?? ''}
                onChange={(e) => setConfig((c) => ({ ...c, [field.key]: e.target.value }))}
              />
            </div>
          ))}
          {mutation.isError && <ErrorMessage>No se pudo crear el canal.</ErrorMessage>}
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
