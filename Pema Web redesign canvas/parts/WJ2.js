// WJ2 · Quản trị agent (Next.js), phần 2: WJ58-WJ115 (Zalo: hộp thoại cuối, Agents, Tools, MCP, Trace agent, Logs, Hồ sơ chính sách, Mô hình & cấu hình). Package W2 step W10.
const wj2NXW = 'Next.js › ';

// ---- Tài khoản Zalo (/admin/accounts): the page behind WJ58-WJ66 ----
const wj2Kill = 'Công tắc khẩn DỪNG MỌI tin nhắn chủ động của kênh này (nhắc lịch, chăm sóc, tin theo lịch) cho tới khi tắt. Tin trả lời khách vừa nhắn tới không bị công tắc này chặn.';
const wj2Toggle = (name, on) => iconBtn(on === false ? 'toggle_off' : 'toggle_on', { aria: 'Bật kênh ' + name });
// ChannelCard (kit: Card + Field, `channel-settings-panel.tsx`): one Zalo channel with its daily cap, spacing, send window and the emergency switch
const wj2ChannelCard = (name, o) => card({ comp: 'ChannelCard', title: name, aside: [...(o.badges || []), wj2Toggle(name)] },
  o.locked ? notice('CÔNG TẮC KHẨN ĐANG BẬT lúc 20/09 08:40 - mọi tin chủ động của kênh này đang bị chặn. Lý do: Tạm dừng tin chủ động để kiểm tra nội dung.', 'danger') : null,
  prog(o.pct, { label: 'Đã gửi chủ động hôm nay ' + o.sent }),
  input('Trần tin chủ động mỗi ngày (0-1000)', o.cap, { ph: 'Không giới hạn' }),
  grid(2, input('Cách nhau tối thiểu (giây, 0-3600)', o.min), input('Cách nhau tối đa (giây, 0-3600)', o.max), time('Khung giờ gửi: từ', o.from), time('Khung giờ gửi: đến', o.to)),
  o.warn ? notice('Kênh zalo_personal dùng nick Zalo thật qua giao thức không chính thức: gửi chủ động nhiều hoặc dồn dập CÓ THỂ khiến Zalo KHÓA tài khoản. Giữ trần mỗi ngày thấp, khoảng cách giữa các tin dài và khung giờ gửi hẹp.', 'warning') : null,
  primary('Lưu cấu hình', { dis: true }), hr(),
  strong('Công tắc khẩn'), sm(wj2Kill), o.locked ? secondary('Tắt công tắc khẩn') : danger('Bật công tắc khẩn'));
// AccountRow: one Zalo account with its agent ("brain"), policy profile and status
const wj2AccountRow = (init, name, badges, sub, actions) => card({ comp: 'AccountRow', title: init + ' · ' + name, sub, aside: [...badges, ...actions] });
const wj2ZaloPage = () => [
  pageHead('Tài khoản Zalo', 'Tài khoản Zalo của bot - mỗi account gắn một agent (não) và có policies riêng', [primary('Thêm account', { icon: 'add' })]),
  card({ title: 'Kênh gửi tin', sub: 'Cấu hình chung của từng kênh Zalo: bật/tắt, trần tin chủ động, khung giờ và công tắc khẩn' },
    grid(2,
      wj2ChannelCard('Tài khoản bot chính thức', { sent: '3/10', pct: 30, cap: '10', min: '20', max: '90', from: '08:00', to: '20:00' }),
      wj2ChannelCard('Tài khoản cá nhân', { badges: [badge('Bridge chờ quét QR', 'warning'), badge('Chỉ gửi cho bạn bè', 'info')], sent: '0/5', pct: 0, cap: '5', min: '60', max: '240', from: '09:00', to: '18:00', warn: true }))),
  wj2AccountRow('P', 'Pema CSKH (Zalo Bot)', [badge('Bot chính thức', 'info'), badge('Kênh bệnh nhân', 'success'), badge('Đang chạy', 'success')], 'pema-bot · não: 🩺 CSKH Da liễu',
    [wj2Toggle('account Pema CSKH (Zalo Bot)'), secondary('Sửa'), danger('Xóa')]),
  wj2AccountRow('Z', 'Zalo lễ tân (cá nhân)', [badge('Nick cá nhân', 'info'), badge('Trợ lý nhân viên', 'warning'), badge('Đang chạy', 'success')], 'le-tan-ca-nhan · não: 🗂️ Trợ lý nội bộ',
    [wj2Toggle('account Zalo lễ tân (cá nhân)'), secondary('Login QR'), secondary('Sửa'), danger('Xóa')])
];
// AccountForm (kit: Sheet + Field; `account-edit-drawer.tsx`): the add/edit drawer of an account, drawn as a dialog
const wj2Policies = (bot) => [
  h4('Policies'),
  check('Trả lời trong nhóm', true), check('Nhóm phải @mention mới trả lời', true),
  check('Nghe passive trong nhóm', false), sm('Tin không @mention vẫn ghi vào ngữ cảnh, không tốn LLM'),
  h4('Phản hồi tức thì'),
  check('Hiện "đang nhập" khi bot xử lý', true), sm('Giống người thật đang gõ, tự tắt khi gửi xong'),
  bot ? stack({ g: 4 }, strong('Thả cảm xúc khi nhận tin'), sm('- Zalo Bot API không có method thả cảm xúc nên tài khoản bot không dùng được mục này.'))
    : [check('Thả cảm xúc khi nhận tin', true), sm('Báo cho người nhắn biết bot đã thấy tin'), chips(['👍', ['❤️', 'sel'], '😆'])]
];
const wj2BrainPolicy = () => [
  select('Agent (não)', '🩺 CSKH Da liễu mặc định', { opts: ['🩺 CSKH Da liễu mặc định', '📊 Báo cáo tuần', '🗂️ Trợ lý nội bộ'] }),
  card({ v: 'soft', eyebrow: 'Hồ sơ chính sách' },
    select('Hồ sơ chính sách', 'Kênh bệnh nhân mặc định'),
    sm('Mọi tin gửi đi vào hàng đợi duyệt để một người duyệt rồi mới gửi; ca cờ đỏ (chảy máu, sốt, mưng mủ, khó thở) chuyển bác sĩ trước khi gọi mô hình AI.'),
    sm('Số điện thoại, CCCD, email bị che trước khi gửi cho mô hình; công cụ ảnh, video, tài liệu và web bị tắt.'),
    notice('Account nhắn tin với BỆNH NHÂN phải ở hồ sơ Kênh bệnh nhân. Chỉ dùng Trợ lý nhân viên cho account nội bộ chỉ có nhân viên. Mặc định là Kênh bệnh nhân.', 'warning'))
];
const wj2TokenHelp = 'Lấy token: mở Zalo, tìm OA "Zalo Bot Manager", chọn "Tạo bot" (tên phải bắt đầu bằng "Bot"). Token được gửi vào tin nhắn Zalo cho bạn. Hệ thống sẽ kiểm token với Zalo trước khi lưu.';
const wj2ZaloDlg = (id, title, note, blocks, o) => ndlg(id, title, wj2NXW + '/admin/accounts · ' + note, blocks, { nx: 'owner', nav: '/admin/accounts', behind: wj2ZaloPage(), w: 480, ...o });

