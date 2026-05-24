import { useRef, useState } from 'react'
import { usePlatformStore } from '../store'
import Plot from '../lib/plotly'
import { getRiskLabel, formatPercent } from '../types'
import SocioEconomicPanel from '../components/analysis/SocioEconomicPanel'

type UnifiedPlatform = {
  overall: number
  n_posts: number
  n_high: number
  signals?: Record<string, any[]>
}

type DetailRow = {
  platform: string
  posts: number
  overallRisk: number
  highRiskPosts: number
  riskLevel: string
  riskColor: string
}

type ColumnKey = keyof Pick<DetailRow, 'platform' | 'posts' | 'overallRisk' | 'highRiskPosts' | 'riskLevel'>

const columns: { key: ColumnKey; label: string; align?: 'left' | 'right'; csv: (row: DetailRow) => string | number }[] = [
  { key: 'platform', label: 'Platform', align: 'left', csv: (row) => row.platform },
  { key: 'posts', label: 'Posts', align: 'right', csv: (row) => row.posts },
  { key: 'overallRisk', label: 'Overall Risk', align: 'right', csv: (row) => formatPercent(row.overallRisk) },
  { key: 'highRiskPosts', label: 'High-Risk Posts', align: 'right', csv: (row) => row.highRiskPosts },
  { key: 'riskLevel', label: 'Risk Level', align: 'left', csv: (row) => row.riskLevel },
]

