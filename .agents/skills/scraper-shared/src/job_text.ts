import { excerpt } from "./http.js"

const _NOISE_PATTERNS: RegExp[] = [
  /linkedin\s+szanuje\s+twoją\s+prywatność/gi,
  /\bcookie(s)?\b/gi,
  /\bzaakceptuj\b/gi,
  /\bzaloguj\s+się\b/gi,
  /\bsign\s+in\b/gi,
  /\bpodobne\s+oferty\b/gi,
  /\bsimilar\s+jobs\b/gi,
  /\bpeople\s+also\s+viewed\b/gi,
  /\bpraca\s+w\s+miastach\b/gi,
  /\bpraca\s+w\s+popularnych\b/gi,
]

const _LINKEDIN_JD_START = [
  " IS HIRING",
  " IS HIRING!",
  "Requirements:",
  "Essential Qualifications",
  "Responsibilities:",
  "About the job",
  "Wymagania",
  "Obowiązki",
]

const _LINKEDIN_JD_END = [
  "Podobne oferty",
  "Similar jobs",
  "People also viewed",
  "Polecenia",
]

export function stripBoilerplate(text: string): string {
  let out = (text || "").replace(/\s+/g, " ").trim()
  for (const re of _NOISE_PATTERNS) {
    out = out.replace(re, " ")
  }
  return out.replace(/\s+/g, " ").trim()
}

export function extractLinkedInJobBody(text: string): string {
  if (!text) return text
  const low = text.toLowerCase()
  const hasChrome =
    low.includes("linkedin") || low.includes("prywatność") || low.includes("cookie")
  if (!hasChrome) return stripBoilerplate(text)

  let start = 0
  for (const marker of _LINKEDIN_JD_START) {
    const idx = text.indexOf(marker)
    if (idx >= 0) {
      start = idx
      break
    }
  }
  if (start === 0) {
    for (const show of ["Show more Show less", "Show more", "Pokaż więcej"]) {
      const idx = text.indexOf(show)
      if (idx >= 0) {
        start = idx + show.length
        break
      }
    }
  }

  let body = (start ? text.slice(start) : text).trim()
  for (const endMarker of _LINKEDIN_JD_END) {
    const idx = body.indexOf(endMarker)
    if (idx > 80) {
      body = body.slice(0, idx).trim()
      break
    }
  }
  const cleaned = stripBoilerplate(body)
  return cleaned.length >= 40 ? cleaned : stripBoilerplate(text)
}

export function buildListingDescription(
  title: string,
  parts: Array<string | null | undefined>,
  max = 300,
): string {
  const extras = parts
    .map((p) => (p || "").trim())
    .filter((p) => p && p.toLowerCase() !== title.trim().toLowerCase())
  const unique: string[] = []
  for (const p of extras) {
    if (!unique.some((u) => u.toLowerCase() === p.toLowerCase())) unique.push(p)
  }
  const combined = unique.length ? `${title.trim()} — ${unique.join(" · ")}` : title.trim()
  return excerpt(combined, max) ?? title.trim()
}

export function excerptJobDescription(text: string | null | undefined, max = 2000): string | null {
  const cleaned = stripBoilerplate(text || "")
  if (!cleaned) return null
  return excerpt(cleaned, max)
}
