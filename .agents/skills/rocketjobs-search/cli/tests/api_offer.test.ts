import { describe, expect, test } from "bun:test"
import { apiOfferToCard } from "../src/api.js"

describe("apiOfferToCard", () => {
  test("uses API snippet instead of title for description", () => {
    const card = apiOfferToCard({
      slug: "senior-dev-acme",
      title: "Senior Developer",
      shortDescription: "Build scalable microservices with Kotlin and AWS.",
      companyName: "Acme",
      city: "Warszawa",
    })
    expect(card.description).toContain("microservices")
    expect(card.description).not.toBe("Senior Developer")
  })

  test("falls back to title when no snippet fields", () => {
    const card = apiOfferToCard({
      slug: "dev",
      title: "Developer",
    })
    expect(card.description).toBe("Developer")
  })
})
