import { useMemo, useState } from 'react'
import { usePlatformStore, useUiStore } from '../store'
import {
  analyzeBluesky,
  analyzeFacebook,
  analyzeMastodon,
  analyzeReddit,
  analyzeTwitter,
  analyzeYouTube,
  analyzeVideo,
} from '../api/analysis'
import { formatPercent, getRiskLabel, type PlatformResult, type VideoResult } from '../types'

type BatchStatus = 'idle' | 'queued' | 'running' | 'complete' | 'failed' | 'skipped'

type BatchRow = {
  key: string
  label: string
  status: BatchStatus
  message: string
  posts?: number
  risk?: number
}

const initialRows: BatchRow[] = [
  { key: 'reddit', label: 'Reddit', status: 'idle', message: 'Waiting for username' },
  { key: 'bluesky', label: 'Bluesky', status: 'idle', message: 'Waiting for handle and credentials' },
  { key: 'mastodon', label: 'Mastodon', status: 'idle', message: 'Waiting for handle' },
  { key: 'youtube', label: 'YouTube', status: 'idle', message: 'Waiting for source' },
  { key: 'facebook', label: 'Facebook', status: 'idle', message: 'Waiting for profile URL' },
  { key: 'twitter', label: 'Twitter / X', status: 'idle', message: 'Waiting for profile URL' },
  { key: 'video', label: 'Video', status: 'idle', message: 'Waiting for video URL' },
]

