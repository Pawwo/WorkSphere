import { describe, expect, test } from "bun:test"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { parseListingCards } from "../../src/helpers.js"

describe("praca-pl-cli search", () => {
  test("parseListingCards returns results from fixture", () => {
    const html = readFileSync(join(import.meta.dir, "../fixtures/praca-pl-listing.html"), "utf-8")
    const cards = parseListingCards(html, "", 10)
    expect(cards.length).toBe(10)
  })
})
