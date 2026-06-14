import { createSearchCommand } from "scraper-shared"
import { searchPracuj } from "../helpers.js"

export const search = createSearchCommand({
  description: "Search IT job listings on Pracuj.pl",
  rateLimitAware: false,
  search: async (flags) =>
    searchPracuj(
      flags.query ?? "",
      flags.page,
      flags.days,
      flags.limit,
      flags.maxAgeHours ?? 0,
      flags.strictFreshness ?? false,
    ),
})
