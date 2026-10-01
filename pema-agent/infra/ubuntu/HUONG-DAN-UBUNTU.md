# Hướng dẫn dựng Pema Agent trên Ubuntu cài hẳn (không WSL2)

Dành cho người quản trị máy. Gói F viết, dựa trên `docker-compose.yml` và các script trong `infra/`.

**Trạng thái kiểm chứng (đọc trước).** Đã chạy thật: Docker/compose, Postgres+pgvector, Redis, role, migration,
sao lưu/khôi phục, và container Ollama dùng GPU RTX 3060 12 GB (Docker Desktop trên Windows) với Qwen3-8B Q5_K_M và
bge-m3 (số đo ở mục 5). **Chưa chạy trên máy Ubuntu thật:** cài driver NVIDIA, NVIDIA Container Toolkit, Ollama cài
trực tiếp, llama-server, Tailscale/WireGuard, ufw, NUT/UPS, timer systemd. Các lệnh đó theo tài liệu chính thức của
từng sản phẩm; mỗi mục có bước "kiểm tra" để bạn tự xác nhận. Chỗ nào ghi "(roadmap)" là kế hoạch, chưa dùng
trong vận hành. Mã hóa age/gpg của sao lưu chưa chạy thử (chỉ nhánh bản không mã hóa).

Quyết định đã chốt (PLAN-AI01 mục 8): PC chạy Ubuntu cài hẳn; LLM qua Ollama, sau chuyển llama-server; vị trí
server (phòng khám hay cloud VN) chưa quyết nên tài liệu này viết cho cả hai.

---

## 0. Chọn mô hình triển khai

Ba thành phần: **stack lõi** (Postgres, Redis, API, worker, frontend: nhẹ, chạy 24/7), **máy GPU** (Ollama với
RTX 3060 12 GB) và **người dùng** (nhân viên mở dashboard).

| Mô hình | Stack lõi chạy ở | Máy GPU | Khi nào chọn |
|---|---|---|---|
| **A. Một máy** | PC Ubuntu có RTX 3060 (tại phòng khám) | cùng máy | Bắt đầu, thử nghiệm, phòng khám nhỏ. Đơn giản nhất, nhưng PC chết là mất tất cả. |
| **B. Server phòng khám + PC GPU** | máy chủ nhỏ tại phòng khám | PC GPU tại phòng khám, nối qua mạng LAN/Tailscale | Có máy chủ riêng chạy 24/7, PC GPU có thể tắt/ bảo trì mà DB không đụng tới. |
| **C. Cloud VN + PC GPU** | VPS/cloud Việt Nam | PC GPU tại phòng khám, nối qua Tailscale | Cần endpoint công khai (webhook Zalo) và sao lưu ngoài phòng khám; chấp nhận độ trễ đến PC GPU. |

Quy tắc chung cho cả ba: **Postgres, Redis, Ollama không bao giờ lắng nghe trên địa chỉ công cộng** (mục 8). Dữ
liệu bệnh nhân ở lại hạ tầng của chủ phòng khám; LLM chạy cục bộ nên không có tin bệnh nhân gửi ra dịch vụ
ngoài. Worker chỉ nói chuyện với LLM qua HTTP, nên đặt worker cạnh DB (mô hình khuyến nghị) và trỏ
`LLM_BASE_URL` sang máy GPU; chạy worker trên chính PC GPU cũng được nhưng khi đó PC GPU phải với tới Postgres và
Redis qua Tailscale (đặt `PEMA_PG_BIND` / `PEMA_REDIS_BIND` bằng IP Tailscale của server).

---

## 1. Chuẩn bị Ubuntu

Dùng **Ubuntu Server hoặc Desktop 24.04 LTS** cài lên ổ đĩa (không WSL2: WSL2 chuyển tiếp GPU qua lớp ảo, khó
ổn định khi chạy 24/7 và không điều khiển được nguồn/UPS).

1. BIOS/UEFI: bật *Above 4G Decoding* và *Resizable BAR* nếu có; đặt **Restore on AC Power Loss = Power On**
   (điện về là máy tự bật). Quyết định Secure Boot ở mục 2.
2. Cài hệ điều hành, tạo một tài khoản quản trị (không dùng `root` đăng nhập), đặt hostname rõ nghĩa
   (`pema-core`, `pema-gpu`).