// ---- Agents (/admin/agents) ----
const wj2Agents = [
  { icon: '🩺', name: 'CSKH Da liễu', badges: [badge('Mặc định', 'brand', { dot: false }), badge('Kênh bệnh nhân', 'success')], slug: 'cskh-da-lieu', accounts: '1 account đang dùng',
    persona: 'Bạn là trợ lý chăm sóc khách hàng của một phòng khám da liễu, xưng "em" và gọi khách là "chị" hoặc "anh". Chỉ trả lời dựa trên tài liệu phòng khám đã được bác sĩ duyệt và luôn nêu nguồn. Không chẩn đoán, không kê thuốc, không hứa kết quả điều trị. Khi khách mô tả chảy máu, sốt, mưng mủ hoặc khó thở, dừng lại và báo nhân viên để bác sĩ liên hệ ngay.' },
  { icon: '📊', name: 'Báo cáo tuần', badges: [badge('Kênh bệnh nhân', 'success'), badge('qwen3-8b', 'neutral', { dot: false })], slug: 'bao-cao-tuan', accounts: 'Chưa gắn account nào',
    persona: '(chưa có persona - dùng giọng mặc định của bot)' },
  { icon: '🗂️', name: 'Trợ lý nội bộ', badges: [badge('Trợ lý nhân viên', 'warning')], slug: 'tro-ly-noi-bo', accounts: '1 account đang dùng',
    persona: 'Bạn hỗ trợ nhân viên phòng khám soạn nháp, tóm tắt hội thoại và tra cứu quy trình nội bộ. Không trả lời trực tiếp bệnh nhân.' }
];
// AgentCard (kit: Card + Badge + Button; `agent-card.tsx`): icon, name, badges, id, persona (cut), accounts in use, "Xem chi tiết", "Sửa" and the row menu
const wj2AgentCard = (a) => card({ comp: 'AgentCard', title: a.icon + ' ' + a.name, sub: a.slug, aside: [...a.badges, iconBtn('more_vert', { aria: 'Hành động khác cho ' + a.name })] },
  txt(a.persona, { size: 's', tone: 'soft' }), hr(),
  row({ jc: 'space-between' }, sm(a.accounts), row(secondary('Xem chi tiết', { icon: 'visibility' }), secondary('Sửa', { icon: 'edit' }))));
// AgentRow: the list view of the same agent
const wj2AgentRow = (a) => card({ comp: 'AgentRow', aside: [sm(a.accounts), secondary('Sửa', { icon: 'edit' }), iconBtn('more_vert', { aria: 'Hành động khác cho ' + a.name })] },
  row({ g: 14 }, avatar(a.icon), stack({ g: 4 }, row(strong(a.name), ...a.badges), txt(a.persona, { size: 's', tone: 'soft' }))));
const wj2AgentsHead = (q, view, total, used) => [
  pageHead('Agents', 'Mỗi agent là một bộ não: persona + model riêng + hồ sơ chính sách, gắn vào tài khoản Zalo ở trang Tài khoản Zalo', [primary('Tạo agent', { icon: 'add' })]),
  kpis(kpi('Tổng số agent', total, '', { icon: 'smart_toy' }), kpi('Tổng tài khoản đang dùng'.replace('tài khoản', 'account'), used, '', { icon: 'group' })),
  q === null ? null : row({ jc: 'space-between', g: 12 }, search('Tìm agent...', { val: q, w: 320 }),
    row(secondary('Sắp xếp: Mặc định trước', { aria: 'Sắp xếp danh sách agent', ric: 'expand_more' }), chips([['Xem dạng lưới', view === 'list' ? '' : 'sel'], ['Xem dạng danh sách', view === 'list' ? 'sel' : '']])))
];
const wj2AgentsPage = (view = 'grid') => [
  wj2AgentsHead('', view, '3', '2'),
  view === 'list' ? wj2Agents.map(wj2AgentRow) : grid(2, ...wj2Agents.map(wj2AgentCard))
];


// ---- Agent mới / Chi tiết agent (/admin/agents/new, /admin/agents/[id]) ----
const wj2Tools = [
  ['Tra cứu', 'Chỉ đọc, không tác động ra ngoài', [
    ['Tra cứu kho tri thức', 'kb_search', 'Tìm đoạn liên quan trong tài liệu phòng khám đã được duyệt rồi trả lời kèm nguồn.'],
    ['Xem ngày giờ', 'get_datetime', 'Biết hôm nay là ngày nào, giờ nào theo múi giờ phòng khám.'],
    ['Tìm trên web', 'web_search', 'Tra tin tức, thông tin công khai bên ngoài.'],
    ['Đọc trang web', 'web_fetch', 'Đọc nội dung một địa chỉ web (đã chặn địa chỉ nội bộ).'],
    ['Nhìn kỹ ảnh', 'read_image', 'Mô tả ảnh người dùng gửi thành chữ. (Chưa cấu hình sidecar đọc ảnh (Settings).)'],
    ['Thông tin nhóm', 'get_group_info', 'Xem tên và thành viên của nhóm chat.']]],
  ['Hành động', 'Gửi hoặc sửa thứ gì đó trên Zalo', [
    ['Ghi nhớ', 'save_memory', 'Lưu một sự thật bền để lần sau còn nhớ.'],
    ['Hẹn lịch', 'schedule_task', 'Tạo việc chạy sau hoặc lặp lại.'],
    ['Gửi tệp', 'send_file', 'Gửi một tệp cho người đang chat.'],
    ['Tạo tài liệu Word', 'create_word_document', 'Soạn tệp .docx từ dữ liệu có cấu trúc.'],
    ['Tạo bảng Excel', 'create_excel_file', 'Soạn tệp .xlsx từ dữ liệu có cấu trúc.'],
    ['Vẽ ảnh AI', 'create_image', 'Vẽ mới hoặc sửa ảnh theo mô tả. (Chưa cấu hình endpoint vẽ ảnh (Settings).)'],
    ['Tải video', 'tai_video', 'Tải video từ liên kết công khai.'],
    ['Gắn thẻ thành viên', 'tag_member', 'Nhắc tên một thành viên trong nhóm.']]]
];
// ToolAllowRow (kit: Badge + Button switch; `agent-tool-picker.tsx`): name, code id, description, state badge and the switch "Bật tắt <tên>"
const wj2ToolRows = (flag) => wj2Tools.map(([t, s, items]) => [h4(t, s), list(items.map(([name, id, desc]) => {
  const f = flag[id];
  return { t: name, sub: id, sub2: desc, actions: [...(f ? [badge(f.t, f.tone || 'neutral', { dot: false })] : []), iconBtn(f && f.off ? 'toggle_off' : 'toggle_on', { aria: 'Bật tắt ' + name })] };
}), { box: true })]);
const wj2Profile = () => [
  h3('Hồ sơ chính sách', 'Khi agent gắn vào một tài khoản, hồ sơ nghiêm hơn (của agent hoặc của tài khoản) sẽ được áp dụng.'),
  grid(2,
    card({ tint: 'info', title: 'Kênh bệnh nhân', aside: [ico('radio_button_checked', { tone: 'link' })] }, sm('Tin gửi ra ngoài vào hàng đợi duyệt để một người bấm gửi; dấu hiệu cờ đỏ chuyển bác sĩ trước khi gọi model. Thông tin cá nhân được che; công cụ ảnh, video, tài liệu, web tắt; save_memory tắt với nội dung từ bệnh nhân.')),
    card({ title: 'Trợ lý nội bộ', aside: [ico('radio_button_unchecked')] }, sm('Giữ hành vi gốc của agent: tin gửi thẳng, không qua hàng đợi duyệt. Chỉ dùng cho trợ lý của nhân viên, không dùng để trả lời bệnh nhân.')))
];
const wj2ModelCard = (stepsVal, stepsErr) => card({ title: 'Model', sub: 'Để trống mọi ô ở đây thì agent chạy đúng cấu hình chung. Chỉ đặt riêng khi agent này cần giới hạn hoặc mức suy nghĩ khác phần còn lại. Nhà cung cấp và tên model luôn lấy từ trang Cấu hình.' },
  input('Số bước tối đa', stepsVal, { ph: 'theo Cấu hình', hint: 'bước · (1 - 30)', err: stepsErr }),
  sm('Một bước là một lần bot nói chuyện với model, có thể gọi nhiều công cụ cùng lúc. Bỏ trống là theo trang Cấu hình.'), hr(),
  select('Cửa sổ ngữ cảnh (Context window)', 'Theo Cấu hình chung'),
  sm('Lượng token tối đa bot gửi đi trong MỘT lần gọi model. Đặt riêng khi agent này chạy model có cửa sổ khác, và đừng đặt lớn hơn cửa sổ thật của model đó. Bỏ trống là theo trang Cấu hình.'), hr(),
  select('Mức suy nghĩ', 'Theo Cấu hình chung'),
  sm('Nghĩ càng kỹ thì trả lời càng chắc nhưng chậm hơn và tốn token hơn. Việc đối chiếu số liệu, dò bảng nên để mức cao; trò chuyện thường để vừa là đủ.'));
