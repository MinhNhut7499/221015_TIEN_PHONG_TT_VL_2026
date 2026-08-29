# Quy trình chấm điểm baseline — dùng chung 1 thang đo cho Gemini, ChatGPT và Hệ thống

Tài liệu này chuẩn hóa cách đo baseline 2 model nền (Gemini, ChatGPT) **chấm thủ công** sao cho
**khớp đúng cách hệ thống tự chấm điểm**. Mục tiêu: cả 3 (Gemini, ChatGPT, Hệ thống) cùng một
thang đo **top-1 theo KB id**, để con số so sánh được với nhau.

> Bảng 106 tên ở Mục 5 được sinh trực tiếp từ `chatbot/knowledge/styles.json`. Khi KB đổi, hãy
> regenerate (xem Mục 6) thay vì sửa tay.

---

## 1. Thang đo của hệ thống (áp dụng y hệt khi chấm tay)

Hệ thống **không** so chuỗi thô. Một dự đoán tính **đúng (top-1 hit)** theo
`scripts/evaluate_openvocab.py` (`_score`) + `StyleKbService.match` (`chatbot/services/style_kb_service.py`):

1. **Chuẩn hóa tên** (`_normalise`): hạ chữ thường → bỏ từ nhiễu (`architecture`, `style`,
   `kiến trúc`, `phong cách`…) → bỏ dấu câu `-_/,.()` → gộp khoảng trắng.
2. **Khớp về KB id**: exact theo `name`/`alias` → nếu trượt thì **fuzzy difflib** (cutoff `0.82`).
   Không khớp → coi như không có id.
3. **Top-1 hit** = `KB_id(dự đoán) == KB_id(đáp án)`. Synonym được gộp ở bước này nhờ cột `alias`
   trong KB (vd `Chinese` ≡ `Traditional Chinese`; `Neo-Gothic` ≡ `Gothic Revival`).

**Khi chấm tay:** lấy **tên chính** model trả về → tra bảng Mục 5 → nếu rơi vào **cùng một dòng KB**
với đáp án `main_style` của ảnh ⇒ đánh **1**, ngược lại **0**.

Quy ước giữ nhất quán với harness:
- Chỉ chấm **tên chính (top-1)**. Phong cách phụ model nêu thêm **không** tính cho top-1.
- Ảnh nào model lỗi / không cho được tên → đánh dấu **ERROR**, **loại khỏi mẫu** (không đếm là sai).
- **Không "mớm" 106 tên** cho model (free naming) — giữ tính công bằng của baseline.

---

## 2. Prompt chuẩn (dùng cái này)

Dùng **CÙNG một prompt** cho cả Gemini và ChatGPT, trên toàn bộ ảnh, để hai cột baseline so sánh được.

```
Bạn là một chuyên gia lịch sử kiến trúc đang xem MỘT bức ảnh công trình.
Hãy gọi tên phong cách kiến trúc CHÍNH của công trình, theo phản xạ chuyên gia ở cái nhìn đầu tiên.

QUY TẮC:
- Chỉ xét KHỐI THÂN/tổng thể công trình, KHÔNG bám vào một chi tiết trang trí lẻ.
- Dùng TÊN TIẾNG ANH phổ thông của phong cách (ví dụ: Gothic, Baroque, Byzantine, Mughal, Art Deco, Romanesque).
- KHÔNG suy diễn sâu thành một tiểu kỳ hẹp hay biến thể "Revival" trừ khi ảnh rõ ràng đòi hỏi — ưu tiên tên phong cách chuẩn (canonical).
- Cho ĐÚNG MỘT phong cách chính, rồi tối đa 2 phương án thay thế (xếp khả năng giảm dần).
- KHÔNG giải thích, KHÔNG mô tả dài dòng.

CHỈ trả về đúng một dòng JSON, không thêm chữ nào khác:
{"main_style": "<Tên tiếng Anh>", "alternates": ["<phương án 1>", "<phương án 2>"]}
```

