export function titleFromSlug(
  url: string,
  pathSegment: string,
  stopWords: string[] = [],
): string {
  const slug = url.split(pathSegment)[1]?.split("?")[0] ?? url
  const parts = slug.split("-").filter((part) => !stopWords.includes(part.toLowerCase()))
  if (!parts.length) {
    return slug.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  }
  return parts.join(" ").replace(/\b\w/g, (c) => c.toUpperCase())
}
