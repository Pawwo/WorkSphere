import { runPortalCli } from "scraper-shared"
import { search } from "./commands/search.js"
import { detail } from "./commands/detail.js"

await runPortalCli({
  name: "justjoin-cli",
  description: "CLI for searching jobs on JustJoin.it",
  search,
  detail,
})
