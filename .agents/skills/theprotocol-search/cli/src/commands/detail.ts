import { createDetailCommand } from "scraper-shared"
import { detailTheProtocol } from "../helpers.js"

export const detail = createDetailCommand({
  description: "Fetch full job detail from TheProtocol.it",
  fetchDetail: detailTheProtocol,
})
