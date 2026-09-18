# SEZOY - Kho bản cài & Lab test

[Tiếng Anh - English](README.md) | **Tiếng Việt**

Repo này chứa các bản cài SEZOY cùng profile VPN làm sẵn cho lab test công cộng.
Tài liệu đầy đủ nằm ở **https://tekdt.xyz** (trang Docs).

> SEZOY là nền tảng triển khai Windows: tạo USB boot hoặc máy chủ boot PXE/HTTP,
> quản lý ISO Windows, nạp driver, cài đặt tự động không chạm tay, và giám sát
> mọi máy khách trên một dashboard web duy nhất.

---

## 1. Trải nghiệm SEZOY trong 10 phút - không cần cài đặt (lab test công cộng)

Máy chủ SEZOY công cộng (`192.168.251.1`) chạy 24/24 kèm VPN Hub mở cho tester.
Bạn (máy C) joined cùng mạng Layer-2 qua VPN, bridge máy ảo thẳng vào card VPN,
và máy ảo của bạn sẽ boot mạng từ server ở xa **như đang cắm cùng switch**.
Bạn cũng có thể mở dashboard dùng chung qua `https://192.168.251.1:5893`
(nếu được cấp quyền).

### Chuẩn bị

- **SoftEther VPN Client** (miễn phí) trên máy bạn.
- **VMware Workstation Pro** (hoặc phần mềm VM nào bridge được vào đúng card mạng).
- Một máy ảo test: firmware **UEFI**, RAM ≥ 4 GB, ổ ≥ 40 GB, **Network Boot / PXE đầu tiên** trong thứ tự boot.

### Bước 1 - Nối VPN (import profile làm sẵn)

1. Cài **SoftEther VPN Client**, mở **VPN Client Manager**.
2. Tạo card ảo một lần: **New Virtual Network Adapter** → đặt tên `SEZOY-VPN` → Enable.
3. Import profile trong repo này: **New VPN Connection Setting → Import VPN Connection Setting**,
   chọn [`SEZOY-VPN-Connection.vpn`](SEZOY-VPN-Connection.vpn) - mọi trường tự điền:
   - Host: `sezoyhost.vpnazure.net`, cổng `443`, hub `SEZOY.HUB`, user `tester00` / `tester99`.
4. Double-click kết nối → **Connected**.
   Lỗi `1 / 2 / 691` nghĩa là sai hub/user/pass hoặc cổng 443 bị chặn - kiểm tra lại.

> Cấu hình tay cũng được (giá trị như trên; mật khẩu hiện tại đăng trong release
> notes / topic cộng đồng - thông tin truy cập có thể xoay vòng định kỳ).

### Bước 2 - Bridge CỨNG máy ảo vào card VPN

> ⚠️ **TUYỆT ĐỐI không để Bridged ở Automatic.** Máy ảo sẽ xin nhầm IP từ router nhà bạn.

1. VMware **Edit → Virtual Network Editor** (Run as Administrator).
2. Chọn VMnet chưa dùng (ví dụ **VMnet2**), kiểu **Bridged**, **Bridged to:** đúng
   card ảo SoftEther - **không** chọn Automatic. Apply.
3. Cài đặt VM → Network Adapter → **Custom: VMnet2**.

### Bước 3 - Boot và test

1. Bật máy → PXE → máy ảo nhận IP dạng `192.168.251.x` → menu boot SEZOY hiện ra
   (qua Internet chờ 5–15 s).
2. Chọn ISO Windows/Linux + mẫu cài dành cho tester → triển khai.
3. **Phép lịch sự trong lab** (dải IP chỉ ~50 địa chỉ, một server cho mọi người):
   - **Mỗi người 1 máy ảo**, boot nhẹ trước (ISO chẩn đoán phần cứng, Linux live),
     rồi hãy cài Windows full (tải hàng GB qua VPN nên chậm là bình thường).
   - Tắt máy ảo gọn gàng, rồi **Disconnect VPN** để nhả chỗ.
   - Không dừng Boot Server / không thoát app trên máy chủ.
   - Phiên treo quá ~5 phút không thao tác sẽ hết hạn - boot lại từ đầu.
4. Báo kết quả: cấu hình VM (UEFI/Legacy, RAM), ISO đã boot, SecureBoot ON/OFF,
   thời gian boot, ảnh chụp + MAC của VM khi lỗi.

| Triệu chứng | Cách xử lý nhanh |
|---|---|
| Boot thẳng vào BIOS, không menu | Bridge sai card - gán cứng lại vào card VPN |
| Có IP nhưng timeout file boot | Mạng VPN yếu/firewall - thử lại, tắt firewall test |
| Menu lên nhưng tải chậm | Jitter đường truyền là bình thường - đừng reboot liên tục |
| VM nhận IP nhà bạn (`192.168.1.x`) | VMnet vẫn Automatic - gán cứng lại rồi reboot VM |

---

## 2. Tải & cài SEZOY của riêng bạn

Lấy bản cài ở trang [**Releases**](releases) của repo này:

| File | Kênh | Khi nào dùng |
|---|---|---|
| `SEZOY_beta.msi` | Beta (`vX.X.X.X-beta`) | Bản hiện hành - tính năng mới có trước |
| `SEZOY.msi` | Stable (`vX.X.X.X`) | Bản ổn định chính thức (khi phát hành) |

- Cài **per-user** (không cần quyền admin để cài đặt), sau đó **chạy SEZOY bằng
  quyền administrator** - vì nó điều khiển driver mạng/VPN và boot server.
- **Lần mở đầu tiên cần Internet** (kích hoạt một lần + tải công cụ);
  từ lần sau chạy offline hoàn toàn.
- Giấy phép FREE tích hợp sẵn - mở app là chạy ngay, không cần xin key.

---

## 3. Bắt đầu trong 5 phút (`https://localhost:5893`)

### Bước 1 - USB drive hoặc Boot Server

| Chế độ | Tác dụng |
|---|---|
| **USB Drive** | Tạo USB/ổ boot cài Windows trực tiếp từng máy (GPT/MBR, exFAT/NTFS/FAT32, theme boot, tự chọn ổ). |
| **BOOT Server** | Dựng máy chủ PXE/HTTP để máy khách boot vào môi trường cài (ProxyDHCP dùng chung router - khuyến nghị, Full DHCP cho mạng cô lập). |

Khi Boot Server đang chạy, cấu hình bị khóa - dừng server để chỉnh tiếp.

### Bước 2 - ISO (3 tab) + Chế độ triển khai

- **ISO List**: dùng ISO có sẵn (thêm/xóa, giữ edition cần thiết, bật ISO chẩn đoán phần cứng).
- **Selenium Download**: tải ISO Microsoft chính chủ (Edition → Language → Architecture), ổn định nhất.
- **Fido Script**: tải nhanh nhiều phiên bản - đừng nện liên tục kẻo Microsoft chặn tạm thời.

Khi chọn edition cho ISO Windows, thẻ **Deployment Modes** hiện ra:

| Chế độ | Chuyện gì xảy ra | Nên dùng khi… |
|---|---|---|
| **SEZOY (Panther Drop-in)** | Tự chuẩn bị ổ disk + cài tự động hoàn toàn bằng file trả lời | Cài hàng loạt, không chạm tay, đã cấu hình sẵn trong Unattend Generator |
| **Microsoft Setup (Standard Setup)** | Bàn giao cho trình Setup gốc; profile/preset quyết định phần còn lại | Muốn giữ trải nghiệm gốc của Microsoft hoặc kiểm soát thủ công |

> ⚠️ **USB = mỗi ISO đúng 1 chế độ** (nút radio). **Boot Server = được tick
> nhiều** - profile từng máy quyết định mode nào khi boot.

### Bước 3 - Ứng dụng sau cài, rồi Create

Duyệt catalog WinGet, tick ứng dụng cho từng máy sau setup
(gói đã chọn áp dụng cho preset mặc định; preset tùy chỉnh có danh sách riêng),
rồi nhấn **Create/Start** và xem tiến trình trực tiếp trên dashboard.

---

## 4. Luôn mới - `Settings → Update`

Mục **Update** (ngay trên About) tự kiểm tra mỗi khi mở nếu có mạng,
hoặc check tay như Firefox/Chrome:

- Tab **Beta** đang hoạt động; **Stable** xám khóa chờ bản chính thức.
- Lúc kiểm tra hiện dải marquee; lúc tải hiện **% thật + dung lượng**
  (nhiều link dự phòng, xác thực hash).
- Mặc định (đều bật): **tự cài sau khi tải xong**, lưu vào **thư mục tạm Windows**,
  **xóa file `.msi`** sau khi cài. Cài im lặng - app tự đóng để hoàn tất.

---

## 5. Giấy phép & hỗ trợ trực tiếp

- **Mã fingerprint** (`Settings → About`) định danh duy nhất máy bạn -
  gửi cho TekDT để nâng PRO/ENTERPRISE. ENTERPRISE mở toàn bộ mục Settings;
  Ngôn ngữ, Drivers, Update và About dùng được ở mọi hạng.
- **Chat trực tiếp**: máy có mạng thì bong bóng chat hiện trong Settings,
  tin nhắn tự kèm fingerprint + phiên bản + hạng giấy phép. Mất mạng bong bóng
  tự ẩn - không bao giờ xếp hàng chờ.

---

## 6. FAQ nhanh

- **Offline được không?** Được từ lần mở thứ 2 (lần đầu cần mạng để tải công cụ + kích hoạt).
- **Có sửa ISO của tôi không?** Không - ISO nguyên bản; edition không tick chỉ bị lược khỏi thiết bị tạo ra.
- **SecureBoot?** Không cần tắt. ISO Linux không chữ ký hợp lệ sẽ hiện màn hình lý do thay vì treo.
- **Boot WiFi?** Cần card phát hotspot trên server + máy khách hỗ trợ HTTP Boot; boot dây luôn chạy.
- **WinPE không thấy ổ?** Tải gói driver MassStorage trước (`Settings → Drivers`).

Hướng dẫn chi tiết, kho driver và tham chiếu Unattend Generator nằm ở trang Docs.