**Vì sao prompt này khớp thang đo:**
- Ép **một tên chính** ở key `main_style` → chấm top-1 hết mơ hồ.
- **Tên tiếng Anh chuẩn** → khớp thẳng `alias` (vốn tiếng Anh) trong KB; nếu model thêm
  "kiến trúc/phong cách" thì `_normalise` đã tự bỏ.
- **Không over-refine sang Revival** → tránh lệch oan giữa `Gothic` và `Gothic Revival` (2 id khác nhau).
- **Cấm mô tả dài** → dập trực tiếp tình trạng "trả lan man".

---

## 3. (Tùy chọn) prompt rút gọn — chỉ cần top-1

```
Bạn là chuyên gia lịch sử kiến trúc. Xét KHỐI THÂN chính của công trình trong ảnh,
gọi tên phong cách kiến trúc CHÍNH bằng TÊN TIẾNG ANH phổ thông (vd: Gothic, Baroque, Mughal).
Không over-refine sang biến thể "Revival" trừ khi rõ ràng. Không giải thích.
Chỉ trả về đúng một dòng: PHONG CÁCH: <Tên tiếng Anh>
```

---

## 4. Quy trình chấm tay (điền `ThucNghiem.xlsx`)

Với mỗi ảnh (100 prompt × 2 nguồn = 200 ảnh):

1. Mở ảnh trên web Gemini / ChatGPT, dán **prompt Mục 2**.
2. Đọc `main_style` model trả về.
3. Tra `main_style` ở **bảng Mục 5** (khớp `Tên` HOẶC một `Alias` bất kỳ của cùng dòng).
   - Nếu khớp tên gần đúng (sai chính tả nhỏ) vẫn tính — hệ thống cũng dùng fuzzy 0.82.
4. So dòng KB vừa tra với đáp án `main_style` của ảnh (lấy từ `docs/image_gen_ground_truth.csv`):
   - **Cùng một dòng KB ⇒ 1** (đúng).
   - **Khác dòng ⇒ 0** (sai).
   - **Model không cho tên / lỗi ⇒ ERROR**, để trống/loại, **không** đếm là 0.
5. Ghi 1/0 vào đúng cột ("…CHAT" cho ảnh ChatGPT-sinh, "…GEMINI" cho ảnh Gemini-sinh).

> Cặp synonym hay gặp khi chấm: `Traditional Chinese` ≡ `Chinese`/`Chinese Imperial`;
> `Gothic Revival` ≡ `Neo-Gothic`/`Victorian Gothic`;
> `International Style/Modernism` ≡ `Modernism`/`Modern Movement`/`International Style`;
> `Byzantine` ≡ `Byzantine Architecture`; `Mughal` ≡ `Indo-Mughal`;
> `Romanesque Revival` ≡ `Richardsonian Romanesque`.

---

## 5. Bảng tra 106 phong cách KB (Tên · Alias · Họ)

Tên chính model trả về chỉ cần khớp **Tên HOẶC một Alias bất kỳ** của cùng dòng với đáp án là tính đúng.
Cột **Họ** dùng cho `family-accuracy` (đúng họ nhưng sai phong cách con) — không bắt buộc cho top-1.

### Họ: Ancient (Cổ đại)
| Tên (canonical) | Alias | Họ |
|---|---|---|
| Ancient Egyptian | Egyptian, Pharaonic | ancient |
| Mesopotamian | Sumerian, Babylonian, Assyrian | ancient |
| Ancient Greek | Classical Greek, Hellenic | ancient |
| Ancient Roman | Roman | ancient |
| Etruscan | — | ancient |
| Achaemenid Persian | Persian (Achaemenid) | ancient |
| Minoan-Mycenaean | Aegean, Minoan, Mycenaean | ancient |

