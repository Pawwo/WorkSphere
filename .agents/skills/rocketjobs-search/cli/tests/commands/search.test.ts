import { describe, expect, test } from "bun:test"
import { searchRocketJobs } from "../../src/helpers.js"

describe("rocketjobs-cli search", () => {
  test(
    "search completes under 15s for Python developer",
    async () => {
      const start = Date.now()
      const result = await searchRocketJobs("Python developer", 1, 2, 10, true, 48, false)
      expect(Date.now() - start).toBeLessThan(15_000)
      expect(Array.isArray(result.results)).toBe(true)
    },
    20_000,
  )
})
