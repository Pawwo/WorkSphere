import { createDetailCommand } from "scraper-shared"
import { detailRocketJobs } from "../helpers.js"

export const detail = createDetailCommand({
  description: "Fetch full job detail from RocketJobs.pl",
  fetchDetail: detailRocketJobs,
})
