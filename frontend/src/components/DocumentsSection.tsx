import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Trash2 } from 'lucide-react'
import { api } from '@/lib/api'
import type { DocumentEntry, DocumentType } from '@/types'
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

const docTypeLabels: Record<DocumentType, string> = {
  manual_tecnico: 'Manual técnico',
  manual_usuario: 'Manual de usuario',
  arquitectura: 'Arquitectura',
  diagrama: 'Diagrama',
  script: 'Script',
  pdf: 'PDF',
  imagen: 'Imagen',
  video: 'Video',
  procedimiento: 'Procedimiento',
}

function UploadDocumentDialog({ systemId }: { systemId: string }) {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [docType, setDocType] = useState<DocumentType>('manual_tecnico')
  const [version, setVersion] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error('no file')
      const formData = new FormData()
      formData.append('title', title)
      formData.append('doc_type', docType)
      if (version) formData.append('version', version)
      formData.append('file', file)
      return api.post(`/systems/${systemId}/documents`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents', systemId] })
      setOpen(false)
      setTitle('')
      setVersion('')
      setFile(null)
    },
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    mutation.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">+ Subir documento</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Subir documento</DialogTitle>
          <DialogDescription>Manuales, diagramas, procedimientos u otro material técnico del sistema.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="doc-title">Título</Label>
            <Input id="doc-title" required value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label>Tipo</Label>
              <Select value={docType} onValueChange={(v) => setDocType(v as DocumentType)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(docTypeLabels).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="doc-version">Versión</Label>
              <Input id="doc-version" value={version} onChange={(e) => setVersion(e.target.value)} />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="doc-file">Archivo</Label>
            <input
              id="doc-file"
              type="file"
              required
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="text-sm text-slate-300 file:mr-3 file:rounded-md file:border-0 file:bg-slate-800 file:px-3 file:py-1.5 file:text-sm file:text-slate-200"
            />
          </div>
          {mutation.isError && <ErrorMessage>No se pudo subir el documento.</ErrorMessage>}
          <DialogFooter>
            <Button type="submit" disabled={mutation.isPending || !file}>
              {mutation.isPending ? 'Subiendo…' : 'Subir'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function DocumentsSection({ systemId }: { systemId: string }) {
  const queryClient = useQueryClient()

  const { data: documents } = useQuery({
    queryKey: ['documents', systemId],
    queryFn: async () => (await api.get<DocumentEntry[]>(`/systems/${systemId}/documents`)).data,
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => api.delete(`/documents/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['documents', systemId] }),
  })

  async function handleDownload(doc: DocumentEntry) {
    const response = await api.get(`/documents/${doc.id}/download`, { responseType: 'blob' })
    const url = URL.createObjectURL(response.data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = doc.title
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-base font-medium text-slate-200">Gestión Documental</h3>
        <UploadDocumentDialog systemId={systemId} />
      </div>

      {documents && documents.length === 0 && <p className="text-xs text-slate-500">Sin documentos.</p>}

      {documents && documents.length > 0 && (
        <div className="flex flex-col gap-2">
          {documents.map((doc) => (
            <div
              key={doc.id}
              className="flex items-center justify-between rounded-md border border-slate-800 px-4 py-2 text-sm"
            >
              <div>
                <span className="text-slate-100">{doc.title}</span>
                <span className="ml-2 text-xs text-slate-500">
                  {docTypeLabels[doc.doc_type]}
                  {doc.version && ` · v${doc.version}`}
                </span>
              </div>
              <div className="flex items-center gap-1">
                <Button variant="ghost" size="sm" onClick={() => handleDownload(doc)}>
                  <Download className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    if (confirm(`¿Eliminar "${doc.title}"?`)) deleteMutation.mutate(doc.id)
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
