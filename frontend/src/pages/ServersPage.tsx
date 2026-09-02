import { useSearchParams } from 'react-router-dom'
import { useAuth } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { ServerFormDialog } from '@/components/ServerFormDialog'
import { cn } from '@/lib/utils'
import { ResumenView } from './servers/ResumenView'
import { ListaView } from './servers/ListaView'

export function ServersPage() {
  const { user } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  // Deep-linkable and reactive to in-place URL changes: "Sedes" tiles and Admin → Sedes
  // both send técnicos here with ?site=<id>&view=lista. Deriving from searchParams (not a
  // useState initialized once) matters because clicking a sede tile while already on
  // /servers only changes the query string — React Router doesn't remount this component,
  // so a one-time useState would never notice the new ?view=lista.
  const view: 'resumen' | 'lista' = searchParams.get('view') === 'lista' ? 'lista' : 'resumen'

  function setView(next: 'resumen' | 'lista') {
    const params = new URLSearchParams(searchParams)
    params.set('view', next)
    setSearchParams(params, { replace: true })
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-base font-medium text-slate-200">Gestión de Infraestructura</h2>
          <p className="text-xs text-slate-500">Servidores y pseudoservidores por sede — conectividad, disco, memoria y red.</p>
        </div>
        {user?.is_superuser && <ServerFormDialog trigger={<Button size="sm">+ Nuevo servidor</Button>} />}
      </div>

      <div className="mb-6 flex gap-1 border-b border-slate-800">
        {(
          [
            ['resumen', 'Resumen'],
            ['lista', 'Lista'],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setView(key)}
            className={cn(
              'px-4 py-2 text-sm transition-colors',
              view === key ? 'border-b-2 border-amber-500 text-slate-100' : 'text-slate-400 hover:text-slate-200',
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {view === 'resumen' ? <ResumenView /> : <ListaView />}
    </div>
  )
}
