import { describe, expect, test } from "bun:test"
import { parseOffers } from "../src/helpers.js"

describe("parseOffers", () => {
  test("stores technologies separately from description", () => {
    const nextData = {
      props: {
        pageProps: {
          offersResponse: {
            offers: [
              {
                id: "123",
                offerUrlName: "senior-dev",
                title: "Senior Developer",
                employer: "Acme",
                technologies: ["Kotlin", "AWS"],
                publicationDateUtc: "2026-06-01T10:00:00Z",
                locationDisplay: "Warszawa",
              },
            ],
          },
        },
      },
    }
    const cards = parseOffers(nextData, 0, "")
    expect(cards).toHaveLength(1)
    expect(cards[0].technologies).toBe("Kotlin, AWS")
    expect(cards[0].description).toBeNull()
  })
})
