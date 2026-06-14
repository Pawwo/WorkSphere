import { runPortalCli } from "scraper-shared"
import { search } from "./commands/search.js"
import { detail } from "./commands/detail.js"

await runPortalCli({
  name: "linkedin-pl-cli",
  description: "CLI for searching jobs on LinkedIn Poland",
  search,
  detail,
})
