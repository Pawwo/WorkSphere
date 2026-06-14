import { option } from "@bunli/core"
import { z } from "zod"
import { createSearchCommand } from "scraper-shared"
import { searchRocketJobs } from "../helpers.js"

export const search = createSearchCommand({
  description: "Search job listings on RocketJobs.pl",
  extraOptions: {
    listingOnly: option(z.coerce.boolean().default(true), {
      description: "Parse listing page only (faster, no per-offer fetch)",
    }),
  },
  search: async (flags) =>
    searchRocketJobs(
      flags.query ?? "",
      flags.page,
      flags.days,
      flags.limit ?? 30,
      flags.listingOnly,
      flags.maxAgeHours ?? 0,
      flags.strictFreshness ?? false,
    ),
})
