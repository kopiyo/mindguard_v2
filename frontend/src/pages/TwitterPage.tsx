import { useState } from 'react'
import { usePlatformStore } from '../store'
import { analyzeTwitter } from '../api/analysis'
import TimelineChart from '../components/analysis/TimelineChart'
import PostCards from '../components/analysis/PostCards'
import OverallBanner from '../components/analysis/OverallBanner'
import SocioEconomicPanel from '../components/analysis/SocioEconomicPanel'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import type { PlatformResult } from '../types'

export default function TwitterPage() {
  const [profileUrl, setProfileUrl] = useState('')
  const [minRisk, setMinRisk] = useState(0)
  const [nShow, setNShow] = useState(20)
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [activeTab, setActiveTab] = useState<'timeline' | 'posts' | 'socio'>('timeline')
  const { twitter, loading, setPlatformResult } = usePlatformStore()

  const handleAnalyze = async () => {
    const url = profileUrl.trim()
    if (!url) {
      setError('Enter a Twitter/X profile URL.')
      return
    }
    const lowered = url.toLowerCase()
    if (!lowered.includes('twitter.com') && !lowered.includes('x.com')) {
      setError('Enter a full Twitter/X URL e.g. https://x.com/username')
      return
    }

    setError('')
    setInfo(`Starting browser scrape of ${url}...`)
    try {
      usePlatformStore.getState().setLoading(true)
      setPlatformResult('twitter', null)
      const result = await analyzeTwitter(url, minRisk, nShow)
      setPlatformResult('twitter', result)
      setActiveTab('timeline')
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Twitter analysis failed')
    } finally {
      setInfo('')
      usePlatformStore.getState().setLoading(false)
    }
  }

  const result = twitter as PlatformResult | null
  const filteredPosts = result?.df.filter((p) => p.risk_score >= result.min_risk) ?? []
  const shownPosts = result ? Math.min(filteredPosts.length, result.n_show) : 0

  return (
    <div className="flex flex-col gap-[18px]">
      <div>
        <h2 className="text-[1.15rem] font-bold text-[#111827]">Twitter / X Public Profile Analysis</h2>
        <p className="text-[0.78rem] text-[#4b5563] mt-[14px]">
          Scrapes public tweets from a Twitter/X profile using a headless browser. Only works for public profiles.
        </p>
        <div className="mt-[8px] rounded-[7px] border border-[#f8d38b] bg-[#fff7e6] px-[14px] py-[10px] text-[0.76rem] text-[#4b5563]">
          Twitter/X increasingly requires login to view profiles. If scraping fails, use the File Upload tab with a Twitter data archive instead.
        </div>
      </div>

      <div className="border-t border-[#d1d5db]" />

      <div className="grid grid-cols-1 lg:grid-cols-[460px_1fr] gap-[32px] items-start">
        <section className="flex flex-col gap-[14px]">
          <label className="flex flex-col gap-[6px] text-[0.78rem] text-[#4b5563]">
            Twitter/X profile URL
            <input
              type="text"
              value={profileUrl}
              onChange={(e) => setProfileUrl(e.target.value)}
              placeholder="https://x.com/username"
              className="w-full bg-white border border-[#d1d5db] rounded-[7px] px-[12px] py-[10px] text-[0.82rem] text-[#111827] outline-none focus:border-[#0F766E]"
            />
          </label>

          <Slider label="Show posts above risk score" value={minRisk} min={0} max={1} step={0.05} display={minRisk.toFixed(2)} onChange={setMinRisk} />
          <Slider label="Max posts to display" value={nShow} min={5} max={50} step={5} display={String(nShow)} onChange={setNShow} />

          <button
            onClick={handleAnalyze}
            disabled={loading}
            className="w-full bg-[#0F766E] text-white border-none rounded-[7px] py-[12px] text-[0.86rem] font-semibold cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed shadow-[0_14px_26px_rgba(15,118,110,0.18)]"
          >
            Scrape and Analyse
          </button>

          {info && (
            <div className="rounded-[7px] bg-[#dbeafe] px-[14px] py-[12px] text-[0.82rem] text-[#4b5563]">
              {info}
            </div>
          )}
          {loading && <LoadingSpinner text="Opening headless browser and scraping..." />}
          {error && (
            <>
              <div className="rounded-[7px] bg-[#fee2e2] px-[14px] py-[12px] text-[0.82rem] text-[#4b5563] border border-[#fecaca]">
                Scraping failed: {error}
              </div>
              <p className="text-[0.72rem] text-[#4b5563]">
                Common causes: profile is private, Twitter/X requires login, the URL is incorrect, or Playwright is not installed.
              </p>
            </>
          )}
        </section>

        <section className="min-h-[260px]">
          {!loading && !result ? (
            <div className="h-[260px] flex flex-col items-center justify-center text-center text-[#4b5563]">
              <p className="text-[0.9rem]">Enter a public Twitter/X URL and click Scrape and Analyse.</p>
              <p className="text-[0.72rem] mt-[10px]">If login is required, use File Upload with a Twitter archive.</p>
            </div>
          ) : result ? (
            <div className="bg-white border border-[#d1d5db] rounded-[8px] overflow-hidden">
              <div className="flex bg-white px-[18px] overflow-x-auto border-b border-[#e5e7eb]">
                {(['timeline', 'posts', 'socio'] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-[18px] py-[12px] text-[0.78rem] border-b-2 ${
                      activeTab === tab
                        ? 'text-[#0F766E] border-[#0F766E] font-semibold'
                        : 'text-[#64748b] border-transparent hover:text-[#0F766E]'
                    }`}
                  >
                    {tab === 'timeline' ? 'Timeline' : tab === 'posts' ? 'Posts' : 'Socio-Economic'}
                  </button>
                ))}
              </div>
              <div className="p-[20px]">
                {activeTab === 'timeline' && (
                  <>
                    <OverallBanner result={result} />
                    <div className="mt-[16px]">
                      <TimelineChart posts={result.df} />
                    </div>
                  </>
                )}
                {activeTab === 'posts' && (
                  <>
                    <p className="mb-[12px] text-[0.72rem] text-[#64748b]">
                      Scraped {result.n_posts} public post{result.n_posts === 1 ? '' : 's'}.
                      {' '}Showing {shownPosts} of {filteredPosts.length} post{filteredPosts.length === 1 ? '' : 's'} matching the risk filter.
                      {' '}The max display setting is {result.n_show}.
                    </p>
                    <PostCards posts={filteredPosts} n={result.n_show} />
                  </>
                )}
                {activeTab === 'socio' && <SocioEconomicPanel signals={result.signals} />}
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </div>
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
    <label className="flex flex-col gap-[4px] text-[0.78rem] text-[#4b5563]">
      {label}
      <span className="text-[0.7rem] text-[#4b5563] text-center">{display}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-[#ef4444]"
      />
    </label>
  )
}
