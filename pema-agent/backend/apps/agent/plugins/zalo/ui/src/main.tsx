/** Adds the Zalo pages to the dashboard. */
import { BridgePage } from "./pages/bridge";
import { AccountsPage } from "./pages/accounts";
import { ContactsPage } from "./pages/contacts";
import { FriendsPage } from "./pages/friends";
import { GroupsPage } from "./pages/groups";
import { sdk } from "./sdk";

sdk.register("zalo", {
  pages: [
    { id: "accounts", title: "Tài khoản Zalo", component: AccountsPage },
    { id: "contacts", title: "Danh bạ Zalo", component: ContactsPage },
    { id: "friends", title: "Bạn bè Zalo", component: FriendsPage },
    { id: "groups", title: "Nhóm Zalo", component: GroupsPage },
    { id: "bridge", title: "Cầu nối Zalo", component: BridgePage },
  ],
});
