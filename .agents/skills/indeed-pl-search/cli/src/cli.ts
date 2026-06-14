import { runPortalCli } from "scraper-shared"
import { search } from "./commands/search.js"
import { detail } from "./commands/detail.js"

await runPortalCli({
  name: "indeed-pl-cli",
  description: "CLI for searching jobs on Indeed Poland",
  search,
  detail,
})