export default function BatchAnalysisPage() {
  const setPage = useUiStore((state) => state.setPage)
  const setPlatformResult = usePlatformStore((state) => state.setPlatformResult)
  const [running, setRunning] = useState(false)
  const [minRisk, setMinRisk] = useState(0)
  const [nShow, setNShow] = useState(20)
  const [redditUsername, setRedditUsername] = useState('')
  const [redditClientId, setRedditClientId] = useState('')
  const [redditClientSecret, setRedditClientSecret] = useState('')
  const [blueskyHandle, setBlueskyHandle] = useState('')
  const [blueskyIdentifier, setBlueskyIdentifier] = useState('')
  const [blueskyPassword, setBlueskyPassword] = useState('')
  const [mastodonHandle, setMastodonHandle] = useState('')
  const [youtubeUrl, setYoutubeUrl] = useState('')
  const [youtubeApiKey, setYoutubeApiKey] = useState('')
  const [youtubeTranscribe, setYoutubeTranscribe] = useState(true)
  const [youtubeTranscriptLimit, setYoutubeTranscriptLimit] = useState(3)
  const [facebookUrl, setFacebookUrl] = useState('')
  const [twitterUrl, setTwitterUrl] = useState('')
  const [videoUrl, setVideoUrl] = useState('')
  const [rows, setRows] = useState<BatchRow[]>(initialRows)

  const selectedCount = useMemo(() => {
    return [
      redditUsername.trim(),
      blueskyHandle.trim() && blueskyIdentifier.trim() && blueskyPassword.trim(),
      mastodonHandle.trim(),
      youtubeUrl.trim(),
      facebookUrl.trim(),
      twitterUrl.trim(),
      videoUrl.trim(),
    ].filter(Boolean).length
  }, [redditUsername, blueskyHandle, blueskyIdentifier, blueskyPassword, mastodonHandle, youtubeUrl, facebookUrl, twitterUrl, videoUrl])

  const updateRow = (key: string, patch: Partial<BatchRow>) => {
    setRows((current) => current.map((row) => row.key === key ? { ...row, ...patch } : row))
  }

  const runTask = async (
    key: string,
    enabled: boolean,
    task: () => Promise<PlatformResult | VideoResult>,
    storeKey = key,
  ) => {
    if (!enabled) {
      updateRow(key, { status: 'skipped', message: 'Skipped - no input provided', posts: undefined, risk: undefined })
      return
    }
    updateRow(key, { status: 'running', message: 'Running...', posts: undefined, risk: undefined })
    try {
      const result = await task()
      setPlatformResult(storeKey, result)
      const isVideo = storeKey === 'video'
      const risk = isVideo ? (result as VideoResult).risk : (result as PlatformResult).overall
      const posts = isVideo ? 1 : (result as PlatformResult).n_posts
      updateRow(key, {
        status: 'complete',
        message: `${formatPercent(risk)} ${getRiskLabel(risk).label}`,
        posts,
        risk,
      })
    } catch (err: any) {
      const message = err.response?.data?.detail || err.message || 'Analysis failed'
      updateRow(key, { status: 'failed', message, posts: undefined, risk: undefined })
    }
  }

  const handleRunAll = async () => {
    if (selectedCount === 0 || running) return
    setRunning(true)
    setRows(initialRows.map((row) => ({ ...row, status: 'queued', message: 'Queued', posts: undefined, risk: undefined })))
    const youtubeIsVideo = /(?:youtube\.com\/watch|youtu\.be\/|youtube\.com\/shorts\/|youtube\.com\/live\/)/i.test(youtubeUrl.trim())

    await Promise.all([
      runTask(
        'reddit',
        Boolean(redditUsername.trim()),
        () => analyzeReddit(redditUsername.trim(), redditClientId.trim(), redditClientSecret.trim(), minRisk, nShow),
      ),
      runTask(
        'bluesky',
        Boolean(blueskyHandle.trim() && blueskyIdentifier.trim() && blueskyPassword.trim()),
        () => analyzeBluesky(blueskyHandle.trim(), blueskyIdentifier.trim(), blueskyPassword, minRisk, nShow),
      ),
      runTask(
        'mastodon',
        Boolean(mastodonHandle.trim()),
        () => analyzeMastodon(mastodonHandle.trim(), minRisk, nShow),
      ),
      runTask(
        'youtube',
        Boolean(youtubeUrl.trim() && (youtubeIsVideo || youtubeApiKey.trim())),
        () => analyzeYouTube(
          youtubeUrl.trim(),
          youtubeApiKey.trim(),
          minRisk,
          nShow,
          youtubeIsVideo ? true : youtubeTranscribe,
          youtubeIsVideo ? 1 : youtubeTranscriptLimit,
        ),
      ),
      runTask(
        'facebook',
        Boolean(facebookUrl.trim()),
        () => analyzeFacebook(facebookUrl.trim(), 3, minRisk, nShow),
      ),
      runTask(
        'twitter',
        Boolean(twitterUrl.trim()),
        () => analyzeTwitter(twitterUrl.trim(), minRisk, nShow),
      ),
      runTask(
        'video',
        Boolean(videoUrl.trim()),
        () => analyzeVideo(videoUrl.trim()),
      ),
    ])
    setRunning(false)
  }

  return (
    <div className="flex flex-col gap-[18px]">
      <section>
        <h2 className="text-[1.2rem] font-bold text-[#111827]">Batch Social Media Analysis</h2>
        <p className="text-[0.8rem] text-[#4b5563] mt-[8px]">
          Enter every available handle or URL once, then run all selected analyses together. Failed platforms will not block successful ones.
        </p>
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-[16px] items-start">
        <div className="bg-white rounded-[10px] border border-[#d1d5db] p-[16px]">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-[14px]">
            <Field label="Reddit username" value={redditUsername} onChange={setRedditUsername} placeholder="spez" />
            <Field label="Mastodon handle" value={mastodonHandle} onChange={setMastodonHandle} placeholder="user@mastodon.social" />
            <Field label="Bluesky handle to analyse" value={blueskyHandle} onChange={setBlueskyHandle} placeholder="nixadon.bsky.social" />
            <Field label="Your Bluesky handle" value={blueskyIdentifier} onChange={setBlueskyIdentifier} placeholder="your.handle.bsky.social" />
            <Field label="Bluesky app password" value={blueskyPassword} onChange={setBlueskyPassword} placeholder="xxxx-xxxx-xxxx-xxxx" type="password" />
            <Field label="YouTube channel or video URL" value={youtubeUrl} onChange={setYoutubeUrl} placeholder="https://youtube.com/@channel" />
            <Field label="YouTube API key" value={youtubeApiKey} onChange={setYoutubeApiKey} placeholder="Required for channel analysis" type="password" />
            <Field label="Facebook profile URL" value={facebookUrl} onChange={setFacebookUrl} placeholder="https://www.facebook.com/username" />
            <Field label="Twitter / X profile URL" value={twitterUrl} onChange={setTwitterUrl} placeholder="https://x.com/username" />
            <Field label="Direct video URL" value={videoUrl} onChange={setVideoUrl} placeholder="TikTok, Instagram, YouTube, Vimeo..." />
          </div>

          <div className="mt-[16px] rounded-[8px] border border-[#e5e7eb] bg-[#f8fafc] p-[14px]">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-[14px]">
              <Slider label="Min risk score" value={minRisk} min={0} max={1} step={0.05} display={minRisk.toFixed(2)} onChange={setMinRisk} />
              <Slider label="Max posts/items to display" value={nShow} min={5} max={50} step={5} display={String(nShow)} onChange={setNShow} />
            </div>
            <label className="mt-[12px] flex items-center gap-[8px] text-[0.76rem] text-[#4b5563] font-semibold">
              <input
                type="checkbox"
                checked={youtubeTranscribe}
                onChange={(event) => setYoutubeTranscribe(event.target.checked)}
                className="accent-[#0F766E]"
              />
              Transcribe recent YouTube channel videos
            </label>
            <Slider
              label="YouTube transcript limit"
              value={youtubeTranscriptLimit}
              min={1}
              max={5}
              step={1}
              display={String(youtubeTranscriptLimit)}
              onChange={setYoutubeTranscriptLimit}
            />
          </div>

          <details className="mt-[14px] rounded-[8px] border border-[#e5e7eb] p-[12px]">
            <summary className="cursor-pointer text-[0.78rem] font-bold text-[#4b5563]">Optional Reddit API credentials</summary>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-[12px] mt-[12px]">
              <Field label="Reddit client ID" value={redditClientId} onChange={setRedditClientId} placeholder="Leave blank for RSS mode" />
              <Field label="Reddit client secret" value={redditClientSecret} onChange={setRedditClientSecret} placeholder="Leave blank for RSS mode" type="password" />
            </div>
          </details>

          <button
            type="button"
            onClick={handleRunAll}
            disabled={running || selectedCount === 0}
            className="mt-[16px] w-full rounded-[8px] bg-[#0F766E] px-[16px] py-[12px] text-[0.9rem] font-bold text-white disabled:opacity-50 disabled:cursor-not-allowed hover:bg-[#115E59]"
          >
            {running ? 'Running selected analyses...' : `Run All Analyses (${selectedCount})`}
          </button>
        </div>

        <section className="bg-white rounded-[10px] border border-[#d1d5db] p-[16px]">
          <h3 className="text-[0.86rem] font-bold uppercase text-[#4b5563] mb-[12px]">Run Status</h3>
          <div className="space-y-[9px]">
            {rows.map((row) => (
              <StatusRow key={row.key} row={row} />
            ))}
          </div>
          <button
            type="button"
            onClick={() => setPage('unified')}
            className="mt-[14px] w-full rounded-[8px] border border-[#d1d5db] bg-white px-[12px] py-[10px] text-[0.8rem] font-semibold text-[#4b5563] hover:border-[#0F766E] hover:text-[#0F766E]"
          >
            View Multi-Platform Report
          </button>
        </section>
      </section>
    </div>
  )
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = 'text',
}: {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder: string
  type?: 'text' | 'password'
}) {
  return (
    <label className="flex flex-col gap-[6px] text-[0.72rem] font-bold uppercase tracking-[0.05em] text-[#0F766E]">
      {label}
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="h-[40px] rounded-[7px] border border-[#d1d5db] bg-white px-[11px] text-[0.8rem] font-normal normal-case tracking-normal text-[#111827] outline-none focus:border-[#0F766E]"
      />
    </label>
  )
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  display,
  onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  display: string
  onChange: (value: number) => void
}) {
  return (
    <label className="flex flex-col gap-[6px] text-[0.72rem] font-bold uppercase tracking-[0.05em] text-[#0F766E]">
      <span className="flex justify-between gap-[12px]">
        {label}
        <span className="text-[#0F766E]">{display}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="h-[4px] accent-[#0F766E]"
      />
    </label>
  )
}

