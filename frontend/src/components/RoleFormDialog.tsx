import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Permission, Role, RoleInput } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { ErrorMessage } from '@/components/ui/error-message'

const emptyForm: RoleInput = { name: '', description: '', permission_codes: [] }

export function RoleFormDialog({ role, trigger }: { role?: Role; trigger: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<RoleInput>(emptyForm)
  const [error, setError] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const isEdit = !!role
  const locked = !!role?.is_system_role

  const { data: permissions } = useQuery({
    queryKey: ['permissions'],
    queryFn: async () => (await api.get<Permission[]>('/permissions')).data,
    enabled: open,
  })

  useEffect(() => {
    if (!open) return
    setError(null)
    setForm(
      role
        ? { name: role.name, description: role.description ?? '', permission_codes: [...role.permission_codes] }
        : emptyForm,
    )
  }, [open, role])

  const mutation = useMutation({
    mutationFn: async () => {
      const payload = { ...form, description: form.description || null }
      if (isEdit) return api.patch(`/roles/${role!.id}`, payload)
      return api.post('/roles', payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['roles'] })
      setOpen(false)
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'No se pudo guardar el perfil.')
    },
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    mutation.mutate()
  }

  function togglePermission(code: string) {
    setForm((f) => ({
      ...f,
      permission_codes: f.permission_codes.includes(code)
        ? f.permission_codes.filter((c) => c !== code)
        : [...f.permission_codes, code],
    }))
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Editar perfil' : 'Nuevo perfil'}</DialogTitle>
          <DialogDescription>Define qué privilegios otorga este perfil.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="role-name">Nombre</Label>
            <Input
              id="role-name"
              required
              disabled={locked}
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="role-desc">Descripción (opcional)</Label>
            <Input
              id="role-desc"
              value={form.description ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Privilegios</Label>
            {locked ? (
              <p className="text-sm text-slate-400">
                El perfil Administrador tiene todos los privilegios y no puede modificarse.
              </p>
            ) : (
              <div className="max-h-64 overflow-y-auto rounded-md border border-slate-800 p-3">
                {(permissions ?? []).map((perm) => (
                  <label key={perm.code} className="flex items-center gap-2 py-1 text-sm text-slate-200">
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-amber-500"
                      checked={form.permission_codes.includes(perm.code)}
                      onChange={() => togglePermission(perm.code)}
                    />
                    <span>{perm.description ?? perm.code}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
          {error && <ErrorMessage>{error}</ErrorMessage>}
          <DialogFooter>
            <Button type="submit" disabled={mutation.isPending || locked}>
              {mutation.isPending ? 'Guardando…' : 'Guardar'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
