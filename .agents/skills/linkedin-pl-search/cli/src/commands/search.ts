import { option } from "@bunli/core"
import { z } from "zod"
import { createSearchCommand } from "scraper-shared"
import { searchLinkedInPl } from "../helpers.js"

export const search = createSearchCommand({
  description: "Search job listings on LinkedIn Poland",
  extraOptions: {
    detailLimit: option(z.coerce.number().default(0), {
      description: "How many offers get full description fetch",
    }),
    pages: option(z.coerce.number().default(2), {
      description: "Number of listing pages to fetch",
    }),
  },
  search: async (flags) =>
    searchLinkedInPl(
      flags.query ?? "",
      flags.page,
      flags.days,
      flags.limit ?? 30,
      flags.detailLimit,
      flags.pages,
      flags.maxAgeHours ?? 0,
      flags.strictFreshness ?? false,
    ),
})
