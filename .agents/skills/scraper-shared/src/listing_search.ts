import type { JobCard, SearchResult } from "./types.js"
import { htmlFetch, sleepJitter } from "./http.js"

export interface ListingSearchConfig {
  baseUrl: string
  pageUrl?: (page: number, baseUrl: string) => string
  extractLinks: (html: string) => string[]
  parseListing?: (html: string, keyword: string, limit: number) => JobCard[]
  fetchOffer: (url: string, keyword: string, days: number) => Promise<JobCard | null>
  keyword: string
  page: number
  days: number
  limit?: number
  listingOnly?: boolean
  maxPages?: number
  detailCap?: number
  acceptLanguage?: string
}

export async function listingDetailSearch(config: ListingSearchConfig): Promise<SearchResult> {
  const {
    baseUrl,
    pageUrl = (p, base) => (p === 1 ? base : `${base}${base.includes("?") ? "&" : "?"}page=${p}`),
    extractLinks,
    parseListing,
    fetchOffer,
    keyword,
    page,
    days,
    limit = 30,
    listingOnly = true,
    maxPages: maxPagesConfig,
    detailCap = Math.min(limit, 10),
    acceptLanguage,
  } = config

  const maxPages = maxPagesConfig ?? (listingOnly ? 1 : limit <= 20 ? 2 : 3)

  const links: string[] = []
  for (let p = 1; p <= maxPages; p++) {
    const url = pageUrl(p, baseUrl)
    const html = await htmlFetch(url, acceptLanguage ? { acceptLanguage } : undefined)
    if (listingOnly && parseListing) {
      const listing = parseListing(html, keyword, limit)
      return { total: listing.length, page, perPage: listing.length, results: listing }
    }
    const pageLinks = extractLinks(html)
    if (!pageLinks.length) break
    links.push(...pageLinks)
    await sleepJitter(0.3, 0.8)
  }

  const unique = [...new Set(links)]
  const results: JobCard[] = []
  for (const link of unique) {
    if (results.length >= detailCap) break
    try {
      const card = await fetchOffer(link, keyword, days)
      if (card) results.push(card)
      await sleepJitter(0.1, 0.4)
    } catch {
      continue
    }
  }

  return { total: results.length, page, perPage: results.length, results }
}