const wj2PersonaBlocks = (val, count) => [
  textarea('Chỉ dẫn (persona)', val, { ph: "Bạn là trợ lý chăm sóc khách hàng, xưng 'em' với khách...", lines: 5 }),
  sm('Viết những gì RIÊNG của agent này: vai trò, cách xưng hô, giọng điệu. Các luật chung (không dùng markdown, chống prompt injection, hỏi lại khi thiếu thông tin) đã có sẵn cho mọi agent, không cần chép lại vào đây.'),
  sm(count + ' / 8.000 ký tự')
];
const wj2KbPick = [['Hướng dẫn chăm sóc da sau laser', true], ['Dấu hiệu cần liên hệ phòng khám', true], ['Bảng giá dịch vụ (nháp)', false, 'chưa được bác sĩ duyệt'], ['Quy trình nhắc tái khám', false, 'chưa được bác sĩ duyệt'],
  ['Phiếu quét (ảnh chụp)', false, 'chưa được bác sĩ duyệt', 'hỏng'], ['Bắt đầu theo vai trò', false, 'chưa được bác sĩ duyệt'], ['CSKH chủ động: xử lý việc hôm nay', false, 'chưa được bác sĩ duyệt'], ['Hồ sơ và Patient 360', false, 'chưa được bác sĩ duyệt']];
const wj2BlockedTools = { web_search: 1, web_fetch: 1, read_image: 1, send_file: 1, create_word_document: 1, create_excel_file: 1, create_image: 1, tai_video: 1 };
const wj2AgentForm = (mode, o = {}) => {
  const edit = mode === 'edit';
  const flag = {};
  Object.keys(wj2BlockedTools).forEach(k => { if (edit) flag[k] = { t: 'Bị chặn bởi hồ sơ chính sách', tone: 'warning', off: true }; });
  if (!edit) { flag.read_image = { t: 'chưa cấu hình' }; flag.create_image = { t: 'chưa cấu hình' }; }
  return [
    pageHead(edit ? 'CSKH Da liễu' : 'Chăm sóc khách hàng', edit ? '1 tài khoản Zalo đang dùng agent này' : 'Chưa tạo - bấm Tạo agent để ghi lại, bấm Hủy là bỏ hẳn',
      edit ? [secondary('Quay lại'), primary('Lưu thay đổi', { dis: true })] : [secondary('Hủy'), primary('Tạo agent')]),
    grid(2,
      card({ title: 'Danh tính', sub: 'Tên và icon hiện trên dashboard. Phần chỉ dẫn thì LLM đọc nguyên văn ở mỗi lượt trả lời.' },
        input('Icon', edit ? '🩺' : '🤖'), input('Icon và tên hiển thị', edit ? 'CSKH Da liễu' : 'Chăm sóc khách hàng'),
        edit ? [strong('ID'), sm('Không đổi được: các tài khoản Zalo đang trỏ vào agent qua chính chuỗi này.'), row(badge('cskh-da-lieu', 'neutral', { dot: false }), badge('agent mặc định', 'brand', { dot: false }))]
          : [input('ID', 'cham-soc-khach-hang', { ph: 'cham-soc-khach-hang' }), sm('Đặt xong là chốt: sau khi tạo thì không đổi được nữa, vì các tài khoản Zalo sẽ trỏ vào agent qua chính chuỗi này.')],
        wj2Profile(), wj2PersonaBlocks(edit ? 'Bạn là trợ lý chăm sóc khách hàng của một phòng khám da liễu, xưng "em" và gọi khách là "chị" hoặc "anh". Chỉ trả lời dựa trên tài liệu phòng khám đã được bác sĩ duyệt…' : '', edit ? '350' : '0')),
      wj2ModelCard(o.steps || '', o.stepsErr || '')),
    h2('Công cụ', edit ? 'Agent này được phép dùng 6/6 công cụ đang có hạ tầng. Đây mới là NĂNG LỰC của agent - công cụ bot THẬT SỰ dùng được là phần GIAO với công cụ đang bật của từng tài khoản Zalo. Agent này đang gắn 1 tài khoản, mỗi tài khoản có lớp tắt riêng ở trang Tools - bật ở đây không bảo đảm bot dùng được.'
      : 'Agent này được phép dùng 12/12 công cụ đang có hạ tầng. Đây mới là NĂNG LỰC của agent - công cụ bot THẬT SỰ dùng được là phần GIAO với công cụ đang bật của từng tài khoản Zalo. Chưa tài khoản nào gắn agent này nên công tắc ở đây chưa có tác dụng thực tế.'),
    wj2ToolRows(flag),
    edit ? [h2('Kho tri thức', 'Agent chỉ đọc được nguồn đã tick - mặc định KHÔNG tick nguồn nào. Nạp tài liệu và xem trạng thái xử lý ở trang "Kho tri thức".'),
      list(wj2KbPick.map(([t, on, why, bad]) => ({ t, actions: [...(bad ? [badge(bad, 'danger')] : []), ...(why ? [badge(why, 'warning')] : []), iconBtn(on ? 'toggle_on' : 'toggle_off', { aria: 'Bật tắt nguồn ' + t })] })), { box: true }),
      primary('Lưu nguồn đã chọn', { dis: true })] : null
  ];
};


// ---- Tools (/admin/tools): công cụ theo tài khoản ----
// AccountToolRow (kit: Badge + Button; `account-tool-row.tsx`): name, code id, description, status badges, optional "Settings" link and the switch "Bật tắt <tên>"
const wj2ToolDefs = {
  kb_search: [], get_datetime: [], get_group_info: [], save_memory: [], schedule_task: [], tag_member: [],
  web_search: [['DuckDuckGo (miễn phí)'], ['Bị chặn bởi hồ sơ chính sách', 'blocked'], ['Agent đang tắt', 'agentoff']],
  web_fetch: [['Bị chặn bởi hồ sơ chính sách', 'blocked'], ['Agent đang tắt', 'agentoff']],
  read_image: [['Bot không đọc được ảnh'], ['Bị chặn bởi hồ sơ chính sách', 'blocked']],
  send_file: [['Bị chặn bởi hồ sơ chính sách', 'blocked']], create_word_document: [['Bị chặn bởi hồ sơ chính sách', 'blocked']], create_excel_file: [['Bị chặn bởi hồ sơ chính sách', 'blocked']],
  create_image: [['Bị chặn bởi hồ sơ chính sách', 'blocked'], ['Agent đang tắt', 'agentoff']], tai_video: [['Bị chặn bởi hồ sơ chính sách', 'blocked']]
};
const wj2ToolSettings = { web_search: 1, web_fetch: 1, read_image: 1, create_image: 1 };
const wj2ToolNotes = { read_image: 'Chưa cấu hình sidecar đọc ảnh (Settings).', create_image: 'Chưa cấu hình endpoint vẽ ảnh (Settings).' };
const wj2ToolsPage = (o = {}) => {
  const agentName = o.noAgent ? '' : 'CSKH Da liễu';
  const rows = (items) => items.map(([name, id, desc]) => {
    const raw = wj2ToolDefs[id] || [];
    const bs = raw.filter(([, k]) => !(o.free && (k === 'blocked' || k === 'agentoff'))).map(([t]) => t);
    if (o.free && (id === 'read_image' || id === 'create_image')) bs.push('Chưa dùng được');
    const agentOff = !o.free && raw.some(([, k]) => k === 'agentoff');
    const extra = [wj2ToolNotes[id], agentOff ? 'Công tắc này đang bật nhưng agent "' + agentName + '" đã tắt công cụ, nên model vẫn không nhận được. Bật lại ở trang Agents.' : ''].filter(Boolean);
    return card({ comp: 'ToolRow', title: name, sub: id, aside: [...bs.map(t => badge(t, t === 'Chưa dùng được' || t.startsWith('Bot không') ? 'warning' : 'neutral', { dot: false })), ...(wj2ToolSettings[id] ? [quiet('Settings', { icon: 'tune' })] : []), iconBtn('toggle_on', { aria: 'Bật tắt ' + name })] },
      sm(desc.split(' (Chưa cấu hình')[0]), ...extra.map(t => sm(t)));
  });
  const [g1, g2] = wj2Tools;
  if (o.empty) return [pageHead('Tools', 'Bật/tắt công cụ cho từng tài khoản. Model chỉ nhận được công cụ mà CẢ tài khoản này LẪN agent của nó cùng bật.'), card({}, sm('Chưa có account nào - tạo account ở trang Accounts trước.'))];
  return [
    pageHead('Tools', 'Bật/tắt công cụ cho từng tài khoản. Model chỉ nhận được công cụ mà CẢ tài khoản này LẪN agent của nó cùng bật.', [secondary('Pema CSKH (Zalo Bot)', { aria: 'Chọn account', ric: 'expand_more' })]),
    o.noAgent ? notice('Chưa đọc được cấu hình agent, nên trang này chỉ đang hiện lớp TÀI KHOẢN. Công cụ bị agent tắt sẽ không có nhãn - tải lại trang để xem đầy đủ.', 'warning') : null,
    h2('Đọc & tra cứu', 'Không tác động ra ngoài - an toàn bật mặc định'), rows(g1[2]),
    h2('Hành động', 'Gửi/sửa thứ gì đó trên Zalo - cân nhắc theo account'), rows(g2[2])
  ];
};
const wj2ToolDlg = (id, title, note, sub, blocks, o = {}) => ndlg(id, title, wj2NXW + '/admin/tools · ' + note, blocks, { nx: 'owner', nav: '/admin/tools', behind: wj2ToolsPage(o.page), w: 640, sub, footer: [secondary('Hủy'), primary('Lưu')], ...o.dlg });
const wj2Always = (n, t, desc) => card({ v: 'soft', eyebrow: n + '. ' + t, aside: [badge('Luôn bật', 'success', { dot: false })] }, sm(desc));
const wj2KeyField = (label, ph) => [input(label, '', { ph, suf: 'visibility' }), iconBtn('visibility', { aria: 'Hiện nội dung' })];


