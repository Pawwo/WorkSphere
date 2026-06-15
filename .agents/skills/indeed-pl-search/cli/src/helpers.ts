import { type JobCard, sleepJitter, stripHtml } from "scraper-shared"
import { chromium, type Browser } from "playwright"

const BASE_URL = "https://pl.indeed.com/jobs"

let browser: Browser | null = null

async function getBrowser(): Promise<Browser> {
  if (!browser) {
    const headless = process.env.INDEED_HEADLESS !== "0"
    browser = await chromium.launch({
      headless,
      executablePath: process.env.INDEED_BROWSER_PATH,
      args: ["--disable-blink-features=AutomationControlled", "--lang=pl-PL"],
    })
  }
  return browser
}

async function fetchPageContent(url: string): Promise<string> {
  const b = await getBrowser()
  const context = await b.newContext({
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    locale: "pl-PL",
  })
  const page = await context.newPage()
  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 })
    await sleepJitter(2, 4)
    return await page.content()
  } finally {
    await context.close()
  }
}

function isBlocked(html: string): boolean {
  const lower = html.toLowerCase()
  return (
    lower.includes("security check") ||
    lower.includes("blocked - indeed.com") ||
    lower.includes("captcha") ||
    lower.includes("cf-challenge")
  )
}

function parseJobCards(html: string): JobCard[] {
  const results: JobCard[] = []
  for (const match of html.matchAll(/<div[^>]*class="[^"]*job_seen_beacon[^"]*"[^>]*>([\s\S]*?)<\/div>\s*<\/div>/gi)) {
    const card = match[1]
    const titleMatch = card.match(/class="[^"]*jcs-JobTitle[^"]*"[^>]*>([\s\S]*?)<\/a>/i)
    const linkMatch = card.match(/href="([^"]+)"/i)
    const companyMatch =
      card.match(/data-testid="company-name"[^>]*>([\s\S]*?)<\//i) ??
      card.match(/class="[^"]*companyName[^"]*"[^>]*>([\s\S]*?)<\//i)
    const locationMatch =
      card.match(/data-testid="text-location"[^>]*>([\s\S]*?)<\//i) ??
      card.match(/class="[^"]*companyLocation[^"]*"[^>]*>([\s\S]*?)<\//i)
    const salaryMatch = card.match(/class="[^"]*salary[^"]*"[^>]*>([\s\S]*?)<\//i)
    if (!titleMatch || !linkMatch) continue
    let url = linkMatch[1]
    if (!url.startsWith("http")) url = `https://pl.indeed.com${url}`
    const jkMatch = url.match(/[?&]jk=([^&]+)/)
    results.push({
      id: jkMatch?.[1] ?? url,
      title: stripHtml(titleMatch[1]),
      company: companyMatch ? stripHtml(companyMatch[1]) : null,
      location: locationMatch ? stripHtml(locationMatch[1]) : null,
      date: null,
      deadline: null,
      salary: salaryMatch ? stripHtml(salaryMatch[1]) : null,
      url,
      description: null,
    })
  }

  if (!results.length) {
    const jsonMatch = html.match(
      /window\.mosaic\.providerData\["mosaic-provider-jobcards"\]\s*=\s*({[\s\S]*?});/,
    )
    if (jsonMatch) {
      try {
        const data = JSON.parse(jsonMatch[1]) as Record<string, unknown>
        const model = data.metaData as Record<string, unknown> | undefined
        const cardsModel = model?.mosaicProviderJobCardsModel as Record<string, unknown> | undefined
        const items = cardsModel?.results
        if (Array.isArray(items)) {
          for (const item of items as Record<string, unknown>[]) {
            const jk = String(item.jobkey ?? "")
            const title = String(item.title ?? "")
            if (!title || !jk) continue
            results.push({
              id: jk,
              title,
              company: String(item.company ?? "") || null,
              location: String(item.displayLocation ?? "") || null,
              date: null,
              deadline: null,
              salary: String((item.salarySnippet as Record<string, unknown>)?.text ?? "") || null,
              url: `https://pl.indeed.com/viewjob?jk=${jk}`,
              description: null,
            })
          }
        }
      } catch {
        // ignore parse errors
      }
    }
  }

  return results
}

async function fetchDescription(jobUrl: string): Promise<string> {
  const html = await fetchPageContent(jobUrl)
  const descMatch =
    html.match(/id="jobDescriptionText"[^>]*>([\s\S]*?)<\/div>/i) ??
    html.match(/class="[^"]*jobsearch-JobComponent-description[^"]*"[^>]*>([\s\S]*?)<\/div>/i)
  return descMatch ? stripHtml(descMatch[1]) : ""
}

export async function searchIndeedPl(
  keyword: string,
  page: number,
  days: number,
  limit = 20,
  detailLimit = 0,
): Promise<{ total: number; page: number; perPage: number; results: JobCard[] }> {
  const start = (page - 1) * 10
  const params = new URLSearchParams({ q: keyword, l: "Poland", start: String(start) })
  if (days > 0) params.set("fromage", String(days))
  const html = await fetchPageContent(`${BASE_URL}?${params.toString()}`)
  if (isBlocked(html)) {
    throw new Error("Indeed blocked automated access. Set INDEED_HEADLESS=0 or paste job text into /apply.")
  }
  let cards = parseJobCards(html)
  if (limit) cards = cards.slice(0, limit)
  const detailCount = Math.max(0, Math.min(detailLimit, cards.length))
  for (let i = 0; i < detailCount; i++) {
    const card = cards[i]
    try {
      card.description = (await fetchDescription(card.url)) || card.title
      await sleepJitter(0.5, 1.5)
    } catch {
      card.description = card.title
    }
  }
  for (let i = detailCount; i < cards.length; i++) {
    cards[i].description = cards[i].description || cards[i].title
  }
  return { total: cards.length, page, perPage: cards.length, results: cards }
}

export async function detailIndeedPl(idOrUrl: string): Promise<JobCard> {
  const url = idOrUrl.startsWith("http")
    ? idOrUrl
    : `https://pl.indeed.com/viewjob?jk=${idOrUrl}`
  const html = await fetchPageContent(url)
  if (isBlocked(html)) throw new Error("Indeed blocked automated access")
  const cards = parseJobCards(html)
  const match = cards[0]
  if (match) {
    if (!match.description) {
      match.description = (await fetchDescription(url)) || match.description
    }
    return match
  }
  const description = await fetchDescription(url)
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

export async function closeIndeedBrowser(): Promise<void> {
  if (browser) {
    await browser.close()
    browser = null
  }
}
