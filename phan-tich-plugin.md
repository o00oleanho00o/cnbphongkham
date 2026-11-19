
Mình đã đọc OpenClaw (extensions/zalo), deepseek-harness (packages/webhook và webhook-github), zalo-agent và hermes-agent rồi so với code hiện tại. Dưới đây là plan cho Zalo, chưa code gì.

Họ cắm gateway vào kiểu gì
Lõi (core) làm gì	Plugin của từng kênh làm gì
deepseek-harness	Lõi chỉ có register(rule) và dispatch(delivery). README ghi rõ: "provider authentication belongs to adapter packages".	webhook-github tự đăng ký route HTTP trên ctx.webServer, tự xác thực HMAC, tự giới hạn kích thước body, chuyển sang dạng chung rồi trả 202. Gỡ plugin thì route biến mất theo.
OpenClaw	Lõi lo định tuyến session (resolveAgentRoute), cắt tin dài, policy DM/nhóm, pairing.	zalo khai báo capabilities (DM/nhóm, media, textChunkLimit 2000), gateway.startAccount (polling hoặc webhook), outbound.sendText/sendMedia, sanitizeText. Route webhook do plugin tự đăng ký (registerPluginHttpRoute), header bí mật X-Bot-Api-Secret-Token cũng do plugin tự kiểm.
hermes	Lõi có BasePlatformAdapter với connect, disconnect, send_message.	Plugin gọi ctx.register_platform(...). Một nền tảng có hai đường truyền thì hai adapter dùng chung một mixin, ví dụ WhatsApp Baileys và Cloud API.
zalo-agent	—	Tự viết client gọi thẳng Bot API, không dùng SDK. Chỉ ~10 endpoint, polling getUpdates, lưu tin vào DB ngay khi nhận.
Triết lý chung, áp vào mình:

Lõi không biết chữ "zalo" là gì; mọi thứ riêng của Zalo nằm trong plugin.
Lõi chỉ cho những thứ dùng chung được cho mọi kênh: hợp đồng adapter, lưu tin vào, gửi lại khi lỗi, cắt tin dài, policy truy cập, chỗ để cắm route HTTP.
Xác thực của từng bên (secret, token) thuộc về plugin.
Mọi thứ plugin đăng ký đều phải gỡ được khi tắt plugin.
Mình đang có sẵn khá đủ: ChannelAdapter (start(receive), stop, send, capabilities.max_text_chars), ctx.register_channel, ChannelHub (lưu tin trước khi chạy, bỏ trùng theo message_id, gửi lại có backoff, failure_reply), split_reply, secret mã hoá cho từng plugin. Polling khớp ngay với start(receive).

Còn thiếu, đều là thứ dùng chung:

Plugin chưa tự đăng ký được route HTTP, nên webhook chưa làm được.
Chưa có policy truy cập: ai được nhắn DM, nhóm có bắt buộc @mention không.
Gợi ý cho model theo kênh, ví dụ "kênh này chỉ hiện chữ thường, tối đa 2000 ký tự". Hiện markdown=False khai báo mà chưa dùng ở đâu.
Chỉ báo "đang gõ" và giới hạn tốc độ gửi theo kênh (đã ghi trong "Known limits").
Thông tin Zalo Bot API (đã thấy ở cả OpenClaw lẫn zalo-agent)
Endpoint: https://bot-api.zaloplatforms.com/bot{token}/{method}. Token nằm ngay trong URL, nên mọi log và lỗi phải che token đi.
Các method: getMe, getUpdates (long poll khoảng 30 s; mã 408 nghĩa là không có tin mới, không phải lỗi), sendMessage, sendPhoto (chỉ nhận URL ảnh), sendChatAction (typing), setWebhook, deleteWebhook.
Polling và webhook loại trừ nhau: đã bật webhook thì không poll được.
Dữ liệu một tin vào: message.chat.id, chat_type là PRIVATE hoặc GROUP, from.id, text/photo, date tính bằng mili giây.
Giới hạn: tối đa 2000 ký tự mỗi tin; không render markdown; không có sửa, xoá hay reaction tin nhắn.
Plan
Z1 — Plugin zalo chạy polling, chỉ chat riêng và chữ (gần như không đụng lõi)

Plugin nằm ở apps/agent/plugins/zalo/, gồm plugin.toml và client.py gọi API bằng httpx.
Secret bot_token lấy qua ctx.secret. Lúc khởi động gọi getMe để kiểm token; trạng thái hiện ở /v1/admin/channels.
Nhận tin: vòng poll chạy đến khi stop(), lỗi mạng thì chờ tăng dần rồi thử lại. Mỗi tin đổi thành InboundMessage(channel="zalo", conversation_id=chat.id, user_id=from.id, message_id=...).
Gửi tin: capabilities.max_text_chars=2000; mã lỗi của Zalo được đổi thành ChannelSendError(retryable=...).
Lõi (chung cho mọi kênh): thêm một dòng gợi ý trong context block khi kênh không có markdown và có giới hạn độ dài.
Test: dựng một Zalo giả bằng httpx.MockTransport, không cần token thật. Thêm một bước kiểm tra để chữ "zalo" không xuất hiện trong agentcore hay agent_app.
Z2 — Policy truy cập (phần lõi viết chung, plugin chỉ báo thông tin)

Plugin gắn vào tin chat_type và cờ mentioned.
Lõi đọc cấu hình [plugins.zalo] dm_policy = open|allowlist|disabled và group_policy = off|mention|allowlist, lọc tin trước khi lưu.
Pairing kiểu OpenClaw (gửi mã, admin duyệt) để sau, vì cần giao diện quản trị.
Z3 — Chế độ webhook (cần URL public)

Lõi: thêm ctx.register_route(path, handler), mount dưới /v1/channels/<plugin></plugin>/..., giống cách deepseek-harness làm. Route này không qua bearer token vì plugin tự xác thực. Lõi vẫn giới hạn kích thước body và tốc độ gọi theo IP. Tắt plugin thì route tự gỡ.
Plugin: kiểm header X-Bot-Api-Secret-Token bằng so sánh không lộ thời gian (compare_digest), gọi setWebhook khi bật và deleteWebhook khi tắt.
Z4 — Hoàn thiện việc gửi tin

Thêm method không bắt buộc typing(conversation_id) vào adapter; hub gọi định kỳ trong lúc agent đang trả lời.
Giới hạn tốc độ gửi cho từng kênh trong ChannelHub.
Ảnh gửi đến được đưa vào metadata dưới dạng URL; đọc ảnh bằng model xử lý hình để sau.
Để sau: Zalo OA, nhiều bot trên một agent, pairing có giao diện. Zalo cá nhân qua zca-js thì không làm: không chính thức, dễ bị khoá tài khoản, lại cần Node.

Mỗi giai đoạn làm xong sẽ commit, dừng lại báo cáo và cập nhật handoff như trước.

Cần bạn chốt mấy điểm:

Đi Zalo Bot API trước như trên, hay đi thẳng Zalo OA (Official Account của phòng khám)? Khách thật thường nhắn qua OA. OA dùng API khác: webhook, access token phải refresh định kỳ, có giới hạn khung thời gian được nhắn lại. Nó có thể là đường truyền thứ hai trong cùng plugin, theo kiểu hermes làm với WhatsApp.
Bạn đã có bot token để chạy thử thật sau Z1 chưa?
Có cần chat nhóm ngay không, hay Z1 chỉ chat riêng là đủ?
