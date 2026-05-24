import type { PostData } from '../../types'
import { formatPercent, getRiskLabel } from '../../types'

interface PostCardsProps {
  posts: PostData[]
  n?: number
}

export default function PostCards({ posts, n = 20 }: PostCardsProps) {
  const displayed = posts.slice(0, n)

  if (displayed.length === 0) {
    return (
      <div className="text-center py-[40px] text-[#9ca3af] text-[0.82rem]">
        No posts match the current filter.
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-[8px]">
      {displayed.map((post, i) => {
        const { color } = getRiskLabel(post.risk_score)
        const sourceStyle = getSourceStyle(post.type)
        return (
          <div
            key={i}
            className="bg-white rounded-[8px] border border-[#f1f5f9] p-[12px_14px] border-l-[4px]"
            style={{ borderLeftColor: color }}
          >
            <div className="flex items-center gap-[8px] mb-[6px] flex-wrap">
              {post.subreddit && (
                <span className="text-[0.7rem] text-[#0F766E] font-semibold">r/{post.subreddit}</span>
              )}
              {post.type && (
                <span
                  className="text-[0.62rem] px-[7px] py-[2px] rounded-full font-semibold"
                  style={{ backgroundColor: sourceStyle.bg, color: sourceStyle.color, border: `1px solid ${sourceStyle.border}` }}
                >
                  {post.type}
                </span>
              )}
              {post.low_context && (
                <span className="text-[0.62rem] text-[#92400e] bg-[#fffbeb] border border-[#fde68a] px-[7px] py-[2px] rounded-full font-semibold">
                  Low context
                </span>
              )}
              <span className="text-[0.62rem] text-[#9ca3af]">
                {post.date ? new Date(post.date).toLocaleDateString() : ''}
              </span>
              <span className="text-[0.74rem] font-bold ml-auto" style={{ color }}>
                {formatPercent(post.risk_score)} - {getRiskLabel(post.risk_score).label}
              </span>
            </div>
            <p className="text-[0.8rem] text-[#4b5563] leading-[1.6]">{post.text.length > 250 ? `${post.text.slice(0, 250)}...` : post.text}</p>
            {post.adjustment_reason && (
              <p className="mt-[6px] text-[0.66rem] text-[#92400e] leading-[1.45]">
                {post.adjustment_reason}
              </p>
            )}
            <div className="flex items-center gap-[8px] mt-[6px]">
              {post.url && (
                <a
                  href={post.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[0.68rem] text-[#0F766E] ml-auto hover:underline"
                >
                  View source →
                </a>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function getSourceStyle(type?: string) {
  if (type === 'Transcript') return { bg: '#ecfeff', color: '#0e7490', border: '#67e8f9' }
  if (type === 'Comment') return { bg: '#fff7ed', color: '#c2410c', border: '#fed7aa' }
  if (type === 'Title/Description') return { bg: '#eef2ff', color: '#4338ca', border: '#c7d2fe' }
  return { bg: '#f1f5f9', color: '#64748b', border: '#e2e8f0' }
}
