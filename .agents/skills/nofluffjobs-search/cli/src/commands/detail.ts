import { createDetailCommand } from "scraper-shared"
import { detailNoFluffJobs } from "../helpers.js"

export const detail = createDetailCommand({
  description: "Fetch full job detail from NoFluffJobs",
  fetchDetail: detailNoFluffJobs,
})
