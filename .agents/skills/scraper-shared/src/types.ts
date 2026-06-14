export interface JobCard {
  id: string
  title: string
  company: string | null
  location: string | null
  date: string | null
  deadline: string | null
  salary: string | null
  url: string
  description: string | null
  /** Stack / tags from listing (TheProtocol etc.) — not a job description body */
  technologies?: string | null
}

export interface SearchMeta {
  total: number
  page: number
  perPage: number
}

export interface SearchOutput {
  meta: SearchMeta
  results: JobCard[]
}

export type OutputFormat = "json" | "table" | "plain"

export interface SearchResult {
  total: number
  page: number
  perPage: number
  results: JobCard[]
}
