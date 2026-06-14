import type { JobCard } from "./types.js"
import { htmlFetch } from "./http.js"
import { isRecent, isRecentHours, ldToJobCard, parseJobPostingLd } from "./jsonld.js"
import { normalizeKeyword } from "./http.js"

export function matchesKeyword(card: JobCard, keyword: string): boolean {
  const query = normalizeKeyword(keyword)
  if (!query) return true
  const haystack = `${card.title} ${card.company ?? ""} ${card.description ?? ""}`.toLowerCase()
  return haystack.includes(query.toLowerCase())
}

export async function fetchLdOffer(
  url: string,
  options: {
    keyword?: string
    days?: number
    maxAgeHours?: number
    strictFreshness?: boolean
    acceptLanguage?: string
  } = {},
): Promise<JobCard | null> {
  const { keyword = "", days = 0, maxAgeHours = 0, strictFreshness = false, acceptLanguage } = options
  const html = await htmlFetch(
    url,
    acceptLanguage ? { acceptLanguage } : undefined,
  )
  const ld = parseJobPostingLd(html)
  if (!ld) return null
  const datePosted = typeof ld.datePosted === "string" ? ld.datePosted : ""
  const fresh =
    maxAgeHours > 0
      ? isRecentHours(datePosted, maxAgeHours, strictFreshness)
      : isRecent(datePosted, days, strictFreshness)
  if (!fresh) return null
  const card = ldToJobCard(ld, url, url)
  if (!matchesKeyword(card, keyword)) return null
  return card
}
