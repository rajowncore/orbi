// src/hooks/usePagination.js
import { useState, useMemo } from 'react'

export function usePagination(data = [], pageSize = 10) {
  const [page, setPage] = useState(1)

  const totalPages = Math.max(1, Math.ceil(data.length / pageSize))
  const safePage   = Math.min(page, totalPages)

  const paged = useMemo(() => {
    const start = (safePage - 1) * pageSize
    return data.slice(start, start + pageSize)
  }, [data, safePage, pageSize])

  return {
    page: safePage,
    setPage,
    totalPages,
    totalItems: data.length,
    paged,
    pageSize,
    hasNext: safePage < totalPages,
    hasPrev: safePage > 1,
  }
}
