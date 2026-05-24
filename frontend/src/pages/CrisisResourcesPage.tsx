import { useState, useEffect } from 'react'
import { getResources, getStateResources } from '../api/resources'
import type { CrisisResource } from '../types'

const USA_STATE_OPTION = 'USA \u2014 Select a State'
const COUNTRIES = ['Kenya', 'USA (National)', 'UK', 'Australia', 'Canada', 'International', USA_STATE_OPTION]
const USA_NATIONAL_RESOURCES: CrisisResource[] = [
  { name: '988 Suicide & Crisis Lifeline', contact: 'Call/text 988', type: 'Crisis line' },
  { name: 'Crisis Text Line', contact: 'Text HOME to 741741', type: 'Text-based' },
  { name: 'NAMI Helpline', contact: '1-800-950-6264', type: 'Mental health' },
  { name: 'SAMHSA Helpline', contact: '1-800-662-4357', type: 'Substance abuse & mental health' },
  { name: 'Veterans Crisis Line', contact: 'Call 988, press 1', type: 'Veterans' },
  { name: 'Trevor Project (LGBTQ+ youth)', contact: '1-866-488-7386', type: 'Youth crisis' },
]

export default function CrisisResourcesPage() {
  const [resources, setResources] = useState<Record<string, CrisisResource[]>>({})
  const [stateResources, setStateResources] = useState<Record<string, CrisisResource[]>>({})
  const [selectedCountry, setSelectedCountry] = useState('Kenya')
  const [selectedState, setSelectedState] = useState('Alabama')

  useEffect(() => {
    getResources().then(setResources).catch((e) => console.error('Failed to load resources:', e))
    getStateResources().then(setStateResources).catch((e) => console.error('Failed to load state resources:', e))
  }, [])

  const isUsaStateMode = selectedCountry === USA_STATE_OPTION
  const stateList = Object.keys(stateResources).sort()
  const nationalResources = resources['USA (National)']?.length ? resources['USA (National)'] : USA_NATIONAL_RESOURCES
  const countryResources = resources[selectedCountry] || []
  const selectedStateResources = stateResources[selectedState] || []

  return (
    <div className="flex flex-col gap-[18px]">
      <div>
        <h2 className="text-[1.15rem] font-bold text-[#111827]">Crisis Resources</h2>
        <p className="text-[0.78rem] text-[#4b5563] mt-[26px]">
          Select your country or US state to see local crisis resources.
        </p>
      </div>

      <div className="border-t border-[#d1d5db]" />

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-[20px] items-start">
        <section className="flex flex-col gap-[18px]">
          <label className="flex flex-col gap-[8px] text-[0.82rem] text-[#4b5563]">
            Country / Region
            <select
              value={selectedCountry}
              onChange={(e) => {
                setSelectedCountry(e.target.value)
                if (e.target.value === USA_STATE_OPTION && !selectedState) setSelectedState('Alabama')
              }}
              className="w-full bg-white border border-[#d1d5db] rounded-[8px] px-[16px] py-[12px] text-[0.9rem] text-[#111827] outline-none focus:border-[#0F766E] focus:ring-2 focus:ring-[#14b8a633]"
            >
              {COUNTRIES.map((country) => (
                <option key={country} value={country}>{country}</option>
              ))}
            </select>
          </label>

          {isUsaStateMode && (
            <>
              <div className="border-t border-[#d1d5db]" />
              <label className="flex flex-col gap-[8px] text-[0.82rem] text-[#4b5563]">
                Select your state
                <select
                  value={selectedState}
                  onChange={(e) => setSelectedState(e.target.value)}
                  className="w-full bg-white border border-[#d1d5db] rounded-[8px] px-[16px] py-[12px] text-[0.9rem] text-[#111827] outline-none focus:border-[#0F766E] focus:ring-2 focus:ring-[#14b8a633]"
                >
                  {stateList.map((state) => (
                    <option key={state} value={state}>{state}</option>
                  ))}
                </select>
              </label>
            </>
          )}

          {isUsaStateMode ? (
            <div className="flex flex-col gap-[10px]">
              <h3 className="text-[0.9rem] font-bold uppercase text-[#4b5563]">Resources for {selectedState}</h3>
              <ResourceSection title="National (available in all states)" resources={nationalResources} borderColor="#0d9488" />
              <ResourceSection title={`State-specific \u2014 ${selectedState}`} resources={selectedStateResources} borderColor="#7c3aed" />
            </div>
          ) : (
            <div className="flex flex-col gap-[10px]">
              {countryResources.map((resource, index) => (
                <ResourceCard key={`${resource.name}-${index}`} resource={resource} borderColor="#0d9488" />
              ))}
            </div>
          )}

          <div className="mt-[10px] rounded-[8px] border border-[#fecaca] bg-[#fef2f2] px-[14px] py-[12px]">
            <p className="text-[#991b1b] text-[0.76rem] leading-[1.55] m-0">
              If someone is in immediate danger, call emergency services immediately. MindGuard is a research tool - it does not replace clinical assessment.
            </p>
          </div>
        </section>

        <section className="bg-white border border-[#d1d5db] rounded-[10px] p-[20px_22px]">
          <h3 className="text-[1rem] font-bold text-[#111827] mb-[18px]">About MindGuard</h3>
          <div className="text-[0.78rem] text-[#4b5563] leading-[1.65] space-y-[12px]">
            <InfoBlock title="What is MindGuard?">
              MindGuard is a consent-first, human-in-the-loop clinical decision-support system designed to help trained mental health professionals identify early signals of suicidal ideation in consented digital text. It is not a diagnostic tool and does not replace clinical judgment - it is built to surface meaningful signals earlier than traditional screening methods allow, giving counsellors and school psychologists a structured, evidence-based starting point for follow-up.
            </InfoBlock>
            <InfoBlock title="Model Architecture">
              MindGuard is powered by Mental-RoBERTa (mental/mental-roberta-base), a transformer pre-trained on millions of mental health domain posts from communities including r/SuicideWatch, r/depression, and r/anxiety. Unlike general-purpose sentiment tools, Mental-RoBERTa understands the nuanced language of psychological distress. The model was fine-tuned on 12,656 annotated posts using a stratified 75/10/15 train-validation-test split, achieving a ROC-AUC of 0.9813 and an accuracy of 92.5%, outperforming both a general RoBERTa baseline and a custom Bi-LSTM model on every evaluation metric.
            </InfoBlock>
            <InfoBlock title="Risk Tiers">
              Low &lt;35% &middot; Moderate 35-55% &middot; High 55-75% &middot; Critical &gt;75%
            </InfoBlock>
            <InfoBlock title="How It Works">
              Every output produced by MindGuard is reviewed by a qualified professional before any action is taken. No automated alerts are sent, no autonomous outreach occurs, and no data is stored between sessions. The system operates across nine digital platforms and is designed to integrate into existing counselling workflows rather than replace them.
            </InfoBlock>
          </div>
        </section>
      </div>
    </div>
  )
}

