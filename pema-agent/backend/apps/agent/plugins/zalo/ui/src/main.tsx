/** Adds the Zalo pages to the dashboard. */
import { BridgePage } from "./pages/bridge";
import { AccountsPage } from "./pages/accounts";
import { ContactsPage } from "./pages/contacts";
import { FriendsPage } from "./pages/friends";
import { GroupsPage } from "./pages/groups";
import { zalo } from "./client";
import { sdk } from "./sdk";

/** The channels of this plugin are named `zalo-<account id>`; people on other channels are not ours to name. */
const CHANNEL_PREFIX = "zalo-";
const MAX_IDS = 60;

sdk.register("zalo", {
  pages: [
    { id: "accounts", title: "Tài khoản Zalo", component: AccountsPage },
    { id: "contacts", title: "Danh bạ Zalo", component: ContactsPage },
    { id: "friends", title: "Bạn bè Zalo", component: FriendsPage },
    { id: "groups", title: "Nhóm Zalo", component: GroupsPage },
    { id: "bridge", title: "Cầu nối Zalo", component: BridgePage },
  ],
  personNames: async (channel, userIds) => {
    if (!channel.startsWith(CHANNEL_PREFIX) || userIds.length === 0) return {};
    return zalo.names(channel.slice(CHANNEL_PREFIX.length), userIds.slice(0, MAX_IDS));
  },
});
