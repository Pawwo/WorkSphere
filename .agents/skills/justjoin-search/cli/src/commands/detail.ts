import { createDetailCommand } from "scraper-shared"
import { detailJustJoin } from "../helpers.js"

export const detail = createDetailCommand({
  description: "Fetch full job detail from JustJoin.it",
  fetchDetail: detailJustJoin,
})
