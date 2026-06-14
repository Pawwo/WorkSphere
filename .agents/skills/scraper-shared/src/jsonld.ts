export function parseJobPostingLd(html: string): Record<string, unknown> | null {
  const scripts = [...html.matchAll(/<script[^>]*type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/gi)]
  for (const match of scripts) {
    const raw = match[1]?.trim()
    if (!raw) continue
    try {
      const data = JSON.parse(raw) as unknown
      const candidates = Array.isArray(data) ? data : [data]
      for (const item of candidates) {
        if (!item || typeof item !== "object") continue
        const record = item as Record<string, unknown>
        const graph = record["@graph"]
        if (Array.isArray(graph)) {
          for (const node of graph) {
            if (node && typeof node === "object" && (node as Record<string, unknown>)["@type"] === "JobPosting") {
              return node as Record<string, unknown>
            }
          }
        }
        if (record["@type"] === "JobPosting") return record
      }
    } catch {
      continue
    }
  }
  return null
}

export function ldSalary(ld: Record<string, unknown>): string {
  const baseSalary = ld.baseSalary
  if (!baseSalary || typeof baseSalary !== "object") return ""
  const bs = baseSalary as Record<string, unknown>
  const value = bs.value
  if (!value || typeof value !== "object") return ""
  const v = value as Record<string, unknown>
  const currency = String(bs.currency ?? v.currency ?? "PLN")
  const unit = String(v.unitText ?? "")
  const minValue = v.minValue
  const maxValue = v.maxValue
  const single = v.value
  if (minValue && maxValue) return `${minValue} - ${maxValue} ${currency}/${unit}`.replace(/\/$/, "")
  if (single) return `${single} ${currency}/${unit}`.replace(/\/$/, "")
  if (minValue) return `Od ${minValue} ${currency}/${unit}`.replace(/\/$/, "")
  return ""
}

export function ldLocation(ld: Record<string, unknown>): string {
  if (ld.jobLocationType === "TELECOMMUTE") return "Remote"
  let loc = ld.jobLocation
  if (Array.isArray(loc) && loc.length > 0) loc = loc[0]
  if (loc && typeof loc === "object") {
    const addr = (loc as Record<string, unknown>).address
    if (addr && typeof addr === "object") {
      return String((addr as Record<string, unknown>).addressLocality ?? "")
    }
  }
  return ""
}

export function isRecentHours(
  datePosted: string | undefined,
  maxAgeHours: number,
  strict = false,
): boolean {
  if (maxAgeHours <= 0) return true
  if (!datePosted) return !strict
  try {
    const dt = new Date(datePosted.replace("Z", "+00:00"))
    if (Number.isNaN(dt.getTime())) return !strict
    const cutoff = Date.now() - maxAgeHours * 60 * 60 * 1000
    return dt.getTime() >= cutoff
  } catch {
    return !strict
  }
}

export function isRecent(datePosted: string | undefined, days: number, strict = false): boolean {
  if (days <= 0) return isRecentHours(datePosted, 0, strict)
  return isRecentHours(datePosted, days * 24, strict)
}

export function ldToJobCard(ld: Record<string, unknown>, url: string, id?: string): {
  id: string
  title: string
  company: string | null
  location: string | null
  date: string | null
  deadline: string | null
  salary: string | null
  url: string
  description: string | null
} {
  const org = ld.hiringOrganization
  const company =
    org && typeof org === "object" ? String((org as Record<string, unknown>).name ?? "") || null : null
  const desc = ld.description
  const description =
    typeof desc === "string" ? desc.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim() : null
  return {
    id: id ?? url,
    title: String(ld.title ?? ""),
    company,
    location: ldLocation(ld) || null,
    date: typeof ld.datePosted === "string" ? ld.datePosted.slice(0, 10) : null,
    deadline: typeof ld.validThrough === "string" ? ld.validThrough.slice(0, 10) : null,
    salary: ldSalary(ld) || null,
    url,
    description,
  }
}
