import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Scale } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorMessage } from '@/components/ui/error-message'
import { api } from '@/lib/api'

export function ForgotPasswordPage() {
  const [dni, setDni] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const { data } = await api.post<{ message: string }>('/auth/forgot-password', { dni })
      setMessage(data.message)
    } catch {
      setError('No se pudo procesar la solicitud. Intenta nuevamente.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-2 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full border border-amber-500/40 bg-red-950/40">
            <Scale className="h-6 w-6 text-amber-500" />
          </div>
          <p className="text-xs font-medium uppercase tracking-widest text-slate-400">
            Poder Judicial del Perú — Corte Superior de Justicia de Lima
          </p>
          <h1 className="text-xl font-bold text-slate-100">CITI Platform</h1>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Restablecer contraseña</CardTitle>
            <CardDescription>Ingresa tu DNI y te enviaremos un enlace a tu correo institucional</CardDescription>
          </CardHeader>
          <CardContent>
            {message ? (
              <p className="text-sm text-emerald-400">{message}</p>
            ) : (
              <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="dni">DNI</Label>
                  <Input
                    id="dni"
                    type="text"
                    inputMode="numeric"
                    autoComplete="username"
                    value={dni}
                    onChange={(e) => setDni(e.target.value)}
                    required
                  />
                </div>
                {error && <ErrorMessage>{error}</ErrorMessage>}
                <Button
                  type="submit"
                  disabled={submitting}
                  className="mt-2 bg-red-800 text-white hover:bg-red-700 focus-visible:ring-amber-500"
                >
                  {submitting ? 'Enviando…' : 'Enviar enlace de restablecimiento'}
                </Button>
              </form>
            )}
          </CardContent>
        </Card>

        <div className="mt-6 text-center">
          <Link
            to="/login"
            className="inline-flex items-center gap-1.5 text-sm text-slate-400 transition-colors hover:text-slate-200"
          >
            <ArrowLeft className="h-4 w-4" />
            Volver al inicio de sesión
          </Link>
        </div>
      </div>
    </div>
  )
}
