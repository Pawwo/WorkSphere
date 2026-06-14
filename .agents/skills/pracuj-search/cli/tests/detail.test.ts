import { describe, expect, test } from "bun:test"
import { extractPracujDetailFromHtml } from "../src/helpers.js"

describe("extractPracujDetailFromHtml", () => {
  test("does not fall back to full body HTML", () => {
    const html = "<html><body><nav>Menu cookies</nav><div>no offer view</div></body></html>"
    const text = extractPracujDetailFromHtml(html)
    expect(text).toBe("")
    expect(text).not.toMatch(/cookie/i)
  })

  test("extracts offer view section when present", () => {
    const html =
      '<div data-test="section-offerView"><p>Senior developer with Kotlin experience.</p></div></div>'
    expect(extractPracujDetailFromHtml(html)).toContain("Kotlin")
  })
})