3. Cập nhật và các gói nền:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y curl git ca-certificates gnupg ufw chrony unattended-upgrades fail2ban jq
sudo timedatectl set-timezone Asia/Ho_Chi_Minh        # lịch hẹn, cron và trần tin/ngày tính theo múi giờ này
sudo dpkg-reconfigure -plow unattended-upgrades        # tự cập nhật bản vá bảo mật
```

4. SSH chỉ dùng khóa: chép khóa công khai lên máy, rồi trong `/etc/ssh/sshd_config.d/10-pema.conf` đặt
   `PasswordAuthentication no`, `PermitRootLogin no`; `sudo systemctl reload ssh`. Giữ phiên cũ mở đến khi thử xong
   phiên mới.

Kiểm tra: `timedatectl` hiện `Asia/Ho_Chi_Minh` và `System clock synchronized: yes`.

---

## 2. Driver NVIDIA cho RTX 3060 12 GB

```bash
sudo ubuntu-drivers devices          # liệt kê, dòng "recommended" là bản nên cài
sudo ubuntu-drivers install          # cài bản khuyến nghị (hoặc: sudo apt install nvidia-driver-<số>)
sudo reboot
nvidia-smi                            # phải thấy "NVIDIA GeForce RTX 3060", 12288 MiB, driver version
```

- **Secure Boot bật:** trình cài sẽ hỏi đặt mật khẩu MOK; sau khi khởi động lại chọn *Enroll MOK* và nhập mật
  khẩu. Bỏ qua bước này thì `nvidia-smi` báo không thấy driver. Cách đơn giản hơn trên máy chủ: tắt Secure Boot
  trong BIOS.
- Chạy 24/7: `sudo systemctl enable --now nvidia-persistenced` (giữ driver nạp, giảm trễ lần gọi đầu).
- Không cần cài CUDA Toolkit để chạy Ollama (Ollama mang theo runtime CUDA). Chỉ cần CUDA Toolkit khi tự build
  llama.cpp (mục 9).
- Nhiệt và điện: RTX 3060 tối đa 170 W. Giám sát bằng `watch -n 2 nvidia-smi`; nếu phòng nóng, hạ giới hạn công
  suất `sudo nvidia-smi -pl 140` (mất ít tốc độ, giảm nhiệt; đặt lại sau mỗi lần khởi động bằng một unit
  systemd nếu muốn giữ).

Kiểm tra: `nvidia-smi` không lỗi, và `nvidia-smi --query-gpu=name,memory.total --format=csv` in ra 12 GB.

---

## 3. Docker và (tùy chọn) NVIDIA Container Toolkit

Cài Docker Engine từ kho apt chính thức của Docker (không dùng gói `docker.io` của Ubuntu để có Compose v2):

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"      # đăng xuất/đăng nhập lại để có hiệu lực
docker compose version
```

Giới hạn nhật ký container để đĩa không đầy: tạo `/etc/docker/daemon.json`

```json
{ "log-driver": "local", "log-opts": { "max-size": "20m", "max-file": "5" } }
```

rồi `sudo systemctl restart docker`.

**NVIDIA Container Toolkit** chỉ cần nếu dùng Ollama *trong* compose (`--profile ollama`). Nếu chạy Ollama trực
tiếp trên máy (mục 5) thì bỏ qua. Cài theo hướng dẫn chính thức của NVIDIA (kho apt `nvidia-container-toolkit`),
sau đó:

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
docker run --rm --gpus all ubuntu nvidia-smi      # phải in cùng bảng như trên máy
```

---

## 4. Lấy mã và dựng stack lõi

```bash
sudo mkdir -p /opt/cnbphongkham && sudo chown "$USER" /opt/cnbphongkham
git clone <địa-chỉ-repo> /opt/cnbphongkham && cd /opt/cnbphongkham/pema-agent
git switch feat/ai-agent-backend