### Họ: Late Antique / Early Medieval (Hậu cổ đại / Trung cổ sớm)
| Tên (canonical) | Alias | Họ |
|---|---|---|
| Byzantine | Byzantine Architecture | late-antique |
| Early Christian | — | late-antique |
| Coptic | — | late-antique |
| Visigothic | — | late-antique |
| Carolingian | — | late-antique |
| Ottonian | — | late-antique |
| Pre-Romanesque | Asturian | late-antique |

### Họ: Islamic (Hồi giáo)
| Tên (canonical) | Alias | Họ |
|---|---|---|
| Umayyad-Abbasid | Early Islamic | islamic |
| Moorish | Hispano-Moresque, Al-Andalus | islamic |
| Mamluk | — | islamic |
| Ottoman | Turkish | islamic |
| Safavid/Persian | Isfahani, Persian Islamic | islamic |
| Mughal | Indo-Mughal | islamic |
| Indo-Islamic | Delhi Sultanate | islamic |
| Fatimid | — | islamic |

### Họ: East Asian (Đông Á)
| Tên (canonical) | Alias | Họ |
|---|---|---|
| Traditional Chinese | Chinese Imperial, Chinese | east-asian |
| Traditional Japanese | Japanese, Sukiya, Shinto | east-asian |
| Japanese Buddhist temple | Pagoda (Japan) | east-asian |
| Korean (Hanok) | Hanok | east-asian |
| Tibetan | Tibetan Buddhist | east-asian |

### Họ: South & Southeast Asian (Nam & Đông Nam Á)
| Tên (canonical) | Alias | Họ |
|---|---|---|
| North Indian temple (Nagara) | Nagara | south-se-asian |
| South Indian temple (Dravidian) | Dravidian | south-se-asian |
| Khmer (Angkorian) | Angkorian, Khmer | south-se-asian |
| Thai | Siamese | south-se-asian |
| Burmese | Myanmar | south-se-asian |
| Javanese (Candi) | Candi, Indonesian | south-se-asian |
| Vietnamese traditional | Vietnamese | south-se-asian |
| Sinhalese | Sri Lankan | south-se-asian |

### Họ: Indigenous Americas & Africa (Bản địa châu Mỹ & châu Phi)
| Tên (canonical) | Alias | Họ |
|---|---|---|
| Maya | Mayan | indigenous |
| Aztec | Mexica | indigenous |
| Inca | Incan | indigenous |
| Pueblo | Ancestral Puebloan, Adobe | indigenous |
| Sudano-Sahelian | Mali, Djenné | indigenous |
| Aksumite/Ethiopian | Ethiopian, Aksumite | indigenous |
| Swahili | Swahili coast | indigenous |

### Họ: Medieval European (Trung cổ châu Âu)
| Tên (canonical) | Alias | Họ |
|---|---|---|
| Romanesque | Norman (English) | medieval-european |
| Norman | — | medieval-european |
| Gothic | Gothic Architecture | medieval-european |
| Venetian Gothic | — | medieval-european |
| Brick Gothic | Backsteingotik | medieval-european |
| Mudéjar | — | medieval-european |

### Họ: Renaissance & Baroque (Phục Hưng & Baroque)
| Tên (canonical) | Alias | Họ |
|---|---|---|
| Renaissance | Renaissance Architecture | renaissance-baroque |
| Mannerism | Mannerist | renaissance-baroque |
| Palladian | Palladianism | renaissance-baroque |
| Baroque | Baroque Architecture | renaissance-baroque |
| Rococo | Late Baroque | renaissance-baroque |
| Churrigueresque | Spanish Baroque | renaissance-baroque |
| Manueline | Portuguese Late Gothic | renaissance-baroque |
| Spanish Colonial | — | renaissance-baroque |
| Dutch Colonial | — | renaissance-baroque |

