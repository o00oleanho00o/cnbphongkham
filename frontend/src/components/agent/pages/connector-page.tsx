// The page of one connector (`/admin/agent/plugins/<name>`, for a name whose script a connector loaded: Zalo). A
// connector is its own service, not an agent plugin: there is no switch or settings here, only its name and the pages
// its script ships, drawn at `/admin/agent/plugins/<name>/<page>` like the pages of a plugin.
import { Link } from "@/lib/link";

import {
  PluginsProblem,
  pluginPageHref,
  useAgentPlugins,
} from "@/components/agent/agent-plugins";
import { PluginDetailPage } from "@/components/agent/pages/plugin-detail-page";
import { PluginPageHost } from "@/components/agent/plugin-page-host";
import { Badge, Card } from "@/components/agent/plugin-kit";
import { SubNav } from "@/components/agent/sub-nav";
import { pluginHref, PLUGINS_HREF } from "@/lib/agent/plugins";
import { PageHeading } from "@/ui/workspace";

/** A connector's page when a connector registered `name`, else the agent plugin's page (once loading is over). */
export function PluginOrConnectorPage({ name, pageId }: { name: string; pageId?: string }) {
  const { state, retry, registered } = useAgentPlugins();
  if (registered.get(name)?.connector) return <ConnectorPage name={name} pageId={pageId} />;
  if (state.kind === "loading") return <PluginsProblem state={state} retry={retry} />;
  return <PluginDetailPage name={name} pageId={pageId} />;
}

function ConnectorPage({ name, pageId }: { name: string; pageId?: string }) {
  const { registered } = useAgentPlugins();
  const pages = registered.get(name)?.pages ?? [];
  const items = [
    { href: pluginHref(name), label: "Tổng quan", exact: true },
    ...pages.map((page) => ({ href: pluginPageHref(name, page.id), label: page.title })),
  ];
  return (
    <div>
      <Link
        href={PLUGINS_HREF}
        className="mb-2 inline-flex min-h-11 items-center text-small text-link hover:underline lg:min-h-9"
      >
        ‹ Plugins
      </Link>
      <PageHeading
        title={name}
        subtitle="Connector: dịch vụ riêng ngoài agent, trang quản trị do chính nó phục vụ."
      />
      <p className="-mt-2 mb-4 flex flex-wrap gap-2">
        <Badge tone="info">Connector</Badge>
      </p>
      <SubNav label={`Trang của connector ${name}`} items={items} />
      {pageId ? (
        <PluginPageHost plugin={name} pageId={pageId} />
      ) : (
        <Card title="Connector">
          <p className="text-small text-ink-soft">
            Connector {name} chạy như một dịch vụ riêng; web phòng khám chỉ chuyển tiếp tới nó. Các
            trang quản trị của nó nằm ở các tab phía trên.
          </p>
        </Card>
      )}
    </div>
  );
}
