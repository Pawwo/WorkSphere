import {
  type JobCard,
  extractHrefs,
  fetchLdOffer,
  htmlFetch,
  resolveJobUrl,
  sleepJitter,
  type SearchResult,
} from "scraper-shared"

export const BASE = "https://nofluffjobs.com"

export const CATEGORIES: Record<string, string> = {
  all: "/pl",
  backend: "/pl/backend",
  frontend: "/pl/frontend",
  fullstack: "/pl/fullstack",
  devops: "/pl/devops",
  data: "/pl/data",
  ai: "/pl/artificial-intelligence",
  testing: "/pl/testing",
  architecture: "/pl/architecture",
  security: "/pl/security",
}

export function extractNfjLinks(html: string, baseUrl: string): string[] {
  return extractHrefs(html, /href="([^"]*\/pl\/job\/[^"?#]+)"/gi, baseUrl).filter((u) =>
    u.startsWith("https://nofluffjobs.com/pl/job/"),
  )
}

function titleFromNfjUrl(url: string): string {
  const slug = url.split("/").pop() ?? url
  return slug.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

export async function searchNoFluffJobs(
  keyword: string,
  category: string,
  days: number,
  limit = 30,
  listingOnly = false,
  maxAgeHours = 0,
  strictFreshness = false,
): Promise<SearchResult> {
  const effectiveCategory = category && category !== "all" ? category : "ai"
  const paths =
    effectiveCategory && CATEGORIES[effectiveCategory]
      ? [CATEGORIES[effectiveCategory]]
      : [CATEGORIES.ai]

  const links = new Set<string>()
  for (const path of paths) {
    const url = `${BASE}${path}`
    try {
      const html = await htmlFetch(url)
      for (const link of extractNfjLinks(html, url)) links.add(link)
      await sleepJitter(0.2, 0.6)
    } catch {
      continue
    }
  }

  const results: JobCard[] = []
  const detailCap = listingOnly ? limit : Math.min(limit, 10)
  for (const link of links) {
    if (results.length >= detailCap) break
    try {
      if (listingOnly) {
        results.push({
          id: link,
          title: titleFromNfjUrl(link),
          company: null,
          location: null,
          date: null,
          deadline: null,
          salary: null,
          url: link,
          description: titleFromNfjUrl(link),
        })
        continue
      }
      const card = await fetchLdOffer(link, {
        keyword,
        days,
        maxAgeHours,
        strictFreshness,
      })
      if (card) results.push(card)
      await sleepJitter(0.1, 0.5)
    } catch {
      continue
    }
  }

  return { total: results.length, page: 1, perPage: results.length, results }
}

export async function detailNoFluffJobs(idOrUrl: string): Promise<JobCard> {
  const url = resolveJobUrl(idOrUrl, (id) => `${BASE}/pl/job/${id}`)
  const card = await fetchLdOffer(url, {})
  if (!card) throw new Error("Job not found")
  return card
}
