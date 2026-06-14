import {
  type JobCard,
  excerpt,
  extractNextData,
  htmlFetch,
  isRecentHours,
  normalizeKeyword,
  stripHtml,
} from "scraper-shared"

export const BASE_URL = "https://it.pracuj.pl/praca"

interface PracujOffer {
  offerId?: string | number
  id?: string | number
  partitionId?: string | number
  offerAbsoluteUri?: string
  displayWorkplace?: string
  salaryDisplayText?: string
}

interface PracujGroup {
  jobTitle?: string
  companyName?: string
  jobDescription?: string
  lastPublicated?: string
  salaryDisplayText?: string
  expirationDate?: string
  offers?: PracujOffer[]
}

function findJobOffersQuery(nextData: Record<string, unknown>): Record<string, unknown> | null {
  const props = nextData.props as Record<string, unknown> | undefined
  const pageProps = props?.pageProps as Record<string, unknown> | undefined
  const dehydrated = pageProps?.dehydratedState as Record<string, unknown> | undefined
  const queries = dehydrated?.queries
  if (!Array.isArray(queries)) return null
  for (const q of queries) {
    if (!q || typeof q !== "object") continue
    const queryKey = (q as Record<string, unknown>).queryKey
    if (Array.isArray(queryKey) && queryKey[0] === "jobOffers") {
      return q as Record<string, unknown>
    }
  }
  return null
}

function getJobOffersData(nextData: Record<string, unknown>): Record<string, unknown> | null {
  const query = findJobOffersQuery(nextData)
  const state = query?.state as Record<string, unknown> | undefined
  const data = state?.data
  return data && typeof data === "object" ? (data as Record<string, unknown>) : null
}

export function parsePracujOffers(
  nextData: Record<string, unknown>,
  days = 0,
  maxAgeHours = 0,
  strictFreshness = false,
): JobCard[] {
  const data = getJobOffersData(nextData)
  if (!data) return []
  const grouped = data.groupedOffers
  if (!Array.isArray(grouped)) return []

  const cutoffMs =
    maxAgeHours > 0
      ? Date.now() - maxAgeHours * 60 * 60 * 1000
      : days > 0
        ? Date.now() - days * 24 * 60 * 60 * 1000
        : 0
  const results: JobCard[] = []

  for (const group of grouped as PracujGroup[]) {
    const jobTitle = group.jobTitle ?? ""
    const companyName = group.companyName ?? null
    const shortDesc = group.jobDescription ?? null
    const pubDateStr = group.lastPublicated
    if (cutoffMs > 0) {
      if (!pubDateStr) {
        if (strictFreshness) continue
      } else if (!isRecentHours(pubDateStr, maxAgeHours || days * 24, strictFreshness)) {
        continue
      }
    }
    for (const off of group.offers ?? []) {
      const id = String(off.offerId ?? off.partitionId ?? off.id ?? "")
      const url = off.offerAbsoluteUri ?? ""
      if (!id || !url) continue
      results.push({
        id,
        title: jobTitle,
        company: companyName,
        location: off.displayWorkplace ?? null,
        date: pubDateStr ? pubDateStr.slice(0, 10) : null,
        deadline: group.expirationDate ? group.expirationDate.slice(0, 10) : null,
        salary: group.salaryDisplayText || off.salaryDisplayText || null,
        url,
        description: excerpt(shortDesc),
      })
    }
  }
  return results
}

export function parsePracujTotalPages(nextData: Record<string, unknown>): number | null {
  const data = getJobOffersData(nextData)
  const pagination = data?.pagination as Record<string, unknown> | undefined
  const total = pagination?.totalPages ?? pagination?.pagesCount
  return typeof total === "number" ? total : typeof total === "string" ? parseInt(total, 10) : null
}

export async function fetchPracujPage(keyword: string, page: number, days: number): Promise<string> {
  const params = new URLSearchParams({
    et: "21,6,20",
    wm: "hybrid,remote",
    pn: String(page),
  })
  if (days > 0) params.set("pd", String(days))
  const query = normalizeKeyword(keyword)
  if (query) params.set("q", query)
  return htmlFetch(`${BASE_URL}?${params.toString()}`, { preferCurl: true })
}

export function extractPracujDetailFromHtml(html: string): string {
  const containerMatch =
    html.match(/<div[^>]*data-test="section-offerView"[^>]*>([\s\S]*?)<\/div>\s*<\/div>/i) ??
    html.match(/<div[^>]*class="[^"]*Offerview[^"]*"[^>]*>([\s\S]*?)<\/div>\s*<\/div>/i)
  if (containerMatch?.[1]) return stripHtml(containerMatch[1])
  return ""
}

export async function fetchPracujDetail(url: string): Promise<string> {
  const html = await htmlFetch(url, { preferCurl: true })
  return extractPracujDetailFromHtml(html)
}

export async function searchPracuj(
  keyword: string,
  page: number,
  days: number,
  limit?: number,
  maxAgeHours = 0,
  strictFreshness = false,
): Promise<{ total: number; page: number; perPage: number; results: JobCard[] }> {
  const html = await fetchPracujPage(keyword, page, days)
  const nextData = extractNextData(html)
  if (!nextData) throw new Error("Failed to parse Pracuj listing page")
  let results = parsePracujOffers(nextData, days, maxAgeHours, strictFreshness)
  const data = getJobOffersData(nextData)
  const total =
    typeof data?.groupedOffersTotalCount === "number"
      ? data.groupedOffersTotalCount
      : results.length
  if (limit !== undefined) results = results.slice(0, limit)
  return { total, page, perPage: results.length || 20, results }
}

export async function detailPracuj(idOrUrl: string): Promise<JobCard> {
  const url = idOrUrl.startsWith("http")
    ? idOrUrl
    : `https://www.pracuj.pl/praca/oferta,${idOrUrl}`
  const pageHtml = await htmlFetch(url, { preferCurl: true })
  const nextData = extractNextData(pageHtml)
  if (nextData) {
    const offers = parsePracujOffers(nextData, 0)
    const match = offers.find((o) => o.id === idOrUrl || o.url === url) ?? offers[0]
    if (match) {
      const description = await fetchPracujDetail(url)
      return { ...match, description: description || match.description }
    }
  }
  const titleMatch = pageHtml.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i)
  const title = titleMatch ? stripHtml(titleMatch[1]) : idOrUrl
  const description = await fetchPracujDetail(url)
  return {
    id: idOrUrl,
    title,
    company: null,
    location: null,
    date: null,
    deadline: null,
    salary: null,
    url,
    description: description || null,
  }
}
