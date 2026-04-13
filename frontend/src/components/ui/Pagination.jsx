// src/components/ui/Pagination.jsx
export function Pagination({ page, totalPages, totalItems, pageSize, setPage }) {
  if (totalPages <= 1) return null
  const start = (page - 1) * pageSize + 1
  const end   = Math.min(page * pageSize, totalItems)

  const pages = () => {
    const p = []
    const delta = 1
    const left  = page - delta
    const right = page + delta

    for (let i = 1; i <= totalPages; i++) {
      if (i === 1 || i === totalPages || (i >= left && i <= right)) {
        p.push(i)
      } else if (i === left - 1 || i === right + 1) {
        p.push('…')
      }
    }
    // dedupe consecutive ellipses
    return p.filter((v, i, a) => !(v === '…' && a[i - 1] === '…'))
  }

  return (
    <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100">
      <span className="text-xs text-slate-400">
        {start}–{end} of {totalItems}
      </span>
      <div className="flex items-center gap-1">
        <button
          onClick={() => setPage(page - 1)}
          disabled={page === 1}
          className="btn btn-ghost btn-sm px-2 disabled:opacity-30">
          ‹
        </button>
        {pages().map((p, i) =>
          p === '…' ? (
            <span key={`e${i}`} className="text-slate-400 text-xs px-1">…</span>
          ) : (
            <button key={p}
              onClick={() => setPage(p)}
              className={`btn btn-sm px-2.5 ${p === page ? 'btn-primary' : 'btn-ghost'}`}>
              {p}
            </button>
          )
        )}
        <button
          onClick={() => setPage(page + 1)}
          disabled={page === totalPages}
          className="btn btn-ghost btn-sm px-2 disabled:opacity-30">
          ›
        </button>
      </div>
    </div>
  )
}
