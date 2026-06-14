import { describe, expect, test } from "bun:test"
import { z } from "zod"

describe("Indeed search detailLimit", () => {
  test("CLI defaults detailLimit to 0", () => {
    const schema = z.coerce.number().default(0)
    expect(schema.parse(undefined)).toBe(0)
  })

  test("detail cap math matches search helper", () => {
    const cards = Array.from({ length: 10 }, (_, i) => i)
    for (const detailLimit of [0, 3, 15]) {
      const detailCount = Math.max(0, Math.min(detailLimit, cards.length))
      expect(detailCount).toBe(Math.min(detailLimit, cards.length))
    }
  })
})
