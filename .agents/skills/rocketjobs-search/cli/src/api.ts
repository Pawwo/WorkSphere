import {
  excerpt,
  isRecent,
  isRecentHours,
  normalizeKeyword,
  type JobCard,
  type SearchResult,
} from "scraper-shared"

const API_BASE = "https://rocketjobs.pl/api/candidate-api/offers"

interface ApiEmploymentType {
  from?: number | null
  to?: number | null
  currency?: string
  type?: string
  unit?: string
  gross?: boolean
}

interface ApiOffer {
  slug: string
  title: string
  companyName?: string
  city?: string
  publishedAt?: string
  lastPublishedAt?: string
  workplaceType?: string
  employmentTypes?: ApiEmploymentType[]
  shortDescription?: string
  lead?: string
  description?: string
  snippet?: string
}

function apiOfferDescription(offer: ApiOffer): string {
  const candidates = [offer.shortDescription, offer.lead, offer.description, offer.snippet]
  for (const raw of candidates) {
    const text = (raw || "").trim()
    if (text && text !== offer.title.trim()) return excerpt(text, 300) ?? text
  }
  return offer.title
}

interface ApiResponse {
  data?: ApiOffer[]
  meta?: { totalItems?: number }
}

function formatSalary(types: ApiEmploymentType[] | undefined): string | null {
  if (!types?.length) return null
  const pln = types.find((t) => t.currency === "PLN" && (t.from || t.to))
  const pick = pln ?? types.find((t) => t.from || t.to)
  if (!pick) return null
  const parts: string[] = []
  if (pick.from) parts.push(String(pick.from))
  if (pick.to) parts.push(String(pick.to))
  const range = parts.join("–")
  const cur = pick.currency ?? "PLN"
  const gross = pick.gross ? " brutto" : ""
  return range ? `${range} ${cur}${gross}` : null
}

export function apiOfferToCard(offer: ApiOffer): JobCard {
  const url = `https://rocketjobs.pl/oferta-pracy/${offer.slug}`
  const dateRaw = offer.publishedAt ?? offer.lastPublishedAt ?? null
  const date = dateRaw ? dateRaw.slice(0, 10) : null
  const location = [offer.city, offer.workplaceType].filter(Boolean).join(" · ") || null
  return {
    id: offer.slug,
    title: offer.title,
    company: offer.companyName ?? null,
    location,
    date,
    deadline: null,
    salary: formatSalary(offer.employmentTypes),
    url,
    description: apiOfferDescription(offer),
  }
}

function isFresh(
  datePosted: string | undefined,
  days: number,
  maxAgeHours: number,
  strict: boolean,
): boolean {
  if (maxAgeHours > 0) return isRecentHours(datePosted, maxAgeHours, strict)
  if (days > 0) return isRecent(datePosted, days, strict)
  return true
}

export async function searchRocketJobsApi(
  keyword: string,
  limit: number,
  days: number,
  maxAgeHours = 0,
  strictFreshness = false,
): Promise<SearchResult> {
  const q = normalizeKeyword(keyword)
  const params = new URLSearchParams()
  if (q) params.set("keywords", q)
  params.set("limit", String(Math.min(Math.max(limit * 2, limit), 50)))

  const response = await fetch(`${API_BASE}?${params}`, {
    headers: {
      Accept: "application/json",
      Origin: "https://rocketjobs.pl",
      Referer: "https://rocketjobs.pl/oferty-pracy/wszystkie-lokalizacje",
    },
    signal: AbortSignal.timeout(25_000),
  })

  if (!response.ok) {
    throw new Error(`RocketJobs API ${response.status} ${response.statusText}`)
  }

  const body = (await response.json()) as ApiResponse
  const results: JobCard[] = []

  for (const offer of body.data ?? []) {
    const card = apiOfferToCard(offer)
    const dateRaw = offer.publishedAt ?? offer.lastPublishedAt
    if (!isFresh(dateRaw, days, maxAgeHours, strictFreshness)) continue
    results.push(card)
    if (results.length >= limit) break
  }

  return {
    total: results.length,
    page: 1,
    perPage: results.length,
    results,
  }
}