// ---- MCP (/admin/mcp) ----
const wj2McpCols = ['Tên', ['URL', '1.4fr'], 'Trạng thái', ['Số tool', '80px'], 'Agent đang dùng', 'Cập nhật', ['', '1.2fr']];
// McpServerRow (kit: TableShell row + Badge + Button; `mcp-server-table.tsx`): name with its message, URL, status, tool count, agents, updated, "Sửa" / "Xóa"
const wj2McpRows = (errFirst) => [
  [[strong('Lịch hẹn nội bộ'), errFirst ? txt('Không kết nối được tới máy chủ MCP (hết thời gian chờ).', { size: 'l', tone: 'danger' }) : null], 'https://mcp.pema.test/lich-hen',
    [errFirst ? badge('Lỗi', 'danger') : badge('Đã kết nối', 'success')], '2', [quiet('1 agent', { icon: 'group' })], '20/09 08:00', cell([quiet('Sửa', { icon: 'edit' }), danger('Xóa')], { row: true })],
  [[strong('Tra cứu danh mục (bản thử)'), sm('Bộ tool của server đã đổi so với lần duyệt trước')], 'https://mcp.example.com/catalog',
    [badge('Chờ duyệt lại', 'warning')], '1', [quiet('Chưa gán', { icon: 'warning' })], '20/09 07:00', cell([quiet('Duyệt lại', { icon: 'undo' }), quiet('Sửa', { icon: 'edit' }), danger('Xóa')], { row: true })],
  [[strong('Báo cáo ngoài'), txt('Không kết nối được tới máy chủ MCP (hết thời gian chờ).', { size: 'l', tone: 'danger' }), sm('Đang tắt')], 'https://mcp.broken.test/report',
    [badge('Lỗi', 'danger')], '0', [quiet('Chưa gán', { icon: 'warning' })], '17/09 09:00', cell([quiet('Sửa', { icon: 'edit' }), danger('Xóa')], { row: true })]
];
const wj2McpPage = (o = {}) => [
  pageHead('MCP', 'Server MCP ngoài cắm cho agent dùng tool của chúng - thêm xong phải GÁN cho agent thì bot mới gọi được', [primary('Thêm server', { icon: 'add' })]),
  o.empty ? table(wj2McpCols, [], { empty: 'Chưa có server nào - bấm "Thêm server" để cắm MCP server ngoài' }) : table(wj2McpCols, wj2McpRows(o.err))
];
const wj2McpDlg = (id, title, note, blocks, o = {}) => ndlg(id, title, wj2NXW + '/admin/mcp · ' + note, blocks, { nx: 'owner', nav: '/admin/mcp', behind: wj2McpPage(), w: 560, ...o });
const wj2McpForm = (edit) => [
  input('Tên', edit ? 'Lịch hẹn nội bộ' : '', { ph: 'vd: Notion' }),
  input('URL (Streamable HTTP)', edit ? 'https://mcp.pema.test/lich-hen' : '', { ph: 'https://mcp.example.com/mcp' }),
  row({ jc: 'space-between' }, stack({ g: 2 }, strong('Bật server này'), sm('Tắt thì bot không nối và không dùng được tool của nó')), iconBtn('toggle_on', { aria: 'Bật server này' })),
  row({ jc: 'space-between' }, strong('Header xác thực'), quiet('+ Thêm header')),
  edit ? row({ jc: 'space-between' }, sm('Đã lưu header (ẩn) - gõ dòng mới bên dưới để thay, hoặc xóa hẳn'), danger('Xóa header'))
    : [sm('Không bắt buộc - chỉ điền nếu server yêu cầu xác thực. Ví dụ token:'), code('Authorization: Bearer sk-abc123def456...')]
];


// ---- Trace agent (/admin/traces) ----
const wj2TraceRuns = Array.from({ length: 12 }, (_, i) => {
  const m = 8 * 60 + 55 - 47 * i, hh = String(Math.floor(m / 60)).padStart(2, '0'), mm = String(m % 60).padStart(2, '0');
  const who = [3, 7, 11].includes(i) ? 'Lễ tân Trâm' : 'Nguyễn Thu Hà';
  const tok = 1680 + 142 * i;
  return { label: who + ' 20/09 ' + hh + ':' + mm + ' - ' + (2 + (i % 3)) + ' step - ' + String(tok).replace(/(\d)(\d{3})$/, '$1.$2') + ' token' };
});
const wj2TraceOpen = { ...wj2TraceRuns[0], open: true, steps: [
  { n: 'Step 1', finish: 'tool-calls', tokens: '700 vào / 60 ra', parts: [{ label: 'Gọi tool: kb_search', text: '{ "query": "chăm sóc da sau laser" }', mono: true }, { label: 'Tool trả về: kb_search', text: '3 đoạn từ 2 nguồn đã được bác sĩ duyệt.' }] },
  { n: 'Step 2', finish: 'stop', tokens: '900 vào / 90 ra', parts: [{ label: 'Model nói', text: 'Em đã soạn nháp trả lời kèm nguồn, chờ nhân viên duyệt.' }] }] };
const wj2TraceHead = () => pageHead('Trace agent', 'Mỗi lượt bot trả lời đã chạy qua những step nào: model nói gì, gọi tool nào với tham số gì');
const wj2TraceEnd = () => sm('Đã hết lượt có trace. Trace cũ hơn bị dọn theo "Giữ trace" ở trang Cấu hình.');

