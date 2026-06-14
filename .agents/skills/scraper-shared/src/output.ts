import type { JobCard, OutputFormat, SearchOutput } from "./types.js"

export function outputSearch(output: SearchOutput, format: OutputFormat): void {
  if (format === "json") {
    console.log(JSON.stringify(output, null, 2))
    return
  }
  if (format === "table") {
    outputTable(output.results)
    return
  }
  outputPlain(output.results)
}

export function outputJob(job: JobCard, format: OutputFormat): void {
  if (format === "json") {
    console.log(JSON.stringify(job, null, 2))
    return
  }
  if (format === "plain") {
    printJob(job)
    return
  }
  outputTable([job])
}

function outputTable(results: JobCard[]): void {
  console.log("id\ttitle\tcompany\tlocation\tsalary")
  for (const r of results) {
    const id = r.id.slice(0, 20).padEnd(20)
    const title = r.title.slice(0, 40).padEnd(40)
    const company = (r.company ?? "-").slice(0, 20).padEnd(20)
    const location = (r.location ?? "-").slice(0, 20)
    const salary = (r.salary ?? "-").slice(0, 20)
    console.log(`${id}\t${title}\t${company}\t${location}\t${salary}`)
  }
}

function outputPlain(results: JobCard[]): void {
  for (const r of results) printJob(r)
}

function printJob(r: JobCard): void {
  console.log(`id: ${r.id}`)
  console.log(`title: ${r.title}`)
  console.log(`company: ${r.company ?? "-"}`)
  console.log(`location: ${r.location ?? "-"}`)
  console.log(`date: ${r.date ?? "-"}`)
  console.log(`deadline: ${r.deadline ?? "-"}`)
  console.log(`salary: ${r.salary ?? "-"}`)
  console.log(`url: ${r.url}`)
  if (r.description) console.log(`description: ${r.description}`)
  console.log("")
}
