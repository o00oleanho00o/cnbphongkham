// Role dictionary of the Pema design tokens. build.cjs refuses to run when a token in tokens.json has no entry here
// (and when an entry here has no token), so a new token cannot ship undocumented.
// Colour: [group, role, where it is used]. Values come from tokens.json, never from this file.

const COLOR = {
  'brand-50': ['Brand', 'Brand wash', 'Selected sidebar item, avatar and AI-card fill, quick-action tiles, brand badge fill'],
  'brand-100': ['Brand', 'Brand line', 'Border of brand-50 surfaces, light button on a hero, selected chip count'],
  'brand-200': ['Brand', 'Brand soft stroke', 'Unlit rail segments on a hero (35% opacity)'],
  'brand-400': ['Brand', 'Sky', 'Graphic details only; never a background for small white text'],
  'brand-500': ['Brand', 'Primary', 'Main button, selected chip, active tab bar item, checkbox/radio on, progress bar, ids on the canvas'],
  'brand-600': ['Brand', 'Navy', 'Primary button hover/pressed, hero gradient start, toast background'],
  'brand-700': ['Brand', 'Text on brand-50', 'Brand badge text, avatar initials, selected sidebar label'],
  canvas: ['Surfaces and text', 'Page background', 'Behind the app shell and every frame'],
  'canvas-alt': ['Surfaces and text', 'Patient-facing background', 'Behind the card column on Patient Mobile pages and behind the canvas itself'],
  surface: ['Surfaces and text', 'Surface', 'Cards, panels, forms, sidebar, top bar, dialogs; text on a dark fill (primary button, hero)'],
  ink: ['Surfaces and text', 'Ink', 'Main content text'],
  'ink-soft': ['Surfaces and text', 'Muted ink', 'Metadata, labels, placeholders (placeholder at 75% opacity), icons'],
  heading: ['Surfaces and text', 'Heading', 'Page and card titles, KPI values'],
  link: ['Surfaces and text', 'Link', 'Links, quiet buttons, selected-tab text and underline (equals brand-500 in light mode)'],
  tile: ['Surfaces and text', 'Tile', 'Neutral badge fill, chip counter, progress track, segmented-control track, customer chat bubble, hover fill'],
  field: ['Surfaces and text', 'Field fill', 'Input background, soft card, code block, dashed upload box'],
  'table-head': ['Surfaces and text', 'Table head', 'Table header row and footer row, expanded trace-run header'],
  'row-hover': ['Surfaces and text', 'Row hover', 'Hover fill of a clickable table row'],
  plate: ['Surfaces and text', 'Paper plate', 'Sheet that stays white in dark mode (A5 print sheet, logo plate)'],
  line: ['Lines', 'Line', 'Card, panel and divider borders'],
  'line-strong': ['Lines', 'Strong line', 'Input, secondary-button, select and search borders; dashed borders'],
  overlay: ['Interaction', 'Overlay', 'Backdrop behind a dialog, sheet or drawer'],
  focus: ['Interaction', 'Focus ring', 'Keyboard focus outline'],
  success: ['Status', 'Success text', 'Text and icon of a success badge, notice, note and bar'],
  'success-soft': ['Status', 'Success fill', 'Background of a success badge, notice, box'],
  'success-line': ['Status', 'Success border', 'Border of success surfaces'],
  info: ['Status', 'Info text', 'Text and icon of an info badge, notice; eyebrow text'],
  'info-soft': ['Status', 'Info fill', 'Background of an info badge, notice; own chat bubble of the patient'],
  'info-line': ['Status', 'Info border', 'Border of info surfaces'],
  warning: ['Status', 'Warning text', 'Text and icon of a warning badge, notice; draft stamp on the A5 sheet'],
  'warning-soft': ['Status', 'Warning fill', 'Background of a warning badge, notice'],
  'warning-line': ['Status', 'Warning border', 'Border of warning surfaces'],
  danger: ['Status', 'Danger text', 'Text of a danger badge, notice, error line; border of an invalid field; fill of a solid danger button'],
  'danger-soft': ['Status', 'Danger fill', 'Background of a danger badge, notice'],
  'danger-line': ['Status', 'Danger border', 'Border of danger surfaces and of the outlined danger button'],
  accent: ['Accent', 'Coral', 'Decoration only'],
  'accent-strong': ['Accent', 'Coral strong', 'Sidebar count badge and avatar background (label `surface`: 5.4:1 light, 4.6:1 dark)'],
};

