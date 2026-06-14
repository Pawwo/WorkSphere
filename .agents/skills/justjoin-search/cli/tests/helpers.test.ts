import { describe, expect, test } from "bun:test"
import { parseListingCards } from "../src/helpers.js"

describe("parseListingCards", () => {
  test("builds description from listing anchor beyond title slug", () => {
    const html = `
      <a href="/job-offer/acme-senior-developer-warsaw">
        Senior Developer · Acme · Warsaw
      </a>
    `
    const cards = parseListingCards(html, "", 0, 5)
    expect(cards.length).toBe(1)
    expect(cards[0].description).toContain("Senior Developer")
    expect(cards[0].description!.length).toBeGreaterThan(cards[0].title.length)
  })

  test("skips company profile links", () => {
    const html = `<a href="/company/acme">Acme profile</a>`
    const cards = parseListingCards(html, "", 0, 5)
    expect(cards.length).toBe(0)
  })
})
