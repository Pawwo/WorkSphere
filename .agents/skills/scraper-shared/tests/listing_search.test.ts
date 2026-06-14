import { describe, expect, test } from "bun:test"
import { listingDetailSearch } from "../src/listing_search.js"
import type { JobCard } from "../src/types.js"

describe("listingDetailSearch listingOnly", () => {
  const originalFetch = globalThis.fetch

  test("returns empty without detail fetch when listingOnly", async () => {
    globalThis.fetch = async () =>
      new Response("<html><body>no jobs</body></html>", { status: 200 })
    let detailCalls = 0
    const result = await listingDetailSearch({
      baseUrl: "https://example.com/jobs",
      extractLinks: () => ["https://example.com/jobs/1"],
      parseListing: () => [],
      fetchOffer: async () => {
        detailCalls += 1
        return null
      },
      keyword: "python",
      page: 1,
      days: 7,
      limit: 10,
      listingOnly: true,
    })

    expect(result.results).toEqual([])
    expect(result.total).toBe(0)
    expect(detailCalls).toBe(0)
    globalThis.fetch = originalFetch
  })

  test("returns listing without detail fetch when matches exist", async () => {
    globalThis.fetch = async () =>
      new Response("<html><body>jobs</body></html>", { status: 200 })
    const card: JobCard = {
      id: "1",
      title: "Python Dev",
      company: null,
      location: null,
      date: null,
      deadline: null,
      salary: null,
      url: "https://example.com/jobs/1",
      description: "Python Dev",
    }
    let detailCalls = 0
    const result = await listingDetailSearch({
      baseUrl: "https://example.com/jobs",
      extractLinks: () => [],
      parseListing: () => [card],
      fetchOffer: async () => {
        detailCalls += 1
        return null
      },
      keyword: "python",
      page: 1,
      days: 7,
      limit: 10,
      listingOnly: true,
    })

    expect(result.results).toHaveLength(1)
    expect(detailCalls).toBe(0)
    globalThis.fetch = originalFetch
  })
})