// Text scale: [role, weight, line height, where it is used]. The canvas CSS (Pema Web redesign canvas/template.html) is the reference for weight and leading.
const TEXT = {
  eyebrow: ['Eyebrow', '600, uppercase, +0.1em', '1.4', 'Small label above a title, sidebar section titles, hero kicker'],
  micro: ['Micro', '500-700', '1.3-1.6', 'Counters inside chips and tabs, table column heads (uppercase +0.06em), timestamps under a bubble'],
  label: ['Label', '500-600', '1.4', 'Field labels (600, ink-soft), badges (500), sub lines, hints, errors'],
  small: ['Small', '500-600', '1.5', 'Buttons (600), chips (500), notices, dense table text, secondary lines'],
  body: ['Body', '400-600', '1.5', 'Default text, table cells, tab labels, list titles (600)'],
  'body-lg': ['Body large', '400-700', '1.35', 'Field values, card titles (700, heading colour), empty-state title (600), h4 heading (600)'],
  section: ['Section', '600-700', '1.3', 'h3 heading, dialog title (600), stat value (700), prescription titles'],
  subtitle: ['Subtitle', '700', '1.25', 'h2 heading, appointment day number, progress label'],
  title: ['Title', '700', '1.2', 'h1 heading in a page body; page title at 390 (replaces page)'],
  metric: ['Metric', '700', '1.2', 'KPI value'],
  page: ['Page', '700', '1.2', 'Page title (`pageHead`) at 1440 and 1920'],
};

const RADIUS = {
  field: ['Field', 'Input, select, textarea, option list, booking card, A5 sheet'],
  control: ['Control', 'Buttons, segmented-control track, skip link'],
  tile: ['Tile', 'Notice, box, soft card, list box rows, code block, image placeholder, board, icon tile, segmented item'],
  card: ['Card', 'Card, panel, table wrapper, KPI tile, empty state, trace run'],
  modal: ['Modal', 'Dialog, bottom sheet (top corners), native-dialog drawing'],
  hero: ['Hero', 'Hero band'],
  pill: ['Pill', 'Badge, chip, avatar, progress bar, count bubble, radio'],
};

const SHADOW = {
  card: ['Card shadow', 'Card, panel, KPI tile, empty state, frame border, selected segment, A5 sheet'],
  pop: ['Pop shadow', 'Dialog, bottom sheet, drawer, dropdown list, toast, native dialog (the only shadow that floats)'],
};

const SPACE = {
  1: 'Tight stacks and icon-to-text gaps',
  2: 'Gap between buttons, chips, badges',
  3: 'Default gap of `stack` and `row`, dialog body gap',
  4: 'Card padding at 390, page gap at 1440, grid gap',
  5: 'Card padding at 1440, page gap at 1920',
  6: 'Content padding top and bottom, hero padding',
};

const LAYOUT = {
  'sidebar-w': 'Sidebar width above 1000px',
  'sidebar-w-narrow': 'Sidebar width at and below 1000px (old web)',
  'topbar-h': 'Top bar height',
  'topbar-h-wide': 'Top bar height from 1600px (frame 1920)',
  'content-pad-x': 'Page content padding left and right at 1440 and 1920 (16px at 390)',
  'content-pad-y': 'Page content padding top and bottom',
  'content-max': 'Widest the page content grows on a big screen',
  'aside-w': 'Second column of a split workspace',
  'touch-min': 'Smallest touch target; buttons and chips are 44px high on a phone, 36-40px on a desktop',
};

const Z = {
  sticky: 'Sticky table head, sticky toolbar',
  topbar: 'Top bar',
  drawer: 'Phone drawer and its scrim',
  modal: 'Dialog and bottom sheet',
  toast: 'Toast',
};

module.exports = { COLOR, TEXT, RADIUS, SHADOW, SPACE, LAYOUT, Z };
