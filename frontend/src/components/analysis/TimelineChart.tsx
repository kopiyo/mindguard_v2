import Plot from '../../lib/plotly'
import type { PostData } from '../../types'

interface TimelineChartProps {
  posts: PostData[]
  dateCol?: string
  scoreCol?: string
}

export default function TimelineChart({ posts, dateCol = 'date', scoreCol = 'risk_score' }: TimelineChartProps) {
  const parsed = posts
    .map((p, index) => ({
      ...p,
      originalIndex: index + 1,
      parsedDate: toDateOnly(p[dateCol as keyof PostData] as string),
      score: Number(p[scoreCol as keyof PostData]),
    }))
    .filter((p) => !isNaN(p.parsedDate.getTime()) && Number.isFinite(p.score))
    .sort((a, b) => a.parsedDate.getTime() - b.parsedDate.getTime())

  if (parsed.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-[200px] text-[#c4c9d0] gap-[5px]">
        <i className="ti ti-chart-line text-[22px]" />
        <span className="text-[0.65rem]">Run an analysis to see the risk timeline</span>
      </div>
    )
  }

  const points = parsed.map((post) => {
    const date = new Date(post.parsedDate)

    return {
      date,
      score: post.score,
      originalDate: post.parsedDate,
      postNumber: post.originalIndex,
    }
  })

  const xValues = points.map((p) => p.date)
  const yValues = points.map((p) => p.score)
  const uniqueDateCount = new Set(xValues.map((date) => date.getTime())).size
  const colors = points.map((p) => {
    if (p.score >= 0.75) return '#ef4444'
    if (p.score >= 0.55) return '#f97316'
    if (p.score >= 0.35) return '#f59e0b'
    return '#0F766E'
  })
  const hoverData = points.map((p) => [
    p.originalDate.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    }),
    p.postNumber,
  ])

  return (
    <Plot
      data={[
        {
          x: xValues,
          y: yValues,
          customdata: hoverData,
          type: 'scatter',
          mode: points.length > 2 ? 'lines+markers' : 'markers',
          name: 'Post risk',
          line: { color: '#0F766E', width: 2 },
          marker: {
            color: colors,
            size: 10,
            opacity: 0.88,
            line: { color: '#ffffff', width: 1.5 },
          },
          hovertemplate: 'Post %{customdata[1]}<br>Date: %{customdata[0]}<br>Risk: %{y:.1%}<extra></extra>',
        },
      ]}
      layout={{
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: '#ffffff',
        font: { color: '#4b5563', size: 10 },
        xaxis: {
          title: 'Post Date',
          gridcolor: '#f1f5f9',
          color: '#9ca3af',
          tickformat: '%b %d, %Y',
          type: 'date',
          range: uniqueDateCount === 1
            ? [
                new Date(xValues[0].getTime() - 12 * 60 * 60 * 1000),
                new Date(xValues[0].getTime() + 12 * 60 * 60 * 1000),
              ]
            : undefined,
        },
        yaxis: { title: 'Risk Score', range: [0, 1], tickformat: '.0%', gridcolor: '#f1f5f9', color: '#9ca3af' },
        margin: { l: 44, r: 20, t: 10, b: 42 },
        height: 200,
        showlegend: false,
        shapes: [
          { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: 0, y1: 0.35, fillcolor: 'rgba(34,197,94,0.05)', line: { width: 0 }, layer: 'below' },
          { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: 0.35, y1: 0.55, fillcolor: 'rgba(245,158,11,0.05)', line: { width: 0 }, layer: 'below' },
          { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: 0.55, y1: 0.75, fillcolor: 'rgba(249,115,22,0.05)', line: { width: 0 }, layer: 'below' },
          { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: 0.75, y1: 1, fillcolor: 'rgba(239,68,68,0.05)', line: { width: 0 }, layer: 'below' },
        ],
      }}
      config={{ displayModeBar: false, responsive: true }}
      className="w-full"
    />
  )
}

function toDateOnly(value: string) {
  const date = new Date(value)
  date.setHours(0, 0, 0, 0)
  return date
}
