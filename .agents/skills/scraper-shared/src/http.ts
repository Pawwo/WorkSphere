export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

export async function sleepJitter(minSeconds = 0.5, maxSeconds = 1.5): Promise<void> {
  const wait = minSeconds + Math.random() * (maxSeconds - minSeconds)
  await new Promise((resolve) => setTimeout(resolve, wait * 1000))
}

export function isCloudflareChallenge(html: string, status: number): boolean {
  if (status === 403) return true
  const lower = html.toLowerCase()
  return (
    lower.includes("just a moment") ||
    lower.includes("cf-challenge") ||
    lower.includes("enable javascript and cookies to continue") ||
    (lower.includes("<title>attention required") && lower.includes("cloudflare"))
  )
}

const HTTP_TIMEOUT_MS = 30_000

export async function curlFetch(url: string, acceptLanguage = "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7"): Promise<string> {
  const proc = Bun.spawn(
    [
      "curl",
      "-sL",
      "--max-time",
      "30",
      url,
      "-H",
      "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
      "-H",
      `Accept-Language: ${acceptLanguage}`,
      "-H",
      "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    ],
    { stdout: "pipe", stderr: "pipe" },
  )
  const stdout = await new Response(proc.stdout).text()
  const exitCode = await proc.exited
  if (exitCode !== 0) {
    const stderr = await new Response(proc.stderr).text()
    throw new Error(`curl failed: ${stderr || exitCode}`)
  }
  if (!stdout || isCloudflareChallenge(stdout, 200)) {
    throw new Error("Request blocked by Cloudflare")
  }
  return stdout
}

export async function htmlFetch(
  url: string,
  options: RequestInit & { retries?: number; acceptLanguage?: string; preferCurl?: boolean } = {},
): Promise<string> {
  const {
    retries = 3,
    acceptLanguage = "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    preferCurl = false,
    ...init
  } = options

  if (preferCurl) {
    return curlFetch(url, acceptLanguage)
  }

  let delay = 500

  for (let attempt = 0; attempt <= retries; attempt++) {
    const response = await fetch(url, {
      ...init,
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": acceptLanguage,
        ...(init.headers ?? {}),
      },
      redirect: "follow",
      signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
    })

    if (response.status === 429 || response.status >= 500) {
      if (attempt === retries) {
        throw new Error(`Request failed: ${response.status} ${response.statusText}`)
      }
      await new Promise((resolve) => setTimeout(resolve, delay + Math.random() * 500))
      delay = Math.min(delay * 2, 5000)
      continue
    }

    const text = await response.text()

    if (isCloudflareChallenge(text, response.status)) {
      try {
        return await curlFetch(url, acceptLanguage)
      } catch {
        if (attempt === retries) throw new Error("Request blocked by Cloudflare")
        await new Promise((resolve) => setTimeout(resolve, delay))
        continue
      }
    }

    if (response.status === 404) {
      throw new Error("Not found")
    }

    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`)
    }

    return text
  }

  throw new Error("Request failed after retries")
}

export function normalizeKeyword(keyword?: string): string {
  const value = (keyword ?? "").trim()
  if (value.toLowerCase().includes("global filter")) return ""
  return value
}

export function excerpt(text: string | null | undefined, max = 300): string | null {
  if (!text) return null
  const cleaned = text.replace(/\s+/g, " ").trim()
  if (!cleaned) return null
  return cleaned.length > max ? `${cleaned.slice(0, max)}...` : cleaned
}

export function stripHtml(html: string): string {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim()
}
