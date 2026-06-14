import { option } from "@bunli/core"
import { z } from "zod"
import { createSearchCommand } from "scraper-shared"
import { searchJustJoin } from "../helpers.js"

export const search = createSearchCommand({
  description: "Search job listings on JustJoin.it",
  extraOptions: {
    listingOnly: option(z.coerce.boolean().default(true), {
      description: "Parse listing page only (faster, no per-offer fetch)",
    }),
  },
  search: async (flags) =>
    searchJustJoin(
      flags.query ?? "",
      flags.page,
      flags.days,
      flags.limit ?? 30,
      flags.listingOnly,
    ),
})
