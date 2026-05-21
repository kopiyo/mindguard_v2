interface GaugeChartProps {
  prob: number
}

export default function GaugeChart({ prob }: GaugeChartProps) {
  const isRisk = prob >= 0.5
  const pct = Math.min(prob * 100, 100)
  const color = isRisk ? '#dc2626' : '#0F6E56'

  const circumference = 176

  return (
    <div className="flex flex-col items-center">
      <svg className="w-[160px] h-[90px]" viewBox="0 0 160 90">
        <defs>
          <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#22c55e" />
            <stop offset="35%" stopColor="#f59e0b" />
            <stop offset="55%" stopColor="#f97316" />
            <stop offset="100%" stopColor="#ef4444" />
          </linearGradient>
        </defs>
        {/* Track arc */}
        <path
          d="M 12 84 A 64 64 0 0 1 148 84"
          fill="none"
          stroke="#f1f5f9"
          strokeWidth="12"
          strokeLinecap="round"
        />
        {/* Fill arc - grows from left (green) to right (red) */}
        <path
          d="M 12 84 A 64 64 0 0 1 148 84"
          fill="none"
          stroke="url(#gaugeGrad)"
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={`${(pct / 100) * circumference} ${circumference}`}
        />
        {/* Needle */}
        <line
          x1="80"
          y1="84"
          x2={80 + 62 * Math.cos(Math.PI - (pct / 100) * Math.PI)}
          y2={84 - 62 * Math.sin(Math.PI - (pct / 100) * Math.PI)}
          stroke={color}
          strokeWidth="2.5"
          strokeLinecap="round"
        />
        <circle cx="80" cy="84" r="6" fill={color} />
        <text x="80" y="70" textAnchor="middle" fontSize="18" fontWeight="800" fill={color}>
          {(prob * 100).toFixed(1)}%
        </text>
      </svg>
      <div
        className="mt-[8px] px-[16px] py-[5px] rounded-full text-[0.8rem] font-bold"
        style={{
          background: isRisk ? '#fef2f2' : '#f0fdf4',
          color: isRisk ? '#991b1b' : '#166534',
        }}
      >
        {isRisk ? 'Suicidal / High Risk' : 'Non-Suicidal / Low Risk'}
      </div>
    </div>
  )
}
