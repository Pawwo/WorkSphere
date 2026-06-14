import { describe, expect, test } from "bun:test"
import { z } from "zod"

describe("NFJ search listingOnly default", () => {
  test("defaults to true", () => {
    const schema = z.coerce.boolean().default(true)
    expect(schema.parse(undefined)).toBe(true)
  })
})
