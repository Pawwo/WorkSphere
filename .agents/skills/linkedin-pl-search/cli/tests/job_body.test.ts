import { describe, expect, test } from "bun:test"
import { extractLinkedInJobBody } from "scraper-shared"

describe("LinkedIn job body extraction", () => {
  test("removes privacy and similar jobs noise from scraped markup text", () => {
    const raw =
      "LinkedIn szanuje Twoją prywatność. ACME IS HIRING Senior PM for cloud programs. Podobne oferty in Kraków."
    const body = extractLinkedInJobBody(raw)
    expect(body).not.toMatch(/prywatność/i)
    expect(body).not.toMatch(/podobne oferty/i)
    expect(body).toContain("Senior PM")
  })
})
