import { createDetailCommand } from "scraper-shared"
import { detailPracuj } from "../helpers.js"

export const detail = createDetailCommand({
  description: "Fetch full detail for a Pracuj.pl job listing",
  fetchDetail: detailPracuj,
  notFoundWhen: (msg) => msg.includes("Not found"),
})
