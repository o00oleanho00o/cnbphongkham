// `bun run dev:mock`: the mock backend plus `vite dev` pointed at it (cross-platform: sets the env var
// itself, so it works on Windows and Ubuntu). The mock also plays the agent service (mock/agent.ts)
// and the Zalo connector (mock/connector-zalo.ts).
import { spawn } from "node:child_process";

const port = process.env.MOCK_PORT ?? "4010";
const mockUrl = `http://127.0.0.1:${port}`;
const env = {
  ...process.env,
  MOCK_PORT: port,
  PEMA_API_URL: mockUrl,
  PEMA_AGENT_INTERNAL_URL: mockUrl,
  // The fake Zalo connector (mock/connector-zalo.ts) answers under this path of the same server.
  PEMA_CONNECTOR_URLS: `zalo=${mockUrl}/connectors/zalo`,
};

const children = [
  spawn("bun", ["run", "mock"], { stdio: "inherit", shell: true, env }),
  spawn("bun", ["run", "dev"], { stdio: "inherit", shell: true, env }),
];

function stop() {
  for (const c of children) c.kill();
}
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
for (const c of children) c.on("exit", stop);
