import { createDetailCommand } from "scraper-shared"
import { detailPracaPl } from "../helpers.js"

export const detail = createDetailCommand({
  description: "Fetch full job detail from Praca.pl",
  fetchDetail: detailPracaPl,
})
