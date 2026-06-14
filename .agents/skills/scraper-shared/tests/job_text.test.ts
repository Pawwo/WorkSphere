import { describe, expect, test } from "bun:test"
import {
  buildListingDescription,
  extractLinkedInJobBody,
  stripBoilerplate,
} from "../src/job_text.js"

describe("stripBoilerplate", () => {
  test("removes cookie banner text", () => {
    const raw = "We use cookies to improve experience. Senior Developer role in Warsaw."
    expect(stripBoilerplate(raw)).not.toMatch(/cookie/i)
    expect(stripBoilerplate(raw)).toContain("Senior Developer")
  })

  test("removes podobne oferty", () => {
    const raw = "Project Manager · Podobne oferty · Kraków"
    expect(stripBoilerplate(raw)).not.toMatch(/podobne oferty/i)
  })
})

describe("extractLinkedInJobBody", () => {
  test("strips LinkedIn privacy chrome", () => {
    const raw =
      "LinkedIn szanuje Twoją prywatność i używa cookies. ACME IS HIRING a Senior Engineer to build APIs. Podobne oferty in Warsaw."
    const body = extractLinkedInJobBody(raw)
    expect(body).not.toMatch(/prywatność/i)
    expect(body).not.toMatch(/podobne oferty/i)
    expect(body).toContain("Senior Engineer")
  })
})

describe("buildListingDescription", () => {
  test("combines title with location snippet", () => {
    const desc = buildListingDescription("IT PM", ["Warszawa", "Hybrid"])
    expect(desc).toContain("IT PM")
    expect(desc).toContain("Warszawa")
    expect(desc).not.toBe("IT PM")
  })
})
