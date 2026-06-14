export function extractHrefs(html: string, pattern: RegExp, baseUrl: string): string[] {
  const links = new Set<string>()
  for (const match of html.matchAll(pattern)) {
    const href = match[1]
    const full = href.startsWith("http") ? href : `${baseUrl.replace(/\/$/, "")}${href.startsWith("/") ? href : `/${href}`}`
    links.add(full.split("?")[0])
  }
  return [...links]
}

export function resolveJobUrl(idOrUrl: string, urlTemplate: (id: string) => string): string {
  return idOrUrl.startsWith("http") ? idOrUrl : urlTemplate(idOrUrl)
}
