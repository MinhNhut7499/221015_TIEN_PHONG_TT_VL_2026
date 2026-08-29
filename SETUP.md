# Hướng dẫn cài đặt dự án Architecture-AI trên máy mới

Tài liệu này hướng dẫn cài đặt và khởi chạy **toàn bộ hệ thống** (Backend FastAPI + Frontend React) trên một máy hoàn toàn mới, từ bước tạo môi trường ảo đến khi server và frontend chạy được như cách dự án này đang hoạt động.

> **Lưu ý:** Repo **không** kèm theo môi trường ảo (`.venv/`), `node_modules/`, hay file `.env`. Bạn phải tự tạo lại theo các bước bên dưới.

---

## 1. Tổng quan kiến trúc

| Thành phần | Công nghệ | Cổng mặc định |
|---|---|---|
| Backend API | Python 3.10 + FastAPI + uvicorn | `8000` |
| Frontend | React 18 + Vite | `5173` |
| Database | Microsoft SQL Server (qua SQLAlchemy async + ODBC) | `1433` |
| Pipeline nhận dạng | LLM đa nhà cung cấp (Gemini / OpenAI / DeepSeek / xAI Grok) | — |

Frontend gọi backend qua **proxy của Vite** (`/auth`, `/analyze`, `/admin`, `/upload`, `/content`, `/billing`), nên khi dev chỉ cần chạy 2 tiến trình: backend ở `8000`, frontend ở `5173`.

---

## 2. Yêu cầu phần mềm (cài trước)

Cài các phần mềm sau trên máy mới:

