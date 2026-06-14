import { describe, expect, test } from "bun:test"
import { searchRocketJobsApi } from "../src/api.js"

describe("searchRocketJobsApi", () => {
  test(
    "returns docker-related offers quickly",
    async () => {
      const result = await searchRocketJobsApi("docker", 5, 14, 0, false)
      expect(result.results.length).toBeGreaterThan(0)
      expect(result.results[0]?.url).toContain("rocketjobs.pl/oferta-pracy/")
    },
    30_000,
  )
})