function StatusRow({ row }: { row: BatchRow }) {
  const styles: Record<BatchStatus, { dot: string; text: string }> = {
    idle: { dot: 'bg-[#cbd5e1]', text: 'text-[#64748b]' },
    queued: { dot: 'bg-[#94a3b8]', text: 'text-[#64748b]' },
    running: { dot: 'bg-[#0F766E] animate-pulse', text: 'text-[#0F766E]' },
    complete: { dot: 'bg-[#22c55e]', text: 'text-[#15803d]' },
    failed: { dot: 'bg-[#ef4444]', text: 'text-[#dc2626]' },
    skipped: { dot: 'bg-[#cbd5e1]', text: 'text-[#94a3b8]' },
  }
  return (
    <div className="rounded-[8px] border border-[#e5e7eb] px-[11px] py-[9px]">
      <div className="flex items-center justify-between gap-[10px]">
        <div className="flex items-center gap-[8px]">
          <span className={`h-[8px] w-[8px] rounded-full ${styles[row.status].dot}`} />
          <span className="text-[0.8rem] font-semibold text-[#1f2937]">{row.label}</span>
        </div>
        {row.posts != null && <span className="text-[0.68rem] text-[#64748b]">{row.posts} item(s)</span>}
      </div>
      <div className={`mt-[5px] text-[0.7rem] leading-[1.35] ${styles[row.status].text}`}>
        {row.message}
      </div>
    </div>
  )
}
