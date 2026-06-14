import { createDetailCommand } from "scraper-shared"
import { detailIndeedPl } from "../helpers.js"

export const detail = createDetailCommand({
  description: "Fetch full job detail from Indeed Poland",
  fetchDetail: detailIndeedPl,
})
