import {
  type JobCard,
  extractLinkedInJobBody,
  htmlFetch,
  isRecentHours,
  sleepJitter,
  stripHtml,
} from "scraper-shared"

const BASE_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

function parseJobCards(html: string): JobCard[] {
  const results: JobCard[] = []

  for (const match of html.matchAll(/<li[\s\S]*?<\/li>/gi)) {
    const chunk = match[0]
    const linkMatch = chunk.match(/href="(https:\/\/[^"]+linkedin\.com\/jobs\/view\/[^"?#]+)/i)
    if (!linkMatch) continue
    const url = linkMatch[1].split("?")[0]
    const titleMatch =
      chunk.match(/class="[^"]*base-card__full-link[^"]*"[^>]*>([\s\S]*?)<\/a>/i) ??
      chunk.match(/class="[^"]*job-search-card__job-title[^"]*"[^>]*>([\s\S]*?)<\//i)
    const companyMatch =
      chunk.match(/class="[^"]*hidden-nested-link[^"]*"[^>]*>([\s\S]*?)<\/a>/i) ??
      chunk.match(/class="[^"]*base-search-card__subtitle[^"]*"[^>]*>([\s\S]*?)<\//i)
    const locationMatch = chunk.match(/class="[^"]*job-search-card__location[^"]*"[^>]*>([\s\S]*?)<\//i)
    const timeMatch = chunk.match(/datetime="([^"]+)"/i)
    const urnMatch = chunk.match(/data-entity-urn="[^"]*:([^:"]+)"/i)
    const idFromUrl = url.split("-").pop()
    results.push({
      id: urnMatch?.[1] ?? (idFromUrl && /^\d+$/.test(idFromUrl) ? idFromUrl : url),
      title: titleMatch ? stripHtml(titleMatch[1]) : "",
      company: companyMatch ? stripHtml(companyMatch[1]) : null,
      location: locationMatch ? stripHtml(locationMatch[1]) : null,
      date: timeMatch ? timeMatch[1].slice(0, 10) : null,
      deadline: null,
      salary: null,
      url,
      description: titleMatch ? stripHtml(titleMatch[1]) : null,
    })
  }
  return results.filter((r) => r.title)
}

async function fetchDetails(url: string): Promise<string> {
  const html = await htmlFetch(url, { acceptLanguage: "en-US,en;q=0.9" })
  const descMatch =
    html.match(/class="[^"]*show-more-less-html__markup[^"]*"[^>]*>([\s\S]*?)<\/div>/i) ??
    html.match(/class="[^"]*description__text[^"]*"[^>]*>([\s\S]*?)<\/div>/i)
  if (!descMatch) return ""
  return extractLinkedInJobBody(stripHtml(descMatch[1]))
}

async function fetchLinkedInPage(
  keyword: string,
  page: number,
  days: number,
): Promise<JobCard[]> {
  const start = (page - 1) * 25
  const params = new URLSearchParams({
    keywords: keyword,
    location: "Poland",
    start: String(start),
  })
  const seconds = days > 0 ? days * 86400 : 0
  if (seconds > 0) params.set("f_TPR", `r${seconds}`)

  await sleepJitter(1, 3)
  const response = await fetch(`${BASE_URL}?${params.toString()}`, {
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      Accept: "text/html,application/xhtml+xml",
      "Accept-Language": "en-US,en;q=0.9",
    },
    redirect: "follow",
    signal: AbortSignal.timeout(30_000),
  })

  if (response.status === 429) {
    throw new Error("LinkedIn rate limited (429). Retry later with a smaller --limit.")
  }
  if (!response.ok) {
    throw new Error(`LinkedIn request failed: ${response.status}`)
  }

  const html = await response.text()
  return parseJobCards(html)
}

export async function searchLinkedInPl(
  keyword: string,
  page: number,
  days: number,
  limit = 25,
  detailLimit = 5,
  pages = 2,
  maxAgeHours = 0,
  strictFreshness = false,
): Promise<{ total: number; page: number; perPage: number; results: JobCard[] }> {
  const cards: JobCard[] = []
  const seen = new Set<string>()
  const pageCount = Math.max(1, pages)
  const liDays = maxAgeHours > 0 ? Math.max(1, Math.ceil(maxAgeHours / 24)) : days

  for (let p = page; p < page + pageCount; p++) {
    const batch = await fetchLinkedInPage(keyword, p, liDays)
    for (const card of batch) {
      if (seen.has(card.url)) continue
      if (maxAgeHours > 0 && !isRecentHours(card.date ?? undefined, maxAgeHours, strictFreshness)) {
        continue
      }
      seen.add(card.url)
      cards.push(card)
      if (limit && cards.length >= limit) break
    }
    if (limit && cards.length >= limit) break
    if (p < page + pageCount - 1) await sleepJitter(0.5, 1.5)
  }

  const capped = limit ? cards.slice(0, limit) : cards
  const detailCount = Math.min(detailLimit, capped.length)
  for (let i = 0; i < detailCount; i++) {
    const card = capped[i]
    try {
      await sleepJitter(0.5, 1.5)
      card.description = (await fetchDetails(card.url)) || card.title
    } catch {
      card.description = card.title
    }
  }
  for (let i = detailCount; i < capped.length; i++) {
    capped[i].description = capped[i].description || capped[i].title
  }

  return { total: capped.length, page, perPage: capped.length, results: capped }
}

export async function detailLinkedInPl(idOrUrl: string): Promise<JobCard> {
  const url = idOrUrl.startsWith("http")
    ? idOrUrl
    : `https://www.linkedin.com/jobs/view/${idOrUrl}`
  const description = await fetchDetails(url)
  return {
    id: idOrUrl,
    title: idOrUrl,
    company: null,
    location: null,
    date: null,
    deadline: null,
    salary: null,
    url,
    description: description || null,
  }
}
