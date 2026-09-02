import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { AdminUser, AdminUserCreateInput, Role, Site } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { ErrorMessage } from '@/components/ui/error-message'

const NONE = '__none__'

interface FormState {
  dni: string
  email: string
  username: string
  full_name: string
  phone: string
  password: string
  site_ids: string[]
  role_id: string
  is_superuser: boolean
  is_active: boolean
}

const emptyForm: FormState = {
  dni: '',
  email: '',
  username: '',
  full_name: '',
  phone: '',
  password: '',
  site_ids: [],
  role_id: NONE,
  is_superuser: false,
  is_active: true,
}

export function UserFormDialog({ user, trigger }: { user?: AdminUser; trigger: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<FormState>(emptyForm)
  const [error, setError] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const isEdit = !!user

  const { data: sites } = useQuery({
    queryKey: ['sites'],
    queryFn: async () => (await api.get<Site[]>('/sites')).data,
    enabled: open,
  })
  const { data: roles } = useQuery({
    queryKey: ['roles'],
    queryFn: async () => (await api.get<Role[]>('/roles')).data,
    enabled: open,
  })

  useEffect(() => {
    if (!open) return
    setError(null)
    setForm(
      user
        ? {
            dni: user.dni,
            email: user.email ?? '',
            username: user.username,
            full_name: user.full_name,
            phone: user.phone ?? '',
            password: '',
            site_ids: user.site_ids,
            role_id: user.role_id ?? NONE,
            is_superuser: user.is_superuser,
            is_active: user.is_active,
          }
        : emptyForm,
    )
  }, [open, user])

  const mutation = useMutation({
    mutationFn: async () => {
      const role_id = form.role_id === NONE ? null : form.role_id
      if (isEdit) {
        return api.patch(`/users/${user!.id}`, {
          email: form.email || null,
          username: form.username,
          full_name: form.full_name,
          phone: form.phone || null,
          site_ids: form.site_ids,
          role_id,
          is_superuser: form.is_superuser,
          is_active: form.is_active,
        })
      }
      const payload: AdminUserCreateInput = {
        dni: form.dni,
        email: form.email || null,
        username: form.username,
        full_name: form.full_name,
        password: form.password,
        phone: form.phone || null,
        site_ids: form.site_ids,
        role_id,
        is_superuser: form.is_superuser,
        is_active: form.is_active,
      }
      return api.post('/users', payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setOpen(false)
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'No se pudo guardar el usuario.')
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
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Editar usuario' : 'Nuevo usuario'}</DialogTitle>
          <DialogDescription>Cuenta de acceso a CITI Platform.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto pr-1">
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="user-dni">DNI</Label>
              <Input
                id="user-dni"
                required
                disabled={isEdit}
                value={form.dni}
                onChange={(e) => setForm((f) => ({ ...f, dni: e.target.value }))}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="user-phone">Teléfono (opcional)</Label>
              <Input
                id="user-phone"
                value={form.phone}
                onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
              />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="user-fullname">Nombre completo</Label>
            <Input
              id="user-fullname"
              required
              value={form.full_name}
              onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="user-email">Correo institucional (opcional)</Label>
              <Input
                id="user-email"
                type="email"
                placeholder="El usuario puede completarlo después"
                value={form.email}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="user-username">Usuario</Label>
              <Input
                id="user-username"
                required
                value={form.username}
                onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
              />
            </div>
          </div>
          {!isEdit && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="user-password">Contraseña inicial</Label>
              <Input
                id="user-password"
                type="password"
                required
                minLength={8}
                value={form.password}
                onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
              />
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <Label>Perfil</Label>
            <Select value={form.role_id} onValueChange={(v) => setForm((f) => ({ ...f, role_id: v }))}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>Sin perfil</SelectItem>
                {(roles ?? []).map((r) => (
                  <SelectItem key={r.id} value={r.id}>
                    {r.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Sedes (una o más)</Label>
            <div className="flex max-h-40 flex-col gap-1.5 overflow-y-auto rounded-md border border-slate-700 bg-slate-900 p-3">
              {(sites ?? []).length === 0 && <p className="text-xs text-slate-500">Sin sedes registradas.</p>}
              {(sites ?? []).map((s) => (
                <label key={s.id} className="flex items-center gap-2 text-sm text-slate-200">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-slate-600 bg-slate-950 accent-amber-500"
                    checked={form.site_ids.includes(s.id)}
                    onChange={(e) =>
                      setForm((f) => ({
                        ...f,
                        site_ids: e.target.checked ? [...f.site_ids, s.id] : f.site_ids.filter((id) => id !== s.id),
                      }))
                    }
                  />
                  {s.name}
                </label>
              ))}
            </div>
            <p className="text-xs text-slate-500">Determina qué servidores puede ver y administrar este usuario.</p>
          </div>
          <div className="flex flex-col gap-2 rounded-md border border-slate-800 p-3">
            <label className="flex items-center gap-2 text-sm text-slate-200">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-amber-500"
                checked={form.is_active}
                onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
              />
              Acceso habilitado
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-200">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-amber-500"
                checked={form.is_superuser}
                onChange={(e) => setForm((f) => ({ ...f, is_superuser: e.target.checked }))}
              />
              Administrador del sistema (acceso total, ignora perfiles)
            </label>
          </div>
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
