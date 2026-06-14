import { runPortalCli } from "scraper-shared"
import { search } from "./commands/search.js"
import { detail } from "./commands/detail.js"

await runPortalCli({
  name: "theprotocol-cli",
  description: "CLI for searching jobs on TheProtocol.it",
  search,
  detail,
})
