import { describe, expect, test } from "bun:test"
import { matchesSearchQuery } from "../src/http.js"

describe("matchesSearchQuery", () => {
  test("matches all tokens when URL sits between title and city", () => {
    const haystack =
      "Chief Operating Officer https://www.praca.pl/chief-operating-officer-szczecin_1.html Szczecin"
    expect(matchesSearchQuery(haystack, "Chief Operating Officer Szczecin")).toBe(true)
  })

  test("rejects when a token is missing", () => {
    const haystack = "Chief Operating Officer https://www.praca.pl/coo_1.html Warszawa"
    expect(matchesSearchQuery(haystack, "Chief Operating Officer Szczecin")).toBe(false)
  })
})