// ---- Logs (/admin/logs) ----
const wj2LogTabs = (on) => tabs(['Log hệ thống', 'Nhật ký thao tác'], on, { seg: true });
const wj2LogHead = () => pageHead('Logs', 'Log toàn hệ thống đọc từ file. File ghi cả mức debug nên đầy đủ hơn nhìn terminal.');
const wj2LogFilters = () => row({ g: 8, ai: 'flex-end' }, secondary('Mọi mức', { aria: 'Lọc theo mức', ric: 'expand_more' }), secondary('Mọi scope', { aria: 'Lọc theo scope', ric: 'expand_more' }), input('', '', { ph: 'Tìm trong log rồi Enter...', w: 420, suf: 'search' }), secondary('Tải lại', { icon: 'refresh' }));
const wj2LogLines = [
  ['09:00:00.000', 'INFO', 'http', 'Nhận tin nhắn đến, đã xếp vào hàng đợi', 1], ['08:59:23.000', 'INFO', 'channel.zalo_bot', 'Lượt agent hoàn tất'], ['08:58:46.000', 'DEBUG', 'agent.loop', 'Quét hàng đợi việc đến hạn'],
  ['08:58:09.000', 'WARN', 'scheduler', 'Cờ đỏ: chuyển bác sĩ trước khi gọi mô hình', 1], ['08:57:32.000', 'INFO', 'knowledge.ingest', 'Nạp tài liệu: đã cắt đoạn xong'], ['08:56:55.000', 'ERROR', 'policy', 'Gửi tin lỗi: kênh không khả dụng, sẽ thử lại'],
  ['08:56:18.000', 'INFO', 'http', 'Nháp chờ duyệt đã được tạo', 1], ['08:55:41.000', 'INFO', 'channel.zalo_bot', 'Nhận tin nhắn đến, đã xếp vào hàng đợi'], ['08:55:04.000', 'INFO', 'agent.loop', 'Lượt agent hoàn tất'],
  ['08:54:27.000', 'DEBUG', 'scheduler', 'Quét hàng đợi việc đến hạn', 1], ['08:53:50.000', 'WARN', 'knowledge.ingest', 'Cờ đỏ: chuyển bác sĩ trước khi gọi mô hình'], ['08:53:13.000', 'INFO', 'policy', 'Nạp tài liệu: đã cắt đoạn xong']
];
const wj2LogTone = { INFO: 'info', DEBUG: 'neutral', WARN: 'warning', ERROR: 'danger' };
// LogLine (kit: Badge + Button; `log-viewer.tsx`): time, level badge, scope, message and "Chi tiết"
const wj2LogList = () => list(wj2LogLines.map(([t, lv, sc, msg, more]) => ({ t: msg, sub: t + ' · ' + sc, actions: [badge(lv, wj2LogTone[lv], { dot: false }), ...(more ? [quiet('Chi tiết')] : [])] })), { box: true });
const wj2LogsPage = () => [wj2LogHead(), wj2LogTabs(0), wj2LogFilters(), wj2LogList(), secondary('Xem thêm 150 dòng cũ hơn')];
const wj2AuditRows = [['Chủ phòng khám', 'review.approve', 'review_item', '· 00000000'], ['Quản lý', 'handoff.claim', 'handoff', '· 00000001'], ['Bác sĩ', 'review.approve', 'review_item', '· 00000002'],
  ['CSKH', 'draft.edit', 'draft', '· 00000003'], ['Lễ tân', 'followup.done', 'followup', '· 00000004'], ['agent', 'draft.create', 'draft', '· 00000005']];
const wj2AuditPage = () => [wj2LogHead(), wj2LogTabs(1),
  row({ jc: 'space-between', g: 12 }, row({ g: 12, ai: 'flex-end' }, input('', '', { ph: 'Lọc theo hành động, ví dụ review.approve', w: 340 }), secondary('Mọi đối tượng', { aria: 'Lọc theo đối tượng', ric: 'expand_more' })),
    row({ g: 8 }, secondary('Trước', { dis: true }), sm('Trang 1'), secondary('Sau'))),
  table(['Lúc', 'Người thực hiện', 'Hành động', 'Đối tượng', ['Chi tiết', '1.6fr']], wj2AuditRows.map(([who, act, obj, id], i) => ['20/09 0' + (9 - i) + ':00', [badge(who, who === 'agent' ? 'brand' : 'neutral', { dot: false })], act, [txt(obj), sm(id)], sm('{"clinic_id":"00000000-0000-4000-8000-000000000001","via":"mock"}')])),
  sm('Nhật ký chỉ thêm, không sửa hay xóa được. Nội dung tin nhắn của bệnh nhân không được ghi ở đây.')];


// ---- Hồ sơ chính sách (/admin/policy) ----
const wj2PolicyRules = [
  ['Tin gửi ra khách', 'Vào hàng đợi duyệt, một người duyệt rồi mới gửi', 'Gửi thẳng cho khách'],
  ['Tin theo lịch', 'Chỉ tin từ mẫu bác sĩ đã duyệt; job agent chỉ soạn nháp', 'Cho phép tin có sẵn và job chạy agent'],
  ['Ghi nhớ (save_memory)', 'Tắt với nội dung từ bệnh nhân; chỉ bác sĩ hoặc CSKH ghi', 'Cho phép ghi nhớ'],
  ['Ảnh khách gửi', 'Gắn cờ Inbox và chuyển nhân viên; không phân tích ảnh', 'Xử lý bình thường'],
  ['Công cụ ảnh, video, tài liệu, web', 'Tắt (8 công cụ)', 'Theo cấu hình từng tài khoản'],
  ['Cờ đỏ (chảy máu, sốt, mưng mủ, khó thở)', 'Chuyển bác sĩ trước khi gọi mô hình', 'Không áp dụng'],
  ['Che thông tin cá nhân', 'Bắt buộc che trước mọi lời gọi mô hình', 'Che tùy chọn'],
  ['Trần tin chủ động', 'Theo từng bệnh nhân và tài khoản mỗi ngày', 'Theo từng cuộc trò chuyện mỗi ngày'],
  ['Khách từ chối tin quảng bá', 'Chặn tin quảng bá', 'Chặn tin quảng bá'],
  ['Sinh nhật', 'Không tự gửi, là việc của nhân viên', 'Không tự gửi, là việc của nhân viên'],
  ['Xác minh danh tính Zalo với hồ sơ', 'Bắt buộc trước khi nhắc tên, lịch hẹn hay thuốc', 'Không cần']
];
const wj2PolicyOwners = [['Pema CSKH (Zalo Bot)', 'Zalo Bot', 'Kênh bệnh nhân'], ['Zalo lễ tân (cá nhân)', 'Zalo cá nhân', 'Trợ lý nội bộ'], ['CSKH Da liễu', 'Agent', 'Kênh bệnh nhân'], ['Trợ lý nội bộ', 'Agent', 'Trợ lý nội bộ'], ['Báo cáo tuần', 'Agent', 'Kênh bệnh nhân']];
const wj2PolicyPage = (o = {}) => [
  pageHead('Hồ sơ chính sách', 'An toàn bệnh nhân là cài đặt, không phải tính năng bị xóa: cùng một trợ lý chạy với hồ sơ khác nhau'),
  h2('Hai hồ sơ'),
  table(['Quy tắc', 'Kênh bệnh nhânpatient_channel', 'Trợ lý nội bộstaff_assistant'], wj2PolicyRules),
  sm('Khi một agent chạy trong một tài khoản, hồ sơ nghiêm hơn của hai bên được áp dụng. Mặc định của cả hai là Kênh bệnh nhân.'),
  h2('Hồ sơ của từng tài khoản và agent'),
  o.empty ? sm('Chưa có tài khoản hay agent nào')
    : list(wj2PolicyOwners.map(([t, k, p]) => ({ t, sub: k, actions: [secondary(p, { aria: 'Hồ sơ chính sách của ' + t, ric: 'expand_more' })] })), { box: true }),
  h2('Liên kết danh tính Zalo chờ xác nhận (3)'),
  notice('Trợ lý chỉ được nhắc tên, lịch hẹn hay thuốc của một bệnh nhân sau khi tài khoản Zalo đó được nhân viên xác nhận là đúng người. Đối chiếu bằng hồ sơ hoặc gọi xác minh trước khi xác nhận.', 'info'),
  list([{ t: 'Hồ sơ P007', sub: 'Zalo Bot · u-demo-004', actions: [badge('Chờ xác nhận', 'warning'), primary('Xác nhận'), secondary('Từ chối')] },
    { t: 'Hồ sơ P009', sub: 'Zalo Bot · u-demo-009', actions: [badge('Chờ xác nhận', 'warning'), primary('Xác nhận'), secondary('Từ chối')] },
    { t: 'Chưa có hồ sơ gợi ý', sub: 'Zalo cá nhân · u-demo-011', actions: [badge('Chưa liên kết', 'neutral')] }], { box: true })
];

