// Công cụ của agent: every tool the agent has or may have, grouped as the agent's own (lõi) and the plugins', each
// with an on/off switch and a way back to what the profile says. A switch moves at once and goes back when the
// agent refuses. Changes apply from the next reply of the agent.
import { useEffect, useState } from "react";

import {
  Badge,
  Button,
  Card,
  Empty,
  type KitTone,
  Notice,
  PageHeader,
  Toggle,
} from "@/components/agent/plugin-kit";
import { agentApi as api } from "@/lib/agent/api";
import {
  type AgentTool,
  groupTools,
  isToolList,
  TOOL_HINTS,
  TOOLS_PATH,
  toolPath,
  withEnabled,
} from "@/lib/agent/agent-tools";

type Message = { tone: KitTone; text: string };

const errorText = (err: unknown) => (err instanceof Error ? err.message : "Lỗi");

function accept(answer: unknown): AgentTool[] {
  if (!isToolList(answer)) throw new Error("Câu trả lời của agent không đúng dạng.");
  return answer.tools;
}

export function ToolsPage() {
  const [tools, setTools] = useState<AgentTool[] | null>(null);
  const [message, setMessage] = useState<Message | null>(null);
  const [busy, setBusy] = useState("");

  useEffect(() => {
    api
      .get<unknown>(TOOLS_PATH)
      .then((answer) => setTools(accept(answer)))
      .catch((err: unknown) => setMessage({ tone: "danger", text: errorText(err) }));
  }, []);

  /** `enabled` null gives the tool back to the profile. The switch moves first; a refusal puts it back. */
  async function put(tool: AgentTool, enabled: boolean | null) {
    const before = tools;
    setBusy(tool.name);
    setMessage(null);
    if (enabled !== null)
      setTools((current) => current && withEnabled(current, tool.name, enabled));
    try {
      setTools(accept(await api.put<unknown>(toolPath(tool.name), { enabled })));
    } catch (err) {
      setTools(before);
      setMessage({ tone: "danger", text: errorText(err) });
    } finally {
      setBusy("");
    }
  }

  if (!tools) {
    return (
      <div>
        <PageHeader title="Công cụ" />
        {message && <Notice tone={message.tone}>{message.text}</Notice>}
      </div>
    );
  }

  const groups = groupTools(tools);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Công cụ"
        subtitle="Các công cụ agent có hoặc có thể có; bật hoặc tắt từng cái. Thay đổi áp dụng từ lượt trả lời tiếp theo của agent, không cần khởi động lại."
      />
      {message && <Notice tone={message.tone}>{message.text}</Notice>}
      {groups.length === 0 && (
        <Card>
          <Empty>Agent chưa có công cụ nào. Bật một plugin có công cụ để thấy nó ở đây.</Empty>
        </Card>
      )}
      {groups.map((group) => (
        <Card
          key={group.key}
          title={group.title}
          aside={<span className="text-small text-ink-soft">{group.tools.length} công cụ</span>}
        >
          <ul aria-label={group.title} className="divide-y divide-line">
            {group.tools.map((tool) => (
              <li key={tool.name}>
                <ToolRow tool={tool} busy={busy === tool.name} onPut={put} />
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}

function ToolRow({
  tool,
  busy,
  onPut,
}: {
  tool: AgentTool;
  busy: boolean;
  onPut: (tool: AgentTool, enabled: boolean | null) => void;
}) {
  const hint = TOOL_HINTS[tool.name];
  return (
    <div className="flex flex-wrap items-center gap-3 px-1 py-3">
      <div className="min-w-0 flex-1 basis-56">
        <p className="truncate font-semibold text-ink">{tool.name}</p>
        <p className="text-small text-ink-soft">{tool.description}</p>
        {hint && <p className="mt-1 text-small text-ink-soft">{hint}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {tool.stored ? <Badge tone="info">Đã chỉnh</Badge> : <Badge>Mặc định</Badge>}
        {tool.stored && (
          <span className="text-small text-ink-soft">Mặc định: {tool.default ? "bật" : "tắt"}</span>
        )}
        {tool.stored && (
          <Button
            variant="ghost"
            aria-label={`Về mặc định: ${tool.name}`}
            disabled={busy}
            onClick={() => onPut(tool, null)}
          >
            Về mặc định
          </Button>
        )}
        <Toggle
          label={`${tool.enabled ? "Tắt" : "Bật"} ${tool.name}`}
          checked={tool.enabled}
          disabled={busy}
          onChange={(next) => onPut(tool, next)}
        />
      </div>
    </div>
  );
}
