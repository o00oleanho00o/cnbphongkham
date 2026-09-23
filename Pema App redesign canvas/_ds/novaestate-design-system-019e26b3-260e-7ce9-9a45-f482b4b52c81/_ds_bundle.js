/* @ds-bundle: {"format":4,"namespace":"NovaEstateDesignSystem_019e26","components":[],"sourceHashes":{"ui_kits/dashboard/App.jsx":"a67066be903b","ui_kits/dashboard/AssetTable.jsx":"cfd8da3fb84b","ui_kits/dashboard/DealPipeline.jsx":"363c2a78e1d2","ui_kits/dashboard/Icon.jsx":"bf36ff991218","ui_kits/dashboard/KpiTile.jsx":"9788682e141b","ui_kits/dashboard/Lattice.jsx":"44d78b1348fd","ui_kits/dashboard/MarketPulse.jsx":"39d453fcac87","ui_kits/dashboard/Primitives.jsx":"02c7adf73756","ui_kits/dashboard/Sidebar.jsx":"cc14faa7ee6a","ui_kits/dashboard/TopBar.jsx":"210547fd011c"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.NovaEstateDesignSystem_019e26 = window.NovaEstateDesignSystem_019e26 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// ui_kits/dashboard/App.jsx
try { (() => {
// App.jsx — assembles the dashboard

const {
  useState
} = React;
function App() {
  const [view, setView] = useState("overview");
  const [q, setQ] = useState("");
  const [tableView, setTableView] = useState("table");
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      minHeight: "100vh",
      display: "flex",
      background: "#FFFFFF",
      fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Inter', sans-serif",
      color: "#0F172A"
    }
  }, /*#__PURE__*/React.createElement(Lattice, null), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      display: "flex",
      width: "100%",
      zIndex: 1
    }
  }, /*#__PURE__*/React.createElement(Sidebar, {
    active: view,
    onSelect: setView
  }), /*#__PURE__*/React.createElement("main", {
    style: {
      flex: 1,
      minWidth: 0,
      display: "flex",
      flexDirection: "column"
    }
  }, /*#__PURE__*/React.createElement(TopBar, {
    view: tableView,
    onView: setTableView,
    query: q,
    onQuery: setQ
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 24,
      display: "flex",
      flexDirection: "column",
      gap: 24
    }
  }, view === "overview" && /*#__PURE__*/React.createElement(OverviewView, {
    filter: q
  }), view === "pipeline" && /*#__PURE__*/React.createElement(PipelineView, null), view === "assets" && /*#__PURE__*/React.createElement(AssetsView, {
    filter: q
  }), view === "market" && /*#__PURE__*/React.createElement(MarketView, null), view === "reports" && /*#__PURE__*/React.createElement(PlaceholderView, {
    title: "Reports",
    note: "Scheduled exports, board packs, and ad-hoc reports live here."
  }), view === "team" && /*#__PURE__*/React.createElement(PlaceholderView, {
    title: "Team",
    note: "Member roles, deal assignments, and notification routing."
  }), view === "settings" && /*#__PURE__*/React.createElement(PlaceholderView, {
    title: "Settings",
    note: "Workspace, billing, integrations, and feature flags."
  }), view === "help" && /*#__PURE__*/React.createElement(PlaceholderView, {
    title: "Help",
    note: "Product docs, keyboard shortcuts, and contact options."
  })))));
}
function OverviewView({
  filter
}) {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Shell, null, /*#__PURE__*/React.createElement(Card, {
    padding: 24,
    style: {
      borderRadius: 23,
      border: 0,
      background: "linear-gradient(135deg, #FFFFFF 0%, #F0FDFA 100%)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "flex-start",
      justifyContent: "space-between",
      gap: 24
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      fontWeight: 500,
      color: "#0F766E",
      letterSpacing: "0.04em",
      textTransform: "uppercase"
    }
  }, "Q2 \xB7 April 28"), /*#__PURE__*/React.createElement("h1", {
    style: {
      fontSize: 36,
      lineHeight: "40px",
      letterSpacing: "-0.025em",
      fontWeight: 600,
      margin: "6px 0 8px"
    }
  }, "Portfolio overview"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 14,
      lineHeight: "20px",
      color: "#475569",
      maxWidth: 520,
      margin: 0
    }
  }, "Six active assets across four markets. Cap rate is up 0.4 pp month over month; 4 items need attention this week.")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "inline-flex",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    icon: "calendar"
  }, "Last 30 days"), /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    icon: "download"
  }, "Export"))))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(4, 1fr)",
      gap: 16
    }
  }, /*#__PURE__*/React.createElement(KpiTile, {
    label: "Net operating income",
    value: "$2.41M",
    delta: "6.2%",
    trend: "up",
    color: "teal",
    spark: [0.2, 0.28, 0.24, 0.36, 0.42, 0.5, 0.55, 0.6, 0.66, 0.72, 0.78, 0.84]
  }), /*#__PURE__*/React.createElement(KpiTile, {
    label: "Occupancy",
    value: "94.2%",
    delta: "0.8 pp",
    trend: "up",
    color: "blue",
    spark: [0.5, 0.52, 0.55, 0.54, 0.58, 0.6, 0.62, 0.65, 0.66, 0.7, 0.72, 0.74]
  }), /*#__PURE__*/React.createElement(KpiTile, {
    label: "Cap rate",
    value: "5.4%",
    delta: "0.1 pp",
    trend: "down",
    color: "gray",
    spark: [0.7, 0.72, 0.68, 0.66, 0.6, 0.58, 0.55, 0.5, 0.48, 0.46, 0.42, 0.4]
  }), /*#__PURE__*/React.createElement(KpiTile, {
    label: "Pipeline value",
    value: "$148M",
    delta: "11.4%",
    trend: "up",
    color: "lime",
    spark: [0.3, 0.32, 0.36, 0.4, 0.44, 0.5, 0.55, 0.6, 0.66, 0.72, 0.78, 0.84]
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "1.6fr 1fr",
      gap: 16,
      alignItems: "start"
    }
  }, /*#__PURE__*/React.createElement(AssetTable, {
    filter: filter
  }), /*#__PURE__*/React.createElement(MarketPulse, null)));
}
function PipelineView() {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "flex-end",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      fontWeight: 500,
      color: "#94A3B8",
      letterSpacing: "0.04em",
      textTransform: "uppercase"
    }
  }, "Deal flow"), /*#__PURE__*/React.createElement("h2", {
    style: {
      fontSize: 28,
      lineHeight: "32px",
      letterSpacing: "-0.02em",
      fontWeight: 600,
      margin: "4px 0 0"
    }
  }, "Pipeline")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "inline-flex",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    icon: "filter"
  }, "Filter"), /*#__PURE__*/React.createElement(Button, {
    variant: "accent",
    icon: "add-circle"
  }, "New deal"))), /*#__PURE__*/React.createElement(DealPipeline, null));
}
function AssetsView({
  filter
}) {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "flex-end",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      fontWeight: 500,
      color: "#94A3B8",
      letterSpacing: "0.04em",
      textTransform: "uppercase"
    }
  }, "Active"), /*#__PURE__*/React.createElement("h2", {
    style: {
      fontSize: 28,
      lineHeight: "32px",
      letterSpacing: "-0.02em",
      fontWeight: 600,
      margin: "4px 0 0"
    }
  }, "Assets")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "inline-flex",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Chip, {
    tone: "tint",
    dot: true
  }, "All sectors"), /*#__PURE__*/React.createElement(Chip, {
    tone: "neutral"
  }, "Stabilized"), /*#__PURE__*/React.createElement(Chip, {
    tone: "neutral"
  }, "At risk"))), /*#__PURE__*/React.createElement(AssetTable, {
    filter: filter
  }));
}
function MarketView() {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      fontWeight: 500,
      color: "#94A3B8",
      letterSpacing: "0.04em",
      textTransform: "uppercase"
    }
  }, "Intelligence"), /*#__PURE__*/React.createElement("h2", {
    style: {
      fontSize: 28,
      lineHeight: "32px",
      letterSpacing: "-0.02em",
      fontWeight: 600,
      margin: "4px 0 0"
    }
  }, "Market pulse")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "1fr 1fr",
      gap: 16
    }
  }, /*#__PURE__*/React.createElement(MarketPulse, null), /*#__PURE__*/React.createElement(MarketPulse, null)));
}
function PlaceholderView({
  title,
  note
}) {
  return /*#__PURE__*/React.createElement(Card, {
    padding: 40,
    style: {
      textAlign: "center"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "inline-flex",
      width: 48,
      height: 48,
      borderRadius: 9999,
      background: "#F0FDFA",
      color: "#0F766E",
      alignItems: "center",
      justifyContent: "center",
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement(NeIcon, {
    name: "cube",
    size: 22
  })), /*#__PURE__*/React.createElement("h2", {
    style: {
      fontSize: 24,
      lineHeight: "28px",
      letterSpacing: "-0.02em",
      fontWeight: 600,
      margin: "0 0 6px"
    }
  }, title), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 14,
      color: "#64748B",
      maxWidth: 380,
      margin: "0 auto"
    }
  }, note), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 16,
      display: "inline-flex",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "ghost"
  }, "Take a tour"), /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    icon: "arrow-right"
  }, "Open module")));
}
ReactDOM.createRoot(document.getElementById("root")).render(/*#__PURE__*/React.createElement(App, null));
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/dashboard/App.jsx", error: String((e && e.message) || e) }); }