make infra-secrets            # tạo infra/.env với mật khẩu ngẫu nhiên (hex); từ chối ghi đè nếu đã có
$EDITOR infra/.env            # xem lại; mục 7/8 nói khi nào đổi PEMA_*_BIND
make up                       # postgres, redis, migrate (một lần), api
make ps
curl -fsS http://127.0.0.1:8000/healthz
```

`make up` chạy theo thứ tự: Postgres khỏe, rồi dịch vụ một lần `migrate` (tạo role `be_app`/`agent_worker` và đặt
mật khẩu từ biến môi trường, rồi `alembic upgrade heads`), rồi `api`. Worker, frontend, bridge Zalo cá nhân và
Ollama nằm trong *profile* và **chỉ bật khi gói tương ứng đã có mã**:

| Profile | Lệnh | Phụ thuộc |
|---|---|---|
| `worker` | `docker compose ... --profile worker up -d` | `pema.workers.main` của gói G |
| `frontend` | `--profile frontend` | ứng dụng Next.js của gói E (`output: "standalone"`) |
| `app` | `make up-app` | worker + frontend |
| `bridge` | `--profile bridge` | gói C2 (và chấp nhận rủi ro khóa tài khoản Zalo) |
| `ollama` | `make up-ollama` | NVIDIA Container Toolkit (mục 3) |

**Zalo Bot API cần địa chỉ HTTPS công khai nếu dùng webhook.** Stack này không mở cổng ra internet. Cách ít rủi ro
nhất cho giai đoạn đầu là dùng chế độ **polling** của gói C1 (chỉ gọi ra ngoài, không cần cổng vào). Nếu bắt buộc
webhook: mô hình C (cloud VN) với reverse proxy HTTPS chỉ chuyển tiếp đường `/api/v1/webhooks/*`, hoặc Tailscale
Funnel cho đúng đường dẫn đó. Việc chọn là quyết định của chủ phòng khám (xem mục "Việc mở" trong báo cáo).

Cập nhật phiên bản: `git pull && make up && make db-migrate` (migrate chạy lại an toàn, chỉ áp bản mới).

---

## 5. Ollama và hai mô hình (Qwen3-8B và bge-m3)

Cài Ollama trực tiếp trên máy GPU (cách khuyến nghị cho Ubuntu cài hẳn):

```bash
curl -fsSL https://ollama.com/install.sh -o /tmp/ollama-install.sh && less /tmp/ollama-install.sh   # đọc trước khi chạy
sh /tmp/ollama-install.sh
sudo install -D -m 0644 infra/ubuntu/systemd/ollama-override.conf /etc/systemd/system/ollama.service.d/pema.conf
sudo systemctl daemon-reload && sudo systemctl restart ollama
infra/scripts/pull-models.sh            # Qwen3-8B Q5_K_M + bge-m3, rồi tạo tên ngắn "pema-chat"
```

**Chọn lượng tử hóa.** Thư viện Ollama chỉ có `qwen3:8b` ở dạng q4_K_M (5,2 GB), q8_0 (8,9 GB) và fp16. Hai dạng
trung gian lấy từ kho GGUF chính thức của Qwen qua `hf.co/Qwen/Qwen3-8B-GGUF:<quant>`:

| Dạng | Dung lượng | Nhận xét |
|---|---|---|
| `Q5_K_M` | 5,85 GB | Mặc định của repo: chừa nhiều VRAM nhất cho ngữ cảnh và bge-m3. |
| `Q6_K` | 6,73 GB | Gần chất lượng Q8 hơn; vẫn vừa. Đổi bằng `PEMA_LLM_MODEL_PULL=hf.co/Qwen/Qwen3-8B-GGUF:Q6_K`. |

Quyết định giữa Q5 và Q6 bằng bộ evals của gói D1/P (ví dụ cờ đỏ, trích nguồn, định dạng tool call), không theo
cảm tính.

**Ngân sách VRAM (ước tính, 12 GB).** Qwen3-8B có 36 lớp, 8 đầu KV, đầu 128 chiều: mỗi token ngữ cảnh tốn khoảng
147 KB KV ở fp16 (khoảng 74 KB ở q8_0). Với `OLLAMA_KV_CACHE_TYPE=q8_0`:

| Hạng mục | VRAM ước tính |
|---|---|
| Qwen3-8B Q6_K (trọng số) | 6,7 GB |
| KV cache, 2 luồng x 16k token, q8_0 | ~2,4 GB |
| bge-m3 (567M tham số, fp16) | ~1,2 GB |
| Bộ đệm tính toán, CUDA context | ~1 GB |
| **Tổng** | **~11,3 GB** (Q5_K_M: ~10,4 GB) |

**Đã đo thật (gói F, RTX 3060 12 GB, Ollama trong Docker, Windows có màn hình dùng chung GPU nên con số bất lợi hơn
Ubuntu không màn hình).** Qwen3-8B Q5_K_M với `num_ctx 16384`, `OLLAMA_NUM_PARALLEL=2`, flash attention, KV q8_0:
`ollama ps` báo `pema-chat` 8,2 GB (100% GPU) và `bge-m3` 664 MB (100% GPU); `nvidia-smi` tổng 9,5 GB đã dùng. Ước tính
ở bảng trên hơi cao (~10,4 GB). **Bài học quan trọng:** gọi thẳng mô hình `hf.co/Qwen/Qwen3-8B-GGUF:Q5_K_M` mà không đặt
`num_ctx` thì Ollama nạp ngữ cảnh 40960 của GGUF, mô hình phình ra 13 GB và **18% chuyển sang CPU**, chậm đi nhiều.
Vì vậy luôn dùng tên `pema-chat` (do `infra/scripts/pull-models.sh` và dịch vụ `ollama-pull` tạo, có `PARAMETER num_ctx`)
và đặt `LLM_MODEL=pema-chat`. Q6_K chưa đo.

Sát giới hạn khi dùng Q6_K với 2 luồng; nếu `nvidia-smi` báo gần đầy hoặc Ollama chuyển một phần lớp sang CPU
(`ollama ps` cột PROCESSOR không còn `100% GPU`), hạ một trong: `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_CONTEXT_LENGTH=8192`,
chuyển Q5_K_M. Không bật `--profile worker` đồng thời với mô hình khác trên cùng GPU mà không đo lại.

Kiểm tra:

```bash
ollama ps                                                   # PROCESSOR: 100% GPU
curl -s http://127.0.0.1:11434/v1/models | jq '.data[].id'  # có pema-chat và bge-m3
curl -s http://127.0.0.1:11434/v1/chat/completions -H 'content-type: application/json' \
  -d '{"model":"pema-chat","messages":[{"role":"user","content":"Xin chào"}]}' | jq -r '.choices[0].message.content'
curl -s http://127.0.0.1:11434/api/embed -d '{"model":"bge-m3","input":"da khô"}' | jq '.embeddings[0]|length'   # 1024
```

Số 1024 phải khớp `agent.kb_chunk.embedding vector(1024)`. Qwen3 có chế độ "suy nghĩ" in thêm đoạn lập luận; cách
tắt/giới hạn là việc của gói D1 (`LLM_REASONING_EFFORT`), không cấu hình ở tầng hạ tầng.

---

## 6. Container gọi tới Ollama trên máy

Khai báo trong `infra/.env` (hoặc trên dashboard, giá trị dashboard thắng):

| Tình huống | `LLM_BASE_URL` |
|---|---|
| Ollama trong compose (`--profile ollama`) | `http://ollama:11434/v1` |
| Ollama chạy trực tiếp, cùng máy với stack | `http://host.docker.internal:11434/v1` (compose cần `extra_hosts: host.docker.internal:host-gateway`; xem dưới) |
| Ollama ở máy GPU khác, nối bằng Tailscale | `http://pema-gpu:11434/v1` (tên MagicDNS) hoặc `http://100.x.y.z:11434/v1` |

Mặc định Ollama chỉ nghe `127.0.0.1`, container không với tới. Gói F đặt `OLLAMA_HOST=0.0.0.0:11434` trong
drop-in systemd và **dựa vào tường lửa** (mục 8) để chặn mọi nguồn trừ `tailscale0` và cầu nối Docker. Nếu không
muốn phụ thuộc tường lửa, dùng một trong hai cách thay thế: (a) chạy Ollama trong compose (profile `ollama`, cổng
chỉ publish ra `127.0.0.1`); (b) đặt `OLLAMA_HOST` bằng đúng địa chỉ IP Tailscale của máy.

Với `host.docker.internal` trên Linux, thêm vào dịch vụ `api` và `worker` (chưa có sẵn trong compose vì mô hình B/C
dùng Tailscale):

```yaml
    extra_hosts: ["host.docker.internal:host-gateway"]
```

---

## 7. Tailscale (hoặc WireGuard) giữa PC, server và nhân viên

Tailscale là lựa chọn mặc định: không mở cổng vào, mã hóa WireGuard, có MagicDNS và ACL.

```bash
curl -fsSL https://tailscale.com/install.sh | sh            # đọc script trước nếu cần
sudo tailscale up --hostname=pema-core --ssh=false          # trên mỗi máy; pema-gpu cho máy GPU
tailscale ip -4                                             # IP 100.x.y.z của máy này
```

- Trên bảng quản trị Tailscale: **tắt hết hạn khóa (Disable key expiry)** cho hai máy chủ để chúng không rớt
  khỏi mạng sau 180 ngày; gắn thẻ `tag:server` (stack lõi) và `tag:gpu` (máy GPU).
- ACL tối thiểu (đặt trong *Access controls*; thay tên nhóm cho đúng):

```json
{
  "tagOwners": { "tag:server": ["autogroup:admin"], "tag:gpu": ["autogroup:admin"] },
  "acls": [
    { "action": "accept", "src": ["autogroup:member"], "dst": ["tag:server:443,3000"] },
    { "action": "accept", "src": ["tag:server"],       "dst": ["tag:gpu:11434"] },
    { "action": "accept", "src": ["autogroup:admin"],  "dst": ["tag:server:22", "tag:gpu:22"] }
  ]
}
```

  Nhân viên chỉ tới được dashboard; chỉ server tới được Ollama; chỉ quản trị viên SSH. Postgres (5432) và Redis
  (6379) không có luật nào cho người dùng.
- HTTPS cho dashboard không cần reverse proxy: `sudo tailscale serve --bg --https=443 http://127.0.0.1:3000`
  (cần bật HTTPS trong bảng quản trị). Nhân viên mở `https://pema-core.<tailnet>.ts.net`.
- Nếu một cổng publish phải bind vào IP Tailscale (mô hình B/C: `PEMA_PG_BIND=100.x.y.z`), cài drop-in để Docker
  khởi động sau `tailscaled`: `infra/ubuntu/systemd/docker-after-tailscale.conf` (hướng dẫn trong file).

**WireGuard thuần (thay thế, không cần tài khoản Tailscale).** Mẫu `/etc/wireguard/wg0.conf` trên máy GPU (khóa
tạo bằng `wg genkey | tee private.key | wg pubkey > public.key`; mọi giá trị dưới đây là chỗ giữ):

```ini
[Interface]
Address = 10.77.0.2/24
PrivateKey = <PRIVATE_KEY_CUA_MAY_NAY>
ListenPort = 51820

[Peer]                         # server lõi
PublicKey = <PUBLIC_KEY_CUA_SERVER>
AllowedIPs = 10.77.0.1/32
Endpoint = <IP_CONG_CONG_HOAC_DDNS_CUA_SERVER>:51820
PersistentKeepalive = 25
```

`sudo systemctl enable --now wg-quick@wg0`. Cần một máy có địa chỉ công khai hoặc DDNS làm điểm gặp, mở đúng
UDP 51820 trên máy đó (cổng này an toàn hơn cổng dịch vụ vì chỉ trả lời gói có khóa hợp lệ). Khi đó `ufw allow in
on wg0` thay cho `tailscale0` ở mục 8, và `LLM_BASE_URL=http://10.77.0.2:11434/v1`.

---

## 8. Không mở Ollama, Postgres, Redis ra internet

Phòng thủ nhiều lớp; kiểm tra từng lớp:

1. **Địa chỉ bind** (lớp quan trọng nhất). Mọi cổng compose publish đều mặc định `127.0.0.1`
   (`PEMA_PG_BIND`, `PEMA_REDIS_BIND`, `PEMA_API_BIND`, `PEMA_FRONTEND_BIND`, `PEMA_OLLAMA_BIND`). **Docker publish cổng
   bằng quy tắc iptables riêng, đứng trước ufw: `ufw deny 5432` không chặn được cổng đã publish ra `0.0.0.0`.** Vì
   vậy không bao giờ đặt `0.0.0.0` cho các biến trên; muốn máy khác tới thì dùng IP Tailscale.
2. **Tường lửa máy chủ** (ufw), mặc định từ chối vào:

```bash
sudo ufw default deny incoming && sudo ufw default allow outgoing
sudo ufw allow in on tailscale0                       # mạng riêng Tailscale
sudo ufw allow from 172.16.0.0/12 to any port 11434 proto tcp   # container -> Ollama chạy trực tiếp (mục 6)
sudo ufw limit 22/tcp                                  # SSH, giới hạn dò mật khẩu; bỏ nếu chỉ SSH qua tailscale0
sudo ufw enable && sudo ufw status verbose
```

3. **Router phòng khám:** không port-forward cổng nào tới các máy này; tắt UPnP trên router.
4. **Cloud VN:** security group/firewall của nhà cung cấp chỉ cho phép 22 (từ IP quản trị), UDP 41641 nếu dùng
   Tailscale trực tiếp, và 443 nếu có reverse proxy cho webhook; không có luật cho 5432, 6379, 11434, 8000, 3000.
5. **Redis có mật khẩu** (`PEMA_REDIS_PASSWORD`), **Postgres dùng scram-sha-256** và `be_app`/`agent_worker` không
   phải superuser; `agent_worker` không có quyền gì trên `clinic.*` (thiết kế ở CONTRACTS-AI01 mục 5).

Kiểm tra (làm một lần sau khi dựng, và sau mỗi lần đổi mạng):

```bash
ss -ltnp | grep -E ':(5432|6379|11434|8000|3000) '     # chỉ được thấy 127.0.0.1 hoặc IP 100.x; 11434 native là 0.0.0.0 + ufw
# từ một máy KHÔNG nằm trong Tailscale (ví dụ điện thoại dùng 4G), thử IP công cộng của phòng khám/cloud:
nc -vz -w3 <IP_CONG_CONG> 5432 ; nc -vz -w3 <IP_CONG_CONG> 6379 ; nc -vz -w3 <IP_CONG_CONG> 11434   # cả ba phải timeout/refused
```

---

## 9. Hạ tầng LLM chuyển dần sang llama-server (roadmap)

Ollama dùng trước vì cài một lệnh và quản lý mô hình sẵn. Chuyển sang `llama-server` (llama.cpp) khi cần: kiểm
soát chính xác tham số (số luồng, KV cache, `--jinja` cho tool calling), chạy bản llama.cpp mới trước khi Ollama
cập nhật, hoặc bớt một lớp phần mềm. **Điều kiện chuyển:** bộ evals cho kết quả tương đương trên cả hai, đo độ
trễ và VRAM đạt, có phương án quay lại Ollama.

1. Dựng llama.cpp với CUDA (cần CUDA Toolkit: `sudo apt install nvidia-cuda-toolkit` hoặc bản của NVIDIA,
   và `build-essential cmake`):

```bash
sudo git clone https://github.com/ggml-org/llama.cpp /opt/llama.cpp && cd /opt/llama.cpp
sudo cmake -B build -DGGML_CUDA=ON && sudo cmake --build build --config Release -j"$(nproc)"
build/bin/llama-server --help | less         # đối chiếu từng cờ trong unit với bản bạn vừa build
```

2. Tải GGUF vào `/srv/llama/models/` (ví dụ `Qwen3-8B-Q6_K.gguf` từ `Qwen/Qwen3-8B-GGUF`, và một bản GGUF của bge-m3).
   Kiểm tra checksum nhà cung cấp công bố.
3. Cài hai unit mẫu `infra/ubuntu/systemd/llama-server-chat.service` (cổng 8080) và `llama-server-embed.service`
   (cổng 8081), đổi đường dẫn cho đúng, rồi `systemctl enable --now`.
4. Đổi `LLM_BASE_URL` sang `http://127.0.0.1:8080/v1` (hoặc địa chỉ Tailscale) và URL embedding sang cổng 8081.
   Hai dịch vụ tách nhau nên VRAM của bge-m3 không bị chia sẻ qua `OLLAMA_MAX_LOADED_MODELS`.
5. Lưu ý: `--ctx-size` là tổng ngữ cảnh chia cho các luồng (`--parallel`); llama-server không có `keep_alive`,
   mô hình nằm sẵn trong VRAM suốt thời gian dịch vụ chạy; không có xác thực, nên bind loopback/Tailscale giống mục 8.

Các unit này **chưa được chạy thử** trong gói F.

---

## 10. Sao lưu Postgres

Dữ liệu cần giữ: database `pema` (CRM + agent + KB), tệp `infra/.env` (đặc biệt `PEMA_SECRET_ENCRYPTION_KEY`; mất
khóa này thì token bot, thông tin Zalo, API key trong DB không đọc lại được), và volume `pema-data` nếu nơi lưu
tệp/ảnh/KB tải lên được chốt là ổ đĩa cục bộ (đang là việc mở). Mô hình Ollama tải lại được, không cần sao lưu.

```bash
sudo apt install -y age
age-keygen -o pema-backup.key            # chạy trên MỘT MÁY KHÁC; in ra "Public key: age1..."
# chép dòng public key vào /etc/pema-backup.env, cất pema-backup.key vào trình quản lý mật khẩu + bản in niêm phong
sudo install -m 0600 /dev/null /etc/pema-backup.env
echo 'PEMA_BACKUP_DIR=/mnt/backup-disk/pema' | sudo tee -a /etc/pema-backup.env
echo 'PEMA_BACKUP_AGE_RECIPIENT=age1...' | sudo tee -a /etc/pema-backup.env

sudo install -m 0644 infra/ubuntu/systemd/pema-backup.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now pema-backup.timer
sudo systemctl start pema-backup.service && journalctl -u pema-backup.service -n 20 --no-pager   # chạy thử ngay
```

`backup-postgres.sh` làm: `pg_dump -Fc` + `pg_dumpall --globals-only` (role và hash mật khẩu), kiểm tra bằng
`pg_restore --list` và sự có mặt của các schema `clinic`, `agent`, `clinic_agent`, gói vào một tệp, **mã hóa bằng
age (hoặc gpg)**, xóa tệp quá `PEMA_BACKUP_KEEP_DAYS`, rồi gọi `PEMA_BACKUP_HOOK` để chép ra nơi khác. Script từ
chối ghi bản không mã hóa, trừ khi `PEMA_BACKUP_ALLOW_PLAINTEXT=true` (chỉ để thử).

Quy tắc:
- **Ba nơi:** ổ đĩa khác máy chủ (không phải chung ổ với Docker), một máy khác (qua Tailscale/rsync), và một nơi
  ngoài phòng khám (cloud VN hoặc ổ rời mang về). Bản sao nằm cùng phòng với máy chủ không chống được cháy, trộm.
- **Diễn tập khôi phục mỗi quý** và sau mỗi lần đổi phiên bản Postgres:
  `make restore-verify FILE=/mnt/backup-disk/pema/pema-YYYYmmdd-HHMMSS.tar.age`
  (đặt `PEMA_RESTORE_AGE_IDENTITY=/đường/dẫn/pema-backup.key`; khôi phục vào CSDL tạm rồi xóa, không đụng CSDL đang chạy).
  Khôi phục thật: `restore-postgres.sh --restore <tệp>` vào `pema_restored`, kiểm tra, rồi đổi tên CSDL khi dừng api/worker.
- Điểm mất dữ liệu tối đa (RPO) của cách này là **một ngày**. Nếu chủ phòng khám cần ngắn hơn, chuyển sang lưu WAL liên tục
  (pgBackRest hoặc WAL-G) là bước kế tiếp, chưa làm.
- Thời hạn lưu bản sao là quyết định của chủ phòng khám (bản sao chứa dữ liệu bệnh nhân; Nghị định 13/2023). Mặc định 14 ngày.

---

## 11. UPS và mất điện

Mục tiêu của UPS là **tắt máy êm khi mất điện lâu**, không phải chạy xuyên mất điện: ngắt đột ngột làm hỏng
hệ thống tệp, và RTX 3060 + CPU cùng sụt nguồn là kiểu hỏng khó đoán.

- **Cỡ UPS (ước tính, đo lại bằng ổ cắm đo công suất khi PC đang chạy suy luận):** máy có RTX 3060 (170 W) và CPU
  tầm trung có thể lên khoảng 350 W đến 450 W lúc cao điểm. Chọn UPS **line-interactive sóng sin chuẩn**, công suất thực
  **từ 600 W đến 900 W (khoảng 1000 VA đến 1500 VA)**; nguồn máy tính có PFC chủ động thường không hợp UPS sóng giả sin.
  Thời gian chạy 10 đến 15 phút ở tải thật là đủ để tắt máy êm.
- **Cắm vào UPS:** máy chủ, PC GPU, modem, router và switch. Nếu chỉ cắm máy mà mạng mất thì Tailscale và Zalo cũng
  ngắt, UPS không giúp được gì.
- **Tắt tự động bằng NUT** (UPS có cổng USB):

```bash
sudo apt install -y nut
sudo nut-scanner -U                       # tìm UPS; ghi lại driver và cổng
# /etc/nut/ups.conf
#   [pema-ups]
#     driver = usbhid-ups
#     port = auto
# /etc/nut/nut.conf        MODE=standalone
# /etc/nut/upsd.users      [upsmon]  password = <MAT_KHAU>  upsmon master
# /etc/nut/upsmon.conf     MONITOR pema-ups@localhost 1 upsmon <MAT_KHAU> master
#                          SHUTDOWNCMD "/sbin/shutdown -h +0"
sudo systemctl restart nut-server nut-monitor
upsc pema-ups                             # phải in battery.charge, ups.status (OL = có điện)
```

  Thử bằng cách rút điện UPS: máy phải ghi nhận `OB` (chạy pin) và tắt khi pin còn thấp (`LB`). Hai máy dùng chung
  một UPS: máy kết nối USB làm `master`, máy kia làm `slave` qua mạng LAN (không qua internet).
- **Sau khi điện về:** BIOS đặt Power On (mục 1), Docker khởi động lại các container `unless-stopped`, Postgres tự phục
  hồi từ nhật ký ghi trước (không bao giờ đặt `fsync=off`). Sau mỗi lần mất điện, kiểm tra `make ps`,
  `journalctl -u pema-backup.service` và `curl /healthz`.
- **Cloud VN:** nhà cung cấp lo điện cho máy chủ; bạn cần snapshot ổ đĩa cộng sao lưu ở vùng khác (mục 10). PC GPU
  tại phòng khám vẫn cần UPS.

---

## 12. Hai kịch bản vị trí server

| | Server tại phòng khám | Cloud Việt Nam |
|---|---|---|
| Dữ liệu bệnh nhân | Nằm trong phòng khám | Nằm tại trung tâm dữ liệu Việt Nam; chủ phòng khám ký điều khoản xử lý dữ liệu với nhà cung cấp |
| Webhook Zalo | Phải có đường vào (Funnel hoặc dùng polling) | Dễ: IP công khai + reverse proxy HTTPS chỉ cho `/api/v1/webhooks/*` |
| Điện, mạng | UPS (mục 11), một đường internet | Nhà cung cấp lo |
| Sao lưu | Ổ khác + máy khác + một nơi ngoài phòng khám | Snapshot + bản mã hóa về phòng khám |
| GPU | Cùng phòng, độ trễ thấp | PC GPU vẫn ở phòng khám, nối Tailscale (thêm vài chục ms, không ảnh hưởng nhắn tin) |
| Chi phí | Mua máy chủ + UPS | Thuê VPS hàng tháng |
| Việc phải làm thêm | Chống trộm/ cháy cho máy | Khóa SSH, security group, giám sát |

Cả hai dùng cùng `docker-compose.yml` và cùng `.env`; chỉ khác địa chỉ bind và nơi đặt GPU. Chọn xong, ghi quyết định vào
`SPEC`/`ARCH-AI01` (gói F làm sau cùng).

---

## 13. Danh sách kiểm tra bàn giao

- [ ] `nvidia-smi` thấy RTX 3060; `ollama ps` báo 100% GPU khi đang trả lời.
- [ ] `make ps`: postgres, redis, api khỏe; `migrate` đã `Exited (0)`.
- [ ] `curl http://127.0.0.1:8000/healthz` trả `{"status":"ok",...}`.
- [ ] `ss -ltnp` không có cổng 5432/6379 trên `0.0.0.0`; thử từ mạng ngoài thất bại (mục 8).
- [ ] `infra/.env` quyền `600`, không nằm trong git (`git status` sạch); khóa mã hóa có bản sao ngoại tuyến.
- [ ] Một bản sao lưu đã chạy và **một lần `restore-verify` thành công**.
- [ ] UPS: rút điện thử, máy tắt êm, bật lại tự động.
- [ ] Tailscale: ACL đúng, nhân viên vào được dashboard, không vào được 5432/6379/11434.
