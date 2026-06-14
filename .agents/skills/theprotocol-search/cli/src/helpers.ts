import {
  type JobCard,
  excerptJobDescription,
  extractNextData,
  htmlFetch,
  isRecentHours,
  normalizeKeyword,
  sleepJitter,
  stripHtml,
} from "scraper-shared"

const LOCATION_SLUGS: Record<string, string> = {
  warszawa: "warszawa",
  krakow: "krakow",
  kraków: "krakow",
  wroclaw: "wroclaw",
  wrocław: "wroclaw",
  gdansk: "gdansk",
  gdańsk: "gdansk",
  poznan: "poznan",
  poznań: "poznan",
  szczecin: "szczecin",
  lodz: "lodz",
  łódź: "lodz",
}

const WORK_MODE_SLUGS: Record<string, string> = {
  remote: "zdalna",
  zdalna: "zdalna",
  hybrid: "hybrydowa",
  hybrydowa: "hybrydowa",
  onsite: "stacjonarna",
  stacjonarna: "stacjonarna",
}

export function buildFilterUrl(locations: string[], workModes: string[]): string {
  const locs =
    locations.length > 0
      ? locations.map((l) => LOCATION_SLUGS[l.toLowerCase()] ?? l.toLowerCase()).join(",")
      : "warszawa,krakow,wroclaw,gdansk,poznan"
  const modes =
    workModes.length > 0
      ? workModes.map((m) => WORK_MODE_SLUGS[m.toLowerCase()] ?? m.toLowerCase()).join(",")
      : "zdalna,hybrydowa"
  return `https://theprotocol.it/filtry/head,manager,lead;p/${locs};wp/${modes};rw`
}

export function parseOffers(
  nextData: Record<string, unknown>,
  days: number,
  keyword: string,
  maxAgeHours = 0,
  strictFreshness = false,
): JobCard[] {
  const props = nextData.props as Record<string, unknown> | undefined
  const pageProps = props?.pageProps as Record<string, unknown> | undefined
  const offersResponse = pageProps?.offersResponse as Record<string, unknown> | undefined
  const rawOffers = offersResponse?.offers
  if (!Array.isArray(rawOffers)) return []

  const query = normalizeKeyword(keyword).toLowerCase()
  const results: JobCard[] = []

  for (const off of rawOffers as Record<string, unknown>[]) {
    const pubDateStr = off.publicationDateUtc as string | undefined
    if (maxAgeHours > 0 || days > 0) {
      const hours = maxAgeHours > 0 ? maxAgeHours : days * 24
      if (!isRecentHours(pubDateStr, hours, strictFreshness)) continue
    }
    const jobId = String(off.id ?? "")
    const urlName = String(off.offerUrlName ?? "")
    const title = String(off.title ?? "")
    const employer = String(off.employer ?? "")
    const technologies = Array.isArray(off.technologies) ? (off.technologies as string[]).join(", ") : ""
    if (query) {
      const haystack = `${title} ${employer} ${technologies}`.toLowerCase()
      if (!haystack.includes(query)) continue
    }
    const salaryData = off.salary as Record<string, unknown> | undefined
    let salary: string | null = null
    if (salaryData) {
      const from = salaryData.from
      const to = salaryData.to
      const curr = salaryData.currency ?? "PLN"
      if (from && to) salary = `${from} - ${to} ${curr}`
      else if (from) salary = `Od ${from} ${curr}`
    }
    const workMode = String(off.workMode ?? off.employmentType ?? "")
    results.push({
      id: jobId,
      title,
      company: employer || null,
      location: String(off.locationDisplay ?? "") || null,
      date: pubDateStr ? pubDateStr.slice(0, 10) : null,
      deadline: null,
      salary,
      url: `https://theprotocol.it/szczegoly/praca/${urlName},oferta,${jobId}`,
      technologies: technologies || null,
      description: technologies ? null : workMode ? excerptJobDescription(workMode, 120) : null,
    })
  }
  return results
}

export async function fetchProtocolPage(
  baseUrl: string,
  page: number,
): Promise<{ nextData: Record<string, unknown>; html: string }> {
  const params = new URLSearchParams({ sort: "date", pageNumber: String(page) })
  const html = await htmlFetch(`${baseUrl}?${params.toString()}`)
  const nextData = extractNextData(html)
  if (!nextData) throw new Error("Failed to parse TheProtocol listing page")
  return { nextData, html }
}

export async function searchTheProtocol(
  keyword: string,
  page: number,
  days: number,
  limit: number | undefined,
  locations: string[],
  workModes: string[],
  maxAgeHours = 0,
  strictFreshness = false,
): Promise<{ total: number; page: number; perPage: number; results: JobCard[] }> {
  const baseUrl = buildFilterUrl(locations, workModes)
  const { nextData } = await fetchProtocolPage(baseUrl, page)
  let results = parseOffers(nextData, days, keyword, maxAgeHours, strictFreshness)
  const offersResponse = (nextData.props as Record<string, unknown>)?.pageProps as Record<string, unknown>
  const pageInfo = ((offersResponse?.offersResponse as Record<string, unknown>)?.page ?? {}) as Record<
    string,
    unknown
  >
  const totalPages = Number(pageInfo.count ?? 1)
  const total = totalPages * Math.max(results.length, 1)
  if (limit !== undefined) results = results.slice(0, limit)
  return { total, page, perPage: results.length || 20, results }
}

export async function detailTheProtocol(idOrUrl: string): Promise<JobCard> {
  const url = idOrUrl.startsWith("http")
    ? idOrUrl
    : `https://theprotocol.it/szczegoly/praca/oferta,oferta,${idOrUrl}`
  const html = await htmlFetch(url)
  const nextData = extractNextData(html)
  if (nextData) {
    const offers = parseOffers(nextData, 0, "")
    const match = offers.find((o) => o.id === idOrUrl || o.url === url) ?? offers[0]
    if (match) {
      const descMatch =
        html.match(/class="[^"]*(description|offer|content)[^"]*"[^>]*>([\s\S]*?)<\/article>/i) ??
        html.match(/<main[^>]*>([\s\S]*?)<\/main>/i)
      if (descMatch) match.description = excerptJobDescription(stripHtml(descMatch[1]))
      return match
    }
  }
  const titleMatch = html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i)
  return {
    id: idOrUrl,
    title: titleMatch ? stripHtml(titleMatch[1]) : idOrUrl,
    company: null,
    location: null,
    date: null,
    deadline: null,
    salary: null,
    url,
    description: null,
  }
}
