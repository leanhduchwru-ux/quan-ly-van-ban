# Hệ Thống Quản Lý Văn Bản Điều Hành (Streamlit)

Dự án này là phiên bản viết hoàn toàn bằng Python (100%), bao gồm:
1. **Frontend**: Streamlit App (`app.py`) tạo giao diện bảng điều khiển trực quan.
2. **Crawler**: Playwright Python (`crawler.py`) tự động lấy dữ liệu.
3. **Database**: PostgreSQL (qua SQLAlchemy).

## Hướng dẫn Triển khai Lên GitHub và Streamlit Cloud

### Bước 1: Khởi tạo Cơ sở dữ liệu Cloud (Miễn phí)
Vì Streamlit Community Cloud không cấp sẵn Database, bạn cần tạo một Database PostgreSQL trên Cloud.
Chúng tôi khuyến nghị sử dụng **[Neon.tech](https://neon.tech/)** hoặc **[Supabase](https://supabase.com/)**:
1. Đăng ký tài khoản Neon.tech bằng GitHub.
2. Tạo một Project mới (chọn PostgreSQL).
3. Copy chuỗi kết nối (Connection String) có dạng: `postgresql://username:password@ep-lively-star-1234.region.aws.neon.tech/dbname`.

### Bước 2: Chuẩn bị mã nguồn trên Local
1. Cài đặt các thư viện:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```
2. Tạo thư mục `.streamlit` trong dự án và tạo file `secrets.toml`:
   ```toml
   # .streamlit/secrets.toml
   DATABASE_URL = "chuỗi_kết_nối_neon_tech_của_bạn_ở_đây"
   VPDT_USERNAME = "user1"
   VPDT_PASSWORD = "pwd"
   HPNET_USERNAME = "user2"
   HPNET_PASSWORD = "pwd"
   ```
3. Chạy thử trên máy cá nhân:
   ```bash
   streamlit run app.py
   ```

### Bước 3: Đẩy mã nguồn lên GitHub (Push to GitHub)
1. Khởi tạo Git repo và push lên GitHub (Không push thư mục `.streamlit/secrets.toml` lên mạng để bảo mật):
   ```bash
   git init
   echo ".streamlit/secrets.toml" > .gitignore
   git add .
   git commit -m "Initial commit Streamlit App"
   git branch -M main
   git remote add origin https://github.com/Taikhoancuaban/quan_ly_van_ban_streamlit.git
   git push -u origin main
   ```

### Bước 4: Triển khai lên Streamlit Community Cloud
1. Truy cập [share.streamlit.io](https://share.streamlit.io/) và đăng nhập bằng tài khoản GitHub.
2. Nhấn nút **New App**.
3. Chọn Repository bạn vừa push lên.
4. Ở mục **Main file path**, gõ `app.py`.
5. **QUAN TRỌNG:** Nhấn vào **Advanced Settings** (Cài đặt nâng cao), tìm ô "Secrets" và dán nội dung y hệt như file `secrets.toml` của bạn (bao gồm `DATABASE_URL` và thông tin đăng nhập).
6. Nhấn **Deploy!**

Hệ thống của bạn sẽ sẵn sàng hoạt động trên nền mạng trong vài phút!
