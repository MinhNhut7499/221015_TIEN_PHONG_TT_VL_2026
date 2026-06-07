# Tài liệu Kiến trúc Hệ thống AI Phân tích Phong cách Kiến trúc

> **Phiên bản:** 1.0 · **Ngày:** 2026-05-13
> Tài liệu này mô tả toàn bộ thiết kế hệ thống multi-agent. Dùng làm tài liệu tham khảo khi cần nhớ lại kiến trúc hoặc onboard thành viên mới.

---

## Mục lục

1. [Tổng quan hệ thống](#1-tổng-quan-hệ-thống)
2. [Pipeline tổng thể](#2-pipeline-tổng-thể)
3. [Tầng 1 — Phân tích thành phần](#3-tầng-1--phân-tích-thành-phần)
4. [Tầng 2 — Suy luận toàn công trình](#4-tầng-2--suy-luận-toàn-công-trình)
5. [Contract dữ liệu YOLO ↔ LLM](#5-contract-dữ-liệu-yolo--llm)
6. [Schemas trung gian giữa các agent](#6-schemas-trung-gian-giữa-các-agent)
7. [Weighted Voting — tính trọng số](#7-weighted-voting--tính-trọng-số)
8. [Database Schema](#8-database-schema)
9. [API Endpoints](#9-api-endpoints)
10. [Cấu trúc thư mục code](#10-cấu-trúc-thư-mục-code)
11. [Quyết định thiết kế quan trọng](#11-quyết-định-thiết-kế-quan-trọng)
12. [Giai đoạn phát triển](#12-giai-đoạn-phát-triển)

---

## 1. Tổng quan hệ thống

Hệ thống nhận một ảnh công trình kiến trúc và trả về phong cách kiến trúc kèm lập luận giải thích. Pipeline gồm hai tầng độc lập:

- **Tầng 1 — Thị giác máy tính:** YOLOv8s phát hiện và cắt (crop) các thành phần kiến trúc. Mỗi thành phần được 4 LLM agent phân tích độc lập để xác định phong cách của thành phần đó.
- **Tầng 2 — Suy luận LLM:** 3 LLM agent nhận tổng hợp kết quả từ Tầng 1, suy luận và đưa ra phong cách cuối cùng của toàn bộ công trình.

**Hai tầng giao tiếp qua một JSON contract cố định** (`DetectedComponent`). Khi swap model YOLO (ví dụ: từ YOLOv8s sang YOLOv8m), không cần sửa bất kỳ LLM agent nào.

**Nguyên tắc xuyên suốt:** Confidence phải được giữ lại và truyền qua mọi bước trong pipeline. Không cắt bỏ xác suất thành nhãn cứng cho đến Agent 7.

**Phân công model LLM (Option A — Balanced):**

| Agent | Model | Lý do |
|---|---|---|
| Agent 1 | Gemini Flash | Vision — mô tả text đơn giản, cần rẻ/nhanh |
| Agent 2 | Gemini Flash | Vision — gọi 3x/component (Monte Carlo), cần rẻ |
| Agent 3a | Code (không LLM) | Hard rule lookup |
| Agent 3b | DeepSeek | Text — kiểm tra mâu thuẫn đơn giản |
| Agent 4 | DeepSeek | Text — tổng hợp component |
| Agent 5 | DeepSeek | Text — lập luận phong cách chính |
| Agent 6 | DeepSeek | Text — đề xuất giả thuyết thay thế |
| Agent 7 | OpenAI GPT-4o | Text — output cuối cùng, dùng model tốt nhất |

---

## 2. Pipeline tổng thể

```
Ảnh đầu vào
    │
    ▼
┌─────────────────────────────────────────┐
│  YOLOv8s (hoặc MockYOLOService khi test) │
│  → List[DetectedComponent]              │
└─────────────────────────────────────────┘
    │
    │  Mỗi component: {type, confidence, bbox, crop_base64, full_image_base64}
    ▼
┌──────────────────────────────────────────────────────────┐
│  TẦNG 1 — asyncio.gather (song song theo component)      │
│                                                          │
│  Mỗi component chạy tuần tự Agent 1 → 2 → 3 → 4:        │
│                                                          │
│  Agent 1: Feature Describer    [Gemini Flash — vision]    │
│      ↓ feature_description (text)                        │
│  Agent 2: Style Classifier     [Gemini Flash — vision]   │
│      ↓ style_distribution {Doric:0.6, Ionic:0.3, ...}    │
│  Agent 3a: Rule Check          [Code — không LLM]        │
│      ↓ violated_rules[]                                  │
│  Agent 3b: Contradiction Detector [DeepSeek — text]      │
│      ↓ {has_contradiction, analysis}                     │
│  Agent 4: Component Synthesizer [DeepSeek — text]        │
│      ↓ {style, confidence, reasoning}                    │
└──────────────────────────────────────────────────────────┘
    │
    │  List[ComponentAnalysis] + Aggregated Votes (tính bởi code)
    ▼
┌──────────────────────────────────────────────────────────┐
│  TẦNG 2 — tuần tự                                        │
│                                                          │
│  Agent 5: Primary Advocate      [DeepSeek — text]        │
│      ↓ {style, confidence, reasoning}                    │
│  Agent 6: Alternative Hypothesist [DeepSeek — text]      │
│      ↓ {style (khác Agent 5), confidence, reasoning}     │  ← chỉ nhận label Agent 5
│  Agent 7: Final Arbitrator      [OpenAI GPT-4o — text]   │
│      ↓ {style, confidence, explanation, key_evidence[]}  │
└──────────────────────────────────────────────────────────┘
    │
    ▼
AnalyzeResponse
{style, confidence, explanation, key_evidence, components, processing_time_ms}
```

---

## 3. Tầng 1 — Phân tích thành phần

### Thiết kế thực thi

Các component được xử lý **song song** (asyncio.gather). Trong mỗi component, các agent chạy **tuần tự** (1→2→3→4) vì đầu ra của agent trước là đầu vào của agent sau.

**KHÔNG** gộp nhiều crop vào một lần gọi LLM. Lý do:
- Attention của model bị pha loãng khi có nhiều ảnh trong cùng context.
- Cần phân phối xác suất độc lập cho từng component để tính trọng số sau.
- Error isolation: nếu một crop lỗi parse, không ảnh hưởng các crop khác.

### Agent 1 — Feature Describer

| | |
|---|---|
| **Input** | `crop_base64` + `component_type` |
| **Output** | `feature_description: str` (3–5 câu) |
| **Model call** | Vision (1 ảnh) |
| **Sampling** | 1 lần |

**Prompt:**
```
You are an architectural feature analyst. Examine this cropped photograph
of a single architectural component: a {component_type}.

Describe its geometric and visual properties in 3–5 sentences. Focus on:
- Shape and proportions (height-to-width ratio, taper, curvature)
- Surface treatment (smooth, fluted, rusticated, carved)
- Decorative elements at the top, bottom, or along the body
- Material appearance (stone, marble, brick, concrete)

Be precise and objective. Do NOT name an architectural style yet.
```

---

### Agent 2 — Style Classifier

| | |
|---|---|
| **Input** | `crop_base64` + `full_image_base64` + `component_type` + `feature_description` (từ Agent 1) |
| **Output** | `style_distribution: Dict[str, float]` — tổng = 1.0 |
| **Model call** | Vision (2 ảnh) |
| **Sampling** | **3 lần** với temperature khác nhau → lấy trung bình distribution |

**Tại sao 3 lần:** LLM không calibrate probability tốt. Sampling nhiều lần và lấy trung bình tạo ra distribution ổn định hơn. Đây là kỹ thuật Monte Carlo đơn giản.

**Cách lấy trung bình:** Với mỗi style, cộng 3 giá trị rồi chia 3. Sau đó normalize lại (chia cho tổng) để đảm bảo tổng = 1.0.

**Prompt:**
```
You are an expert in architectural history and style classification.

Component: {component_type}
Feature analysis: {feature_description}

You are provided with: (1) a cropped image of this component, (2) the full building photo.

Classify this component by assigning a probability to each plausible style.

Candidate styles: Classical Greek, Roman, Romanesque, Gothic, Renaissance,
Baroque, Neoclassical, Beaux-Arts, Art Deco, Art Nouveau, Modernist, Brutalist, Postmodern.

Return ONLY a JSON object. Keys = style names, values = probabilities summing to 1.0.
Include only styles with probability > 0.0. Maximum 5 styles.
Example: {"Neoclassical": 0.55, "Beaux-Arts": 0.30, "Classical Greek": 0.15}
```

**Lưu ý downstream:** Giá trị từ Agent 2 được dùng như **heuristic ranking**, KHÔNG phải xác suất thống kê. Downstream (Agent 4, Agent 5) nhận top-3 styles và margin (khoảng cách top-1 vs top-2), không nhân xác suất trực tiếp.

---

### Agent 3a — Rule Checker (code, không phải LLM)

| | |
|---|---|
| **Input** | `component_type` + `top_style` (từ Agent 2) + `feature_description` (từ Agent 1) |
| **Output** | `violated_rules: List[str]` |
| **Implementation** | Python dict lookup, không gọi LLM |

**Tại sao cần lớp rule-based:** LLM không đảm bảo nhớ các rule cứng của kiến trúc (ví dụ: cột Doric không bao giờ có base). Rule-based layer xử lý hard violations; LLM xử lý soft contradictions.

**Ví dụ rule dictionary:**
```python
HARD_RULES = {
    "Doric":       {"capital_type": "plain",   "no_base": True},
    "Ionic":       {"capital_type": "volute"},
    "Corinthian":  {"capital_type": "acanthus"},
    "Gothic":      {"arch_type":    "pointed"},
    "Romanesque":  {"arch_type":    "round"},
}
```

Bắt đầu với 15–25 rules cho các style phổ biến nhất trong dataset. Mở rộng dần sau khi có dữ liệu thực tế.

---

### Agent 3b — Contradiction Detector (LLM)

| | |
|---|---|
| **Input** | `feature_description` + `style_distribution` + `violated_rules` (từ 3a) |
| **Output** | `{has_contradiction: bool, contradiction_analysis: str}` |
| **Model** | **DeepSeek** (text-only) |
| **Sampling** | 1 lần |

**Prompt:**
```
You are a critical reviewer checking consistency of an architectural analysis.

Component type: {component_type}
Feature description: {feature_description}
Style distribution: {style_distribution_formatted}
Rule violations detected: {violated_rules}

Determine whether the described features are consistent with the top-ranked styles.
If rule violations are listed, explain why they matter.

Return ONLY:
{"has_contradiction": true/false, "contradiction_analysis": "1–3 sentences"}
```

**Fallback khi parse lỗi:** `{"has_contradiction": false, "contradiction_analysis": "Parse error, skipped"}`

---

### Agent 4 — Component Synthesizer

| | |
|---|---|
| **Input** | Agent 1, 2, 3 outputs + `detection_confidence` từ YOLO |
| **Output** | `{style: str, confidence: float, reasoning: str}` |
| **Model** | **DeepSeek** (text-only) |
| **Sampling** | 1 lần |

**Prompt:**
```
Synthesize the analysis of a {component_type}.

YOLO detection confidence: {detection_confidence:.2f}
Feature description: {feature_description}
Style distribution (top 3): {top3_styles}
Contradiction: has_contradiction={has_contradiction}, {contradiction_analysis}

Produce a final verdict. Reduce confidence if:
- has_contradiction is true
- detection_confidence < 0.5
- No style exceeds 0.4 in the distribution (high uncertainty)

Return ONLY:
{"style": "...", "confidence": 0.0–1.0, "reasoning": "1–2 sentences"}
```

**Fallback:** top-1 style từ Agent 2, confidence = 0.5.

---

## 4. Tầng 2 — Suy luận toàn công trình

Tầng 2 nhận đầu vào là `List[ComponentAnalysis]` và một **aggregated vote summary** được tính bằng code (xem [Mục 7](#7-weighted-voting--tính-trọng-số)).

### Agent 5 — Primary Advocate

| | |
|---|---|
| **Input** | Component analyses summary + aggregated vote summary |
| **Output** | `{style: str, confidence: float, reasoning: str}` |
| **Model** | **DeepSeek** (text-only) |
| **Sampling** | 1 lần |

**Prompt:**
```
You are a primary advocate arguing for the most likely architectural style.

Aggregated component votes:
{aggregated_votes_table}

Detailed component analyses:
{component_analyses_summary}

Identify the single most dominant style supported by the evidence.
Argue for it citing specific component evidence.

Return ONLY:
{"style": "...", "confidence": 0.0–1.0, "reasoning": "2–4 sentences"}
```

---

### Agent 6 — Alternative Hypothesist

| | |
|---|---|
| **Input** | Component analyses summary + **chỉ label của Agent 5** (không phải full reasoning) |
| **Output** | `{style: str (khác Agent 5), confidence: float, reasoning: str}` |
| **Model** | **DeepSeek** (text-only) |
| **Sampling** | 1 lần |

**Thiết kế quan trọng — Weak Adversarial Dependency:**
Agent 6 chỉ nhận **kết luận cuối** của Agent 5 (tên style), không nhận reasoning. Mục đích: buộc Agent 6 chọn style khác (tránh redundancy) nhưng vẫn xây reasoning chain độc lập từ evidence (tránh anchoring bias trên lập luận của Agent 5).

**Prompt:**
```
The primary analysis concludes: "{agent5_style}".

Using ONLY the component evidence below, propose the strongest ALTERNATIVE
interpretation that is different from "{agent5_style}".
Build your own reasoning from the evidence — do not respond to Agent 5's argument.

Component evidence:
{component_analyses_summary}

Return ONLY:
{"style": "...", "confidence": 0.0–1.0, "reasoning": "2–4 sentences"}
```

---

### Agent 7 — Final Arbitrator

| | |
|---|---|
| **Input** | Component analyses + Agent 5 full output + Agent 6 full output |
| **Output** | `{style, confidence, explanation, key_evidence[]}` |
| **Model** | **OpenAI GPT-4o** — output quan trọng nhất, dùng model tốt nhất |
| **Sampling** | 1 lần |
| **Technique** | Chain-of-Thought forcing (xem bên dưới) |

**CoT Forcing — tại sao:** Agent 7 gánh 3 nhiệm vụ (compare, decide, explain). Nếu không buộc CoT, model có xu hướng quyết định trước rồi fabricate reasoning. CoT forcing không thêm API call, chỉ sửa prompt.

**Prompt:**
```
You are the final arbiter in a panel discussion about architectural style.

Primary advocate: {agent5_style} (confidence {agent5_confidence:.2f})
{agent5_reasoning}

Alternative hypothesist: {agent6_style} (confidence {agent6_confidence:.2f})
{agent6_reasoning}

Component evidence:
{component_analyses_summary}

BEFORE your final answer, write a REASONING section:
Step 1: List the 3 strongest pieces of component evidence.
Step 2: Evaluate how well each hypothesis explains the evidence.
Step 3: Identify which hypothesis is better supported and why.

Then return ONLY this JSON (after the reasoning):
{
  "style": "...",
  "confidence": 0.0–1.0,
  "explanation": "3–5 sentences covering the decision rationale",
  "key_evidence": ["point 1", "point 2", "point 3"]
}
key_evidence: 3–5 items, each citing a specific component or feature.
```

**Parse strategy:** Extract JSON block sau phần REASONING bằng regex `\{[\s\S]*\}` — bỏ qua text trước đó.

---

## 5. Contract dữ liệu YOLO ↔ LLM

Đây là interface duy nhất giữa tầng thị giác và tầng LLM. **Không thay đổi khi swap model YOLO.**

```python
class BoundingBox(BaseModel):
    x_min: int
    y_min: int
    x_max: int
    y_max: int

class DetectedComponent(BaseModel):
    component_id: str           # uuid4
    component_type: str         # 18 YOLO classes — see chatbot/utils/schemas.py:ComponentType
    detection_confidence: float # 0.0–1.0 (từ YOLO hoặc mock)
    bounding_box: BoundingBox
    crop_base64: str            # base64 JPEG của vùng crop
    full_image_base64: str      # base64 JPEG ảnh gốc (giống nhau cho mọi component trong cùng request)
```

**Khi tích hợp YOLO thật:**
1. Tạo `chatbot/services/yolo_service.py` với class `RealYOLOService`
2. Method signature: `detect(image_bytes: bytes) -> List[DetectedComponent]`
3. Trong `analysis_orchestrator.py`: thay `MockYOLOService()` → `RealYOLOService(model_path=settings.YOLO_MODEL_PATH)`
4. **Không sửa gì trong pipeline_runner.py hay bất kỳ agent nào**

---

## 6. Schemas trung gian giữa các agent

Tất cả nằm trong `chatbot/utils/schemas.py`.

```python
# ── Tier 1 outputs ─────────────────────────────────────────────────────────────

class Agent1Output(BaseModel):
    component_id: str
    feature_description: str

class Agent2Output(BaseModel):
    component_id: str
    style_distribution: Dict[str, float]   # tổng = 1.0 sau normalize

class Agent3Output(BaseModel):
    component_id: str
    has_contradiction: bool
    contradiction_analysis: str
    violated_rules: List[str]              # từ Agent 3a (rule-based)

class Agent4Output(BaseModel):
    component_id: str
    component_type: str
    style: str
    confidence: float
    reasoning: str

class ComponentAnalysis(BaseModel):
    component_id: str
    component_type: str
    detection_confidence: float            # từ YOLO
    agent1: Agent1Output
    agent2: Agent2Output
    agent3: Agent3Output
    agent4: Agent4Output

# ── Tier 2 outputs ─────────────────────────────────────────────────────────────

class Agent5Output(BaseModel):
    style: str
    confidence: float
    reasoning: str

class Agent6Output(BaseModel):
    style: str
    confidence: float
    reasoning: str

class FinalAnalysisResult(BaseModel):
    style: str
    confidence: float
    explanation: str
    key_evidence: List[str]
    components: List[ComponentAnalysis]
    agent5: Agent5Output
    agent6: Agent6Output
    processing_time_ms: float

# ── API Response ────────────────────────────────────────────────────────────────

class AnalyzeResponse(BaseModel):
    analysis_id: str
    file_id: str
    style: str
    confidence: float
    explanation: str
    key_evidence: List[str]
    components: List[Dict[str, Any]]
    status: str                            # "completed" | "failed"
    processing_time_ms: float

class HistoryResponse(BaseModel):
    items: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int
```

---

## 7. Weighted Voting — tính trọng số

**Đây là bước code (orchestrator), KHÔNG phải LLM agent.**

Trước khi gọi Agent 5, orchestrator tính aggregated vote summary từ `List[ComponentAnalysis]`:

```python
def compute_aggregated_votes(
    components: List[ComponentAnalysis],
) -> Dict[str, float]:
    """
    Mỗi component bỏ phiếu cho style của nó, trọng số:
        w = detection_confidence × agent4_confidence
    Tổng hợp theo style, normalize về [0, 1].
    """
    votes: Dict[str, float] = {}
    for comp in components:
        style = comp.agent4.style
        weight = comp.detection_confidence * comp.agent4.confidence
        votes[style] = votes.get(style, 0.0) + weight

    total = sum(votes.values()) or 1.0
    return {s: round(v / total, 4) for s, v in sorted(votes.items(), key=lambda x: -x[1])}
```

**Ví dụ output truyền cho Agent 5:**
```
Style vote summary:
  Neoclassical : 0.4821  (3 components)
  Doric        : 0.3104  (2 components)
  Ionic        : 0.2075  (1 component)
```

**Lý do không để LLM tính:** Con số từ LLM không đáng tin dùng cho arithmetic. Code đảm bảo reproducible và deterministic.

---

## 8. Database Schema

### 8.1 Sơ đồ quan hệ

```
Roles ──< Users ──< Projects ──< Images ──< Components ──< GeometricFeatures
                                    │           │           ├── StylePredictions
                                    │           │           ├── ConsistencyChecks
                                    │           │           └── ComponentFinalStyles
                                    │           │
                                    │       AgentRuns >── Agents
                                    │
                                    ├──< BuildingStyleResults
                                    └──< BuildingStyleHypotheses >── Agents
```

### 8.2 DDL hoàn chỉnh

```sql
-- ── Roles ──────────────────────────────────────────────────────────────────────
CREATE TABLE Roles (
    RoleId    INT PRIMARY KEY IDENTITY,
    RoleName  NVARCHAR(50) NOT NULL  -- 'USER', 'ADMIN'
);

-- ── Users ───────────────────────────────────────────────────────────────────────
CREATE TABLE Users (
    UserId      UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    Email       NVARCHAR(255) NOT NULL UNIQUE,
    Name        NVARCHAR(255) NOT NULL,
    Picture     NVARCHAR(500) NULL,
    GoogleSub   NVARCHAR(255) NULL UNIQUE,  -- Google OAuth2 subject
    IsActive    BIT NOT NULL DEFAULT 1,
    RoleId      INT,
    CreatedAt   DATETIME DEFAULT GETDATE(),
    UpdatedAt   DATETIME NULL,
    FOREIGN KEY (RoleId) REFERENCES Roles(RoleId)
);

-- ── Projects ────────────────────────────────────────────────────────────────────
CREATE TABLE Projects (
    ProjectId    UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    UserId       UNIQUEIDENTIFIER NOT NULL,
    ProjectName  NVARCHAR(255),
    Description  NVARCHAR(MAX),
    CreatedAt    DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (UserId) REFERENCES Users(UserId)
);

-- ── Images ──────────────────────────────────────────────────────────────────────
CREATE TABLE Images (
    ImageId          UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    ProjectId        UNIQUEIDENTIFIER NOT NULL,
    ImagePath        NVARCHAR(500) NOT NULL,       -- local path, UUID-named
    AnalysisStatus   NVARCHAR(50) NOT NULL DEFAULT 'pending',
                     -- pending | processing | completed | failed
    ErrorMessage     NVARCHAR(MAX) NULL,
    UploadedAt       DATETIME DEFAULT GETDATE(),
    UpdatedAt        DATETIME NULL,
    FOREIGN KEY (ProjectId) REFERENCES Projects(ProjectId)
);

-- ── Components ──────────────────────────────────────────────────────────────────
CREATE TABLE Components (
    ComponentId    UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    ImageId        UNIQUEIDENTIFIER NOT NULL,
    ComponentType  NVARCHAR(100),               -- column, capital, arch...
    BoundingBox    NVARCHAR(255),               -- JSON: {x_min,y_min,x_max,y_max}
    CropImagePath  NVARCHAR(500),               -- local path đến crop image
    DetectionConf  FLOAT,                       -- YOLO detection confidence
    CreatedAt      DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (ImageId) REFERENCES Images(ImageId)
);

-- ── Agents ──────────────────────────────────────────────────────────────────────
CREATE TABLE Agents (
    AgentId      UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    AgentName    NVARCHAR(100),  -- 'agent1_feature_describer', ...
    Description  NVARCHAR(500),
    Tier         INT             -- 1 (component-level) hoặc 2 (building-level)
);

-- ── AgentRuns ───────────────────────────────────────────────────────────────────
CREATE TABLE AgentRuns (
    RunId          UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    ImageId        UNIQUEIDENTIFIER NULL,     -- cho agent 5, 6, 7 (building-level)
    ComponentId    UNIQUEIDENTIFIER NULL,     -- cho agent 1, 2, 3, 4 (component-level)
    AgentId        UNIQUEIDENTIFIER NOT NULL,
    InputData      NVARCHAR(MAX),             -- prompt + structured input đưa vào agent
    RawOutput      NVARCHAR(MAX),             -- raw LLM response trước khi parse
    ParsedOutput   NVARCHAR(MAX),             -- structured output sau khi parse thành công
    AgentVersion   VARCHAR(16)    NULL,       -- md5[:8] của prompt template
    ModelId        NVARCHAR(100)  NULL,       -- e.g., "gemini-1.5-flash-001"
    ParseSuccess   BIT           NULL,        -- 1 = parse OK, 0 = dùng fallback
    LatencyMs      INT           NULL,        -- thời gian gọi LLM tính bằng ms
    CreatedAt      DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (ComponentId) REFERENCES Components(ComponentId),
    FOREIGN KEY (ImageId) REFERENCES Images(ImageId),
    FOREIGN KEY (AgentId) REFERENCES Agents(AgentId),
    CONSTRAINT CK_AgentRuns_Target CHECK (
        ImageId IS NOT NULL OR ComponentId IS NOT NULL
    )
);

-- ── GeometricFeatures (Agent 1 output) ─────────────────────────────────────────
CREATE TABLE GeometricFeatures (
    FeatureId      UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    ComponentId    UNIQUEIDENTIFIER NOT NULL,
    Description    NVARCHAR(MAX),
    CreatedAt      DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (ComponentId) REFERENCES Components(ComponentId)
);

-- ── StylePredictions (Agent 2 output) ──────────────────────────────────────────
CREATE TABLE StylePredictions (
    PredictionId   UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    ComponentId    UNIQUEIDENTIFIER NOT NULL,
    StyleName      NVARCHAR(100),   -- "Doric", "Ionic"...
    Probability    FLOAT,           -- giá trị trong distribution, không phải xác suất thật
    SampleIndex    INT DEFAULT 0,   -- 0,1,2 nếu dùng 3x sampling; 99 = averaged
    CreatedAt      DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (ComponentId) REFERENCES Components(ComponentId)
);

-- ── ConsistencyChecks (Agent 3 output) ─────────────────────────────────────────
CREATE TABLE ConsistencyChecks (
    CheckId          UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    ComponentId      UNIQUEIDENTIFIER NOT NULL,
    IsConsistent     BIT,
    ViolatedRules    NVARCHAR(MAX),  -- JSON array từ rule-based Agent 3a
    Reason           NVARCHAR(MAX),  -- LLM analysis từ Agent 3b
    CreatedAt        DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (ComponentId) REFERENCES Components(ComponentId)
);

-- ── ComponentFinalStyles (Agent 4 output) ──────────────────────────────────────
CREATE TABLE ComponentFinalStyles (
    Id             UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    ComponentId    UNIQUEIDENTIFIER NOT NULL,
    FinalStyle     NVARCHAR(100),
    Confidence     FLOAT,
    Explanation    NVARCHAR(MAX),
    CreatedAt      DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (ComponentId) REFERENCES Components(ComponentId)
);

-- ── BuildingStyleHypotheses (Agent 5, 6 output) ────────────────────────────────
CREATE TABLE BuildingStyleHypotheses (
    HypothesisId     UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    ImageId          UNIQUEIDENTIFIER NOT NULL,
    AgentId          UNIQUEIDENTIFIER NOT NULL,
    HypothesisType   NVARCHAR(50),    -- 'PRIMARY' (agent5), 'ALTERNATIVE' (agent6)
    StyleName        NVARCHAR(100),
    Confidence       FLOAT,
    Explanation      NVARCHAR(MAX),
    BasedOnFeatures  NVARCHAR(MAX),   -- JSON: component styles dùng làm evidence
    CreatedAt        DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (ImageId) REFERENCES Images(ImageId),
    FOREIGN KEY (AgentId) REFERENCES Agents(AgentId)
);

-- ── BuildingStyleResults (Agent 7 output) ──────────────────────────────────────
CREATE TABLE BuildingStyleResults (
    ResultId     UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    ImageId      UNIQUEIDENTIFIER NOT NULL,
    FinalStyle   NVARCHAR(100),
    Confidence   FLOAT,
    Explanation  NVARCHAR(MAX),
    KeyEvidence  NVARCHAR(MAX),  -- JSON array: ["point 1", "point 2", ...]
    CreatedAt    DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (ImageId) REFERENCES Images(ImageId)
);

-- ── SystemLogs ──────────────────────────────────────────────────────────────────
CREATE TABLE SystemLogs (
    LogId      UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    LogLevel   NVARCHAR(50),    -- INFO, WARNING, ERROR
    Source     NVARCHAR(100),   -- "agent2", "pipeline_runner", "api"
    Message    NVARCHAR(MAX),
    CreatedAt  DATETIME DEFAULT GETDATE()
);
```

---

## 9. API Endpoints

| Method | Path | Auth | Mô tả |
|---|---|---|---|
| `GET` | `/health` | Không | Health check |
| `GET` | `/auth/google/login` | Không | Redirect đến Google consent |
| `GET` | `/auth/google/callback` | Không | Nhận code → trả JWT |
| `POST` | `/upload/image` | Bearer JWT | Upload ảnh → trả `file_id` |
| `POST` | `/analyze` | Bearer JWT | Chạy pipeline → trả `AnalyzeResponse` |
| `GET` | `/analyze/history` | Bearer JWT | Lịch sử phân tích (stub hiện tại) |

**POST `/analyze` request body:**
```json
{"file_id": "uuid-string"}
```

**POST `/analyze` response:**
```json
{
  "analysis_id": "uuid",
  "file_id": "uuid",
  "style": "Neoclassical",
  "confidence": 0.74,
  "explanation": "The building exhibits...",
  "key_evidence": ["Corinthian columns...", "Symmetrical facade...", "Pediment..."],
  "components": [...],
  "status": "completed",
  "processing_time_ms": 12430
}
```

---

## 10. Cấu trúc thư mục code

```
Architecture-AI/
├── app/
│   ├── config.py              ← Settings (thêm GEMINI_API_KEY, PIPELINE_MAX_COMPONENTS)
│   ├── main.py                ← Register thêm analyze.router
│   ├── models/base_db.py      ← KHÔNG SỬA (DBA-owned)
│   ├── routers/
│   │   ├── analyze.py         ← POST /analyze, GET /analyze/history
│   │   ├── auth.py
│   │   ├── base.py
│   │   └── file_upload.py
│   └── services/
│       └── analysis_service.py  ← Business logic cho /analyze (nếu cần tách)
│
├── chatbot/
│   ├── services/
│   │   ├── llm_service.py         ← BaseLLMService, StubLLMService, factory (cập nhật)
│   │   ├── gemini_service.py      ← GeminiService + generate() method
│   │   ├── mock_yolo_service.py   ← MockYOLOService (deterministic hash-based)
│   │   ├── pipeline_runner.py     ← Chạy 7 agents, asyncio.gather Tier 1
│   │   └── analysis_orchestrator.py ← Nối YOLO + Pipeline, gọi từ router
│   └── utils/
│       ├── schemas.py         ← Tất cả Pydantic inter-agent models
│       ├── prompt_builder.py  ← 7 hàm build prompt (pure string, không LLM)
│       └── image_utils.py     ← base64 encode, crop helper
│
├── ingestion/                 ← Dataset loading, preprocessing (tương lai)
│
└── test/
    ├── test_base.py
    └── test_analyze.py
```

---

## 11. Quyết định thiết kế quan trọng

### 11.1 Agent 6 — Weak Adversarial Dependency
Agent 6 chỉ nhận **label kết luận** của Agent 5, không nhận reasoning. Buộc chọn style khác (tránh redundancy) nhưng xây reasoning chain độc lập (tránh anchoring bias).

### 11.2 LLM Probability là Heuristic
Output số của Agent 2 không phải xác suất thống kê. Dùng như **confidence-weighted ranking**. Downstream dùng weighted voting (`detection_confidence × agent4_confidence`), không nhân xác suất.

### 11.3 Contradiction Checking hai lớp
- **Agent 3a** (code): Hard rules, deterministic, fast.
- **Agent 3b** (LLM): Soft contradictions, contextual nuance.
Tách biệt để giữ rule layer debuggable và LLM layer flexible.

### 11.4 Agent 7 — CoT Forcing thay vì tách agent
Gộp compare + decide + explain trong một prompt với Chain-of-Thought forcing. Không tách thành 7a/7b trừ khi có evidence evaluation cho thấy explanation inconsistent với decision.

### 11.5 Mỗi crop gọi Agent 2 riêng biệt
Không gộp nhiều crop vào một lần gọi. Lý do: attention dilution, cần distribution độc lập cho weighted voting, error isolation. Các component chạy **song song** qua asyncio.gather.

### 11.6 AgentVersion — Automatic Prompt Versioning
```python
AGENT_VERSION = hashlib.md5(PROMPT_TEMPLATE.encode()).hexdigest()[:8]
```
Khi sửa prompt → version tự thay đổi → historical runs vẫn traceable. Không cần quản lý version thủ công.

### 11.7 Component cap
`PIPELINE_MAX_COMPONENTS = 6` trong config. YOLO thật có thể detect 10–20 components (80+ API calls/request). Cap tại 6 (27 calls/request) kiểm soát chi phí. Configurable qua `.env`.

### 11.8 MockYOLOService
Deterministic: `random.Random(hashlib.md5(image_bytes).hexdigest())`. Cùng ảnh → cùng detections → reproducible test. Detection confidence trong `[0.60, 0.95]`.

---

## 12. Giai đoạn phát triển

### Phase 1 — LLM Foundation (hiện tại)
- [x] Định nghĩa contract YOLO ↔ LLM
- [ ] Schemas (`chatbot/utils/schemas.py`)
- [ ] MockYOLOService
- [ ] GeminiService
- [ ] Pipeline Runner (7 agents)
- [ ] Analysis Orchestrator
- [ ] POST `/analyze` endpoint
- [ ] Tests

### Phase 2 — YOLO Integration (sau khi train xong)
- [ ] Train YOLOv8s trên dataset đã label
- [ ] Tạo `RealYOLOService` với signature `detect() -> List[DetectedComponent]`
- [ ] Thay MockYOLOService trong orchestrator
- [ ] Không sửa gì trong pipeline agent

### Phase 3 — Database Integration
- [ ] Thêm SQLAlchemy vào requirements
- [ ] Repository layer cho Images, Components, AgentRuns, BuildingStyleResults
- [ ] Persist kết quả sau mỗi lần phân tích
- [ ] GET `/analyze/history` đầy đủ

### Phase 4 — Incremental Labeling & Online Learning
- [ ] Confidence-weighted co-occurrence matrix
- [ ] Prior anchoring từ feedback người dùng
- [ ] (Chi tiết trong memory: `project_online_learning_plan.md`)
