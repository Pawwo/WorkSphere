import { describe, expect, test } from "bun:test"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import {
  matchesQueryTokens,
  parseRocketListingCards,
  queryTokens,
} from "../src/helpers.js"

const fixture = readFileSync(
  join(import.meta.dir, "fixtures/listing_sample.html"),
  "utf-8",
)

describe("queryTokens", () => {
  test("drops stop words and short tokens", () => {
    expect(queryTokens('"Python developer" Warszawa hybrid')).toEqual(["python"])
  })

  test("keeps docker token", () => {
    expect(queryTokens("Docker Szczecin")).toContain("docker")
  })
})

describe("matchesQueryTokens", () => {
  test("avoids coo substring false positive in coordinating", () => {
    expect(matchesQueryTokens("coordinating team member", ["coo"])).toBe(false)
  })

  test("matches docker in slug", () => {
    expect(
      matchesQueryTokens(
        "docker ops engineer https://rocketjobs.pl/oferta-pracy/docker-ops",
        ["docker"],
      ),
    ).toBe(true)
  })
})

describe("parseRocketListingCards", () => {
  test("matches python developer by token", () => {
    const cards = parseRocketListingCards(fixture, "Python developer", 10)
    expect(cards.some((c) => c.url.includes("python-developer"))).toBe(true)
    expect(cards.some((c) => c.url.includes("coordinating"))).toBe(false)
  })

  test("matches docker via link fallback", () => {
    const cards = parseRocketListingCards(fixture, "Docker", 10)
    expect(cards.some((c) => c.url.includes("docker-ops"))).toBe(true)
  })
})
