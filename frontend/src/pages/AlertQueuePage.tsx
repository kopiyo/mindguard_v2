import { useEffect, useState } from 'react'
import { getAlerts, disposeAlert } from '../api/counsellor'
import { getRiskLabel } from '../types'
import type { Alert, AlertDisposition } from '../types'

function formatRelative(d: string) {
  const diff = Date.now() - new Date(d).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function formatFull(d: string) {
  return new Date(d).toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

const DISMISS_REASONS = [
  { code: 'FALSE_POSITIVE_CONTEXT', label: 'False positive — context' },
  { code: 'ALREADY_IN_CARE', label: 'Already in care' },
  { code: 'PARENT_ENGAGED', label: 'Parent already engaged' },
  { code: 'OTHER', label: 'Other' },
]

function RiskBadge({ score }: { score: number }) {
  const { label, color } = getRiskLabel(score)
  return (
    <span
      className="px-[8px] py-[2px] rounded-full text-[0.7rem] font-semibold text-white"
      style={{ backgroundColor: color }}
    >
      {(score * 100).toFixed(0)}% · {label}
    </span>
  )
}

function AlertPanel({
  alert,
  onClose,
  onDisposed,
}: {
  alert: Alert
  onClose: () => void
  onDisposed: () => void
}) {
  const isOpen = alert.status === 'OPEN'
  const [escalateNote, setEscalateNote] = useState('')
  const [dismissReason, setDismissReason] = useState<string>('')
  const [dismissNote, setDismissNote] = useState('')
  const [activeAction, setActiveAction] = useState<AlertDisposition | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { color } = getRiskLabel(alert.risk_score)

  const handleAction = async (action: AlertDisposition, reasonCode: string, note?: string) => {
    setSubmitting(true)
    setError(null)
    try {
      await disposeAlert(alert.id, { action, reason_code: reasonCode, reason_note: note })
      onDisposed()
      onClose()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div className="flex-1 bg-black/30" onClick={onClose} />

      {/* Panel */}
      <div className="w-[420px] bg-white h-full shadow-2xl flex flex-col overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-[20px] py-[14px] border-b border-[#f1f5f9]">
          <h3 className="text-[0.95rem] font-bold text-[#1f2937]">Alert Detail</h3>
          <button
            onClick={onClose}
            className="text-[#9ca3af] hover:text-[#6b7280] cursor-pointer bg-transparent border-none"
          >
            <i className="ti ti-x text-[18px]" />
          </button>
        </div>

        <div className="flex flex-col gap-[16px] p-[20px]">
          {/* Student info */}
          <div className="flex items-center gap-[12px]">
            <div className="w-[40px] h-[40px] rounded-full bg-gradient-to-br from-[#0F766E] to-[#1D9E75] flex items-center justify-center text-white font-bold text-[0.9rem] flex-shrink-0">
              {(alert.student_name || 'S').charAt(0).toUpperCase()}
            </div>
            <div>
              <div className="text-[0.9rem] font-semibold text-[#1f2937]">
                {alert.student_name || alert.student_id}
              </div>
              {alert.student_email && (
                <div className="text-[0.75rem] text-[#6b7280]">{alert.student_email}</div>
              )}
            </div>
          </div>

          {/* Risk score bar */}
          <div>
            <div className="flex items-center justify-between mb-[6px]">
              <span className="text-[0.78rem] text-[#6b7280] font-medium">Risk Score</span>
              <RiskBadge score={alert.risk_score} />
            </div>
            <div className="h-[8px] rounded-full bg-[#f1f5f9] overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${alert.risk_score * 100}%`, backgroundColor: color }}
              />
            </div>
            <div className="text-[0.7rem] text-[#9ca3af] mt-[4px]">
              Threshold at fire: {(alert.threshold_at_fire * 100).toFixed(0)}%
            </div>
          </div>

          {/* Meta */}
          <div className="grid grid-cols-2 gap-[10px] text-[0.82rem]">
            {alert.platform && (
              <div>
                <div className="text-[#6b7280] text-[0.72rem] uppercase tracking-wide font-semibold mb-[2px]">Platform</div>
                <div className="text-[#1f2937] font-medium capitalize">{alert.platform}</div>
              </div>
            )}
            <div>
              <div className="text-[#6b7280] text-[0.72rem] uppercase tracking-wide font-semibold mb-[2px]">Fired At</div>
              <div className="text-[#1f2937] font-medium">{formatFull(alert.fired_at)}</div>
            </div>
            <div>
              <div className="text-[#6b7280] text-[0.72rem] uppercase tracking-wide font-semibold mb-[2px]">Status</div>
              <div className={`inline-block px-[8px] py-[2px] rounded-full text-[0.7rem] font-semibold ${
                alert.status === 'OPEN' ? 'bg-[#fef3c7] text-[#92400e]' : 'bg-[#f1f5f9] text-[#6b7280]'
              }`}>
                {alert.status}
              </div>
            </div>
          </div>

          {/* Closed alert: show disposition */}
          {!isOpen && alert.disposition && (
            <div className="rounded-[8px] bg-[#f1f5f9] px-[14px] py-[10px] text-[0.82rem]">
              <span className="text-[#6b7280]">Dispositioned: </span>
              <span className="font-semibold text-[#1f2937] capitalize">
                {alert.disposition.replace(/_/g, ' ').toLowerCase()}
              </span>
              {alert.dispositioned_at && (
                <span className="text-[#9ca3af]"> on {formatFull(alert.dispositioned_at)}</span>
              )}
              {alert.disposition_note && (
                <div className="mt-[4px] text-[#6b7280]">Note: {alert.disposition_note}</div>
              )}
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="flex items-center gap-[6px] text-[#ef4444] text-[0.82rem]">
              <i className="ti ti-alert-circle" /> {error}
            </div>
          )}

          {/* Actions — only for OPEN alerts */}
          {isOpen && (
            <div className="flex flex-col gap-[10px]">
              <div className="text-[0.78rem] font-semibold text-[#6b7280] uppercase tracking-wide">Actions</div>

              {/* Reach Out */}
              <button
                onClick={() => handleAction('REACH_OUT', 'REACH_OUT')}
                disabled={submitting}
                className="flex items-center gap-[8px] px-[14px] py-[10px] bg-[#d1fae5] text-[#065f46] rounded-[8px] text-[0.82rem] font-semibold cursor-pointer hover:bg-[#a7f3d0] transition-colors border border-[#6ee7b7] disabled:opacity-50"
              >
                <i className="ti ti-phone text-[16px]" />
                Review &amp; Reach Out
              </button>

              {/* Schedule Check-in */}
              <button
                onClick={() => handleAction('SCHEDULE_CHECKIN', 'SCHEDULE_CHECKIN')}
                disabled={submitting}
                className="flex items-center gap-[8px] px-[14px] py-[10px] bg-[#dbeafe] text-[#1e40af] rounded-[8px] text-[0.82rem] font-semibold cursor-pointer hover:bg-[#bfdbfe] transition-colors border border-[#93c5fd] disabled:opacity-50"
              >
                <i className="ti ti-calendar text-[16px]" />
                Schedule Check-in
              </button>

              {/* Escalate */}
              {activeAction === 'ESCALATE' ? (
                <div className="flex flex-col gap-[6px]">
                  <textarea
                    value={escalateNote}
                    onChange={(e) => setEscalateNote(e.target.value)}
                    placeholder="Add escalation note..."
                    rows={2}
                    className="w-full rounded-[8px] border border-[#e5e7eb] px-[10px] py-[6px] text-[0.8rem] text-[#1f2937] placeholder-[#9ca3af] resize-none focus:outline-none focus:ring-2 focus:ring-[#f97316] focus:border-transparent"
                  />
                  <div className="flex gap-[6px]">
                    <button
                      onClick={() => handleAction('ESCALATE', 'ESCALATE', escalateNote)}
                      disabled={submitting}
                      className="flex-1 px-[10px] py-[6px] bg-[#f97316] text-white rounded-[7px] text-[0.78rem] font-semibold cursor-pointer hover:bg-[#ea6c00] transition-colors disabled:opacity-50"
                    >
                      {submitting ? 'Escalating...' : 'Confirm Escalate'}
                    </button>
                    <button
                      onClick={() => setActiveAction(null)}
                      className="px-[10px] py-[6px] border border-[#e5e7eb] text-[#6b7280] rounded-[7px] text-[0.78rem] cursor-pointer hover:bg-[#f9fafb] bg-white"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setActiveAction('ESCALATE')}
                  disabled={submitting}
                  className="flex items-center gap-[8px] px-[14px] py-[10px] bg-[#fff7ed] text-[#9a3412] rounded-[8px] text-[0.82rem] font-semibold cursor-pointer hover:bg-[#ffedd5] transition-colors border border-[#fdba74] disabled:opacity-50"
                >
                  <i className="ti ti-urgent text-[16px]" />
                  Escalate
                </button>
              )}

              {/* Dismiss */}
              {activeAction === 'DISMISS' ? (
                <div className="flex flex-col gap-[6px]">
                  <select
                    value={dismissReason}
                    onChange={(e) => setDismissReason(e.target.value)}
                    className="w-full rounded-[8px] border border-[#e5e7eb] px-[10px] py-[7px] text-[0.8rem] text-[#1f2937] bg-white focus:outline-none focus:ring-2 focus:ring-[#6b7280]"
                  >
                    <option value="">Select reason...</option>
                    {DISMISS_REASONS.map((r) => (
                      <option key={r.code} value={r.code}>{r.label}</option>
                    ))}
                  </select>
                  {dismissReason === 'OTHER' && (
                    <textarea
                      value={dismissNote}
                      onChange={(e) => setDismissNote(e.target.value)}
                      placeholder="Describe reason..."
                      rows={2}
                      className="w-full rounded-[8px] border border-[#e5e7eb] px-[10px] py-[6px] text-[0.8rem] text-[#1f2937] placeholder-[#9ca3af] resize-none focus:outline-none focus:ring-2 focus:ring-[#6b7280]"
                    />
                  )}
                  <div className="flex gap-[6px]">
                    <button
                      onClick={() => handleAction('DISMISS', dismissReason, dismissReason === 'OTHER' ? dismissNote : undefined)}
                      disabled={submitting || !dismissReason}
                      className="flex-1 px-[10px] py-[6px] bg-[#6b7280] text-white rounded-[7px] text-[0.78rem] font-semibold cursor-pointer hover:bg-[#4b5563] transition-colors disabled:opacity-50"
                    >
                      {submitting ? 'Dismissing...' : 'Confirm Dismiss'}
                    </button>
                    <button
                      onClick={() => { setActiveAction(null); setDismissReason(''); setDismissNote('') }}
                      className="px-[10px] py-[6px] border border-[#e5e7eb] text-[#6b7280] rounded-[7px] text-[0.78rem] cursor-pointer hover:bg-[#f9fafb] bg-white"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setActiveAction('DISMISS')}
                  disabled={submitting}
                  className="flex items-center gap-[8px] px-[14px] py-[10px] bg-[#f9fafb] text-[#6b7280] rounded-[8px] text-[0.82rem] font-semibold cursor-pointer hover:bg-[#f1f5f9] transition-colors border border-[#e5e7eb] disabled:opacity-50"
                >
                  <i className="ti ti-ban text-[16px]" />
                  Dismiss
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function AlertQueuePage() {
  const [tab, setTab] = useState<'OPEN' | 'CLOSED'>('OPEN')
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Alert | null>(null)

  const load = async (status: 'OPEN' | 'CLOSED') => {
    setLoading(true)
    setError(null)
    try {
      const data = await getAlerts(status)
      setAlerts(data)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(tab)
  }, [tab])

  const handleDisposed = () => {
    load(tab)
  }

  return (
    <div className="flex flex-col gap-[16px]">
      <div>
        <h2 className="text-[1.3rem] font-bold text-[#1f2937]">Alert Queue</h2>
        <p className="text-[0.82rem] text-[#6b7280] mt-[2px]">
          Risk alerts triggered for your students
        </p>
      </div>

      {/* Tab bar */}
      <div className="flex items-center gap-[2px] bg-[#f1f5f9] rounded-[8px] p-[4px] w-fit">
        {(['OPEN', 'CLOSED'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-[14px] py-[6px] rounded-[6px] text-[0.8rem] font-semibold cursor-pointer transition-colors border-none ${
              tab === t
                ? 'bg-white text-[#1f2937] shadow-sm'
                : 'bg-transparent text-[#6b7280] hover:text-[#374151]'
            }`}
          >
            {t === 'OPEN' ? 'Open' : 'Closed'}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-[rgba(229,231,235,0.7)] overflow-hidden">
        <div className="flex items-center justify-between px-[20px] py-[14px] border-b border-[#f1f5f9]">
          <div className="flex items-center gap-[8px]">
            <i className="ti ti-bell-ringing text-[16px] text-[#6b7280]" />
            <span className="text-[0.9rem] font-bold text-[#1f2937]">
              {tab === 'OPEN' ? 'Open' : 'Closed'} Alerts
            </span>
            {!loading && (
              <span className="text-[0.78rem] text-[#9ca3af] ml-[4px]">({alerts.length})</span>
            )}
          </div>
          <button
            onClick={() => load(tab)}
            className="flex items-center gap-[6px] px-[12px] py-[6px] bg-[#0F766E] text-white rounded-[7px] text-[0.78rem] font-semibold cursor-pointer hover:bg-[#115E59] transition-colors"
          >
            <i className="ti ti-refresh text-[14px]" />
            Refresh
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-[60px] text-[#6b7280]">
            <div className="w-[24px] h-[24px] border-2 border-[#e5e7eb] border-t-[#0F766E] rounded-full animate-spin mr-[10px]" />
            <span className="text-[0.82rem]">Loading alerts...</span>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-[60px] text-[#ef4444]">
            <i className="ti ti-alert-circle text-[32px] mb-[8px]" />
            <span className="text-[0.82rem]">{error}</span>
          </div>
        ) : alerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-[60px] text-[#9ca3af]">
            <i className="ti ti-bell-off text-[32px] mb-[8px]" />
            <span className="text-[0.82rem]">No {tab.toLowerCase()} alerts</span>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[0.82rem]">
              <thead className="bg-[#f9fafb]">
                <tr className="text-[#6b7280] font-semibold text-[0.72rem] uppercase tracking-wider">
                  <th className="text-left py-[10px] px-[20px]">Student</th>
                  <th className="text-left py-[10px] px-[20px]">Platform</th>
                  <th className="text-left py-[10px] px-[20px]">Risk Score</th>
                  <th className="text-left py-[10px] px-[20px]">Fired At</th>
                  <th className="text-left py-[10px] px-[20px]">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f1f5f9]">
                {alerts.map((alert) => (
                  <tr
                    key={alert.id}
                    onClick={() => setSelected(alert)}
                    className="hover:bg-[#f8fafc] cursor-pointer transition-colors"
                  >
                    <td className="py-[12px] px-[20px] font-medium text-[#1f2937]">
                      {alert.student_name || alert.student_id}
                    </td>
                    <td className="py-[12px] px-[20px] text-[#6b7280] capitalize">
                      {alert.platform || '—'}
                    </td>
                    <td className="py-[12px] px-[20px]">
                      <RiskBadge score={alert.risk_score} />
                    </td>
                    <td className="py-[12px] px-[20px] text-[#6b7280]">
                      {formatRelative(alert.fired_at)}
                    </td>
                    <td className="py-[12px] px-[20px]">
                      <span className={`inline-block px-[8px] py-[2px] rounded-full text-[0.7rem] font-semibold ${
                        alert.status === 'OPEN'
                          ? 'bg-[#fef3c7] text-[#92400e]'
                          : 'bg-[#f1f5f9] text-[#6b7280]'
                      }`}>
                        {alert.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Side panel */}
      {selected && (
        <AlertPanel
          alert={selected}
          onClose={() => setSelected(null)}
          onDisposed={handleDisposed}
        />
      )}
    </div>
  )
}
