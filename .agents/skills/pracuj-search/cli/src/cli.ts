import { runPortalCli } from "scraper-shared"
import { search } from "./commands/search.js"
import { detail } from "./commands/detail.js"

await runPortalCli({
  name: "pracuj-cli",
  description: "CLI for searching jobs on Pracuj.pl (IT)",
  search,
  detail,
})