function ResourceSection({
  title,
  resources,
  borderColor,
}: {
  title: string
  resources: CrisisResource[]
  borderColor: string
}) {
  return (
    <div className="flex flex-col gap-[10px]">
      <p className="text-[0.72rem] font-semibold text-[#4b5563] mt-[4px] mb-0">{title}</p>
      {resources.map((resource, index) => (
        <ResourceCard key={`${resource.name}-${index}`} resource={resource} borderColor={borderColor} />
      ))}
    </div>
  )
}

function ResourceCard({ resource, borderColor }: { resource: CrisisResource; borderColor: string }) {
  return (
    <div
      className="bg-white border border-[#d1d5db] rounded-[8px] px-[16px] py-[12px] shadow-[0_10px_26px_rgba(15,23,42,0.05)] border-l-[5px]"
      style={{ borderLeftColor: borderColor }}
    >
      <div className="text-[0.8rem] font-bold text-[#111827]">{resource.name}</div>
      <div className="text-[0.7rem] text-[#64748b] mt-[8px]">{resource.type}</div>
      <a
        href={contactHref(resource.contact)}
        className="inline-block text-[0.74rem] text-[#0f766e] font-bold underline mt-[6px]"
      >
        {resource.contact}
      </a>
    </div>
  )
}

function InfoBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[0.7rem] font-bold text-[#4b5563] uppercase mb-[6px]">{title}</div>
      <p className="m-0">{children}</p>
    </div>
  )
}

function contactHref(contact: string) {
  if (contact.startsWith('http')) return contact
  const phone = contact.match(/[+\d][\d\s().-]{5,}/)?.[0]
  if (phone) return `tel:${phone.replace(/[^\d+]/g, '')}`
  return '#'
}
