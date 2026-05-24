import { useState } from 'react'
import { usePlatformStore } from '../store'
import { analyzeYouTube } from '../api/analysis'
import TimelineChart from '../components/analysis/TimelineChart'
import PostCards from '../components/analysis/PostCards'
import OverallBanner from '../components/analysis/OverallBanner'
import SocioEconomicPanel from '../components/analysis/SocioEconomicPanel'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import type { PlatformResult } from '../types'

export default function YouTubePage() {
  const [channelUrl, setChannelUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [minRisk, setMinRisk] = useState(0)
  const [nShow, setNShow] = useState(20)
  const [transcribeVideos, setTranscribeVideos] = useState(true)
  const [transcriptLimit, setTranscriptLimit] = useState(3)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState<'timeline' | 'posts' | 'socio'>('timeline')
  const { youtube, loading, setPlatformResult } = usePlatformStore()
  const isVideoUrl = /(?:youtube\.com\/watch|youtu\.be\/|youtube\.com\/shorts\/|youtube\.com\/live\/)/i.test(channelUrl.trim())

  const handleAnalyze = async () => {
    const source = channelUrl.trim()
    if (!source) {
      setError('Enter a YouTube channel or video URL.')
      return
    }
    if (!isVideoUrl && !apiKey.trim()) {
      setError('YouTube API key is required for channel analysis. Direct video URLs can be analysed without an API key.')
      return
    }
    setError('')
    try {
      usePlatformStore.getState().setLoading(true)
      setPlatformResult('youtube', null)
      const result = await analyzeYouTube(source, apiKey, minRisk, nShow, isVideoUrl ? true : transcribeVideos, isVideoUrl ? 1 : transcriptLimit)
      setPlatformResult('youtube', result)
      setActiveTab('timeline')
    } catch (err: any) {
      setError(err.message || 'YouTube analysis failed')
    } finally {
      usePlatformStore.getState().setLoading(false)
    }
  }

  const result = youtube as PlatformResult | null

  return (
    <div className="flex flex-col gap-[14px]">
      <h2 className="text-[1.1rem] font-bold text-[#1f2937]">YouTube Analysis</h2>
      <p className="text-[0.74rem] text-[#6b7280] -mt-[10px]">
        Enter a YouTube channel URL with an API key, or paste a direct YouTube video URL to transcribe and analyse up to 10 minutes.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-[14px]">
        <div className="bg-white rounded-xl border border-[rgba(229,231,235,0.7)] p-[16px_18px]">
          <div className="text-[0.62rem] font-bold text-[#374151] uppercase tracking-[0.06em] mb-[4px]">Channel or Video URL</div>
          <input
            type="text"
            value={channelUrl}
            onChange={(e) => setChannelUrl(e.target.value)}
            placeholder="https://youtube.com/@channel or https://youtube.com/watch?v=..."
            className="w-full bg-[#fafbfc] border-[1.5px] border-[#e5e7eb] rounded-[7px] px-[10px] py-[7px] text-[0.7rem] text-[#4b5563] outline-none focus:border-[#0F766E] mb-[8px]"
          />
          <div className="text-[0.62rem] font-bold text-[#374151] uppercase tracking-[0.06em] mb-[4px]">
            YouTube API Key {isVideoUrl && <span className="text-[#9ca3af] font-semibold normal-case">(not needed for video URL)</span>}
          </div>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="AIza..."
            disabled={isVideoUrl}
            className="w-full bg-[#fafbfc] border-[1.5px] border-[#e5e7eb] rounded-[7px] px-[10px] py-[7px] text-[0.7rem] text-[#4b5563] outline-none focus:border-[#0F766E] mb-[8px]"
          />
          <div className="text-[0.62rem] font-bold text-[#374151] uppercase tracking-[0.06em] mb-[4px]">Min risk score</div>
          <div className="flex items-center gap-[8px] mb-[8px]">
            <input
              type="range"
              min={0}
              max={100}
              value={minRisk * 100}
              onChange={(e) => setMinRisk(Number(e.target.value) / 100)}
              className="flex-1 h-[3px]"
            />
            <span className="text-[0.68rem] text-[#6b7280] font-semibold min-w-[32px]">{(minRisk * 100).toFixed(0)}%</span>
          </div>
          <div className="text-[0.62rem] font-bold text-[#374151] uppercase tracking-[0.06em] mb-[4px]">Max items to display</div>
          <div className="flex items-center gap-[8px] mb-[8px]">
            <input
              type="range"
              min={5}
              max={50}
              step={5}
              value={nShow}
              onChange={(e) => setNShow(Number(e.target.value))}
              className="flex-1 h-[3px]"
            />
            <span className="text-[0.68rem] text-[#6b7280] font-semibold min-w-[32px]">{nShow}</span>
          </div>
          {!isVideoUrl && (
            <>
              <label className="flex items-center gap-[8px] text-[0.7rem] text-[#4b5563] font-semibold mb-[8px]">
                <input
                  type="checkbox"
                  checked={transcribeVideos}
                  onChange={(e) => setTranscribeVideos(e.target.checked)}
                  className="accent-[#0F766E]"
                />
                Transcribe recent videos
              </label>
              <div className="text-[0.62rem] font-bold text-[#374151] uppercase tracking-[0.06em] mb-[4px]">Videos to transcribe</div>
              <div className="flex items-center gap-[8px] mb-[8px]">
                <input
                  type="range"
                  min={0}
                  max={3}
                  step={1}
                  value={transcribeVideos ? transcriptLimit : 0}
                  disabled={!transcribeVideos}
                  onChange={(e) => setTranscriptLimit(Number(e.target.value))}
                  className="flex-1 h-[3px]"
                />
                <span className="text-[0.68rem] text-[#6b7280] font-semibold min-w-[32px]">{transcribeVideos ? transcriptLimit : 0}</span>
              </div>
              <p className="text-[0.62rem] text-[#6b7280] mb-[8px]">
                Adds separate Transcript rows for up to 10 minutes of each selected recent video. Capped at 3 recent videos.
              </p>
            </>
          )}
          {error && (
            <div className="text-[0.65rem] text-[#dc2626] bg-[#fef2f2] rounded-[6px] px-[10px] py-[7px] mb-[8px] border border-[#fecaca]">
              {error}
            </div>
          )}
          <button
            onClick={handleAnalyze}
            disabled={!channelUrl.trim() || (!isVideoUrl && !apiKey.trim()) || loading}
            className="w-full bg-gradient-to-r from-[#0F766E] to-[#1D9E75] text-white border-none rounded-[7px] py-[7px] text-[0.72rem] font-semibold cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? (isVideoUrl ? 'Transcribing up to 10 minutes...' : 'Analysing...') : (isVideoUrl ? 'Transcribe and Analyse Video' : 'Analyse YouTube Channel')}
          </button>
        </div>

        <div className="bg-white rounded-xl border border-[rgba(229,231,235,0.7)] overflow-hidden">
          <div className="flex bg-[#f8fafc] border-b border-[#f1f5f9] px-[14px] overflow-x-auto">
            {(['timeline', 'posts', 'socio'] as const).map((tab) => (
              <div
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`py-[10px] px-[14px] text-[0.7rem] cursor-pointer border-b-2 transition-colors ${
                  activeTab === tab
                    ? 'text-[#0F766E] border-[#0F766E] font-semibold'
                    : 'text-[#94a3b8] border-transparent font-medium hover:text-[#6b7280]'
                }`}
              >
                {tab === 'timeline' ? 'Timeline' : tab === 'posts' ? 'Posts' : 'Socio-Economic'}
              </div>
            ))}
          </div>
          <div className="p-[14px_16px]">
            {loading ? (
              <LoadingSpinner text={isVideoUrl ? 'Downloading audio, transcribing up to 10 minutes, then analysing...' : transcribeVideos ? `Fetching channel data and transcribing ${transcriptLimit} recent video${transcriptLimit === 1 ? '' : 's'}...` : 'Fetching and analysing YouTube titles, descriptions, and comments...'} />
            ) : !result ? (
              <div className="flex flex-col items-center justify-center h-[200px] text-[#c4c9d0] gap-[5px]">
                <i className="ti ti-brand-youtube text-[22px]" />
                <span className="text-[0.65rem]">Enter a channel or video URL and click Analyse</span>
              </div>
            ) : (
              <>
                {activeTab === 'timeline' && (
                  <>
                    <OverallBanner result={result} />
                    <div className="mt-[10px]">
                      <TimelineChart posts={result.df} />
                    </div>
                  </>
                )}
                {activeTab === 'posts' && (
                  <>
                    <p className="mb-[12px] text-[0.72rem] text-[#64748b]">
                      Source types are shown on each card: Title/Description, Comment, or Transcript.
                    </p>
                    <PostCards posts={result.df.filter((p) => p.risk_score >= result.min_risk)} n={result.n_show} />
                  </>
                )}
                {activeTab === 'socio' && <SocioEconomicPanel signals={result.signals} />}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