// ui_kits/dashboard/AssetTable.jsx
try { (() => {
// AssetTable.jsx

const ASSETS = [{
  name: "Riverside Heights",
  meta: "Multifamily · Austin, TX",
  status: "Stabilized",
  tone: "success",
  noi: "$842K",
  occ: "96.1%",
  delta: "▲ 4.2%",
  deltaUp: true
}, {
  name: "Cedar Logistics Park",
  meta: "Industrial · Reno, NV",
  status: "At risk",
  tone: "warn",
  noi: "$614K",
  occ: "88.4%",
  delta: "▼ 0.6%",
  deltaUp: false
}, {
  name: "Atrium West 32",
  meta: "Office · Denver, CO",
  status: "Vacancy",
  tone: "danger",
  noi: "$402K",
  occ: "71.0%",
  delta: "▼ 2.8%",
  deltaUp: false
}, {
  name: "Belford Common",
  meta: "Multifamily · Charlotte",
  status: "Stabilized",
  tone: "success",
  noi: "$731K",
  occ: "94.8%",
  delta: "▲ 1.1%",
  deltaUp: true
}, {
  name: "Northpoint Plaza",
  meta: "Retail · Portland, OR",
  status: "Under review",
  tone: "info",
  noi: "$298K",
  occ: "82.5%",
  delta: "▲ 0.3%",
  deltaUp: true
}, {
  name: "Cypress Bay",
  meta: "Multifamily · Miami, FL",
  status: "Stabilized",
  tone: "success",
  noi: "$1.02M",
  occ: "97.4%",
  delta: "▲ 3.0%",
  deltaUp: true
}];
function AssetTable({
  filter = ""
}) {
  const rows = ASSETS.filter(r => !filter || r.name.toLowerCase().includes(filter.toLowerCase()) || r.meta.toLowerCase().includes(filter.toLowerCase()) || r.status.toLowerCase().includes(filter.toLowerCase()));
  const head = ["Asset", "Status", "NOI", "Occupancy", "Δ MoM", ""];
  return /*#__PURE__*/React.createElement(Card, {
    padding: 0
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "16px 24px",
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 16,
      fontWeight: 600,
      color: "#0F172A"
    }
  }, "Active assets"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "#94A3B8"
    }
  }, rows.length, " of ", ASSETS.length)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "inline-flex",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    icon: "filter"
  }, "Filter"), /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    icon: "download"
  }, "Export"))), /*#__PURE__*/React.createElement("table", {
    style: {
      width: "100%",
      borderCollapse: "collapse",
      fontSize: 13
    }
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, head.map((h, i) => /*#__PURE__*/React.createElement("th", {
    key: i,
    style: {
      textAlign: i >= 2 && i <= 4 ? "right" : "left",
      fontSize: 11,
      fontWeight: 500,
      color: "#94A3B8",
      textTransform: "uppercase",
      letterSpacing: "0.04em",
      padding: "10px 24px",
      borderTop: "1px solid #F1F5F9",
      borderBottom: "1px solid #F1F5F9",
      background: "#F8FAFC"
    }
  }, h)))), /*#__PURE__*/React.createElement("tbody", null, rows.map((r, i) => /*#__PURE__*/React.createElement("tr", {
    key: i,
    style: {
      transition: "background 150ms ease"
    },
    onMouseEnter: e => e.currentTarget.style.background = "#F8FAFC",
    onMouseLeave: e => e.currentTarget.style.background = "transparent"
  }, /*#__PURE__*/React.createElement("td", {
    style: {
      padding: "14px 24px",
      borderBottom: "1px solid #F1F5F9"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 600,
      color: "#0F172A"
    }
  }, r.name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "#94A3B8"
    }
  }, r.meta)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: "14px 24px",
      borderBottom: "1px solid #F1F5F9"
    }
  }, /*#__PURE__*/React.createElement(Chip, {
    tone: r.tone,
    dot: true
  }, r.status)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: "14px 24px",
      borderBottom: "1px solid #F1F5F9",
      textAlign: "right",
      fontVariantNumeric: "tabular-nums"
    }
  }, r.noi), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: "14px 24px",
      borderBottom: "1px solid #F1F5F9",
      textAlign: "right",
      fontVariantNumeric: "tabular-nums"
    }
  }, r.occ), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: "14px 24px",
      borderBottom: "1px solid #F1F5F9",
      textAlign: "right",
      fontVariantNumeric: "tabular-nums",
      color: r.deltaUp ? "#047857" : "#B91C1C",
      fontWeight: 500
    }
  }, r.delta), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: "14px 24px",
      borderBottom: "1px solid #F1F5F9",
      textAlign: "right"
    }
  }, /*#__PURE__*/React.createElement("button", {
    style: {
      background: "transparent",
      border: 0,
      color: "#94A3B8",
      cursor: "pointer",
      display: "inline-flex",
      padding: 6
    }
  }, /*#__PURE__*/React.createElement(NeIcon, {
    name: "menu-dots",
    size: 16
  }))))))));
}
Object.assign(window, {
  AssetTable
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/dashboard/AssetTable.jsx", error: String((e && e.message) || e) }); }

// ui_kits/dashboard/DealPipeline.jsx
try { (() => {
// DealPipeline.jsx — kanban with stage columns

const STAGES = [{
  id: "sourcing",
  title: "Sourcing",
  tone: "neutral",
  count: 12,
  cards: [{
    name: "Beacon Hill Towers",
    city: "Seattle, WA",
    value: "$14.2M",
    tag: "Multifamily"
  }, {
    name: "Greenmount Retail",
    city: "Baltimore, MD",
    value: "$6.8M",
    tag: "Retail"
  }]
}, {
  id: "loi",
  title: "LOI",
  tone: "info",
  count: 7,
  cards: [{
    name: "Stonebridge Park",
    city: "Nashville, TN",
    value: "$22.0M",
    tag: "Industrial"
  }, {
    name: "Linden Quarter",
    city: "Boston, MA",
    value: "$9.4M",
    tag: "Office"
  }, {
    name: "Vista del Mar",
    city: "San Diego, CA",
    value: "$31.5M",
    tag: "Multifamily"
  }]
}, {
  id: "diligence",
  title: "Diligence",
  tone: "warn",
  count: 4,
  cards: [{
    name: "Hawthorne Logistics",
    city: "Memphis, TN",
    value: "$18.7M",
    tag: "Industrial"
  }, {
    name: "Maple & 4th",
    city: "Austin, TX",
    value: "$11.2M",
    tag: "Mixed-use"
  }]
}, {
  id: "closing",
  title: "Closing",
  tone: "success",
  count: 2,
  cards: [{
    name: "Cypress Bay",
    city: "Miami, FL",
    value: "$42.0M",
    tag: "Multifamily"
  }]
}];
function DealPipeline() {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(4, 1fr)",
      gap: 16
    }
  }, STAGES.map(s => /*#__PURE__*/React.createElement("div", {
    key: s.id,
    style: {
      background: "#F8FAFC",
      border: "1px solid #F1F5F9",
      borderRadius: 24,
      padding: 12,
      display: "flex",
      flexDirection: "column",
      gap: 10,
      minHeight: 360
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      padding: "4px 8px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Chip, {
    tone: s.tone,
    dot: true
  }, s.title), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "#94A3B8"
    }
  }, s.count)), /*#__PURE__*/React.createElement("button", {
    style: {
      background: "transparent",
      border: 0,
      color: "#94A3B8",
      cursor: "pointer",
      display: "inline-flex"
    }
  }, /*#__PURE__*/React.createElement(NeIcon, {
    name: "add-circle",
    size: 16
  }))), s.cards.map((c, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      background: "#FFFFFF",
      border: "1px solid #F1F5F9",
      borderRadius: 16,
      padding: 12,
      boxShadow: "0 1px 2px rgba(0,0,0,.04)",
      display: "flex",
      flexDirection: "column",
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600,
      color: "#0F172A"
    }
  }, c.name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "#94A3B8"
    }
  }, c.city), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      marginTop: 4
    }
  }, /*#__PURE__*/React.createElement(Chip, {
    tone: "neutral"
  }, c.tag), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      fontWeight: 600,
      color: "#0F172A",
      fontVariantNumeric: "tabular-nums"
    }
  }, c.value)))))));
}
Object.assign(window, {
  DealPipeline
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/dashboard/DealPipeline.jsx", error: String((e && e.message) || e) }); }

// ui_kits/dashboard/Icon.jsx
try { (() => {
// Icon.jsx — <NeIcon name="..." size={16} /> using Solar Linear via Iconify CDN
// Falls back to Lucide if the requested name resolves to nothing useful.

function NeIcon({
  name,
  size = 20,
  color = "currentColor",
  style = {}
}) {
  // Iconify renders an inline SVG from a URL like:
  //   https://api.iconify.design/solar/home-linear.svg?color=...
  // We use an <img> for simplicity (color inherited via CSS mask).
  const url = `https://api.iconify.design/solar/${name}-linear.svg`;
  return /*#__PURE__*/React.createElement("span", {
    role: "img",
    "aria-label": name,
    style: {
      display: "inline-block",
      width: size,
      height: size,
      backgroundColor: color,
      WebkitMaskImage: `url(${url})`,
      maskImage: `url(${url})`,
      WebkitMaskRepeat: "no-repeat",
      maskRepeat: "no-repeat",
      WebkitMaskSize: "contain",
      maskSize: "contain",
      WebkitMaskPosition: "center",
      maskPosition: "center",
      ...style
    }
  });
}
Object.assign(window, {
  NeIcon
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/dashboard/Icon.jsx", error: String((e && e.message) || e) }); }

// ui_kits/dashboard/KpiTile.jsx
try { (() => {
// KpiTile.jsx — headline number + delta + sparkline

function KpiTile({
  label,
  value,
  delta,
  trend = "up",
  color = "teal",
  spark = []
}) {
  const palette = {
    teal: {
      bg: "#F0FDFA",
      fg: "#0F766E",
      stroke: "#14B8A6"
    },
    blue: {
      bg: "#DBEAFE",
      fg: "#1D4ED8",
      stroke: "#3B82F6"
    },
    lime: {
      bg: "#F4FCE3",
      fg: "#4D7C0F",
      stroke: "#84CC16"
    },
    gray: {
      bg: "#F8FAFC",
      fg: "#475569",
      stroke: "#94A3B8"
    }
  };
  const p = palette[color] || palette.teal;
  const w = 200,
    h = 36;
  const pts = spark.length ? spark.map((v, i) => `${i / (spark.length - 1) * w},${h - v * (h - 4) - 2}`).join(" ") : "";
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: "#FFFFFF",
      border: "1px solid #F1F5F9",
      borderRadius: 24,
      padding: 20,
      boxShadow: "0 1px 2px rgba(0,0,0,.05)",
      display: "flex",
      flexDirection: "column",
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      lineHeight: "16px",
      color: "#64748B",
      fontWeight: 500
    }
  }, label), /*#__PURE__*/React.createElement(Chip, {
    tone: trend === "up" ? "success" : "danger"
  }, trend === "up" ? "▲" : "▼", " ", delta)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 32,
      lineHeight: "36px",
      fontWeight: 600,
      letterSpacing: "-0.02em",
      color: "#0F172A",
      fontVariantNumeric: "tabular-nums"
    }
  }, value), /*#__PURE__*/React.createElement("svg", {
    viewBox: `0 0 ${w} ${h}`,
    preserveAspectRatio: "none",
    style: {
      width: "100%",
      height: 36,
      marginTop: 2
    }
  }, /*#__PURE__*/React.createElement("polyline", {
    fill: "none",
    stroke: p.stroke,
    strokeWidth: "1.6",
    strokeLinejoin: "round",
    points: pts
  })));
}
Object.assign(window, {
  KpiTile
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/dashboard/KpiTile.jsx", error: String((e && e.message) || e) }); }

// ui_kits/dashboard/Lattice.jsx
try { (() => {
// Lattice.jsx — DOM fallback for the WebGL line-lattice background.
// Used as the chrome backdrop on Overview. If the real product ships
// a ThreeJS / Skia implementation, replace this with the canvas mount.

function Lattice({
  style = {}
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      inset: 0,
      overflow: "hidden",
      pointerEvents: "none",
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      inset: "-20%",
      backgroundImage: "linear-gradient(to right, rgba(15,23,42,0.05) 1px, transparent 1px)," + "linear-gradient(to bottom, rgba(15,23,42,0.05) 1px, transparent 1px)",
      backgroundSize: "32px 32px",
      transformOrigin: "50% 70%",
      transform: "perspective(900px) rotateX(58deg) scale(1.15)",
      animation: "neBreathe 7s cubic-bezier(.4,0,.2,1) infinite"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      inset: "-20%",
      backgroundImage: "linear-gradient(to right, rgba(20,184,166,0.15) 1px, transparent 1px)," + "linear-gradient(to bottom, rgba(20,184,166,0.15) 1px, transparent 1px)",
      backgroundSize: "128px 128px",
      transformOrigin: "50% 70%",
      transform: "perspective(900px) rotateX(58deg) scale(1.15)",
      opacity: 0.75,
      animation: "neBreathe 7s cubic-bezier(.4,0,.2,1) infinite"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      inset: 0,
      background: "radial-gradient(ellipse at 50% 110%, rgba(20,184,166,0.10), transparent 60%)"
    }
  }), /*#__PURE__*/React.createElement("style", null, `
        @keyframes neBreathe {
          0%, 100% { opacity: .55; }
          50%      { opacity: .85; }
        }
      `));
}
Object.assign(window, {
  Lattice
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/dashboard/Lattice.jsx", error: String((e && e.message) || e) }); }

// ui_kits/dashboard/MarketPulse.jsx
try { (() => {
// MarketPulse.jsx — side panel with mini chart and insight feed

function AreaChart({
  points,
  color = "#14B8A6",
  fill = "rgba(20,184,166,0.12)"
}) {
  const w = 260,
    h = 90;
  const xs = i => i / (points.length - 1) * w;
  const ys = v => h - v * (h - 8) - 4;
  const line = points.map((v, i) => `${xs(i)},${ys(v)}`).join(" ");
  const area = `M0,${h} L${points.map((v, i) => `${xs(i)},${ys(v)}`).join(" L")} L${w},${h} Z`;
  return /*#__PURE__*/React.createElement("svg", {
    viewBox: `0 0 ${w} ${h}`,
    preserveAspectRatio: "none",
    style: {
      width: "100%",
      height: 90
    }
  }, /*#__PURE__*/React.createElement("path", {
    d: area,
    fill: fill
  }), /*#__PURE__*/React.createElement("polyline", {
    points: line,
    stroke: color,
    strokeWidth: "1.6",
    fill: "none",
    strokeLinejoin: "round"
  }));
}
function MarketPulse() {
  const insights = [{
    tone: "success",
    icon: "trend-up",
    title: "Austin multifamily rents +1.2%",
    meta: "Week of Apr 22"
  }, {
    tone: "warn",
    icon: "shield-warning",
    title: "Office vacancy widens in Denver",
    meta: "Cushman & Wakefield"
  }, {
    tone: "info",
    icon: "info-circle",
    title: "Industrial cap rates compress 8 bps",
    meta: "JLL Q1 brief"
  }, {
    tone: "neutral",
    icon: "global",
    title: "10Y Treasury settles at 4.28%",
    meta: "Today · 14:02"
  }];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 16
    }
  }, /*#__PURE__*/React.createElement(Card, {
    padding: 20
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      marginBottom: 8
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "#94A3B8",
      fontWeight: 500
    }
  }, "Portfolio NOI \xB7 trailing 12m"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 22,
      fontWeight: 600,
      color: "#0F172A",
      letterSpacing: "-0.02em",
      fontVariantNumeric: "tabular-nums"
    }
  }, "$24.8M")), /*#__PURE__*/React.createElement(Chip, {
    tone: "success",
    dot: true
  }, "\u25B2 6.2%")), /*#__PURE__*/React.createElement(AreaChart, {
    points: [0.2, 0.28, 0.24, 0.32, 0.36, 0.34, 0.42, 0.48, 0.46, 0.55, 0.62, 0.68, 0.74]
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "space-between",
      fontSize: 10,
      color: "#94A3B8",
      marginTop: 6
    }
  }, /*#__PURE__*/React.createElement("span", null, "May '25"), /*#__PURE__*/React.createElement("span", null, "Aug"), /*#__PURE__*/React.createElement("span", null, "Nov"), /*#__PURE__*/React.createElement("span", null, "Feb"), /*#__PURE__*/React.createElement("span", null, "Apr '26"))), /*#__PURE__*/React.createElement(Card, {
    padding: 20
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 16,
      fontWeight: 600,
      color: "#0F172A"
    }
  }, "Market pulse"), /*#__PURE__*/React.createElement("button", {
    style: {
      background: "transparent",
      border: 0,
      color: "#64748B",
      fontSize: 12,
      fontWeight: 500,
      cursor: "pointer",
      padding: 4
    }
  }, "View all \u2192")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 12
    }
  }, insights.map((it, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: "flex",
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 32,
      height: 32,
      flexShrink: 0,
      background: it.tone === "success" ? "#ECFDF5" : it.tone === "warn" ? "#FFFBEB" : it.tone === "info" ? "#DBEAFE" : "#F8FAFC",
      color: it.tone === "success" ? "#047857" : it.tone === "warn" ? "#B45309" : it.tone === "info" ? "#1D4ED8" : "#64748B",
      borderRadius: 9999,
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center"
    }
  }, /*#__PURE__*/React.createElement(NeIcon, {
    name: it.icon,
    size: 16
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      lineHeight: "18px",
      fontWeight: 500,
      color: "#0F172A"
    }
  }, it.title), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "#94A3B8",
      marginTop: 2
    }
  }, it.meta)))))));
}
Object.assign(window, {
  MarketPulse
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/dashboard/MarketPulse.jsx", error: String((e && e.message) || e) }); }

// ui_kits/dashboard/Primitives.jsx
try { (() => {
// Primitives.jsx — Button, Chip, Card, Field, SectionHeader
// Depends on: colors_and_type.css for tokens.

const {
  useState
} = React;
function Button({
  children,
  variant = "primary",
  icon,
  onClick,
  disabled
}) {
  const base = {
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    padding: "8px 16px",
    borderRadius: 9999,
    fontSize: 14,
    lineHeight: "20px",
    fontWeight: 500,
    border: 0,
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.5 : 1,
    transition: "background 150ms cubic-bezier(.4,0,.2,1), color 150ms cubic-bezier(.4,0,.2,1)",
    fontFamily: "inherit"
  };
  const variants = {
    primary: {
      background: "#FDF2F8",
      color: "#DB2777"
    },
    accent: {
      background: "#14B8A6",
      color: "#FFFFFF"
    },
    ghost: {
      background: "#F8FAFC",
      color: "#0F172A"
    },
    link: {
      background: "transparent",
      color: "#64748B",
      padding: 8
    }
  };
  return /*#__PURE__*/React.createElement("button", {
    style: {
      ...base,
      ...variants[variant]
    },
    onClick: onClick,
    disabled: disabled
  }, icon ? /*#__PURE__*/React.createElement(NeIcon, {
    name: icon,
    size: 16
  }) : null, children);
}
function Chip({
  children,
  tone = "neutral",
  dot = false
}) {
  const tones = {
    neutral: {
      background: "#F8FAFC",
      color: "#64748B",
      dot: "#94A3B8"
    },
    success: {
      background: "#ECFDF5",
      color: "#047857",
      dot: "#10B981"
    },
    warn: {
      background: "#FFFBEB",
      color: "#B45309",
      dot: "#F59E0B"
    },
    danger: {
      background: "#FEF2F2",
      color: "#B91C1C",
      dot: "#EF4444"
    },
    info: {
      background: "#DBEAFE",
      color: "#1D4ED8",
      dot: "#3B82F6"
    },
    tint: {
      background: "#F0FDFA",
      color: "#0F766E",
      dot: "#14B8A6"
    }
  };
  const t = tones[tone] || tones.neutral;
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      padding: "2px 10px",
      borderRadius: 9999,
      background: t.background,
      color: t.color,
      fontSize: 12,
      lineHeight: "16px",
      fontWeight: 500
    }
  }, dot ? /*#__PURE__*/React.createElement("span", {
    style: {
      width: 6,
      height: 6,
      borderRadius: 9999,
      background: t.dot
    }
  }) : null, children);
}
function Card({
  variant = "solid",
  padding = 20,
  children,
  style = {}
}) {
  const surfaces = {
    solid: {
      background: "#FFFFFF",
      border: "1px solid #F1F5F9",
      borderRadius: 24,
      boxShadow: "0 1px 2px rgba(0,0,0,.05)"
    },
    glass: {
      background: "rgba(255,255,255,0.8)",
      borderRadius: 23,
      backdropFilter: "blur(12px)",
      WebkitBackdropFilter: "blur(12px)"
    },
    compact: {
      background: "#FFFFFF",
      border: "1px solid #F1F5F9",
      borderRadius: 16,
      boxShadow: "0 1px 2px rgba(0,0,0,.05)"
    }
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      ...surfaces[variant],
      padding,
      ...style
    }
  }, children);
}
function Shell({
  children,
  padding = 1,
  borderRadius = 24,
  style = {}
}) {
  // Gradient-shell wrapper — reserved for the hero panel.
  return /*#__PURE__*/React.createElement("div", {
    style: {
      padding,
      borderRadius,
      background: "linear-gradient(to right bottom, rgba(255,255,255,0.7), rgba(255,255,255,0.15), rgba(0,0,0,0))",
      ...style
    }
  }, children);
}
function Field({
  label,
  icon,
  value,
  placeholder,
  onChange
}) {
  const [focused, setFocused] = useState(false);
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 6
    }
  }, label ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      lineHeight: "16px",
      fontWeight: 500,
      color: "#0F172A"
    }
  }, label) : null, /*#__PURE__*/React.createElement("span", {
    style: {
      position: "relative",
      display: "flex",
      alignItems: "center"
    }
  }, icon ? /*#__PURE__*/React.createElement("span", {
    style: {
      position: "absolute",
      left: 12,
      top: "50%",
      transform: "translateY(-50%)",
      color: "#94A3B8",
      display: "inline-flex"
    }
  }, /*#__PURE__*/React.createElement(NeIcon, {
    name: icon,
    size: 16
  })) : null, /*#__PURE__*/React.createElement("input", {
    value: value || "",
    placeholder: placeholder,
    onChange: e => onChange && onChange(e.target.value),
    onFocus: () => setFocused(true),
    onBlur: () => setFocused(false),
    style: {
      width: "100%",
      fontFamily: "inherit",
      fontSize: 14,
      lineHeight: "20px",
      padding: icon ? "10px 12px 10px 36px" : "10px 12px",
      border: `1px solid ${focused ? "#14B8A6" : "#E2E8F0"}`,
      borderRadius: 16,
      background: "#FFFFFF",
      color: "#0F172A",
      outline: "none",
      boxShadow: focused ? "0 0 0 3px rgba(20,184,166,.15)" : "none",
      transition: "border-color 150ms cubic-bezier(.4,0,.2,1), box-shadow 150ms cubic-bezier(.4,0,.2,1)"
    }
  })));
}
function SectionHeader({
  eyebrow,
  title,
  action
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement("div", null, eyebrow ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      fontWeight: 500,
      color: "#94A3B8",
      letterSpacing: "0.04em",
      textTransform: "uppercase"
    }
  }, eyebrow) : null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 20,
      lineHeight: "28px",
      fontWeight: 600,
      color: "#0F172A"
    }
  }, title)), action);
}
Object.assign(window, {
  Button,
  Chip,
  Card,
  Shell,
  Field,
  SectionHeader
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/dashboard/Primitives.jsx", error: String((e && e.message) || e) }); }

// ui_kits/dashboard/Sidebar.jsx
try { (() => {
// Sidebar.jsx — vertical nav with primary product sections.

function Sidebar({
  active,
  onSelect
}) {
  const items = [{
    id: "overview",
    label: "Overview",
    icon: "home"
  }, {
    id: "pipeline",
    label: "Pipeline",
    icon: "branching-paths"
  }, {
    id: "assets",
    label: "Assets",
    icon: "buildings-3"
  }, {
    id: "market",
    label: "Market",
    icon: "global"
  }, {
    id: "reports",
    label: "Reports",
    icon: "chart-2"
  }, {
    id: "team",
    label: "Team",
    icon: "users-group-two-rounded"
  }];
  const footer = [{
    id: "settings",
    label: "Settings",
    icon: "settings"
  }, {
    id: "help",
    label: "Help",
    icon: "question-circle"
  }];
  const row = it => {
    const selected = active === it.id;
    return /*#__PURE__*/React.createElement("button", {
      key: it.id,
      onClick: () => onSelect && onSelect(it.id),
      style: {
        display: "flex",
        alignItems: "center",
        gap: 12,
        width: "100%",
        padding: "9px 12px",
        borderRadius: 16,
        border: 0,
        cursor: "pointer",
        background: selected ? "#F0FDFA" : "transparent",
        color: selected ? "#0F766E" : "#64748B",
        fontFamily: "inherit",
        fontSize: 14,
        lineHeight: "20px",
        fontWeight: 500,
        textAlign: "left",
        transition: "background 150ms cubic-bezier(.4,0,.2,1), color 150ms cubic-bezier(.4,0,.2,1)"
      },
      onMouseEnter: e => {
        if (!selected) {
          e.currentTarget.style.color = "#0F172A";
        }
      },
      onMouseLeave: e => {
        if (!selected) {
          e.currentTarget.style.color = "#64748B";
        }
      }
    }, /*#__PURE__*/React.createElement(NeIcon, {
      name: it.icon,
      size: 18
    }), /*#__PURE__*/React.createElement("span", null, it.label));
  };
  return /*#__PURE__*/React.createElement("aside", {
    style: {
      width: 240,
      flexShrink: 0,
      display: "flex",
      flexDirection: "column",
      padding: 16,
      gap: 4,
      borderRight: "1px solid #F1F5F9",
      background: "rgba(255,255,255,0.7)",
      backdropFilter: "blur(12px)",
      WebkitBackdropFilter: "blur(12px)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 10,
      padding: "8px 12px 16px"
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/novaestate-mark.svg",
    width: "28",
    height: "28",
    alt: ""
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 16,
      fontWeight: 600,
      letterSpacing: "-0.01em",
      color: "#0F172A"
    }
  }, "Nova", /*#__PURE__*/React.createElement("span", {
    style: {
      color: "#14B8A6"
    }
  }, "Estate"))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 2
    }
  }, items.map(row)), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 2
    }
  }, footer.map(row)), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 12,
      padding: 12,
      background: "linear-gradient(135deg, #F0FDFA, #ECFCCB)",
      borderRadius: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      fontWeight: 600,
      color: "#0F172A"
    }
  }, "Q2 portfolio review"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "#64748B",
      marginTop: 4,
      lineHeight: "14px"
    }
  }, "3 assets need attention before Friday."), /*#__PURE__*/React.createElement("button", {
    style: {
      marginTop: 10,
      fontSize: 12,
      fontWeight: 500,
      background: "#14B8A6",
      color: "#FFFFFF",
      border: 0,
      borderRadius: 9999,
      padding: "5px 12px",
      cursor: "pointer"
    }
  }, "Open review \u2192")));
}
Object.assign(window, {
  Sidebar
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/dashboard/Sidebar.jsx", error: String((e && e.message) || e) }); }

// ui_kits/dashboard/TopBar.jsx
try { (() => {
// TopBar.jsx — search + view switcher + notifications + user

function TopBar({
  view,
  onView,
  query,
  onQuery
}) {
  const views = [{
    id: "table",
    label: "Table"
  }, {
    id: "grid",
    label: "Grid"
  }, {
    id: "map",
    label: "Map"
  }];
  return /*#__PURE__*/React.createElement("header", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 16,
      padding: "16px 24px",
      borderBottom: "1px solid #F1F5F9",
      background: "rgba(255,255,255,0.8)",
      backdropFilter: "blur(12px)",
      WebkitBackdropFilter: "blur(12px)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      flex: 1,
      maxWidth: 480
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      position: "absolute",
      left: 12,
      top: "50%",
      transform: "translateY(-50%)",
      color: "#94A3B8"
    }
  }, /*#__PURE__*/React.createElement(NeIcon, {
    name: "magnifer",
    size: 16
  })), /*#__PURE__*/React.createElement("input", {
    value: query || "",
    onChange: e => onQuery && onQuery(e.target.value),
    placeholder: "Search assets, deals, contacts\u2026",
    style: {
      width: "100%",
      fontFamily: "inherit",
      fontSize: 14,
      lineHeight: "20px",
      padding: "9px 12px 9px 36px",
      border: "1px solid #E2E8F0",
      borderRadius: 9999,
      background: "#FFFFFF",
      color: "#0F172A",
      outline: "none"
    }
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "inline-flex",
      padding: 4,
      gap: 2,
      background: "#F8FAFC",
      borderRadius: 9999
    }
  }, views.map(v => {
    const sel = view === v.id;
    return /*#__PURE__*/React.createElement("button", {
      key: v.id,
      onClick: () => onView && onView(v.id),
      style: {
        fontFamily: "inherit",
        fontSize: 13,
        fontWeight: 500,
        padding: "6px 14px",
        borderRadius: 9999,
        border: 0,
        cursor: "pointer",
        background: sel ? "#FFFFFF" : "transparent",
        color: sel ? "#0F172A" : "#64748B",
        boxShadow: sel ? "0 1px 2px rgba(0,0,0,.05)" : "none",
        transition: "all 150ms cubic-bezier(.4,0,.2,1)"
      }
    }, v.label);
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement("button", {
    style: {
      position: "relative",
      width: 36,
      height: 36,
      borderRadius: 9999,
      background: "#F8FAFC",
      border: 0,
      cursor: "pointer",
      color: "#64748B",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center"
    }
  }, /*#__PURE__*/React.createElement(NeIcon, {
    name: "bell",
    size: 18
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      position: "absolute",
      top: 6,
      right: 8,
      width: 7,
      height: 7,
      borderRadius: 9999,
      background: "#14B8A6",
      boxShadow: "0 0 0 2px #FFFFFF"
    }
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 8,
      padding: "4px 14px 4px 4px",
      background: "#FFFFFF",
      border: "1px solid #F1F5F9",
      borderRadius: 9999,
      boxShadow: "0 1px 2px rgba(0,0,0,.05)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 28,
      height: 28,
      borderRadius: 9999,
      background: "linear-gradient(135deg, #14B8A6, #0EA5E9)",
      color: "#FFFFFF",
      fontSize: 12,
      fontWeight: 600,
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center"
    }
  }, "AT"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      lineHeight: 1.1
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 13,
      fontWeight: 600,
      color: "#0F172A"
    }
  }, "Anika Tan"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "#94A3B8"
    }
  }, "Operator \xB7 Q2"))));
}
Object.assign(window, {
  TopBar
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/dashboard/TopBar.jsx", error: String((e && e.message) || e) }); }

})();
