import { defineCommand, option } from "@bunli/core"
import { z } from "zod"
import type { JobCard, OutputFormat, SearchResult } from "./types.js"
import { writeError } from "./http.js"
import { outputJob, outputSearch } from "./output.js"

export const formatOption = option(z.enum(["json", "table", "plain"]).default("json"), {
  description: "Output format",
})

export const baseSearchOptions = {
  query: option(z.string().optional(), {
    short: "q",
    description: "Keyword search",
  }),
  page: option(z.coerce.number().default(1), {
    description: "Page number (1-indexed)",
  }),
  days: option(z.coerce.number().default(0), {
    description: "Max age of posting in days (0 = all)",
  }),
  maxAgeHours: option(z.coerce.number().default(0), {
    description: "Max age of posting in hours (0 = use days only)",
  }),
  strictFreshness: option(z.coerce.boolean().default(false), {
    description: "Exclude offers without a parseable publication date",
  }),
  limit: option(z.coerce.number().optional(), {
    description: "Cap total results returned",
  }),
  format: formatOption,
}

function classifySearchError(message: string, rateLimitAware: boolean): string {
  if (rateLimitAware && message.toLowerCase().includes("rate limit")) {
    return "RATE_LIMITED"
  }
  return "API_ERROR"
}

export interface BaseSearchFlags {
  query?: string
  page: number
  days: number
  maxAgeHours?: number
  strictFreshness?: boolean
  limit?: number
  format?: OutputFormat
}

export interface SearchCommandConfig<TExtra extends Record<string, unknown> = Record<string, never>> {
  description: string
  extraOptions?: Record<string, ReturnType<typeof option>>
  search: (flags: BaseSearchFlags & TExtra) => Promise<SearchResult>
  defaultLimit?: number
  rateLimitAware?: boolean
}

export function createSearchCommand<TExtra extends Record<string, unknown> = Record<string, never>>(
  config: SearchCommandConfig<TExtra>,
) {
  return defineCommand({
    name: "search",
    description: config.description,
    options: {
      ...baseSearchOptions,
      ...(config.extraOptions ?? {}),
    },
    handler: async ({ flags, signal }) => {
      if (signal.aborted) return
      try {
        const result = await config.search(flags as BaseSearchFlags & TExtra)
        outputSearch(
          { meta: { total: result.total, page: result.page, perPage: result.perPage }, results: result.results },
          (flags as BaseSearchFlags).format ?? "json",
        )
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        writeError(msg, classifySearchError(msg, config.rateLimitAware ?? true))
        process.exit(1)
      }
    },
  })
}

export interface DetailCommandConfig {
  description: string
  fetchDetail: (idOrUrl: string) => Promise<JobCard>
  notFoundWhen?: (message: string) => boolean
}

export function createDetailCommand(config: DetailCommandConfig) {
  const notFoundWhen = config.notFoundWhen ?? ((msg: string) => /not found/i.test(msg))
  return defineCommand({
    name: "detail",
    description: config.description,
    options: {
      format: formatOption,
    },
    handler: async ({ positional, flags, signal }) => {
      if (signal.aborted) return
      const id = positional[0]
      if (!id) {
        writeError("Job ID or URL is required", "MISSING_REQUIRED")
        process.exit(1)
      }
      try {
        const job = await config.fetchDetail(id)
        outputJob(job, flags.format)
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        writeError(msg, notFoundWhen(msg) ? "NOT_FOUND" : "API_ERROR")
        process.exit(1)
      }
    },
  })
}
