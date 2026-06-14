export function extractNextData(html: string): Record<string, unknown> | null {
  const match = html.match(/<script id="__NEXT_DATA__" type="application\/json">([\s\S]*?)<\/script>/)
  if (!match?.[1]) return null
  try {
    return JSON.parse(match[1]) as Record<string, unknown>
  } catch {
    return null
  }
}
