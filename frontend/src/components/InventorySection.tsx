import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { api } from '@/lib/api'
import type { Dependency, DependencyType, License } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ErrorMessage } from '@/components/ui/error-message'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'

function NewLicenseDialog({ systemId }: { systemId: string }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ name: '', vendor: '', expiry_date: '', seats: '', cost: '', notes: '' })
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: async () =>
      api.post('/licenses', {
        name: form.name,
        vendor: form.vendor || null,
        system_id: systemId,
        server_id: null,
        expiry_date: form.expiry_date || null,
        seats: form.seats ? Number(form.seats) : null,
        cost: form.cost ? Number(form.cost) : null,
        notes: form.notes || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['licenses', systemId] })
      setOpen(false)
      setForm({ name: '', vendor: '', expiry_date: '', seats: '', cost: '', notes: '' })
    },
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          + Licencia
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nueva licencia</DialogTitle>
          <DialogDescription>Software, sistema operativo u otro activo licenciado.</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e: FormEvent) => {
            e.preventDefault()
            mutation.mutate()
          }}
          className="flex flex-col gap-4"
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="lic-name">Nombre</Label>
            <Input id="lic-name" required value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="lic-vendor">Proveedor</Label>
              <Input id="lic-vendor" value={form.vendor} onChange={(e) => setForm((f) => ({ ...f, vendor: e.target.value }))} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="lic-expiry">Vencimiento</Label>
              <Input
                id="lic-expiry"
                type="date"
                value={form.expiry_date}
                onChange={(e) => setForm((f) => ({ ...f, expiry_date: e.target.value }))}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="lic-seats">Asientos</Label>
              <Input id="lic-seats" type="number" value={form.seats} onChange={(e) => setForm((f) => ({ ...f, seats: e.target.value }))} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="lic-cost">Costo</Label>
              <Input id="lic-cost" type="number" value={form.cost} onChange={(e) => setForm((f) => ({ ...f, cost: e.target.value }))} />
            </div>
          </div>
          {mutation.isError && <ErrorMessage>No se pudo guardar la licencia.</ErrorMessage>}
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

function NewDependencyDialog({ systemId }: { systemId: string }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<{ name: string; type: DependencyType; version: string; criticality: string }>({
    name: '',
    type: 'library',
    version: '',
    criticality: '',
  })
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: async () =>
      api.post('/dependencies', {
        system_id: systemId,
        name: form.name,
        type: form.type,
        version: form.version || null,
        criticality: form.criticality || null,
        notes: null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dependencies', systemId] })
      setOpen(false)
      setForm({ name: '', type: 'library', version: '', criticality: '' })
    },
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          + Dependencia
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nueva dependencia</DialogTitle>
          <DialogDescription>Librería, servicio o API externa de la que depende el sistema.</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e: FormEvent) => {
            e.preventDefault()
            mutation.mutate()
          }}
          className="flex flex-col gap-4"
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="dep-name">Nombre</Label>
            <Input id="dep-name" required value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label>Tipo</Label>
              <Select value={form.type} onValueChange={(v) => setForm((f) => ({ ...f, type: v as DependencyType }))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="library">Librería</SelectItem>
                  <SelectItem value="service">Servicio</SelectItem>
                  <SelectItem value="external_api">API externa</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="dep-version">Versión</Label>
              <Input id="dep-version" value={form.version} onChange={(e) => setForm((f) => ({ ...f, version: e.target.value }))} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="dep-criticality">Criticidad</Label>
              <Input
                id="dep-criticality"
                placeholder="alta/media/baja"
                value={form.criticality}
                onChange={(e) => setForm((f) => ({ ...f, criticality: e.target.value }))}
              />
            </div>
          </div>
          {mutation.isError && <ErrorMessage>No se pudo guardar la dependencia.</ErrorMessage>}
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

export function InventorySection({ systemId }: { systemId: string }) {
  const queryClient = useQueryClient()

  const { data: licenses } = useQuery({
    queryKey: ['licenses', systemId],
    queryFn: async () => (await api.get<License[]>('/licenses', { params: { system_id: systemId } })).data,
  })
  const { data: dependencies } = useQuery({
    queryKey: ['dependencies', systemId],
    queryFn: async () => (await api.get<Dependency[]>('/dependencies', { params: { system_id: systemId } })).data,
  })

  const deleteLicense = useMutation({
    mutationFn: async (id: string) => api.delete(`/licenses/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['licenses', systemId] }),
  })
  const deleteDependency = useMutation({
    mutationFn: async (id: string) => api.delete(`/dependencies/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dependencies', systemId] }),
  })

  return (
    <div>
      <h3 className="mb-4 text-base font-medium text-slate-200">Inventario Tecnológico</h3>

      <div className="mb-6">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-sm font-medium text-slate-300">Licencias</p>
          <NewLicenseDialog systemId={systemId} />
        </div>
        {licenses && licenses.length === 0 && <p className="text-xs text-slate-500">Sin licencias registradas.</p>}
        {licenses && licenses.length > 0 && (
          <div className="flex flex-col gap-2">
            {licenses.map((lic) => (
              <div key={lic.id} className="flex items-center justify-between rounded-md border border-slate-800 px-4 py-2 text-sm">
                <div>
                  <span className="text-slate-100">{lic.name}</span>
                  <span className="ml-2 text-xs text-slate-500">
                    {lic.vendor} {lic.expiry_date && `· vence ${lic.expiry_date}`}
                  </span>
                </div>
                <Button variant="ghost" size="sm" onClick={() => deleteLicense.mutate(lic.id)}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <p className="text-sm font-medium text-slate-300">Dependencias</p>
          <NewDependencyDialog systemId={systemId} />
        </div>
        {dependencies && dependencies.length === 0 && <p className="text-xs text-slate-500">Sin dependencias registradas.</p>}
        {dependencies && dependencies.length > 0 && (
          <div className="flex flex-col gap-2">
            {dependencies.map((dep) => (
              <div key={dep.id} className="flex items-center justify-between rounded-md border border-slate-800 px-4 py-2 text-sm">
                <div>
                  <span className="text-slate-100">{dep.name}</span>
                  <span className="ml-2 text-xs text-slate-500">
                    {dep.type} {dep.version && `· v${dep.version}`} {dep.criticality && `· ${dep.criticality}`}
                  </span>
                </div>
                <Button variant="ghost" size="sm" onClick={() => deleteDependency.mutate(dep.id)}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
