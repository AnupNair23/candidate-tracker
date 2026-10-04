export function Skeleton({ width = '100%', height = 12, style }: { width?: number | string; height?: number; style?: React.CSSProperties }) {
  return <div className="skeleton" style={{ width, height, ...style }} aria-hidden />
}

export function SkeletonRows({ rows = 6 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Loading" style={{ padding: 16, display: 'grid', gap: 14 }}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} style={{ display: 'grid', gap: 6 }}>
          <Skeleton width="38%" height={12} />
          <Skeleton width="62%" height={10} />
        </div>
      ))}
    </div>
  )
}
