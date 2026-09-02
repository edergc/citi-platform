import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Activity, Scale } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorMessage } from '@/components/ui/error-message'
import { useAuth } from '@/lib/auth'
import loginBuilding from '@/assets/login-building.jpg'

const SESSION_END_MESSAGES: Record<string, string> = {
  expired: 'Tu sesión expiró. Por favor, inicia sesión nuevamente.',
  inactivity: 'Tu sesión se cerró por inactividad (5 horas sin actividad). Por favor, inicia sesión nuevamente.',
}

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const sessionEndReason = searchParams.get('reason')
  const [dni, setDni] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(dni, password)
      navigate('/', { replace: true })
    } catch {
      setError('DNI o contraseña incorrectos')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-slate-950 lg:flex-row">
      {/* Institutional panel */}
      <div className="relative flex h-48 shrink-0 flex-col justify-end overflow-hidden p-6 sm:h-64 lg:h-auto lg:w-1/2 lg:flex-1 lg:justify-between lg:p-12">
        <div
          className="animate-kenburns absolute inset-0 bg-cover bg-top"
          style={{ backgroundImage: `url(${loginBuilding})` }}
        />
        {/* Institutional red tint over the photo, lighter near the sky, solid where text sits */}
        <div className="absolute inset-0 bg-gradient-to-b from-red-950/50 via-red-950/75 to-red-950/95 lg:from-red-950/55 lg:via-red-950/70 lg:to-red-950/95" />
        <div
          className="pointer-events-none absolute inset-0 opacity-20"
          style={{
            backgroundImage:
              'radial-gradient(circle at 20% 20%, rgba(251,191,36,0.25), transparent 40%), radial-gradient(circle at 80% 70%, rgba(251,191,36,0.15), transparent 45%)',
          }}
        />

        <div className="relative z-10 hidden items-center gap-3 lg:flex">
          <div className="flex h-12 w-12 items-center justify-center rounded-full border border-amber-400/40 bg-red-950/50 backdrop-blur-sm">
            <Scale className="h-6 w-6 text-amber-400" />
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-widest text-amber-400/90">Poder Judicial del Perú</p>
            <p className="text-base font-semibold text-white">Corte Superior de Justicia de Lima</p>
          </div>
        </div>

        <div className="relative z-10 flex items-center gap-3 lg:hidden">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-amber-400/40 bg-red-950/50 backdrop-blur-sm">
            <Scale className="h-5 w-5 text-amber-400" />
          </div>
          <div>
            <p className="text-[11px] font-medium uppercase tracking-widest text-amber-400/90">
              Poder Judicial del Perú
            </p>
            <h1 className="text-lg font-bold leading-tight text-white">CITI Platform</h1>
          </div>
        </div>

        <div className="relative z-10 mt-6 hidden max-w-md space-y-4 lg:block">
          <p className="text-xs font-medium uppercase tracking-widest text-amber-400/80">
            Coordinación de Informática
          </p>
          <h1 className="text-5xl font-bold tracking-tight text-white text-shadow-lg">CITI Platform</h1>
          <p className="max-w-sm text-lg leading-relaxed text-red-50/85">
            Centro Inteligente de Tecnologías de la Información. Plataforma de administración y monitoreo de los
            sistemas institucionales.
          </p>
        </div>

        <p className="relative z-10 mt-8 hidden text-xs text-red-200/60 lg:block">
          © {new Date().getFullYear()} Coordinación de Informática — Corte Superior de Justicia de Lima
        </p>
      </div>

      {/* Login form */}
      <div className="relative flex flex-1 items-center justify-center px-4 py-10 lg:py-12">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.15]"
          style={{
            backgroundImage: 'radial-gradient(circle at 50% 0%, rgba(251,191,36,0.2), transparent 55%)',
          }}
        />
        <div className="relative w-full max-w-sm">
          {sessionEndReason && SESSION_END_MESSAGES[sessionEndReason] && (
            <div className="mb-4 rounded-md border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-400">
              {SESSION_END_MESSAGES[sessionEndReason]}
            </div>
          )}

          <Card className="border-t-2 border-t-amber-500/60 shadow-xl shadow-black/30">
            <CardHeader>
              <CardTitle>Iniciar sesión</CardTitle>
              <CardDescription>Ingresa con tu DNI y contraseña institucional</CardDescription>
            </CardHeader>
            <CardContent>
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
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="password">Contraseña</Label>
                    <Link to="/forgot-password" className="text-xs text-amber-500 hover:text-amber-400">
                      ¿Olvidaste tu contraseña?
                    </Link>
                  </div>
                  <Input
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </div>
                {error && <ErrorMessage>{error}</ErrorMessage>}
                <Button type="submit" disabled={submitting} className="mt-2">
                  {submitting ? 'Ingresando…' : 'Ingresar'}
                </Button>
              </form>
            </CardContent>
          </Card>

          <div className="mt-6 text-center">
            <Link
              to="/estado"
              className="inline-flex items-center gap-1.5 text-sm text-slate-400 transition-colors hover:text-slate-200"
            >
              <Activity className="h-4 w-4" />
              Consulta pública del estado de los servicios
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
