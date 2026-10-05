// `pnpm mock`: start the mock backend on MOCK_PORT (default 4010).
import { startMockServer } from "./server";

const port = Number.parseInt(process.env.MOCK_PORT ?? "4010", 10);
await startMockServer(port);
process.stdout.write(`pema mock backend on http://127.0.0.1:${port}\n`);
