import { describe, expect, test } from "bun:test"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import {
  extractOfferLinks,
  isNoiseOffer,
  parseListingCards,
  slugifyKeyword,
} from "../src/helpers.js"

const fixtureHtml = readFileSync(
  join(import.meta.dir, "fixtures/praca-pl-listing.html"),
  "utf-8",
)

describe("slugifyKeyword", () => {
  test("slugifies COO query", () => {
    expect(slugifyKeyword('"COO" warszawa')).toBe("coo-warszawa")
  })
})

describe("extractOfferLinks", () => {
  test("finds offer URLs in fixture", () => {
    const links = extractOfferLinks(fixtureHtml)
    expect(links.length).toBeGreaterThan(5)
    expect(links[0]).toMatch(/praca\.pl\/.+_\d+\.html$/)
  })
})

describe("parseListingCards", () => {
  test("parses cards from fixture without network", () => {
    const cards = parseListingCards(fixtureHtml, "praktykant", 5)
    expect(cards.length).toBeGreaterThan(0)
    expect(cards[0].title.length).toBeGreaterThan(3)
    expect(cards[0].url).toContain("praca.pl")
  })

  test("description includes listing metadata when available", () => {
    const cards = parseListingCards(fixtureHtml, "", 10)
    const withLocation = cards.find((c) => c.location && c.description !== c.title)
    if (withLocation) {
      expect(withLocation.description).toContain(withLocation.title)
      expect(withLocation.description!.length).toBeGreaterThan(withLocation.title.length)
    }
  })

  test("fixture listing has no cookie noise in descriptions", () => {
    const cards = parseListingCards(fixtureHtml, "", 20)
    for (const card of cards) {
      expect(card.description?.toLowerCase() ?? "").not.toMatch(/cookie/)
    }
  })
})

describe("praca-pl noise filter", () => {
  test("rejects podobne oferty listing", () => {
    expect(isNoiseOffer("Magazynier", "Podobne oferty", "Wróć do listy ofert")).toBe(true)
  })

  test("accepts real offer", () => {
    expect(
      isNoiseOffer(
        "IT Project Manager",
        "Acme Sp. z o.o.",
        "Zarządzanie projektami IT w środowisku korporacyjnym zespołu 15 osób.",
      ),
    ).toBe(false)
  })
})
