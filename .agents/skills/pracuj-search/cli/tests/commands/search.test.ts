import { describe, expect, test } from "bun:test"
import { parsePracujOffers } from "../../src/helpers.js"

describe("parsePracujOffers", () => {
  test("returns empty for invalid data", () => {
    expect(parsePracujOffers({})).toEqual([])
  })
})
