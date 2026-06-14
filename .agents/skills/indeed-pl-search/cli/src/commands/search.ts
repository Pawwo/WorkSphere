import { option } from "@bunli/core"
import { z } from "zod"
import { createSearchCommand } from "scraper-shared"
import { searchIndeedPl } from "../helpers.js"

export const search = createSearchCommand({
  description: "Search job listings on Indeed Poland",
  extraOptions: {
    detailLimit: option(z.coerce.number().default(0), {
      description: "How many offers get full description fetch (Playwright)",
    }),
  },
  search: async (flags) =>
    searchIndeedPl(
      flags.query ?? "",
      flags.page,
      flags.days,
      flags.limit ?? 30,
      flags.detailLimit ?? 0,
    ),
})
