import {
  type JobCard,
  buildListingDescription,
  extractHrefs,
  fetchLdOffer,
  htmlFetch,
  listingDetailSearch,
  normalizeKeyword,
  resolveJobUrl,
  stripHtml,
  titleFromSlug,
  type SearchResult,
} from "scraper-shared"

export const BASE_URL = "https://justjoin.it/"

const JJ_STOP_WORDS = ["warsaw", "warszawa", "krakow", "gdansk", "remote", "hybrid", "pm", "js", "python"]

export function extractOfferLinks(html: string): string[] {
  return extractHrefs(
    html,
    /href="(\/job-offer\/[^"?#]+|https:\/\/justjoin\.it\/job-offer\/[^"?#]+)"/gi,
    "https://justjoin.it",
  )
}

function titleFromJustJoinUrl(url: string): string {
  return titleFromSlug(url, "/job-offer/", JJ_STOP_WORDS)
}

export function parseListingCards(html: string, keyword: string, _days: number, limit: number): JobCard[] {
  const query = normalizeKeyword(keyword).toLowerCase()
  const results: JobCard[] = []
  const seen = new Set<string>()

  for (const match of html.matchAll(
    /<a[^>]+href="(\/job-offer\/[^"?#]+|https:\/\/justjoin\.it\/job-offer\/[^"?#]+)"[^>]*>([\s\S]*?)<\/a>/gi,
  )) {
    const href = match[1]
    const full = href.startsWith("http") ? href : `https://justjoin.it${href}`
    const url = full.split("?")[0]
    if (seen.has(url)) continue
    seen.add(url)

    const anchorText = stripHtml(match[2])
    const title = anchorText || titleFromJustJoinUrl(url)
    const slugTitle = titleFromJustJoinUrl(url)
    const displayTitle = anchorText || slugTitle
    const haystack = `${displayTitle} ${url}`.toLowerCase()
    if (query && !haystack.includes(query)) continue

    results.push({
      id: url,
      title: displayTitle,
      company: null,
      location: null,
      date: null,
      deadline: null,
      salary: null,
      url,
      description: buildListingDescription(displayTitle, [
        anchorText && anchorText !== slugTitle ? slugTitle : null,
      ]),
    })
    if (results.length >= limit) break
  }

  if (results.length) return results

  for (const link of extractOfferLinks(html)) {
    if (seen.has(link)) continue
    seen.add(link)
    const title = titleFromJustJoinUrl(link)
    const haystack = `${title} ${link}`.toLowerCase()
    if (query && !haystack.includes(query)) continue
    results.push({
      id: link,
      title,
      company: null,
      location: null,
      date: null,
      deadline: null,
      salary: null,
      url: link,
      description: buildListingDescription(title, []),
    })
    if (results.length >= limit) break
  }

  return results
}

export async function searchJustJoin(
  keyword: string,
  page: number,
  days: number,
  limit = 30,
  listingOnly = true,
): Promise<SearchResult> {
  return listingDetailSearch({
    baseUrl: BASE_URL,
    pageUrl: (p) => (p === 1 ? BASE_URL : `${BASE_URL}?page=${p}`),
    extractLinks: extractOfferLinks,
    parseListing: (html, kw, lim) => parseListingCards(html, kw, days, lim),
    fetchOffer: (url, kw, d) =>
      fetchLdOffer(url, {
        keyword: kw,
        days: d,
        acceptLanguage: "en-US,en;q=0.9,pl;q=0.8",
      }),
    keyword,
    page,
    days,
    limit,
    listingOnly,
    acceptLanguage: "en-US,en;q=0.9,pl;q=0.8",
  })
}

export async function detailJustJoin(idOrUrl: string): Promise<JobCard> {
  const url = resolveJobUrl(idOrUrl, (id) => `https://justjoin.it/job-offer/${id}`)
  const card = await fetchLdOffer(url, { acceptLanguage: "en-US,en;q=0.9,pl;q=0.8" })
  if (!card) throw new Error("Job not found")
  return card
}
