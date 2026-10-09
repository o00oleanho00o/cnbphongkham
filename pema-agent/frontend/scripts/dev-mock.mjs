// `pnpm dev:mock`: the mock backend plus `next dev` pointed at it (cross-platform: sets the env var
// itself, so it works on Windows and Ubuntu). The mock also plays the agent service (mock/agent.ts).
import { spawn } from "node:child_process";

const port = process.env.MOCK_PORT ?? "4010";
const mockUrl = `http://127.0.0.1:${port}`;
const env = {
  ...process.env,
  MOCK_PORT: port,
  PEMA_API_URL: mockUrl,
  PEMA_AGENT_INTERNAL_URL: mockUrl,
};

const children = [
  spawn("pnpm", ["mock"], { stdio: "inherit", shell: true, env }),
  spawn("pnpm", ["dev"], { stdio: "inherit", shell: true, env }),
];

function stop() {
  for (const c of children) c.kill();
}
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
for (const c of children) c.on("exit", stop);