export default function MultiPlatformPage() {
  const { reddit, bluesky, mastodon, youtube, file, facebook, twitter, video } = usePlatformStore()
  const [search, setSearch] = useState('')
  const [hiddenColumns, setHiddenColumns] = useState<ColumnKey[]>([])
  const [columnPanelOpen, setColumnPanelOpen] = useState(false)
  const [menuColumn, setMenuColumn] = useState<ColumnKey | null>(null)
  const [sort, setSort] = useState<{ key: ColumnKey; direction: 'asc' | 'desc' } | null>(null)
  const [pinnedColumns, setPinnedColumns] = useState<ColumnKey[]>([])
  const [autosizeColumns, setAutosizeColumns] = useState<ColumnKey[]>([])
  const tableRef = useRef<HTMLDivElement>(null)

  const platforms: Record<string, UnifiedPlatform> = {}
  if (reddit) platforms.Reddit = reddit
  if (bluesky) platforms.Bluesky = bluesky
  if (mastodon) platforms.Mastodon = mastodon
  if (youtube) platforms.YouTube = youtube
  if (file) platforms['File Upload'] = file
  if (facebook) platforms.Facebook = facebook
  if (twitter) platforms['Twitter/X'] = twitter
  if (video?.ok) {
    platforms.Video = {
      overall: video.risk,
      n_posts: 1,
      n_high: video.risk >= 0.55 ? 1 : 0,
      signals: video.signals,
    }
  }

  const platformKeys = Object.keys(platforms)

  if (platformKeys.length === 0) {
    return (
      <div className="flex flex-col gap-[18px]">
        <h2 className="text-[1.15rem] font-bold text-[#111827]">Multi-Platform Unified Risk Profile</h2>
        <p className="text-[0.78rem] text-[#4b5563]">
          Combines results from all platforms you have already analysed in this session into one unified risk profile.
        </p>
        <div className="border-t border-[#d1d5db]" />
        <div className="bg-white rounded-[8px] border border-[#d1d5db] p-[60px_20px] flex flex-col items-center text-[#9ca3af] gap-[8px]">
          <i className="ti ti-share text-[24px]" />
          <p className="text-[0.78rem]">No platforms analysed yet.</p>
          <p className="text-[0.7rem]">Go to each tab and run an analysis first.</p>
        </div>
      </div>
    )
  }

  const allScores = platformKeys.map((key) => platforms[key].overall)
  const unifiedScore = allScores.reduce((sum, score) => sum + score, 0) / allScores.length
  const unifiedLabel = getRiskLabel(unifiedScore)

  const rows = platformKeys.map((key) => {
    const platform = platforms[key]
    const label = getRiskLabel(platform.overall)
    return {
      platform: key,
      posts: platform.n_posts,
      overallRisk: platform.overall,
      highRiskPosts: platform.n_high,
      riskLevel: label.label,
      riskColor: label.color,
    }
  })

  const visibleColumns = columns.filter((column) => !hiddenColumns.includes(column.key))
  const query = search.trim().toLowerCase()
  const filteredRows = query
    ? rows.filter((row) =>
        [
          row.platform,
          String(row.posts),
          formatPercent(row.overallRisk),
          String(row.highRiskPosts),
          row.riskLevel,
        ].some((value) => value.toLowerCase().includes(query)),
      )
    : rows
  const tableRows = sort
    ? [...filteredRows].sort((a, b) => {
        const aValue = a[sort.key]
        const bValue = b[sort.key]
        const result = typeof aValue === 'number' && typeof bValue === 'number'
          ? aValue - bValue
          : String(aValue).localeCompare(String(bValue))
        return sort.direction === 'asc' ? result : -result
      })
    : filteredRows

  const combinedSignals: Record<string, any[]> = {}
  platformKeys.forEach((key) => {
    const signals = platforms[key].signals
    if (!signals) return
    Object.entries(signals).forEach(([category, items]) => {
      if (!combinedSignals[category]) combinedSignals[category] = []
      items.forEach((item) => {
        const exists = combinedSignals[category].some(
          (existing) => existing.keyword === item.keyword && existing.snippet === item.snippet,
        )
        if (!exists) combinedSignals[category].push(item)
      })
    })
  })

  const totalSignals = Object.values(combinedSignals).reduce((sum, items) => sum + items.length, 0)
  const activeSignalCategories = Object.values(combinedSignals).filter((items) => items.length > 0).length
  const barColors = platformKeys.map((key) => getRiskLabel(platforms[key].overall).color)
  const reportContent = [
    `MindGuard Unified Risk Report\n${'='.repeat(40)}\n`,
    `Unified Risk Score: ${formatPercent(unifiedScore)} (${unifiedLabel.label})\n`,
    `Platforms analysed: ${platformKeys.join(', ')}\n\n`,
    ...platformKeys.map((key) => {
      const platform = platforms[key]
      return `${key}: ${formatPercent(platform.overall)} - ${getRiskLabel(platform.overall).label} (${platform.n_posts} posts, ${platform.n_high} high-risk)\n`
    }),
    `\nSocio-economic signals: ${totalSignals} across ${activeSignalCategories} categories\n`,
    `Timestamp: ${new Date().toLocaleString()}\n`,
  ].join('')

  const downloadCsv = () => {
    const headers = visibleColumns.map((column) => column.label)
    const lines = tableRows.map((row) =>
      visibleColumns.map((column) => `"${String(column.csv(row)).replace(/"/g, '""')}"`).join(','),
    )
    const blob = new Blob([[headers.join(','), ...lines].join('\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'mindguard-platform-detail.csv'
    link.click()
    URL.revokeObjectURL(url)
  }

  const toggleColumn = (key: ColumnKey) => {
    setHiddenColumns((current) => current.includes(key) ? current.filter((column) => column !== key) : [...current, key])
  }

  const togglePinned = (key: ColumnKey) => {
    setPinnedColumns((current) => current.includes(key) ? current.filter((column) => column !== key) : [...current, key])
  }

  const toggleAutosize = (key: ColumnKey) => {
    setAutosizeColumns((current) => current.includes(key) ? current.filter((column) => column !== key) : [...current, key])
  }

  return (
    <div className="flex flex-col gap-[18px]">
      <div>
        <h2 className="text-[1.15rem] font-bold text-[#111827]">Multi-Platform Unified Risk Profile</h2>
        <p className="text-[0.78rem] text-[#4b5563] mt-[14px]">
          Combines results from all platforms you have already analysed in this session into one unified risk profile.
        </p>
      </div>

      <div className="border-t border-[#d1d5db]" />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-[24px]">
        <Metric label="Unified Risk Score" value={formatPercent(unifiedScore)} color={unifiedLabel.color} />
        <Metric label="Platforms Analysed" value={String(platformKeys.length)} />
        <Metric label="Unified Risk Level" value={unifiedLabel.label} />
      </div>

      <div
        className="inline-block w-fit px-[16px] py-[8px] rounded-[8px] text-[0.82rem] font-bold"
        style={{
          background: `${unifiedLabel.color}22`,
          color: unifiedLabel.color,
          border: `1.5px solid ${unifiedLabel.color}`,
        }}
      >
        {unifiedLabel.label} - Unified across {platformKeys.length} platform(s)
      </div>

      {unifiedScore >= 0.55 && (
        <div className="bg-[#fef2f2] border border-[#fecaca] rounded-[7px] p-[10px_14px] text-[0.78rem] text-[#991b1b] font-semibold flex items-center gap-[8px]">
          <i className="ti ti-alert-triangle text-[16px]" />
          CRISIS ALERT - Elevated risk detected across multiple platforms.
        </div>
      )}

      <div className="border-t border-[#d1d5db]" />

      <section>
        <h3 className="text-[0.86rem] font-bold uppercase text-[#4b5563] mb-[12px]">Platform Breakdown</h3>
        <div className="bg-white rounded-[8px] border border-[#d1d5db] p-[14px]">
          <Plot
            data={[
              {
                type: 'bar',
                x: platformKeys,
                y: platformKeys.map((key) => platforms[key].overall),
                marker: { color: barColors },
                text: platformKeys.map((key) => formatPercent(platforms[key].overall)),
                textposition: 'outside',
                textfont: { color: '#4b5563', size: 10 },
                hovertemplate: '%{x}<br>Overall risk: %{y:.1%}<extra></extra>',
              },
            ]}
            layout={{
              paper_bgcolor: 'rgba(0,0,0,0)',
              plot_bgcolor: '#ffffff',
              font: { color: '#4b5563', size: 10 },
              yaxis: { tickformat: '.0%', range: [0, 1.1], gridcolor: '#e5e7eb', color: '#6b7280' },
              xaxis: { color: '#6b7280' },
              margin: { l: 44, r: 24, t: 16, b: 36 },
              height: 320,
              showlegend: false,
              shapes: [
                {
                  type: 'line',
                  xref: 'paper',
                  yref: 'y',
                  x0: 0,
                  x1: 1,
                  y0: unifiedScore,
                  y1: unifiedScore,
                  line: { dash: 'dot', color: '#0F766E', width: 1.5 },
                },
              ],
              annotations: [
                {
                  x: 1,
                  y: unifiedScore,
                  xref: 'paper',
                  yref: 'y',
                  text: `Unified avg: ${formatPercent(unifiedScore)}`,
                  showarrow: false,
                  font: { size: 9, color: '#0F766E' },
                  xanchor: 'right',
                  yanchor: 'bottom',
                },
              ],
            }}
            config={{
              displayModeBar: true,
              displaylogo: false,
              responsive: true,
              toImageButtonOptions: { format: 'png', filename: 'mindguard-platform-breakdown' },
              modeBarButtonsToAdd: [
                {
                  name: 'Full screen',
                  title: 'Full screen',
                  icon: {
                    width: 1000,
                    height: 1000,
                    path: 'M120 120h280v80H200v200h-80V120zm480 0h280v280h-80V200H600v-80zM120 600h80v200h200v80H120V600zm680 0h80v280H600v-80h200V600z',
                  },
                  click: (gd: any) => gd?.requestFullscreen?.(),
                },
              ],
            } as any}
            className="w-full"
          />
        </div>
      </section>

      <section ref={tableRef} className="bg-white rounded-[8px] border border-[#d1d5db] p-[16px_18px]">
        <div className="flex flex-col gap-[12px] md:flex-row md:items-center md:justify-between mb-[12px]">
          <h3 className="text-[0.86rem] font-bold uppercase text-[#4b5563]">Detail Table</h3>
          <div className="flex flex-wrap items-center gap-[8px]">
            <button type="button" onClick={() => setColumnPanelOpen((open) => !open)} className="toolbar-btn" title="Show/hide columns">
              <i className="ti ti-eye text-[15px]" />
              Columns
            </button>
            <button type="button" onClick={downloadCsv} className="toolbar-btn" title="Download as CSV">
              <i className="ti ti-download text-[15px]" />
              CSV
            </button>
            <div className="relative">
              <i className="ti ti-search absolute left-[9px] top-1/2 -translate-y-1/2 text-[#94a3b8] text-[15px]" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Type to search"
                className="h-[34px] w-[220px] rounded-[7px] border border-[#d1d5db] pl-[30px] pr-[10px] text-[0.78rem] outline-none focus:border-[#0F766E]"
              />
            </div>
            <button type="button" onClick={() => tableRef.current?.requestFullscreen?.()} className="toolbar-btn" title="Full screen">
              <i className="ti ti-arrows-maximize text-[15px]" />
              Full Screen
            </button>
          </div>
        </div>

        {columnPanelOpen && (
          <div className="mb-[12px] rounded-[8px] border border-[#d1d5db] bg-[#f8fafc] p-[10px] flex flex-wrap gap-[12px]">
            {columns.map((column) => (
              <label key={column.key} className="flex items-center gap-[6px] text-[0.76rem] text-[#4b5563]">
                <input
                  type="checkbox"
                  checked={!hiddenColumns.includes(column.key)}
                  onChange={() => toggleColumn(column.key)}
                  className="accent-[#0F766E]"
                />
                {column.label}
              </label>
            ))}
          </div>
        )}

        <div className="overflow-auto rounded-[8px] border border-[#e5e7eb]">
          <table className="w-full text-[0.78rem] border-collapse">
            <thead>
              <tr className="bg-[#f8fafc] text-[#6b7280]">
                {visibleColumns.map((column) => (
                  <th
                    key={column.key}
                    className={`relative border-b border-r border-[#e5e7eb] py-[10px] px-[10px] font-medium ${
                      column.align === 'right' ? 'text-right' : 'text-left'
                    } ${autosizeColumns.includes(column.key) ? 'whitespace-nowrap w-[1%]' : ''} ${
                      pinnedColumns.includes(column.key) ? 'sticky left-0 z-10 bg-[#f8fafc] shadow-[1px_0_0_#e5e7eb]' : ''
                    }`}
                  >
                    <span>{column.label}</span>
                    <button
                      type="button"
                      onClick={() => setMenuColumn(menuColumn === column.key ? null : column.key)}
                      className="ml-[8px] align-middle text-[#94a3b8] hover:text-[#0F766E]"
                      title={`${column.label} menu`}
                    >
                      <i className="ti ti-dots-vertical" />
                    </button>
                    {menuColumn === column.key && (
                      <div className="absolute right-[8px] top-[34px] z-20 w-[190px] rounded-[8px] border border-[#d1d5db] bg-white p-[8px] text-left shadow-[0_16px_30px_rgba(15,23,42,0.18)]">
                        <div className="px-[8px] py-[6px] text-[0.72rem] font-semibold text-[#4b5563] border border-[#d1d5db] rounded-[6px] mb-[6px]">
                          {column.label}
                        </div>
                        <MenuButton icon="ti ti-arrow-up" label="Sort ascending" onClick={() => { setSort({ key: column.key, direction: 'asc' }); setMenuColumn(null) }} />
                        <MenuButton icon="ti ti-arrow-down" label="Sort descending" onClick={() => { setSort({ key: column.key, direction: 'desc' }); setMenuColumn(null) }} />
                        <div className="h-px bg-[#e5e7eb] my-[6px]" />
                        <MenuButton icon="ti ti-arrows-horizontal" label="Autosize" onClick={() => { toggleAutosize(column.key); setMenuColumn(null) }} />
                        <MenuButton icon="ti ti-pin" label={pinnedColumns.includes(column.key) ? 'Unpin column' : 'Pin column'} onClick={() => { togglePinned(column.key); setMenuColumn(null) }} />
                        <MenuButton icon="ti ti-eye-off" label="Hide column" onClick={() => { toggleColumn(column.key); setMenuColumn(null) }} />
                      </div>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tableRows.map((row) => (
                <tr key={row.platform} className="border-b border-[#f1f5f9] hover:bg-[#eff6ff]">
                  {visibleColumns.map((column) => (
                    <td
                      key={column.key}
                      className={`border-r border-[#e5e7eb] py-[10px] px-[10px] ${
                        column.align === 'right' ? 'text-right' : 'text-left'
                      } ${autosizeColumns.includes(column.key) ? 'whitespace-nowrap w-[1%]' : ''} ${
                        pinnedColumns.includes(column.key) ? 'sticky left-0 z-10 bg-white shadow-[1px_0_0_#e5e7eb]' : ''
                      }`}
                    >
                      {column.key === 'overallRisk' && formatPercent(row.overallRisk)}
                      {column.key === 'riskLevel' && <span style={{ color: row.riskColor }} className="font-semibold">{row.riskLevel}</span>}
                      {column.key === 'platform' && row.platform}
                      {column.key === 'posts' && row.posts}
                      {column.key === 'highRiskPosts' && row.highRiskPosts}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {tableRows.length === 0 && (
          <div className="text-center py-[24px] text-[0.78rem] text-[#9ca3af]">No rows match the current search.</div>
        )}
      </section>

      <section className="bg-white rounded-[8px] border border-[#d1d5db] p-[16px_18px]">
        <h3 className="text-[0.86rem] font-bold uppercase text-[#4b5563] mb-[12px]">
          Combined Socio-Economic Signals
        </h3>
        <p className="text-[0.72rem] text-[#4b5563] mb-[12px]">
          {totalSignals} socio-economic distress signal(s) detected across {activeSignalCategories} categories.
        </p>
        <SocioEconomicPanel signals={combinedSignals} />
      </section>

      <a
        href={`data:text/plain;charset=utf-8,${encodeURIComponent(reportContent)}`}
        download="mindguard_unified_report.txt"
        className="block w-full text-center bg-white border border-[#d1d5db] rounded-[8px] py-[11px] text-[0.86rem] font-semibold text-[#4b5563] hover:border-[#0F766E] hover:text-[#0F766E]"
      >
        Download unified report
      </a>
    </div>
  )
}

function MenuButton({ icon, label, onClick }: { icon: string; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center gap-[9px] rounded-[6px] px-[8px] py-[7px] text-[0.78rem] text-[#111827] hover:bg-[#f1f5f9]"
    >
      <i className={`${icon} text-[15px]`} />
      {label}
    </button>
  )
}

function Metric({ label, value, color = '#4b5563' }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div className="text-[0.78rem] text-[#4b5563]">{label}</div>
      <div className="text-[2rem] leading-tight" style={{ color }}>{value}</div>
    </div>
  )
}
