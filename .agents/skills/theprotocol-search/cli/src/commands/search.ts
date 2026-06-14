import { option } from "@bunli/core"
import { z } from "zod"
import { createSearchCommand } from "scraper-shared"
import { searchTheProtocol } from "../helpers.js"

export const search = createSearchCommand({
  description: "Search job listings on TheProtocol.it",
  extraOptions: {
    location: option(z.string().optional(), {
      description: "Comma-separated cities (warszawa,krakow,wroclaw,...)",
    }),
    workMode: option(z.string().optional(), {
      description: "Comma-separated work modes (remote,hybrid,onsite)",
    }),
  },
  search: async (flags) => {
    const location = String((flags as { location?: string }).location ?? "")
    const workMode = String((flags as { workMode?: string }).workMode ?? "")
    return searchTheProtocol(
      flags.query ?? "",
      flags.page,
      flags.days,
      flags.limit,
      location.split(",").filter(Boolean),
      workMode.split(",").filter(Boolean),
      flags.maxAgeHours ?? 0,
      flags.strictFreshness ?? false,
    )
  },
})