// @@DEFS
const WJ2 = [
  // ---- Tài khoản Zalo: công tắc khẩn, thêm, sửa, QR, xóa ----
  wj2ZaloDlg('WJ58', 'BẬT công tắc khẩn của Tài khoản bot chính thức?', 'hộp xác nhận bật công tắc khẩn của kênh; nút bật tắt khi chưa nhập lý do',
    [txt(wj2Kill, { size: 's', tone: 'soft' }), textarea('Lý do (bắt buộc, ghi vào nhật ký kiểm toán)', '', { ph: 'vd: Zalo nhắc tài khoản có dấu hiệu gửi quá nhiều', lines: 3 })],
    { footer: [secondary('Hủy'), danger('Bật công tắc khẩn', { dis: true })] }),
  wj2ZaloDlg('WJ59', 'Tắt công tắc khẩn của Tài khoản bot chính thức?', 'hộp xác nhận tắt công tắc khẩn; lý do không bắt buộc',
    [txt(wj2Kill, { size: 's', tone: 'soft' }), txt('Tắt công tắc: tin chủ động sẽ được gửi lại theo trần, khoảng cách và khung giờ đang cài.', { size: 's', tone: 'soft' }), textarea('Lý do (không bắt buộc)', '', { lines: 3 })],
    { footer: [secondary('Hủy'), primary('Tắt công tắc khẩn')] }),
  wj2ZaloDlg('WJ60', 'Thêm account Zalo', 'ngăn kéo "Thêm account Zalo" của tài khoản cá nhân quét QR, vẽ như hộp thoại', [
    input('ID (kebab-case, dùng làm thư mục data)', '', { ph: 'vd: acc-cham-soc' }),
    select('Loại kênh', 'Tài khoản cá nhân quét QR', { opts: ['Tài khoản cá nhân quét QR', 'Tài khoản bot chính thức nhập token'] }),
    sm('Dùng nick Zalo thật qua giao thức không chính thức - đủ tính năng nhất nhưng CÓ rủi ro bị Zalo khóa. Chỉ dùng nick phụ.'),
    sm('Chốt lúc tạo, không đổi được sau đó.'),
    input('Tên hiển thị', '', { ph: 'vd: Nick chăm sóc khách hàng' }),
    wj2BrainPolicy(), wj2Policies(false),
    h4('Kết bạn'), check('Tự động chấp nhận yêu cầu kết bạn', true), sm('Bot tự accept sau khoảng chờ dưới đây. Tắt thì bạn tự duyệt ở tab Bạn bè.'),
    h4('Allowlist'), select('Allowlist', 'Trả lời tất cả mọi người')
  ], { w: 560, footer: [secondary('Đóng'), primary('Tạo account', { dis: true })] }),
  wj2ZaloDlg('WJ61', 'Thêm account Zalo', 'ngăn kéo "Thêm account Zalo" của tài khoản bot chính thức nhập token: có ô token, không có thả cảm xúc, allowlist theo user ID', [
    input('ID (kebab-case, dùng làm thư mục data)', '', { ph: 'vd: acc-cham-soc' }),
    select('Loại kênh', 'Tài khoản bot chính thức nhập token', { opts: ['Tài khoản cá nhân quét QR', 'Tài khoản bot chính thức nhập token'] }),
    sm('Không gửi được file, tài liệu Word/Excel, ảnh tự vẽ, video tải về, thả cảm xúc, tag thành viên, và không đọc được danh sách thành viên nhóm - đó là giới hạn của Zalo Bot API. Đổi lại không có rủi ro bị khóa tài khoản.'),
    sm('Chốt lúc tạo, không đổi được sau đó.'),
    input('Tên hiển thị', '', { ph: 'vd: Nick chăm sóc khách hàng' }),
    input('Token bot', '', { ph: '123456789:...', suf: 'visibility' }), sm(wj2TokenHelp),
    wj2BrainPolicy(), wj2Policies(true),
    h4('Allowlist'), select('Allowlist', 'Chỉ trả lời user ID trong danh sách'), textarea('', '', { ph: 'Mỗi dòng 1 user ID 1234567890123456789', lines: 2 })
  ], { w: 560, footer: [secondary('Đóng'), primary('Tạo account', { dis: true })] }),
  wj2ZaloDlg('WJ62', 'Sửa: Pema CSKH (Zalo Bot)', 'ngăn kéo sửa account bot: token đã có (nhập mới để thay), không có mục chọn loại kênh', [
    input('Tên hiển thị', 'Pema CSKH (Zalo Bot)', { ph: 'vd: Nick chăm sóc khách hàng' }),
    input('Token bot (đã có - nhập mới để thay)', '', { ph: 'Để trống nếu không đổi', suf: 'visibility' }), sm(wj2TokenHelp),
    wj2BrainPolicy(),
    h4('Policies'), check('Trả lời trong nhóm', true), check('Nhóm phải @mention mới trả lời', true),
    check('Nghe passive trong nhóm', false), sm('Tin không @mention vẫn ghi vào ngữ cảnh, không tốn LLM'),
    h4('Phản hồi tức thì'), check('Hiện "đang nhập" khi bot xử lý', true), sm('Giống người thật đang gõ, tự tắt khi gửi xong'),
    strong('Thả cảm xúc khi nhận tin'), sm('- Zalo Bot API không có method thả cảm xúc nên tài khoản bot không dùng được mục này.'),
    h4('Allowlist'), select('Allowlist', 'Trả lời tất cả mọi người')
  ], { w: 560, footer: [secondary('Đóng'), primary('Lưu thay đổi')] }),
  wj2ZaloDlg('WJ63', 'Login QR - Zalo lễ tân (cá nhân)', 'hộp đăng nhập QR: mã QR chờ quét', [
    sm('Mở app Zalo trên điện thoại và quét mã này'), img('Mã QR đăng nhập Zalo', { icon: 'qr_code_2', h: 208 })
  ], { w: 400, footer: [secondary('Đóng')] }),
  wj2ZaloDlg('WJ64', 'Login QR - Zalo lễ tân (cá nhân)', 'hộp đăng nhập QR sau khi quét: chờ xác nhận trên điện thoại', [
    sm('Đã quét - xác nhận đăng nhập trên điện thoại'), txt('📱', { size: 'ti' })
  ], { w: 400, footer: [secondary('Đóng')] }),
  wj2ZaloDlg('WJ65', 'Login QR - Zalo lễ tân (cá nhân)', 'hộp đăng nhập QR hết thời gian chờ quét: nút "Thử lại"', [
    sm('Hết thời gian chờ quét (3 phút)'), txt('⚠️', { size: 'ti' })
  ], { w: 400, footer: [primary('Thử lại'), secondary('Đóng')] }),
  wj2ZaloDlg('WJ66', 'Xóa account "Pema CSKH (Zalo Bot)"?', 'hộp xác nhận xóa account',
    [txt('Credentials đăng nhập Zalo sẽ bị xóa, lịch sử hội thoại vẫn giữ lại.', { size: 's', tone: 'soft' })],
    { w: 440, footer: [secondary('Hủy'), danger('Xóa')] }),

  // ---- Agents ----
  npage('WJ67', 'Agents', wj2NXW + '/admin/agents · lưới thẻ agent, ô tìm, sắp xếp, chuyển lưới/danh sách', '/admin/agents', wj2AgentsPage('grid'), { nx: 'owner' }),
  npage('WJ68', 'Agents · dạng danh sách', wj2NXW + '/admin/agents · cùng trang ở dạng danh sách (mỗi agent một dòng)', '/admin/agents', wj2AgentsPage('list'), { nx: 'owner', state: true }),
  npage('WJ69', 'Agents · không có kết quả tìm', wj2NXW + '/admin/agents · tìm "zzz" không khớp agent nào', '/admin/agents', [
    wj2AgentsHead('zzz', 'grid', '3', '2'), empty('Không có agent nào khớp "zzz".', '', { flat: true, icon: 'search_off' })
  ], { nx: 'owner', state: true }),
  npage('WJ70', 'Agents · chưa có agent', wj2NXW + '/admin/agents · chưa có agent nào: hai ô tổng bằng 0, không có ô tìm', '/admin/agents', [
    wj2AgentsHead(null, 'grid', '0', '0'), empty('Chưa có agent nào.', '', { flat: true, icon: 'smart_toy' })
  ], { nx: 'owner', state: true }),
  ndlg('WJ71', 'Tạo agent mới', wj2NXW + '/admin/agents · hộp "Tạo agent mới": tên, icon, persona, hồ sơ chính sách; agent chỉ được tạo ở bước sau', [
    grid({ cols: '96px minmax(0,1fr)', g: 12 }, input('Icon', '🤖'), input('Tên hiển thị', '', { ph: 'vd: Chăm Sóc Khách Hàng' })),
    row({ g: 6 }, sm('ID:'), sm('chưa tạo được từ tên'), quiet('sửa', { sm: true })),
    textarea('Agent này làm gì? (để trống cũng được, bước sau sửa tiếp)', '', { ph: "Bạn là trợ lý chăm sóc khách hàng, xưng 'em' với khách...", lines: 4 }),
    h3('Hồ sơ chính sách', 'Khi agent gắn vào một tài khoản, hồ sơ nghiêm hơn (của agent hoặc của tài khoản) sẽ được áp dụng.'),
    grid(2,
      card({ tint: 'info', title: 'Kênh bệnh nhân', aside: [ico('radio_button_checked', { tone: 'link' })] }, sm('Tin gửi ra ngoài vào hàng đợi duyệt để một người bấm gửi; dấu hiệu cờ đỏ chuyển bác sĩ trước khi gọi model. Thông tin cá nhân được che; công cụ ảnh, video, tài liệu, web tắt; save_memory tắt với nội dung từ bệnh nhân.')),
      card({ title: 'Trợ lý nội bộ', aside: [ico('radio_button_unchecked')] }, sm('Giữ hành vi gốc của agent: tin gửi thẳng, không qua hàng đợi duyệt. Chỉ dùng cho trợ lý của nhân viên, không dùng để trả lời bệnh nhân.')))
  ], { nx: 'owner', nav: '/admin/agents', behind: wj2AgentsPage('grid'), w: 720, sub: 'Đặt tên trước đã. Bước sau còn model, số bước và công cụ - agent chỉ được tạo khi bạn bấm Tạo ở đó.', footer: [secondary('Hủy'), primary('Tiếp tục', { dis: true })] }),
  ndlg('WJ72', 'Xóa agent "Trợ lý nội bộ"?', wj2NXW + '/admin/agents · hộp xác nhận xóa agent', [
    txt('Persona và cấu hình model riêng của agent này sẽ mất.', { size: 's', tone: 'soft' })
  ], { nx: 'owner', nav: '/admin/agents', behind: wj2AgentsPage('grid'), w: 440, footer: [secondary('Hủy'), danger('Xóa')] }),
  npage('WJ73', 'Agent mới', wj2NXW + '/admin/agents/new · form tạo agent: danh tính, hồ sơ chính sách, persona, model, công cụ (chưa có kho tri thức, agent chưa tồn tại)', '/admin/agents', wj2AgentForm('new'), { nx: 'owner' }),
  ndlg('WJ74', 'Bỏ agent đang tạo?', wj2NXW + '/admin/agents/new · hộp xác nhận khi rời trang mà chưa tạo agent', [
    txt('Agent này chưa được tạo. Rời đi là mất những gì bạn vừa nhập.', { size: 's', tone: 'soft' })
  ], { nx: 'owner', nav: '/admin/agents', behind: wj2AgentForm('new'), w: 440, footer: [secondary('Ở lại'), primary('Bỏ')] }),
  npage('WJ75', 'Agent mới · lỗi nhập hoặc lỗi tải công cụ', wj2NXW + '/admin/agents/new · "Số bước tối đa" nhập 99, ngoài khoảng 1 - 30: dòng lỗi dưới ô', '/admin/agents', wj2AgentForm('new', { steps: '99', stepsErr: 'Phải trong khoảng 1 - 30' }), { nx: 'owner', state: true }),
  npage('WJ76', 'Chi tiết agent', wj2NXW + '/admin/agents/[id] · sửa agent đã có: ID bị khóa, công cụ bị hồ sơ chính sách chặn, thêm khối Kho tri thức để tick nguồn', '/admin/agents', wj2AgentForm('edit'), { nx: 'owner' }),
  npage('WJ77', 'Chi tiết agent · không tìm thấy', wj2NXW + '/admin/agents/[id] · id không có agent nào', '/admin/agents', [
    pageHead('Không tìm thấy agent', 'Không có agent nào mang id "khong-co"'), quiet('Quay lại danh sách agent', { icon: 'arrow_back' })
  ], { nx: 'owner', state: true }),
  ndlg('WJ78', 'Rời trang mà chưa lưu?', wj2NXW + '/admin/agents/[id] · hộp xác nhận khi rời trang chi tiết agent có thay đổi chưa lưu', [
    txt('Những thay đổi bạn vừa sửa trên trang này sẽ mất.', { size: 's', tone: 'soft' })
  ], { nx: 'owner', nav: '/admin/agents', behind: wj2AgentForm('edit'), w: 440, footer: [secondary('Ở lại'), primary('Rời đi')] }),

  npage('WJ79', 'Tools', wj2NXW + '/admin/tools · công cụ theo tài khoản, chọn account ở góc phải; nhãn khi bị hồ sơ chính sách hoặc agent chặn', '/admin/tools', wj2ToolsPage(), { nx: 'owner' }),
  npage('WJ80', 'Tools · chưa có account', wj2NXW + '/admin/tools · chưa có account nào: chỉ có dòng hướng dẫn, không có nút chọn account', '/admin/tools', wj2ToolsPage({ empty: true }), { nx: 'owner', state: true }),
  npage('WJ81', 'Tools · chỉ đọc được lớp tài khoản', wj2NXW + '/admin/tools · không đọc được cấu hình agent: dòng cảnh báo trên đầu, tên agent trong nhãn để trống', '/admin/tools', wj2ToolsPage({ noAgent: true }), { nx: 'owner', state: true }),
  wj2ToolDlg('WJ82', 'Tìm trên web - chuỗi nguồn', 'hộp cấu hình "Tìm trên web": Brave Search (cần API key) rồi DuckDuckGo', 'Thử lần lượt từ trên xuống, dừng ở bậc đầu tiên cho kết quả dùng được.', [
    card({ v: 'soft', eyebrow: '1. Brave Search', aside: [iconBtn('toggle_on', { aria: 'Bật tắt Brave Search' })] }, sm('Kết quả tốt hơn, cần API key. Hết quota hoặc lỗi thì tự rơi xuống bậc dưới.'),
      wj2KeyField('API key(chưa có key)', 'Dán key vào đây'), row({ g: 4 }, sm('Lấy key miễn phí tại'), lnk('brave.com/search/api'), sm('.'))),
    wj2Always(2, 'DuckDuckGo', 'Miễn phí, không cần key. Là bậc cuối nên web search không bao giờ thiếu nguồn.')
  ]),
  wj2ToolDlg('WJ83', 'Đọc trang web - chuỗi nguồn', 'hộp cấu hình "Đọc trang web": tự tải trực tiếp rồi Jina Reader', 'Thử lần lượt từ trên xuống, dừng ở bậc đầu tiên cho kết quả dùng được.', [
    wj2Always(1, 'Tự tải trực tiếp', 'Nhanh, riêng tư, đã chặn IP nội bộ chống SSRF. Không đọc được trang render bằng JavaScript.'),
    card({ v: 'soft', eyebrow: '2. Jina Reader (r.jina.ai)', aside: [iconBtn('toggle_off', { aria: 'Bật tắt Jina Reader (r.jina.ai)' })] }, sm('Dùng khi bậc 1 hỏng hoặc ra quá ít chữ: render được trang JavaScript, qua được một phần chặn bot. Chậm hơn nhiều và URL đi qua dịch vụ bên thứ ba.'))
  ]),
  ndlg('WJ84', 'Xóa API key Brave?', wj2NXW + '/admin/tools · hộp xác nhận xóa API key Brave', [
    txt('Web search sẽ chỉ còn DuckDuckGo (miễn phí) cho tới khi bạn nhập key mới.', { size: 's', tone: 'soft' })
  ], { nx: 'owner', nav: '/admin/tools', behind: wj2ToolsPage(), w: 440, footer: [secondary('Hủy'), danger('Xóa')] }),
  wj2ToolDlg('WJ85', 'Đọc ảnh - chuỗi nguồn', 'hộp cấu hình "Nhìn kỹ ảnh": model chính rồi model sidecar mô tả ảnh', 'Model chính đọc pixel trước; không đọc được thì sidecar mô tả ảnh thành chữ.', [
    wj2Always(1, 'Model chính tự đọc ảnh', 'Luôn thử trước nếu model có khả năng đọc ảnh. Không có gì để cài ở bậc này.'),
    card({ v: 'soft', eyebrow: '2. Model sidecar mô tả ảnh', aside: [iconBtn('toggle_off', { aria: 'Bật tắt Model sidecar mô tả ảnh' })] },
      select('Nhà cung cấp', 'OpenAI-compatible (Ollama, llama-server, router)'),
      input('Base URL', '', { ph: 'https://generativelanguage.googleapis.com/v1beta/openai' }),
      input('Model', '', { ph: 'qwen2.5-vl' }), sm('Ví dụ một model có vision chạy trên máy phòng khám.'),
      wj2KeyField('API key', 'Dán API key vào đây')),
    notice('Với hồ sơ chính sách Kênh bệnh nhân, công cụ đọc ảnh bị tắt và ảnh khách gửi được chuyển cho nhân viên xem: sidecar không đọc ảnh của bệnh nhân ở đó.', 'info')
  ], { dlg: { w: 720 } }),
  wj2ToolDlg('WJ86', 'Vẽ ảnh AI', 'hộp cấu hình "Vẽ ảnh AI": endpoint OpenAI-compatible, đang tắt', 'Endpoint OpenAI-compatible /v1/images/generations - vẽ mới hoặc sửa ảnh người dùng gửi.', [
    row({ jc: 'space-between' }, stack({ g: 2 }, strong('Bật vẽ ảnh'), sm('Tắt thì bot không có công cụ vẽ ảnh.')), iconBtn('toggle_off', { aria: 'Bật vẽ ảnh' })),
    input('Base URL', '', { ph: 'https://api.example.com' }), sm('Chỉ phần gốc, không kèm /v1/images/generations - bot tự nối.'),
    input('Model', '', { ph: 'gpt-5.5-image' }), sm('Không có danh sách để chọn và chưa có nút vẽ thử: gõ đúng tên model của nhà cung cấp.'),
    wj2KeyField('API key', 'Dán API key vào đây'),
    notice('Mỗi ảnh mất khoảng 1 phút và tốn phí của nhà cung cấp. Hồ sơ chính sách Kênh bệnh nhân tắt công cụ này bất kể cấu hình ở đây.', 'warning')
  ], { page: { free: true } }),

  npage('WJ87', 'MCP', wj2NXW + '/admin/mcp · bảng server MCP ngoài: trạng thái, số tool, agent đang dùng, Duyệt lại / Sửa / Xóa', '/admin/mcp', wj2McpPage(), { nx: 'owner' }),
  npage('WJ88', 'MCP · chưa có server', wj2NXW + '/admin/mcp · bảng trống với dòng hướng dẫn', '/admin/mcp', wj2McpPage({ empty: true }), { nx: 'owner', state: true }),
  npage('WJ89', 'MCP · lỗi và chờ duyệt lại', wj2NXW + '/admin/mcp · server báo "Lỗi" kèm thông báo lỗi, server "Chờ duyệt lại" có nút "Duyệt lại"', '/admin/mcp', wj2McpPage({ err: true }), { nx: 'owner', state: true }),
  wj2McpDlg('WJ90', 'Thêm server MCP', 'hộp thêm server: tên, URL, bật, header xác thực', wj2McpForm(false), { footer: [secondary('Đóng'), primary('Thêm server', { dis: true })] }),
  wj2McpDlg('WJ91', 'Sửa: Lịch hẹn nội bộ', 'hộp sửa server: có header đã lưu (ẩn) và "Xóa header"', wj2McpForm(true), { footer: [secondary('Đóng'), primary('Lưu thay đổi')] }),
  wj2McpDlg('WJ92', 'Agent nào được dùng server này', 'hộp chọn agent được dùng server "Tra cứu danh mục (bản thử)"', [
    list([['🩺', 'CSKH Da liễu'], ['🗂️', 'Trợ lý nội bộ'], ['📊', 'Báo cáo tuần']].map(([i, n]) => ({ avatar: i, t: n, actions: [iconBtn('toggle_off', { aria: 'Bật tắt agent ' + n })] })), { box: true }),
    sm('Không agent nào dùng được server này')
  ], { sub: 'Tra cứu danh mục (bản thử)', footer: [secondary('Đóng'), primary('Lưu')] }),
  wj2McpDlg('WJ93', 'Xóa server "Lịch hẹn nội bộ"?', 'hộp xác nhận xóa server', [txt('1 agent đang dùng server này sẽ mất quyền gọi tool ngoài của nó.', { size: 's', tone: 'soft' })], { w: 440, footer: [secondary('Hủy'), danger('Xóa')] }),

  npage('WJ94', 'Trace agent', wj2NXW + '/admin/traces · danh sách các lượt bot trả lời, mỗi lượt là một nút "Xem"; hết trang thì có dòng báo', '/admin/traces', [wj2TraceHead(), trace(...wj2TraceRuns), wj2TraceEnd()], { nx: 'owner' }),
  npage('WJ95', 'Trace agent · chưa có trace', wj2NXW + '/admin/traces · chưa có lượt nào (trace chưa bật hoặc đã dọn)', '/admin/traces', [wj2TraceHead(), empty('Chưa có trace nào. Trace chỉ ghi từ lúc bật AGENT_TRACE_ENABLED, và tự dọn sau AGENT_TRACE_RETENTION_DAYS ngày.', '', { flat: true, icon: 'account_tree' })], { nx: 'owner', state: true }),
  npage('WJ96', 'Trace agent · lượt đã mở', wj2NXW + '/admin/traces · lượt đầu đã mở: từng step với finish, token, tool gọi, tool trả về, lời model', '/admin/traces', [wj2TraceHead(), trace(wj2TraceOpen, ...wj2TraceRuns.slice(1)), wj2TraceEnd()], { nx: 'owner', state: true }),
  npage('WJ97', 'Trace agent · hết lượt có trace', wj2NXW + '/admin/traces · cuối danh sách: "Đã hết lượt có trace"', '/admin/traces', [wj2TraceHead(), trace(...wj2TraceRuns), wj2TraceEnd()], { nx: 'owner', state: true }),
  npage('WJ98', 'Logs', wj2NXW + '/admin/logs · tab "Log hệ thống": lọc theo mức, scope, tìm; mỗi dòng có mức, scope, nội dung và "Chi tiết"', '/admin/logs', wj2LogsPage(), { nx: 'owner' }),
  npage('WJ99', 'Logs · Nhật ký thao tác', wj2NXW + '/admin/logs · tab "Nhật ký thao tác": bảng người thực hiện, hành động, đối tượng, chi tiết; phân trang', '/admin/logs', wj2AuditPage(), { nx: 'owner' }),
  npage('WJ100', 'Logs · ghi log ra file đang tắt', wj2NXW + '/admin/logs · LOG_TO_FILE chưa bật: dòng báo thay cho danh sách', '/admin/logs', [wj2LogHead(), wj2LogTabs(0), notice('Ghi log ra file đang tắt. Bật LOG_TO_FILE=true rồi khởi động lại backend để xem nhật ký ứng dụng ở đây.', 'warning'), wj2LogFilters()], { nx: 'owner', state: true }),
  npage('WJ101', 'Logs · không có dòng log', wj2NXW + '/admin/logs · bộ lọc không khớp dòng nào', '/admin/logs', [wj2LogHead(), wj2LogTabs(0), wj2LogFilters(), empty('Không có dòng log nào khớp.', '', { flat: true, icon: 'search_off' })], { nx: 'owner', state: true }),

  npage('WJ102', 'Hồ sơ chính sách', wj2NXW + '/admin/policy · bảng so sánh hai hồ sơ, hồ sơ của từng tài khoản và agent, liên kết danh tính Zalo chờ xác nhận', '/admin/policy', wj2PolicyPage(), { nx: 'owner' }),
  ndlg('WJ103', 'Chuyển "Pema CSKH (Zalo Bot)" sang Trợ lý nội bộ?', wj2NXW + '/admin/policy · hộp xác nhận khi đổi tài khoản sang hồ sơ Trợ lý nội bộ (tin gửi thẳng, không qua duyệt)', [
    txt('Tin gửi ra ngoài sẽ đi thẳng, không qua hàng đợi duyệt; cờ đỏ không còn chuyển bác sĩ tự động và thông tin cá nhân không bắt buộc che. Chỉ dùng cho trợ lý của nhân viên, không dùng để trả lời bệnh nhân.', { size: 's', tone: 'soft' })
  ], { nx: 'owner', nav: '/admin/policy', behind: wj2PolicyPage(), w: 520, footer: [secondary('Hủy'), danger('Chuyển sang Trợ lý nội bộ')] }),
  npage('WJ104', 'Hồ sơ chính sách · chưa có tài khoản hay agent', wj2NXW + '/admin/policy · phần "Hồ sơ của từng tài khoản và agent" chỉ còn dòng báo chưa có', '/admin/policy', wj2PolicyPage({ empty: true }), { nx: 'owner', state: true }),

  // @@ENTRIES
];
