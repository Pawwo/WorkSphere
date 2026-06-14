import { option } from "@bunli/core"
import { z } from "zod"
import { createSearchCommand } from "scraper-shared"
import { searchNoFluffJobs } from "../helpers.js"

export const search = createSearchCommand({
  description: "Search job listings on NoFluffJobs",
  extraOptions: {
    category: option(z.string().default("ai"), {
      description:
        "Category: all, backend, frontend, fullstack, devops, data, ai, testing, architecture, security",
    }),
    listingOnly: option(z.coerce.boolean().default(true), {
      description: "Parse listing page only (faster, no per-offer fetch)",
    }),
  },
  search: async (flags) =>
    searchNoFluffJobs(
      flags.query ?? "",
      flags.category,
      flags.days,
      flags.limit ?? 30,
      flags.listingOnly ?? true,
      flags.maxAgeHours ?? 0,
      flags.strictFreshness ?? false,
    ),
})
