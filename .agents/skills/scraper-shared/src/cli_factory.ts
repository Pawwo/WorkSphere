import { createCLI, type Command } from "@bunli/core"

export interface PortalCliConfig {
  name: string
  version?: string
  description: string
  search: Command<any, any, any>
  detail: Command<any, any, any>
}

export async function runPortalCli(config: PortalCliConfig): Promise<void> {
  const cli = await createCLI({
    name: config.name,
    version: config.version ?? "1.0.0",
    description: config.description,
  })
  cli.command(config.search)
  cli.command(config.detail)
  await cli.run()
}
