import { option } from "@bunli/core"
import { z } from "zod"
import { createSearchCommand } from "scraper-shared"
import { searchPracaPl } from "../helpers.js"

export const search = createSearchCommand({
  description: "Search job listings on Praca.pl",
  extraOptions: {
    listingOnly: option(z.coerce.boolean().default(true), {
      description: "Parse listing page only (faster, no per-offer fetch)",
    }),
  },
  search: async (flags) =>
    searchPracaPl(
      flags.query ?? "",
      flags.page,
      flags.days,
      flags.limit ?? 30,
      flags.maxAgeHours ?? 0,
      flags.listingOnly ? false : (flags.strictFreshness ?? false),
      flags.listingOnly,
    ),
})
