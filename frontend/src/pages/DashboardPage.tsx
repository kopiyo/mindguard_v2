import { useAnalysisStore, usePlatformStore, useUiStore } from '../store'
import { formatPercent, getRiskLabel } from '../types'

export default function DashboardPage() {
  const setPage = useUiStore((state) => state.setPage)
  const { analytics, lastResult } = useAnalysisStore()
  const { reddit, bluesky, mastodon, youtube, file, facebook, twitter, video } = usePlatformStore()

  const platformResults = [
    ['Reddit', reddit],
    ['Bluesky', bluesky],
    ['Mastodon', mastodon],
    ['YouTube', youtube],
    ['File Upload', file],
    ['Facebook', facebook],
    ['Twitter / X', twitter],
  ] as const

  const analysedPlatforms = platformResults.filter(([, result]) => result)
  const videoAnalysed = Boolean(video?.ok)
  const platformCount = analysedPlatforms.length + (videoAnalysed ? 1 : 0)
  const postCount = analysedPlatforms.reduce((sum, [, result]) => sum + (result?.n_posts || 0), videoAnalysed ? 1 : 0)
  const highRiskCount = analysedPlatforms.reduce((sum, [, result]) => sum + (result?.n_high || 0), video?.ok && video.risk >= 0.55 ? 1 : 0)
  const scores = [
    ...analysedPlatforms.map(([, result]) => result!.overall),
    ...(video?.ok ? [video.risk] : []),
  ]
  const unifiedScore = scores.length ? scores.reduce((sum, score) => sum + score, 0) / scores.length : 0
  const unified = getRiskLabel(unifiedScore)
  const single = lastResult ? getRiskLabel(lastResult.prob) : null

  return (
    <div className="flex flex-col gap-[18px]">
      <section>
        <h2 className="text-[1.2rem] font-bold text-[#111827]">Dashboard</h2>
        <p className="text-[0.8rem] text-[#4b5563] mt-[8px]">
          Session overview for quick triage, recent activity, and next actions.
        </p>
      </section>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-[14px]">
        <MetricCard label="Platforms Analysed" value={String(platformCount)} icon="ti ti-share" />
        <MetricCard label="Posts / Items Reviewed" value={String(postCount)} icon="ti ti-files" />
        <MetricCard label="High-Risk Items" value={String(highRiskCount)} icon="ti ti-alert-triangle" tone={highRiskCount ? '#f97316' : '#22c55e'} />
        <MetricCard label="Unified Risk" value={scores.length ? formatPercent(unifiedScore) : '--'} icon="ti ti-activity" tone={scores.length ? unified.color : '#6b7280'} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1.1fr_0.9fr] gap-[16px]">
        <section className="bg-white rounded-[10px] border border-[#d1d5db] p-[16px]">
          <div className="flex items-center justify-between gap-[12px] mb-[14px]">
            <h3 className="text-[0.86rem] font-bold uppercase text-[#4b5563]">Analysis Status</h3>
            {scores.length > 0 && (
              <span className="text-[0.74rem] font-semibold px-[10px] py-[5px] rounded-full" style={{ color: unified.color, background: `${unified.color}18` }}>
                {unified.label}
              </span>
            )}
          </div>
          <div className="space-y-[10px]">
            {platformResults.map(([name, result]) => (
              <PlatformRow key={name} name={name} done={Boolean(result)} detail={result ? `${result.n_posts} posts, ${formatPercent(result.overall)} overall` : 'Not analysed'} />
            ))}
            <PlatformRow name="Video" done={videoAnalysed} detail={video?.ok ? `1 item, ${formatPercent(video.risk)} risk` : 'Not analysed'} />
          </div>
        </section>

        <section className="bg-white rounded-[10px] border border-[#d1d5db] p-[16px]">
          <h3 className="text-[0.86rem] font-bold uppercase text-[#4b5563] mb-[14px]">Recent Single-Item Analysis</h3>
          {lastResult && single ? (
            <div>
              <div className="text-[2.2rem] leading-none font-semibold" style={{ color: single.color }}>
                {formatPercent(lastResult.prob)}
              </div>
              <div className="text-[0.8rem] text-[#4b5563] mt-[8px]">{lastResult.label} - {single.label}</div>
              <div className="text-[0.72rem] text-[#9ca3af] mt-[4px]">Latency: {lastResult.latency_ms.toFixed(0)}ms</div>
            </div>
          ) : (
            <div className="text-[0.78rem] text-[#9ca3af] py-[18px]">
              No text or image analysis run yet.
            </div>
          )}
          <div className="grid grid-cols-3 gap-[8px] mt-[18px]">
            <MiniStat label="Analysed" value={analytics.total_analyses} />
            <MiniStat label="At-Risk" value={analytics.positive_count} tone="#ef4444" />
            <MiniStat label="Safe" value={analytics.negative_count} tone="#22c55e" />
          </div>
        </section>
      </div>

      <section className="bg-white rounded-[10px] border border-[#d1d5db] p-[16px]">
        <h3 className="text-[0.86rem] font-bold uppercase text-[#4b5563] mb-[12px]">Next Actions</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-[10px]">
          <ActionButton icon="ti ti-pencil" label="Text / Image Analysis" onClick={() => setPage('text-image')} />
          <ActionButton icon="ti ti-brand-reddit" label="Run Platform Analysis" onClick={() => setPage('reddit')} />
          <ActionButton icon="ti ti-file-report" label="View Unified Profile" onClick={() => setPage('unified')} />
        </div>
      </section>
    </div>
  )
}

function MetricCard({ label, value, icon, tone = '#0F766E' }: { label: string; value: string; icon: string; tone?: string }) {
  return (
    <div className="bg-white rounded-[10px] border border-[#d1d5db] p-[14px]">
      <div className="flex items-center justify-between">
        <span className="text-[0.72rem] text-[#4b5563]">{label}</span>
        <i className={`${icon} text-[18px]`} style={{ color: tone }} />
      </div>
      <div className="text-[1.8rem] leading-tight mt-[10px]" style={{ color: tone }}>{value}</div>
    </div>
  )
}

function PlatformRow({ name, done, detail }: { name: string; done: boolean; detail: string }) {
  return (
    <div className="flex items-center justify-between gap-[12px] rounded-[8px] bg-[#f8fafc] px-[12px] py-[9px]">
      <div className="flex items-center gap-[8px]">
        <span className={`w-[8px] h-[8px] rounded-full ${done ? 'bg-[#22c55e]' : 'bg-[#cbd5e1]'}`} />
        <span className="text-[0.8rem] font-semibold text-[#1f2937]">{name}</span>
      </div>
      <span className="text-[0.72rem] text-[#6b7280] text-right">{detail}</span>
    </div>
  )
}

function MiniStat({ label, value, tone = '#0F766E' }: { label: string; value: number; tone?: string }) {
  return (
    <div className="rounded-[8px] border border-[#e5e7eb] p-[10px] text-center">
      <div className="text-[1.3rem] font-semibold" style={{ color: tone }}>{value}</div>
      <div className="text-[0.62rem] uppercase tracking-[0.08em] text-[#9ca3af] font-bold">{label}</div>
    </div>
  )
}

function ActionButton({ icon, label, onClick }: { icon: string; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center justify-center gap-[8px] rounded-[8px] border border-[#d1d5db] bg-white px-[14px] py-[11px] text-[0.82rem] font-semibold text-[#4b5563] hover:border-[#0F766E] hover:text-[#0F766E]"
    >
      <i className={`${icon} text-[16px]`} />
      {label}
    </button>
  )
}
