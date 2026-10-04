/**
 * Emergency stop of the zalo-personal bridge from a terminal: `pnpm kill-switch on`.
 * See README, "EMERGENCY OFF". The logic is in `src/kill-switch-cli.ts`.
 */
import { USAGE, parseKillSwitchArgs, sendKillSwitch } from "../src/kill-switch-cli.js";

function loadDotEnv(): void {
  try {
    process.loadEnvFile();
  } catch {
    /* no .env here: the variables may already be in the environment */
  }
}

async function main(): Promise<number> {
  loadDotEnv();
  const command = parseKillSwitchArgs(process.argv.slice(2));
  if ("error" in command) {
    console.error(`${command.error}\n${USAGE}`);
    return 2;
  }
  try {
    const result = await sendKillSwitch(command, process.env);
    console.log(`HTTP ${result.status} ${result.body}`);
    return result.ok ? 0 : 1;
  } catch (err) {
    console.error(err instanceof Error ? err.message : "kill-switch request failed");
    return 1;
  }
}

process.exit(await main());
