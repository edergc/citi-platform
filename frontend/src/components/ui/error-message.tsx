import { type ReactNode } from 'react'
import { AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

export function ErrorMessage({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p className={cn('flex items-center gap-1.5 text-sm text-red-400', className)}>
      <AlertCircle className="h-4 w-4 shrink-0" />
      {children}
    </p>
  )
}
