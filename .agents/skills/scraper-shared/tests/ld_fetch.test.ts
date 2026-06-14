import { describe, expect, test } from "bun:test"
import { matchesKeyword } from "../src/ld_fetch.js"
import type { JobCard } from "../src/types.js"

const card: JobCard = {
  id: "1",
  title: "Python Developer",
  company: "Acme",
  location: "Warszawa",
  date: "2026-06-01",
  deadline: null,
  salary: null,
  url: "https://example.com/job/1",
  description: "Backend Python role",
}

describe("matchesKeyword", () => {
  test("empty keyword matches all", () => {
    expect(matchesKeyword(card, "")).toBe(true)
  })

  test("matches title", () => {
    expect(matchesKeyword(card, "python")).toBe(true)
  })

  test("rejects unrelated keyword", () => {
    expect(matchesKeyword(card, "golang")).toBe(false)
  })
})