### Họ: Neoclassical & 19th-century Revival (Tân cổ điển & Phục hưng TK19)
| Tên (canonical) | Alias | Họ |
|---|---|---|
| Neoclassical | Neoclassicism | revival-19c |
| Greek Revival | — | revival-19c |
| Gothic Revival | Neo-Gothic, Victorian Gothic | revival-19c |
| Romanesque Revival | Richardsonian Romanesque | revival-19c |
| Renaissance Revival | Neo-Renaissance | revival-19c |
| Byzantine Revival | Neo-Byzantine | revival-19c |
| Egyptian Revival | — | revival-19c |
| Moorish Revival | Neo-Moorish | revival-19c |
| Beaux-Arts | Beaux-Arts Classicism | revival-19c |
| Second Empire | Napoleon III style | revival-19c |
| Italianate | — | revival-19c |
| Russian Revival | Pseudo-Russian | revival-19c |
| Tudor Revival | Mock Tudor | revival-19c |
| Colonial Revival | — | revival-19c |
| Spanish Colonial Revival | — | revival-19c |
| Mission Revival | — | revival-19c |

### Họ: European-American Vernacular (Bản địa Âu-Mỹ)
| Tên (canonical) | Alias | Họ |
|---|---|---|
| Georgian | Georgian Architecture | vernacular-euro-american |
| Federal | Adam style | vernacular-euro-american |
| Regency | — | vernacular-euro-american |
| Victorian (Queen Anne) | Queen Anne | vernacular-euro-american |
| Gründerzeit | German Historicism | vernacular-euro-american |
| Jacobean | Jacobethan | vernacular-euro-american |

### Họ: Early Modern Movements (Hiện đại sơ kỳ)
| Tên (canonical) | Alias | Họ |
|---|---|---|
| Arts and Crafts | Craftsman | early-modern |
| Art Nouveau | Art Nouveau Architecture | early-modern |
| Jugendstil/Secession | Vienna Secession, Jugendstil | early-modern |
| Catalan Modernisme | Modernisme, Gaudí | early-modern |
| Prairie School | Prairie style | early-modern |
| Art Deco | Style Moderne, Deco | early-modern |
| Streamline Moderne | Art Moderne | early-modern |
| Expressionism | Expressionist architecture | early-modern |
| Amsterdam School | — | early-modern |
| Constructivism | Constructivist | early-modern |
| De Stijl | Neoplasticism | early-modern |
| Futurism | Futurist architecture | early-modern |
| Bauhaus | — | early-modern |

### Họ: Modern & Contemporary (Hiện đại & Đương đại)
| Tên (canonical) | Alias | Họ |
|---|---|---|
| International Style/Modernism | International Style, Modern Movement, Modernism | modern-contemporary |
| Mid-Century Modern | MCM | modern-contemporary |
| Brutalism | Brutalist, Béton brut | modern-contemporary |
| Metabolism | Japanese Metabolism | modern-contemporary |
| Organic architecture | — | modern-contemporary |
| Googie | Populuxe | modern-contemporary |
| Postmodernism | Postmodern, Po-Mo | modern-contemporary |
| Deconstructivism | Deconstructivist | modern-contemporary |
| High-tech | Structural Expressionism | modern-contemporary |
| Neo-futurism | Neofuturist | modern-contemporary |
| Parametricism/Blobitecture | Blobitecture, Parametric | modern-contemporary |
| Critical Regionalism | — | modern-contemporary |
| Minimalism | Minimalist architecture | modern-contemporary |
| Contemporary vernacular | Neo-vernacular | modern-contemporary |

**Tổng: 106 phong cách / 12 họ.**

---

## 6. Regenerate bảng Mục 5 khi KB thay đổi

```bash
cd d:\Study\Thesis\Architecture-AI
python -c "import json; s=json.load(open('chatbot/knowledge/styles.json',encoding='utf-8'))['styles']; print('TOTAL',len(s)); [print(f\"| {x['name']} | {', '.join(x.get('aliases',[])) or '—'} | {x.get('parent','')} |\") for x in s]"
```

Dán lại các dòng vào đúng nhóm họ. Luôn kiểm `TOTAL` khớp số phong cách thực tế của `styles.json`.
