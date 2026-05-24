import { useState } from 'react'
import { usePlatformStore } from '../store'
import { analyzeFacebook } from '../api/analysis'
import TimelineChart from '../components/analysis/TimelineChart'
import PostCards from '../components/analysis/PostCards'
import OverallBanner from '../components/analysis/OverallBanner'
import SocioEconomicPanel from '../components/analysis/SocioEconomicPanel'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import type { PlatformResult } from '../types'

export default function FacebookPage() {
  const [profileUrl, setProfileUrl] = useState('')
  const [months, setMonths] = useState(3)
  const [minRisk, setMinRisk] = useState(0)
  const [nShow, setNShow] = useState(20)
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [activeTab, setActiveTab] = useState<'timeline' | 'posts' | 'socio'>('timeline')
  const { facebook, loading, setPlatformResult } = usePlatformStore()

  const handleAnalyze = async () => {
    const url = profileUrl.trim()
    if (!url) {
      setError('Enter a Facebook profile URL.')
      return
    }
    if (!url.toLowerCase().includes('facebook.com')) {
      setError('Enter a full Facebook URL e.g. https://www.facebook.com/username')
      return
    }

    setError('')
    setInfo(`Headless browser starting - scraping ${url} ...`)
    try {
      usePlatformStore.getState().setLoading(true)
      setPlatformResult('facebook', null)
      const result = await analyzeFacebook(url, months, minRisk, nShow)
      setPlatformResult('facebook', result)
      setActiveTab('timeline')
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Scraping failed')
    } finally {
      setInfo('')
      usePlatformStore.getState().setLoading(false)
    }
  }

  const result = facebook as PlatformResult | null
  const filteredPosts = result?.df.filter((p) => p.risk_score >= result.min_risk) ?? []
  const shownPosts = result ? Math.min(filteredPosts.length, result.n_show) : 0

  return (
    <div className="flex flex-col gap-[18px]">
      <div>
        <h2 className="text-[1.15rem] font-bold text-[#111827]">Facebook Public Profile Analysis</h2>
        <p className="text-[0.78rem] text-[#4b5563] mt-[14px]">
          Scrapes public posts from a Facebook profile using a headless browser. Only works for profiles with public post visibility.
        </p>
        <div className="mt-[8px] rounded-[7px] border border-[#f8d38b] bg-[#fff7e6] px-[14px] py-[10px] text-[0.76rem] text-[#4b5563]">
          Only publicly visible posts are accessed. Research use under ethics approval TUM-SERC MSC/028/2025A.
        </div>
      </div>

      <div className="border-t border-[#d1d5db]" />

      <div className="grid grid-cols-1 lg:grid-cols-[460px_1fr] gap-[32px] items-start">
        <section className="flex flex-col gap-[14px]">
          <label className="flex flex-col gap-[6px] text-[0.78rem] text-[#4b5563]">
            Facebook profile URL
            <input
              type="text"
              value={profileUrl}
              onChange={(e) => setProfileUrl(e.target.value)}
              placeholder="https://www.facebook.com/username"
              className="w-full bg-white border border-[#d1d5db] rounded-[7px] px-[12px] py-[10px] text-[0.82rem] text-[#111827] outline-none focus:border-[#0F766E]"
            />
          </label>

          <Slider label="Months to analyse" value={months} min={1} max={6} step={1} display={String(months)} onChange={setMonths} />
          <Slider label="Show posts above risk score" value={minRisk} min={0} max={1} step={0.05} display={minRisk.toFixed(2)} onChange={setMinRisk} />
          <Slider label="Max posts to display" value={nShow} min={5} max={50} step={5} display={String(nShow)} onChange={setNShow} />
          <p className="mt-[-8px] text-[0.68rem] text-[#64748b]">
            Display limit only. Facebook may expose fewer public posts to the scraper.
          </p>

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
          {loading && <LoadingSpinner text="This takes 30-60 seconds. Please wait..." />}
          {error && (
            <>
              <div className="rounded-[7px] bg-[#fee2e2] px-[14px] py-[12px] text-[0.82rem] text-[#4b5563] border border-[#fecaca]">
                Scraping failed: {error}
              </div>
              <p className="text-[0.72rem] text-[#4b5563]">
                Common causes: profile is private, Facebook blocked the request, the URL is incorrect, or Playwright is not installed.
              </p>
            </>
          )}
        </section>

        <section className="min-h-[260px]">
          {!loading && !result ? (
            <div className="h-[260px] flex flex-col items-center justify-center text-center text-[#4b5563]">
              <p className="text-[0.9rem]">Enter a public Facebook profile URL and click Scrape and Analyse.</p>
              <p className="text-[0.72rem] mt-[10px]">Only public posts are accessible.</p>
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
                    <OverallBanner result={result} period={`${months} months`} />
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
