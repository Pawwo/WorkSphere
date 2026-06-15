import {
  type JobCard,
  buildListingDescription,
  excerpt,
  htmlFetch,
  isRecentHours,
  listingDetailSearch,
  matchesSearchQuery,
  normalizeKeyword,
  parseJobPostingLd,
  stripHtml,
  type SearchResult,
} from "scraper-shared"

export function slugifyKeyword(keyword: string): string {
  const slug = keyword
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
  return slug || "it"
}

export function listingUrl(keyword: string, page: number): string {
  const slug = slugifyKeyword(normalizeKeyword(keyword))
  const base = `https://www.praca.pl/s-${slug}.html`
  return page > 1 ? `${base}?pn=${page}` : base
}

export function extractOfferLinks(html: string): string[] {
  const links: string[] = []
  for (const match of html.matchAll(/href="([^"]+)"/gi)) {
    const href = match[1].split("#")[0].split("?")[0]
    if (!/_\d+\.html$/i.test(href)) continue
    const full = href.startsWith("http") ? href : `https://www.praca.pl/${href.replace(/^\//, "")}`
    if (full.includes("praca.pl/") && !links.includes(full)) {
      links.push(full)
    }
  }
  return links.slice(0, 80)
}

function titleFromPracaUrl(url: string, titleAttr?: string): string {
  if (titleAttr?.trim()) {
    return titleAttr.split(",")[0].trim()
  }
  const match = url.match(/praca\.pl\/(.+)_\d+\.html/i)
  if (!match) return url
  return match[1]
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export function isNoiseOffer(
  title: string,
  company: string | null,
  description: string,
  listing = false,
): boolean {
  const blob = `${title} ${company ?? ""} ${description}`.toLowerCase()
  if (/podobne oferty|praca w miastach|praca w popularnych/.test(blob)) return true
  if ((company ?? "").toLowerCase().includes("podobne oferty")) return true
  if (!listing && description.trim().length < 50 && !(company ?? "").trim()) return true
  return false
}

export function parseListingCards(html: string, keyword: string, limit: number): JobCard[] {
  const query = normalizeKeyword(keyword).toLowerCase()
  const results: JobCard[] = []
  const seen = new Set<string>()

  for (const match of html.matchAll(
    /<a[^>]+href="(https:\/\/www\.praca\.pl\/[^"]+_\d+\.html)"[^>]*(?:title="([^"]*)")?[^>]*>([\s\S]*?)<\/a>/gi,
  )) {
    const url = match[1].split("?")[0]
    if (seen.has(url)) continue
    seen.add(url)

    const titleAttr = match[2]
    const anchorText = stripHtml(match[3])
    const title = titleFromPracaUrl(url, titleAttr)
    const location = titleAttr?.includes(",") ? titleAttr.split(",").slice(1).join(",").trim() : anchorText || null
    const snippet =
      anchorText && anchorText.toLowerCase() !== title.toLowerCase() ? anchorText : null
    const description = buildListingDescription(title, [location, snippet])

    if (isNoiseOffer(title, null, description, true)) continue

    const haystack = `${title} ${url} ${location ?? ""}`
    if (query && !matchesSearchQuery(haystack, query)) continue

    const idMatch = url.match(/_(\d+)\.html/)
    results.push({
      id: idMatch?.[1] ?? url,
      title,
      company: null,
      location: location || null,
      date: null,
      deadline: null,
      salary: null,
      url,
      description,
    })
    if (results.length >= limit) break
  }

  if (results.length) return results

  for (const link of extractOfferLinks(html)) {
    if (seen.has(link)) continue
    seen.add(link)
    const title = titleFromPracaUrl(link)
    const haystack = `${title} ${link}`
    if (query && !matchesSearchQuery(haystack, query)) continue
    if (isNoiseOffer(title, null, title, true)) continue
    const idMatch = link.match(/_(\d+)\.html/)
    results.push({
      id: idMatch?.[1] ?? link,
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

async function fetchOfferDetail(
  url: string,
  maxAgeHours = 0,
  strictFreshness = false,
): Promise<JobCard | null> {
  const html = await htmlFetch(url)
  const ld = parseJobPostingLd(html)
  const datePosted = ld && typeof ld.datePosted === "string" ? ld.datePosted : null
  if (maxAgeHours > 0 && !isRecentHours(datePosted ?? undefined, maxAgeHours, strictFreshness)) {
    return null
  }
  const titleMatch = html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i)
  const title = titleMatch ? stripHtml(titleMatch[1]) : ld ? String(ld.title ?? "") : ""
  if (!title) return null
  const companyMatch =
    html.match(/data-test="[^"]*company[^"]*"[^>]*>([\s\S]*?)<\//i) ?? html.match(/<h2[^>]*>([\s\S]*?)<\/h2>/i)
  const org = ld?.hiringOrganization
  const ldCompany =
    org && typeof org === "object" ? String((org as Record<string, unknown>).name ?? "") || null : null
  const company = companyMatch ? stripHtml(companyMatch[1]) : ldCompany
  const descMatch = html.match(/class="[^"]*(description|offer)[^"]*"[^>]*>([\s\S]*?)<\/div>/i)
  const description = descMatch ? stripHtml(descMatch[2]) : title
  const salaryMatch = html.match(/(?:PLN|zł)[^<]{0,120}/i)
  if (isNoiseOffer(title, company, description)) return null

  const idMatch = url.match(/_(\d+)\.html/)
  return {
    id: idMatch?.[1] ?? url,
    title,
    company,
    location: null,
    date: datePosted ? datePosted.slice(0, 10) : null,
    deadline: null,
    salary: salaryMatch ? salaryMatch[0].trim() : null,
    url,
    description: excerpt(description),
  }
}

export async function searchPracaPl(
  keyword: string,
  page: number,
  days: number,
  limit = 30,
  maxAgeHours = 0,
  strictFreshness = false,
  listingOnly = true,
): Promise<SearchResult> {
  const base = listingUrl(keyword, page)
  return listingDetailSearch({
    baseUrl: base,
    pageUrl: (p, _base) => listingUrl(keyword, p),
    extractLinks: extractOfferLinks,
    parseListing: (html, kw, lim) => parseListingCards(html, kw, lim),
    fetchOffer: async (url) => fetchOfferDetail(url, maxAgeHours, strictFreshness),
    keyword,
    page,
    days,
    limit,
    listingOnly,
    maxPages: listingOnly ? 1 : limit <= 20 ? 2 : 3,
    detailCap: Math.min(limit, 10),
  })
}

export async function detailPracaPl(idOrUrl: string): Promise<JobCard> {
  const url = idOrUrl.startsWith("http")
    ? idOrUrl
    : `https://www.praca.pl/oferta_${idOrUrl}.html`
  const card = await fetchOfferDetail(url)
  if (!card) throw new Error("Job not found")
  const html = await htmlFetch(url)
  const descMatch = html.match(/class="[^"]*(description|offer)[^"]*"[^>]*>([\s\S]*?)<\/article>/i)
  if (descMatch) card.description = stripHtml(descMatch[1])
  return card
}
