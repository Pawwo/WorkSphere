import {
  type JobCard,
  extractHrefs,
  fetchLdOffer,
  listingDetailSearch,
  normalizeKeyword,
  resolveJobUrl,
  stripHtml,
  titleFromSlug,
  type SearchResult,
} from "scraper-shared"
import { searchRocketJobsApi } from "./api.js"

export const BASE_URL = "https://rocketjobs.pl/oferty-pracy/wszystkie-lokalizacje"

const RJ_STOP_WORDS = new Set([
  "warszawa",
  "warsaw",
  "krakow",
  "kraków",
  "gdansk",
  "gdańsk",
  "szczecin",
  "remote",
  "hybrid",
  "polska",
  "poland",
  "developer",
  "manager",
])

export function extractRocketLinks(html: string): string[] {
  return extractHrefs(html, /href="([^"]*\/oferta-pracy\/[^"?#]+)"/gi, "https://rocketjobs.pl")
}

function titleFromRocketUrl(url: string): string {
  return titleFromSlug(url, "/oferta-pracy/")
}

export function queryTokens(keyword: string): string[] {
  const q = normalizeKeyword(keyword).toLowerCase()
  if (!q) return []
  return q
    .split(/[\s,/]+/)
    .map((t) => t.replace(/^["']+|["']+$/g, ""))
    .filter((t) => t.length >= 3 && !RJ_STOP_WORDS.has(t))
}

export function matchesQueryTokens(haystack: string, tokens: string[]): boolean {
  if (!tokens.length) return true
  const lower = haystack.toLowerCase()
  return tokens.some((token) => {
    if (token.length <= 3) {
      return new RegExp(`\\b${token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i").test(lower)
    }
    return lower.includes(token)
  })
}

function cardFromUrl(url: string, title: string): JobCard {
  return {
    id: url,
    title,
    company: null,
    location: null,
    date: null,
    deadline: null,
    salary: null,
    url,
    description: title,
  }
}

export function parseRocketListingCards(html: string, keyword: string, limit: number): JobCard[] {
  const tokens = queryTokens(keyword)
  const results: JobCard[] = []
  const seen = new Set<string>()

  const push = (url: string, title: string) => {
    if (seen.has(url)) return
    const haystack = `${title} ${url}`
    if (!matchesQueryTokens(haystack, tokens)) return
    seen.add(url)
    results.push(cardFromUrl(url, title))
  }

  for (const match of html.matchAll(
    /<a[^>]+href="([^"]*\/oferta-pracy\/[^"?#]+)"[^>]*>([\s\S]*?)<\/a>/gi,
  )) {
    const href = match[1]
    const full = href.startsWith("http") ? href : `https://rocketjobs.pl${href}`
    const url = full.split("?")[0]
    const anchorText = stripHtml(match[2])
    const title = anchorText || titleFromRocketUrl(url)
    push(url, title)
    if (results.length >= limit) return results
  }

  if (!results.length) {
    for (const link of extractRocketLinks(html)) {
      const title = titleFromRocketUrl(link)
      push(link, title)
      if (results.length >= limit) break
    }
  }

  return results
}

function listingUrl(keyword: string, page: number): string {
  const q = normalizeKeyword(keyword)
  const base = BASE_URL
  const params = new URLSearchParams()
  if (q) params.set("search", q)
  if (page > 1) params.set("page", String(page))
  const qs = params.toString()
  return qs ? `${base}?${qs}` : base
}

export async function searchRocketJobsHtml(
  keyword: string,
  page: number,
  days: number,
  limit = 30,
  listingOnly = true,
): Promise<SearchResult> {
  return listingDetailSearch({
    baseUrl: BASE_URL,
    pageUrl: (p) => listingUrl(keyword, p),
    extractLinks: extractRocketLinks,
    parseListing: (html, kw, lim) => parseRocketListingCards(html, kw, lim),
    fetchOffer: (url, kw, d) => fetchLdOffer(url, { keyword: kw, days: d }),
    keyword,
    page,
    days,
    limit,
    listingOnly,
  })
}

export async function searchRocketJobs(
  keyword: string,
  page: number,
  days: number,
  limit = 30,
  listingOnly = true,
  maxAgeHours = 0,
  strictFreshness = false,
): Promise<SearchResult> {
  try {
    return await searchRocketJobsApi(keyword, limit, days, maxAgeHours, strictFreshness)
  } catch {
    return searchRocketJobsHtml(keyword, page, days, limit, listingOnly)
  }
}

export async function detailRocketJobs(idOrUrl: string): Promise<JobCard> {
  const url = resolveJobUrl(idOrUrl, (id) => `https://rocketjobs.pl/oferta-pracy/${id}`)
  const card = await fetchLdOffer(url, {})
  if (!card) throw new Error("Job not found")
  return card
}