1. **Python 3.10** (bắt buộc đúng 3.10 — đây là ràng buộc cứng của dự án).
   - Kiểm tra: `python --version` → phải in `Python 3.10.x`.
   - **Chưa có Python 3.10? Xem mục [2.1 Cài đặt Python 3.10](#21-cài-đặt-python-310-nếu-máy-chưa-có) bên dưới.**
2. **Node.js 18 trở lên** (kèm `npm`) — cho frontend.
   - Kiểm tra: `node --version` và `npm --version`.
3. **Git** — để clone mã nguồn.
4. **Microsoft SQL Server** (2019/2022 hoặc SQL Server Express) — cơ sở dữ liệu.
5. **ODBC Driver cho SQL Server** — bắt buộc để `pyodbc`/`aioodbc` kết nối được:
   - Tải **"ODBC Driver 17 for SQL Server"** (hoặc 18) từ Microsoft.
   - Tên driver này phải khớp với biến `DB_ODBC_DRIVER` trong `.env`.

> **Không có DB cũng chạy được phần nào?** Backend vẫn khởi động được nếu DB chưa kết nối (cảnh báo, không sập), nhưng các tính năng lưu lịch sử / admin / đăng nhập sẽ lỗi. Để chạy đầy đủ, hãy chuẩn bị SQL Server.

### 2.1. Cài đặt Python 3.10 (nếu máy chưa có)

Dự án yêu cầu **đúng Python 3.10** (không dùng 3.11/3.12/3.13 vì một số thư viện được pin theo 3.10). Trước hết kiểm tra xem máy đã có chưa:

**Windows:**
```powershell
py -0p          # liệt kê mọi bản Python đã cài kèm đường dẫn
py -3.10 --version
```
**Linux / macOS:**
```bash
python3.10 --version
```

Nếu lệnh báo lỗi/không tìm thấy → cài theo hệ điều hành bên dưới. **Không cần gỡ** các bản Python khác đang có; 3.10 sẽ cài song song và ta gọi nó qua launcher (`py -3.10`) hoặc đường dẫn riêng.

#### Windows

**Cách A — Cài thẳng trong terminal bằng `winget` (khuyến nghị, nhanh nhất):**

`winget` là trình quản lý gói có sẵn trên Windows 10/11 — không cần mở trình duyệt hay tải file `.exe` thủ công. Mở PowerShell và chạy:
```powershell
winget install Python.Python.3.10
```
- winget tự tải bản 3.10.x mới nhất, cài kèm **py launcher** và tự thêm vào PATH.
- Cài xong, **đóng và mở lại PowerShell** (để PATH cập nhật) rồi kiểm tra:
  ```powershell
  py -3.10 --version      # Python 3.10.x
  ```
- Nếu báo `winget` không tồn tại: cập nhật **App Installer** từ Microsoft Store, hoặc dùng Cách B.

**Cách B — Trình cài đặt chính thức (nếu không dùng được winget):**
1. Tải Python **3.10.x** (ví dụ 3.10.11) — file *Windows installer (64-bit)* tại:
   `https://www.python.org/downloads/release/python-31011/`
   (hoặc `https://www.python.org/downloads/` → mục *Looking for a specific release* → chọn 3.10.x).
2. Chạy file `.exe`. Ở màn hình đầu tiên **tích vào ô `Add python.exe to PATH`**, rồi bấm **Install Now**.
3. Giữ tùy chọn cài **py launcher** (mặc định có) để dùng được `py -3.10`.
4. Mở PowerShell **mới** và kiểm tra `py -3.10 --version`.

#### macOS

**Cách A — Homebrew (khuyến nghị):**
```bash
brew install python@3.10
# Sau khi cài, đường dẫn thường là:
/usr/local/bin/python3.10 --version      # Intel
/opt/homebrew/bin/python3.10 --version   # Apple Silicon
```

**Cách B — pyenv (quản lý nhiều phiên bản):**
```bash
brew install pyenv
pyenv install 3.10.14
pyenv local 3.10.14     # ghim 3.10 cho thư mục dự án
python --version
```

#### Linux (Ubuntu/Debian)

**Cách A — deadsnakes PPA (khuyến nghị, có sẵn gói 3.10):**
```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3.10-dev
python3.10 --version
```
> Quan trọng: phải cài kèm **`python3.10-venv`** thì lệnh tạo môi trường ảo ở mục 4.1 mới chạy được.

**Cách B — pyenv (mọi distro):**
```bash
curl https://pyenv.run | bash
# Thêm pyenv vào shell theo hướng dẫn in ra, mở terminal mới, rồi:
pyenv install 3.10.14
pyenv local 3.10.14
python --version
```

#### Sau khi cài xong

Ở các bước tiếp theo, **luôn dùng đúng bản 3.10** khi tạo môi trường ảo:
- Windows: `py -3.10 -m venv .venv`
- Linux/macOS: `python3.10 -m venv .venv` (hoặc `python` nếu đã `pyenv local 3.10.x`)

Một khi đã kích hoạt môi trường ảo (`.venv`), bên trong nó lệnh `python` luôn là 3.10 — không cần gõ `py -3.10` nữa.

---

## 3. Lấy mã nguồn

```bash
git clone <URL_REPO> Architecture-AI
cd Architecture-AI
```

---

## 4. Cài đặt Backend

### 4.1. Tạo môi trường ảo (Python 3.10)

**Windows (PowerShell):**
```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> Nếu PowerShell chặn script, chạy một lần:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

**Windows (CMD):**
```cmd
py -3.10 -m venv .venv
.venv\Scripts\activate.bat
```

**Linux / macOS:**
```bash
python3.10 -m venv .venv
source .venv/bin/activate
```

Sau khi kích hoạt, dấu nhắc lệnh sẽ có tiền tố `(.venv)`.

### 4.2. Cài thư viện Python

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Lệnh này cài toàn bộ thư viện backend, gồm:
- **Web:** `fastapi`, `uvicorn[standard]`
- **Cấu hình:** `pydantic`, `pydantic-settings`, `python-dotenv`
- **Bảo mật:** `python-jose[cryptography]`, `bcrypt`, `cryptography`
- **HTTP / Email / Upload:** `httpx`, `aiosmtplib`, `python-multipart`
- **Database:** `sqlalchemy[asyncio]`, `aioodbc`, `pyodbc`
- **LLM SDK:** `google-genai`, `openai`, `pillow`
- **Khác:** `scipy` (đo đồng thuận hội đồng), `pytest`, `pytest-asyncio`

### 4.3. Tạo các thư mục cần thiết

Backend ghi file upload vào các thư mục này (tạo sẵn để tránh lỗi):

**Windows (PowerShell):**
```powershell
New-Item -ItemType Directory -Force utils\upload_temp, utils\download, utils\data_vector | Out-Null
```

**Linux / macOS:**
```bash
mkdir -p utils/upload_temp utils/download utils/data_vector
```

### 4.4. Tạo file `.env` cho backend

Tạo file `.env` ở **thư mục gốc dự án** (cùng cấp với `run_api.py`). Dưới đây là cấu hình tối thiểu để khởi động + chạy được pipeline. Điền giá trị thật của bạn vào các chỗ `...`.

```dotenv
# ── Ứng dụng ───────────────────────────────────────────────
APP_ENV=development
DEBUG=true
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
ADMIN_EMAILS=email_admin_cua_ban@gmail.com

# ── Bảo mật / JWT (BẮT BUỘC) ──────────────────────────────
# Sinh khóa: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=DAN_KHOA_NGAU_NHIEN_VAO_DAY

# ── Google OAuth (BẮT BUỘC để đăng nhập) ─────────────────
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

# ── Database SQL Server ──────────────────────────────────
DB_HOST=localhost
DB_PORT=1433
DB_NAME=architecture_ai
DB_USER=sa
DB_PASSWORD=MatKhauSQL_cua_ban
DB_ENCRYPT=true
DB_TRUST_SERVER_CERT=true
DB_ODBC_DRIVER=ODBC Driver 17 for SQL Server

# ── LLM Pipeline (điền key của các nhà cung cấp bạn dùng) ──
GEMINI_API_KEY=...
OPENAI_API_KEY=...
DEEPSEEK_API_KEY=...
XAI_API_KEY=...

# ── Frontend base URL (dùng cho link email) ──────────────
FRONTEND_BASE_URL=http://localhost:5173
```

**Ghi chú quan trọng về `.env`:**

- `SECRET_KEY` **bắt buộc** và không được để trống / không được là `changeme` — server sẽ từ chối khởi động nếu thiếu.
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` lấy từ **Google Cloud Console → APIs & Services → Credentials**. Nhớ thêm `http://localhost:8000/auth/google/callback` vào **Authorized redirect URIs**.
- Các key LLM: chỉ cần điền nhà cung cấp bạn thực sự dùng. Pipeline mặc định dùng Gemini (trích đặc trưng) + OpenAI (trọng tài) + Grok (giám khảo) + DeepSeek (dịch). Thiếu key nào thì luồng dùng key đó sẽ lỗi/giảm cấp.
- `DB_TRUST_SERVER_CERT=true` nên bật khi dùng SQL Server local (chứng chỉ self-signed).
- Các biến khác (billing, SMTP, API-key CMS, model name…) đã có **giá trị mặc định** trong `app/config.py`, **không bắt buộc** điền. Chỉ thêm khi cần bật tính năng tương ứng (ví dụ `BILLING_ENABLED=true`).

> Mặc định model trong `config.py` có thể trỏ tới tên model mới; nếu một model báo lỗi "not found", hãy override trong `.env`, ví dụ:
> `GEMINI_MODEL=gemini-2.5-flash`, `OPENAI_MODEL=gpt-4o`, `DEEPSEEK_MODEL=deepseek-chat`.

### 4.5. Chuẩn bị cơ sở dữ liệu

1. Tạo một database trống tên khớp với `DB_NAME` (mặc định `architecture_ai`):
   ```sql
   CREATE DATABASE architecture_ai;
   ```
2. Chạy script DDL tạo bảng (nếu có file schema bạn dùng). Các script bổ sung tính năng nằm trong `docs/sql/`:
   - `docs/sql/billing_v2_apply.sql` — bảng billing/token (chỉ cần nếu bật `BILLING_ENABLED`)
   - `docs/sql/api_keys_v1.sql`, `docs/sql/cms_v1.sql`, `docs/sql/login_sessions_v1.sql` — tính năng quản lý API key, CMS, đăng nhập mobile (tùy chọn)
3. Cột phụ cần thiết cho lưu chi tiết phân tích (nếu schema gốc chưa có):
   ```sql
   ALTER TABLE BuildingStyleResults ADD DetailJson NVARCHAR(MAX) NULL;
   ```

> Khi backend khởi động, nó tự **seed** role (`user`/`admin`) và danh sách agent vào DB (idempotent), nên bạn không cần seed thủ công các bảng đó.

### 4.6. Khởi động Backend

```bash
python run_api.py
```

- Server chạy tại `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

Khi `DEBUG=true`, hot-reload được bật. Bạn cũng có thể chạy qua `bash start.sh` (Linux/macOS) — script này tự kiểm tra Python, cài deps và tạo thư mục upload.

---

## 5. Cài đặt Frontend

Mở một **terminal mới** (giữ backend đang chạy).

### 5.1. Cài thư viện Node

```bash
cd frontend
npm install
```

Lệnh này tạo `node_modules/` và cài: React 18, react-router-dom, `@react-oauth/google`, `lucide-react`, `recharts`, Vite, Tailwind CSS, PostCSS, Autoprefixer.

### 5.2. Tạo file `frontend/.env`

Frontend cần Google Client ID để hiện nút đăng nhập Google. Tạo file `frontend/.env`:

```dotenv
VITE_GOOGLE_CLIENT_ID=<GOOGLE_CLIENT_ID_giong_voi_backend>.apps.googleusercontent.com
```

> Giá trị này phải là **cùng một Google OAuth Client** với `GOOGLE_CLIENT_ID` ở backend.

### 5.3. Khởi động Frontend (chế độ dev)

```bash
npm run dev
```

- Frontend chạy tại `http://localhost:5173`
- Proxy đã được cấu hình sẵn trong `frontend/vite.config.js` — mọi gọi API tới `/auth`, `/analyze`, `/admin`, `/upload`, `/content`, `/billing` (trừ route SPA `/billing/result`) sẽ tự chuyển sang backend `http://localhost:8000`.

### 5.4. (Tùy chọn) Build bản production của frontend

```bash
npm run build      # tạo thư mục dist/
npm run preview    # xem thử bản build
```

---

## 6. Kiểm tra hệ thống chạy đúng

1. Mở trình duyệt: `http://localhost:5173` → thấy trang Landing.
2. Bấm đăng nhập → đăng nhập Google → vào trang người dùng.
3. Tải một ảnh kiến trúc lên → bấm phân tích → nhận kết quả phong cách + giải thích.
4. (Tùy chọn) Chạy test backend để chắc chắn môi trường ổn:
   ```bash
   pytest test/ -v
   ```

---

## 7. Thứ tự khởi động hằng ngày (tóm tắt)

**Terminal 1 — Backend:**
```bash
cd Architecture-AI
.\.venv\Scripts\Activate.ps1      # Windows; hoặc: source .venv/bin/activate
python run_api.py
```

**Terminal 2 — Frontend:**
```bash
cd Architecture-AI/frontend
npm run dev
```

Truy cập `http://localhost:5173`.

---

## 8. Khắc phục sự cố thường gặp

| Triệu chứng | Nguyên nhân & cách xử lý |
|---|---|
| `SECRET_KEY must be set...` khi khởi động | Chưa điền `SECRET_KEY` trong `.env`. Sinh khóa và dán vào. |
| Lỗi ODBC / `Data source name not found` | Chưa cài ODBC Driver, hoặc `DB_ODBC_DRIVER` không khớp tên driver đã cài (kiểm tra trong "ODBC Data Sources" trên Windows). |
| Kết nối DB lỗi SSL/cert | Đặt `DB_TRUST_SERVER_CERT=true` (SQL Server local self-signed). |
| `py -3.10` không nhận | Python 3.10 chưa cài hoặc chưa vào PATH. Cài đúng 3.10. |
| LLM trả lỗi "model not found" | Override tên model trong `.env` (xem mục 4.4). |
| Frontend không gọi được API | Backend chưa chạy ở cổng 8000, hoặc đang chạy ở cổng khác (proxy Vite trỏ cố định tới 8000). |
| Nút đăng nhập Google không hiện | Thiếu `frontend/.env` với `VITE_GOOGLE_CLIENT_ID`. |
| `pip install` lỗi build `pyodbc` | Trên Windows cần "Build Tools for Visual C++" hoặc dùng wheel có sẵn; đảm bảo đã cài ODBC Driver. |

---

## 9. Những thứ KHÔNG có trong repo (phải tự tạo)

- `.venv/` — môi trường ảo Python (mục 4.1)
- `node_modules/` — thư viện Node (mục 5.1)
- `.env` (gốc) và `frontend/.env` — file cấu hình bí mật (mục 4.4 & 5.2)
- Database thật + các bảng (mục 4.5)
- Các API key của bạn (Google OAuth, Gemini, OpenAI, DeepSeek, xAI)
