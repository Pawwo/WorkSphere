import { runPortalCli } from "scraper-shared"
import { search } from "./commands/search.js"
import { detail } from "./commands/detail.js"

await runPortalCli({
  name: "rocketjobs-cli",
  description: "CLI for searching jobs on RocketJobs.pl",
  search,
  detail,
})
