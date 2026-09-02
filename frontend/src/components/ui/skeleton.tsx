import { type HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('animate-pulse rounded-md bg-slate-800/80', className)} {...props} />
}

export function TableSkeleton({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-800">
      <table className="w-full text-sm">
        <tbody className="divide-y divide-slate-800">
          {Array.from({ length: rows }).map((_, r) => (
            <tr key={r}>
              {Array.from({ length: cols }).map((_, c) => (
                <td key={c} className="px-4 py-3">
                  <Skeleton className="h-4" style={{ width: `${55 + ((r + c) % 4) * 10}%` }} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function CardGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-lg border border-slate-800 bg-slate-900/60 p-6 shadow-lg shadow-black/20">
          <div className="flex items-start justify-between gap-2">
            <Skeleton className="h-5 w-2/3" />
            <Skeleton className="h-5 w-16 rounded-full" />
          </div>
          <Skeleton className="mt-3 h-3.5 w-full" />
          <Skeleton className="mt-1.5 h-3.5 w-4/5" />
          <div className="mt-5 flex items-center justify-between border-t border-slate-800 pt-3">
            <Skeleton className="h-3.5 w-24" />
            <Skeleton className="h-3.5 w-16" />
          </div>
        </div>
      ))}
    </div>
  )
}

export function StatCardsSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-lg border border-slate-800 bg-slate-900/60 p-4 shadow-lg shadow-black/20">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="mt-2.5 h-7 w-14" />
        </div>
      ))}
    </div>
  )
}

export function DetailPageSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-5 shadow-lg shadow-black/20">
        <div className="flex items-center gap-2">
          <Skeleton className="h-6 w-56" />
          <Skeleton className="h-5 w-20 rounded-full" />
        </div>
        <Skeleton className="mt-2.5 h-4 w-80" />
      </div>
      <StatCardsSkeleton count={4} />
      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6 shadow-lg shadow-black/20">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="mt-4 h-20 w-full" />
      </div>
    </div>
  )
}
