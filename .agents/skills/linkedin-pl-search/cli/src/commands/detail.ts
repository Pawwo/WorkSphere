import { createDetailCommand } from "scraper-shared"
import { detailLinkedInPl } from "../helpers.js"

export const detail = createDetailCommand({
  description: "Fetch full job detail from LinkedIn Poland",
  fetchDetail: detailLinkedInPl,
})
