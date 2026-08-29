import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useApp } from '../context/AppContext';
import FancySelect from '../components/FancySelect';
import SiteFooter from '../components/SiteFooter';
import {
    LayoutDashboard, Users, FolderOpen, Image as ImageIcon,
    Cpu, FileText, FolderTree, Sun, Moon,
    Search, Bell, LogOut, Trash2, CheckCircle2, XCircle,
    Filter, Activity, Database, ShieldCheck,
    ChevronDown, Loader2, RefreshCw, HardDrive,
    X, Eye, AlertTriangle, Lock, Pencil, Check,
    ArrowUpDown, BarChart3, Globe, BookOpen, Plus, Inbox,
    ExternalLink, Wallet, Coins, DollarSign, Trophy,
    KeyRound, Save, Power, LayoutTemplate, History, FlaskConical, UserCog,
    Package
} from 'lucide-react';
import {
    XAxis, YAxis, CartesianGrid, Tooltip, Legend,
    ResponsiveContainer, PieChart, Pie, Cell, AreaChart, Area,
    LineChart, Line, RadarChart, Radar, PolarGrid, PolarAngleAxis
} from 'recharts';
import {
    adminGetStats, adminGetUsers, adminGetProjects, adminGetImages,
    adminGetAgents, adminGetLogs, adminGetFiles,
    adminUpdateUserStatus, adminDeleteProject, adminDeleteImage, getMe,
    adminGetProjectDetail, adminGetImageDetail, adminGetImageRaw,
    adminGetFileRaw, adminDeleteFile, adminRenameProject,
    adminKbListStyles, adminKbCreateStyle, adminKbUpdateStyle, adminKbDeleteStyle,
    adminKbListFamilies, adminKbCreateFamily, adminKbRenameFamily, adminKbDeleteFamily,
    adminKbListSuggestions, adminKbDismissSuggestion,
    adminGetRevenue, adminGetTransactions, adminGetRevenueByUser, adminGetTopSpenders,
    adminGetApiKeys, adminGetApiKeyProviders, adminCreateApiKey, adminUpdateApiKey,
    adminToggleApiKey, adminDeleteApiKey, adminTestApiKey, adminTestStoredApiKey,
    adminGetCmsDraft, adminSaveCmsDraft, adminPublishCms, adminGetCmsRevisions, adminRestoreCms,
    adminGetBillingPlans, adminCreatePlan, adminUpdatePlan, adminDeactivatePlan
} from '../utils/api';

/**
 * Decode the JWT payload (diacritic-safe) so the admin's real name renders
 * correctly even with Vietnamese characters.
 */
function jwtClaims() {
    try {
        const token = localStorage.getItem('archi_access_token');
        if (!token) return {};
        const [, payload] = token.split('.');
        const binary = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
        const json = decodeURIComponent(
            binary
                .split('')
                .map((c) => '%' + c.charCodeAt(0).toString(16).padStart(2, '0'))
                .join('')
        );
        return JSON.parse(json);
    } catch {
        return {};
    }
}

/**
 * Bilingual dictionary — every visible string on the Admin page lives here.
 */
const translations = {
    en: {
        // nav + chrome
        dashboard: "Dashboard",
        users: "Users",
        projects: "Projects",
        images: "Analysis",
        agents: "Agents",
        revenue: "Revenue",
        logs: "System Logs",
        files: "File Browser",
        apikeys: "API Keys",
        content: "Content",
        plans: "Plans",
        userMode: "User mode",
        logout: "Logout",
        adminLabel: "Admin",
        search: "Search...",
        refresh: "Refresh",
        loading: "Loading...",
        loadError: "Could not load data",
        // header identity
        systemRoot: "Administrator",
        // dashboard cards
        totalFiles: "Total Files",
        totalSize: "Total Size",
        activeUsers: "Active Users",
        fileTypes: "file types",
        usersTotal: "total users",
        runsLabel: "runs",
        storedAt: "Stored at",
        // charts
        systemPerformance: "Uploads Over Time",
        performanceDesc: "Number of images uploaded, from the database.",
        byMonth: "By month",
        byDay: "By day",
        byWeek: "By week",
        byYear: "By year",
        yearLabel: "Year",
        monthLabel: "Month",
        filterByUser: "Filter by user",
        allUsers: "All users",
        usersSelected: "selected",
        topSpenders: "Top spenders",
        topSpendersDesc: "Users ranked by total net spend.",
        rank: "Rank",
        totalSpent: "Total spent",
        txnCount: "Transactions",
        netRevenue: "Net revenue",
        grossRevenue: "Gross",
        activeSubs: "Subscriptions",
        searchUser: "Search user…",
        allPlans: "All plans",
        allStatuses: "All statuses",
        allTime: "All time",
        rangeToday: "Today",
        range7d: "Last 7 days",
        range30d: "Last 30 days",
        colDate: "Date",
        colUser: "User",
        colPlan: "Plan",
        colAmount: "Amount",
        colStatus: "Status",
        tokensCol: "Tokens",
        fileBreakdown: "File Type Breakdown",
        fileBreakdownDesc: "Storage distribution by extension.",
        totalCount: "Total",
        noData: "No data available yet.",
        // users table
        name: "Name",
        email: "Email",
        role: "Role",
        status: "Status",
        createdAt: "Created At",
        actions: "Actions",
        noUsers: "No users found matching your criteria.",
        allStatus: "All Status",
        active: "Active",
        inactive: "Inactive",
        filterBy: "Filter by status",
        clearFilters: "Clear filters",
        on: "ON",
        off: "OFF",
        // role / status labels
        roleAdmin: "Admin",
        roleUser: "User",
        statusActive: "Active",
        statusInactive: "Inactive",
        statusCompleted: "Completed",
        statusFailed: "Failed",
        statusPending: "Pending",
        statusProcessing: "Processing",
        // agents
        successRate: "Success Rate",
        avgLatency: "Avg Latency",
        liveLabel: "Live",
        noAgents: "No agents registered yet.",
        noDescription: "No description.",
        // projects
        userIdLabel: "User ID",
        ownerLabel: "Owner",
        untitledProject: "Untitled Project",
        noProjects: "No projects found.",
        // images
        imageCol: "Image",
        projectCol: "Project",
        uploadedAt: "Uploaded At",
        noImages: "No images found.",
        // files
        filename: "Filename",
        extension: "Type",
        sizeCol: "Size",
        modifiedAt: "Modified",
        noFiles: "No files in the upload directory.",
        uploadDir: "Upload Directory",
        // logs
        logsConsole: "System Events Console",
        levelCol: "Level",
        noLogs: "No log entries yet.",
        // delete modal
        confirmDeleteProject: "Delete this project?",
        confirmDeleteImage: "Delete this image?",
        confirmDeleteFile: "Delete this file?",
        deleteConfirmDesc: "This action cannot be undone. All related records will be permanently removed.",
        cancel: "Cancel",
        delete: "Delete",
        deleting: "Deleting...",
        // detail modals + extras
        close: "Close",
        viewDetail: "View detail",
        adminLockTip: "Admin accounts cannot be deactivated",
        projectDetailTitle: "Project Detail",
        imageDetailTitle: "Analysis Detail",
        noAnalysis: "No stored analysis for this image yet.",
        styleLabel: "Architectural Style",
        confidenceLabel: "Confidence",
        processingLabel: "Processing Time",
        distributionLabel: "Style Distribution",
        componentsLabel: "Components Detected",
        evidenceSheetLabel: "Evidence (12 dimensions)",
        evidenceLabel: "Key Evidence",
        compositionLabel: "Composition Explanation",
        viewOriginal: "Original",
        viewBoxes: "Detections",
        viewHeatmap: "Heatmap",
        uncertainBadge: "Uncertain",
        degradedBadge: "Degraded",
        orphanBadge: "Orphan",
        orphanTip: "File not referenced by any database record",
        linkedBadge: "Linked",
        linkedDeleteTip: "Linked to an analysis — delete the analysis (Analysis tab) to remove this file",
        preview: "Preview",
        modelLabel: "Model",
        allLevels: "All levels",
        openImage: "Open analysis",
        rename: "Rename",
        save: "Save",
        allTypes: "All types",
        sizeAsc: "Size ↑",
        sizeDesc: "Size ↓",
        // knowledge base
        knowledge: "Knowledge Base",
        kbStylesTab: "Styles",
        kbFamiliesTab: "Families",
        kbSuggestionsTab: "Suggestions",
        kbAllFamilies: "All families",
        addStyle: "Add style",
        editStyle: "Edit style",
        newStyle: "New style",
        kbId: "ID (slug)",
        kbName: "Name",
        kbAliases: "Aliases",
        kbParent: "Family",
        kbRegion: "Region",
        kbPeriod: "Period",
        kbFeatures: "Defining features",
        kbProfile: "Expected profile",
        kbDescription: "Description",
        kbReferences: "References",
        kbListHint: "one per line",
        kbProfileHint: "one key: value per line",
        kbAatHelp: "ID in the Getty Art & Architecture Thesaurus (AAT), the standard vocabulary for art/architecture terms. Used to trace the source of the style name. If set, it becomes a clickable link.",
        kbWikidataHelp: "Wikidata Q-item id (e.g. Q176483); property P149 is \"architectural style\". If set, it becomes a clickable link.",
        kbProfileHelp: "Expected feature values per dimension (massing/supports/material…). The system matches these against features observed in the image to name the style more accurately (feature retrieval).",
        kbReferencesHelp: "One source per line. Prefer full citations (author, year, book/database) so it can be looked up on Google Scholar.",
        kbRequiredMissing: "Please fill in the required fields:",
        kbDeleteImpact: "This removes the entry from the knowledge base (a JSON file). It does NOT affect saved analyses; future analyses will simply no longer name this style.",
        kbEditImpact: "Changes apply only to FUTURE analyses. Saved analyses keep their original result.",
        kbSourcesLegend: "Common sources (full citations)",
        kbViewSource: "View full citation",
        kbStylesTabReq: "required",
        kbNoStyles: "No styles found.",
        kbStylesCount: "styles",
        confirmDeleteStyle: "Delete this style?",
        addFamily: "Add family",
        familyName: "Family name",
        familyId: "Family ID (slug)",
        kbNoFamilies: "No families yet.",
        kbStylesInFamily: "styles",
        deleteFamilyBlocked: "Cannot delete a family that still has styles.",
        kbNoSuggestions: "No pending suggestions. Out-of-KB names proposed during analysis appear here.",
        kbSuggestionsDesc: "Style names the AI proposed that are not in the knowledge base — review and add or dismiss.",
        seenCount: "seen",
        promoteToKb: "Add to KB",
        dismiss: "Dismiss",
        kbSaved: "Saved.",
        kbIdImmutable: "ID cannot be changed after creation."
    },
    vi: {
        // nav + chrome
        dashboard: "Bảng điều khiển",
        users: "Người dùng",
        projects: "Dự án",
        images: "Phân tích",
        agents: "Tác tử AI",
        revenue: "Doanh thu",
        logs: "Nhật ký hệ thống",
        files: "Trình duyệt tệp",
        apikeys: "Khóa API",
        content: "Nội dung",
        plans: "Quản lý gói",
        userMode: "Chế độ người dùng",
        logout: "Đăng xuất",
        adminLabel: "Quản trị",
        search: "Tìm kiếm...",
        refresh: "Làm mới",
        loading: "Đang tải...",
        loadError: "Không tải được dữ liệu",
        // header identity
        systemRoot: "Quản trị viên",
        // dashboard cards
        totalFiles: "Tổng số tệp",
        totalSize: "Dung lượng",
        activeUsers: "Người dùng hoạt động",
        fileTypes: "loại tệp",
        usersTotal: "tổng người dùng",
        runsLabel: "lượt chạy",
        storedAt: "Lưu tại",
        // charts
        systemPerformance: "Lượt tải lên theo thời gian",
        performanceDesc: "Số ảnh được tải lên, lấy từ cơ sở dữ liệu.",
        byMonth: "Theo tháng",
        byDay: "Theo ngày",
        byWeek: "Theo tuần",
        byYear: "Theo năm",
        yearLabel: "Năm",
        monthLabel: "Tháng",
        filterByUser: "Lọc theo người dùng",
        allUsers: "Tất cả người dùng",
        usersSelected: "đã chọn",
        topSpenders: "Bảng xếp hạng chi tiêu",
        topSpendersDesc: "Người dùng xếp theo tổng chi tiêu thực.",
        rank: "Hạng",
        totalSpent: "Tổng chi",
        txnCount: "Số giao dịch",
        netRevenue: "Doanh thu thực",
        grossRevenue: "Tổng thu",
        activeSubs: "Gói đang hoạt động",
        searchUser: "Tìm người dùng…",
        allPlans: "Tất cả gói",
        allStatuses: "Tất cả trạng thái",
        allTime: "Tất cả thời gian",
        rangeToday: "Hôm nay",
        range7d: "7 ngày qua",
        range30d: "30 ngày qua",
        colDate: "Ngày",
        colUser: "Người dùng",
        colPlan: "Gói",
        colAmount: "Số tiền",
        colStatus: "Trạng thái",
        tokensCol: "Token",
        fileBreakdown: "Phân loại tệp tin",
        fileBreakdownDesc: "Phân bổ dung lượng theo định dạng tệp.",
        totalCount: "Tổng",
        noData: "Chưa có dữ liệu.",
        // users table
        name: "Tên",
        email: "Email",
        role: "Vai trò",
        status: "Trạng thái",
        createdAt: "Ngày tạo",
        actions: "Hành động",
        noUsers: "Không tìm thấy người dùng phù hợp.",
        allStatus: "Tất cả trạng thái",
        active: "Hoạt động",
        inactive: "Ngừng hoạt động",
        filterBy: "Lọc theo trạng thái",
        clearFilters: "Xóa bộ lọc",
        on: "Bật",
        off: "Tắt",
        // role / status labels
        roleAdmin: "Quản trị",
        roleUser: "Người dùng",
        statusActive: "Hoạt động",
        statusInactive: "Ngừng hoạt động",
        statusCompleted: "Hoàn tất",
        statusFailed: "Thất bại",
        statusPending: "Chờ xử lý",
        statusProcessing: "Đang xử lý",
        // agents
        successRate: "Tỷ lệ thành công",
        avgLatency: "Độ trễ TB",
        liveLabel: "Trực tuyến",
        noAgents: "Chưa có tác tử nào được đăng ký.",
        noDescription: "Không có mô tả.",
        // projects
        userIdLabel: "Mã người dùng",
        ownerLabel: "Chủ sở hữu",
        untitledProject: "Dự án chưa đặt tên",
        noProjects: "Không tìm thấy dự án nào.",
        // images
        imageCol: "Hình ảnh",
        projectCol: "Dự án",
        uploadedAt: "Ngày tải lên",
        noImages: "Không tìm thấy hình ảnh nào.",
        // files
        filename: "Tên tệp",
        extension: "Loại",
        sizeCol: "Kích thước",
        modifiedAt: "Sửa đổi",
        noFiles: "Không có tệp nào trong thư mục tải lên.",
        uploadDir: "Thư mục tải lên",
        // logs
        logsConsole: "Bảng điều khiển sự kiện hệ thống",
        levelCol: "Mức độ",
        noLogs: "Chưa có bản ghi nhật ký nào.",
        // delete modal
        confirmDeleteProject: "Xóa dự án này?",
        confirmDeleteImage: "Xóa hình ảnh này?",
        confirmDeleteFile: "Xóa tệp này?",
        deleteConfirmDesc: "Hành động này không thể hoàn tác. Mọi bản ghi liên quan sẽ bị xóa vĩnh viễn.",
        cancel: "Hủy",
        delete: "Xóa",
        deleting: "Đang xóa...",
        // detail modals + extras
        close: "Đóng",
        viewDetail: "Xem chi tiết",
        adminLockTip: "Không thể vô hiệu hóa tài khoản admin",
        projectDetailTitle: "Chi tiết dự án",
        imageDetailTitle: "Chi tiết phân tích",
        noAnalysis: "Chưa có phân tích nào được lưu cho ảnh này.",
        styleLabel: "Phong cách kiến trúc",
        confidenceLabel: "Độ tin cậy",
        processingLabel: "Thời gian xử lý",
        distributionLabel: "Phân bố phong cách",
        componentsLabel: "Thành phần phát hiện",
        evidenceSheetLabel: "Bằng chứng (12 chiều)",
        evidenceLabel: "Bằng chứng chính",
        compositionLabel: "Giải thích tổ hợp",
        viewOriginal: "Ảnh gốc",
        viewBoxes: "Thành phần",
        viewHeatmap: "Bản đồ nhiệt",
        uncertainBadge: "Chưa chắc chắn",
        degradedBadge: "Suy giảm",
        orphanBadge: "Mồ côi",
        orphanTip: "Tệp không còn bản ghi nào trong cơ sở dữ liệu",
        linkedBadge: "Đã liên kết",
        linkedDeleteTip: "Đang liên kết một phân tích — xóa phân tích đó (tab Phân tích) để dọn tệp này",
        preview: "Xem trước",
        modelLabel: "Mô hình",
        allLevels: "Tất cả mức",
        openImage: "Mở phân tích",
        rename: "Đổi tên",
        save: "Lưu",
        allTypes: "Tất cả loại",
        sizeAsc: "Kích thước ↑",
        sizeDesc: "Kích thước ↓",
        // knowledge base
        knowledge: "Cơ sở tri thức",
        kbStylesTab: "Phong cách",
        kbFamiliesTab: "Họ",
        kbSuggestionsTab: "Đề xuất",
        kbAllFamilies: "Tất cả họ",
        addStyle: "Thêm phong cách",
        editStyle: "Sửa phong cách",
        newStyle: "Phong cách mới",
        kbId: "ID (slug)",
        kbName: "Tên",
        kbAliases: "Tên gọi khác",
        kbParent: "Họ",
        kbRegion: "Khu vực",
        kbPeriod: "Thời kỳ",
        kbFeatures: "Đặc trưng nhận dạng",
        kbProfile: "Hồ sơ kỳ vọng",
        kbDescription: "Mô tả",
        kbReferences: "Nguồn tham khảo",
        kbListHint: "mỗi mục một dòng",
        kbProfileHint: "mỗi dòng dạng khóa: giá trị",
        kbAatHelp: "Mã trong Getty Art & Architecture Thesaurus (AAT) — từ điển chuẩn quốc tế về thuật ngữ nghệ thuật/kiến trúc, dùng để truy nguồn tên phong cách. Nếu có, sẽ hiển thị thành liên kết bấm được.",
        kbWikidataHelp: "Mã Q-item trên Wikidata (vd Q176483); thuộc tính P149 = \"phong cách kiến trúc\". Nếu có, sẽ hiển thị thành liên kết bấm được.",
        kbProfileHelp: "Đặc trưng KỲ VỌNG theo từng chiều (massing/supports/material…). Hệ thống so khớp với đặc trưng quan sát được từ ảnh để gọi tên phong cách chính xác hơn (feature retrieval).",
        kbReferencesHelp: "Mỗi dòng một nguồn. Nên ghi trích dẫn đầy đủ (tác giả, năm, tên sách/CSDL) để có thể tra trên Google Scholar.",
        kbRequiredMissing: "Vui lòng nhập các trường bắt buộc:",
        kbDeleteImpact: "Thao tác này xóa mục khỏi cơ sở tri thức (file JSON). KHÔNG ảnh hưởng các phân tích đã lưu; phân tích tương lai chỉ đơn giản không còn gọi tên phong cách này.",
        kbEditImpact: "Thay đổi chỉ áp dụng cho phân tích TƯƠNG LAI. Phân tích đã lưu giữ nguyên kết quả gốc.",
        kbSourcesLegend: "Nguồn dùng chung (trích dẫn đầy đủ)",
        kbViewSource: "Xem trích dẫn đầy đủ",
        kbStylesTabReq: "bắt buộc",
        kbNoStyles: "Không tìm thấy phong cách nào.",
        kbStylesCount: "phong cách",
        confirmDeleteStyle: "Xóa phong cách này?",
        addFamily: "Thêm họ",
        familyName: "Tên họ",
        familyId: "ID họ (slug)",
        kbNoFamilies: "Chưa có họ nào.",
        kbStylesInFamily: "phong cách",
        deleteFamilyBlocked: "Không thể xóa họ đang còn phong cách.",
        kbNoSuggestions: "Chưa có đề xuất nào. Các tên ngoài KB do AI đề xuất khi phân tích sẽ hiện ở đây.",
        kbSuggestionsDesc: "Các tên phong cách AI đề xuất nhưng chưa có trong cơ sở tri thức — duyệt để thêm hoặc bỏ qua.",
        seenCount: "lần gặp",
        promoteToKb: "Thêm vào KB",
        dismiss: "Bỏ qua",
        kbSaved: "Đã lưu.",
        kbIdImmutable: "Không thể đổi ID sau khi tạo."
    }
};

// Colour palette for the file-type pie chart (cycled by extension index).
const PALETTE = ['#00d2ff', '#9d50bb', '#6366f1', '#f43f5e', '#22c55e', '#f59e0b', '#14b8a6'];

// The 5 agents actually used by the open-vocabulary pipeline. Keyed by the
// (ASCII-safe) AgentName stored in the DB, so the admin roster shows rich,
// correctly-encoded bilingual labels regardless of the DB column's collation.
// Any other agent rows (e.g. legacy "Agent 1..7") are hidden.
const AGENT_META = {
    'Agent A': {
        en: 'Agent A — Evidence Extraction',
        vi: 'Tác tử A — Trích xuất bằng chứng',
        descEn: 'Fills the 12-dimension evidence sheet from the image (vision).',
        descVi: 'Điền phiếu bằng chứng 12 chiều từ ảnh (thị giác).'
    },
    'Panel: Gemini': {
        en: 'Judge — Gemini',
        vi: 'Giám khảo — Gemini',
        descEn: 'Independent judge scoring the style mixture (Gemini).',
        descVi: 'Giám khảo độc lập chấm hỗn hợp phong cách (Gemini).'
    },
    'Panel: OpenAI': {
        en: 'Judge — OpenAI',
        vi: 'Giám khảo — OpenAI',
        descEn: 'Independent judge scoring the style mixture (OpenAI).',
        descVi: 'Giám khảo độc lập chấm hỗn hợp phong cách (OpenAI).'
    },
    'Panel: Grok': {
        en: 'Judge — Grok',
        vi: 'Giám khảo — Grok',
        descEn: 'Independent judge scoring the style mixture (Grok, vision).',
        descVi: 'Giám khảo độc lập chấm hỗn hợp phong cách (Grok, thị giác).'
    },
    'Arbiter': {
        en: 'Arbiter — Final Decision',
        vi: 'Trọng tài — Quyết định cuối',
        descEn: 'Reconciles the 3 verdicts + image into the final answer (CoT).',
        descVi: 'Hợp nhất 3 phiếu + ảnh thành kết quả cuối (suy luận từng bước).'
    }
};

// Icon + bilingual label + canonical order for the 12 evidence-sheet dimensions
// Agent A fills in. Used to render the analysis-detail evidence as tidy grouped
// cards (one per dimension) instead of a flat pill cloud. Mirrors UserPage.
const DIMENSION_META = {
    massing: { icon: '🏗️', en: 'Massing', vi: 'Khối tổng thể' },
    roof: { icon: '🏛️', en: 'Roof', vi: 'Mái' },
    supports: { icon: '🏛️', en: 'Supports', vi: 'Hệ đỡ / cột' },
    arch: { icon: '⛪', en: 'Arches', vi: 'Vòm cuốn' },
    openings: { icon: '🪟', en: 'Openings', vi: 'Cửa mở' },
    facade: { icon: '🧱', en: 'Facade', vi: 'Mặt tiền' },
    ornament: { icon: '✨', en: 'Ornament', vi: 'Trang trí' },
    material: { icon: '🪨', en: 'Material', vi: 'Vật liệu' },
    verticals: { icon: '📐', en: 'Verticals', vi: 'Yếu tố đứng' },
    vault_dome: { icon: '🔵', en: 'Vault / Dome', vi: 'Vòm mái / dome' },
    spatial_org: { icon: '📊', en: 'Spatial org.', vi: 'Tổ chức không gian' },
    diagnostic: { icon: '🔍', en: 'Diagnostic', vi: 'Chẩn đoán' },
};
const DIMENSION_ORDER = Object.keys(DIMENSION_META);

// Full citations for the abbreviated source names commonly used in the KB
// `references` field. Keys are matched case-insensitively against each
// reference string so they can be expanded to a Scholar-searchable citation in
// the UI without rewriting the underlying styles.json data.
const SOURCE_CITATIONS = {
    'ching': 'Ching, F. D. K., Jarzombek, M. M., & Prakash, V. (2017). A Global History of Architecture (3rd ed.). Wiley.',
    'banister fletcher': 'Fletcher, B. (1996). A History of Architecture (20th ed.). Architectural Press.',
    'fletcher': 'Fletcher, B. (1996). A History of Architecture (20th ed.). Architectural Press.',
    'getty aat': 'Getty Research Institute. Art & Architecture Thesaurus (AAT). https://www.getty.edu/research/tools/vocabularies/aat/',
    'aat': 'Getty Research Institute. Art & Architecture Thesaurus (AAT). https://www.getty.edu/research/tools/vocabularies/aat/',
    'wikidata p149': 'Wikidata. Property P149 — architectural style. https://www.wikidata.org/wiki/Property:P149',
    'wikidata': 'Wikidata. https://www.wikidata.org/',
};

/**
 * Group a flat evidence-item list by dimension, in canonical order, with any
 * unknown dimensions appended alphabetically. Returns [{ dimension, items }].
 */
function groupEvidenceByDimension(items) {
    const grouped = {};
    for (const it of items) {
        const key = it.dimension || 'diagnostic';
        (grouped[key] = grouped[key] || []).push(it);
    }
    const known = DIMENSION_ORDER.filter((d) => grouped[d]).map((d) => ({ dimension: d, items: grouped[d] }));
    const extra = Object.keys(grouped)
        .filter((d) => !DIMENSION_ORDER.includes(d))
        .sort()
        .map((d) => ({ dimension: d, items: grouped[d] }));
    return [...known, ...extra];
}

/**
 * Lazily-loaded image thumbnail for an analysis row. Fetches the original
 * bytes (auth-protected) as an object URL on mount and revokes it on unmount.
 * Module-level so its component type is stable across parent re-renders.
 */
function AdminThumb({ imageId, theme }) {
    const [url, setUrl] = useState(null);
    useEffect(() => {
        let cancelled = false;
        let objUrl = null;
        adminGetImageRaw(imageId)
            .then((u) => {
                if (cancelled) { URL.revokeObjectURL(u); return; }
                objUrl = u;
                setUrl(u);
            })
            .catch(() => {});
        return () => { cancelled = true; if (objUrl) URL.revokeObjectURL(objUrl); };
    }, [imageId]);
    return (
        <div className={`w-12 h-10 rounded-lg overflow-hidden flex items-center justify-center border flex-shrink-0 ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-slate-100 border-slate-200'}`}>
            {url ? <img src={url} alt="" className="w-full h-full object-cover" /> : <ImageIcon size={18} className="opacity-40" />}
        </div>
    );
}

/**
 * ADMIN DASHBOARD — all data is fetched live from the /admin API (DB-backed).
 */
const App = () => {
    const { theme, lang, toggleTheme, toggleLang } = useApp();
    const [activeSection, setActiveSection] = useState('dashboard');
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);

    const [searchTerm, setSearchTerm] = useState("");
    const [statusFilter, setStatusFilter] = useState("all");
    const [isFilterOpen, setIsFilterOpen] = useState(false);
    const filterRef = useRef(null);

    // Uploads chart controls: granularity (months of a year / days of a month).
    const now = new Date();
    const [chartMode, setChartMode] = useState('monthly'); // 'monthly' | 'daily'
    const [chartYear, setChartYear] = useState(now.getFullYear());
    const [chartMonth, setChartMonth] = useState(now.getMonth() + 1);
    const [activePie, setActivePie] = useState(null); // hovered pie slice for centre overlay

    // Project rename inline editing: { id, value } or null.
    const [editingProject, setEditingProject] = useState(null);
    const [renamingId, setRenamingId] = useState(null);

    // File browser controls.
    const [fileTypeFilter, setFileTypeFilter] = useState('all');
    const [fileSort, setFileSort] = useState('none'); // 'none' | 'asc' | 'desc'

    // Live data from the backend.
    const [stats, setStats] = useState(null);
    const [users, setUsers] = useState([]);
    const [projects, setProjects] = useState([]);
    const [images, setImages] = useState([]);
    const [agents, setAgents] = useState([]);
    const [logs, setLogs] = useState([]);
    const [files, setFiles] = useState([]);
    const [revenue, setRevenue] = useState(null);
    const [revenueTxns, setRevenueTxns] = useState([]);
    const [revenueGranularity, setRevenueGranularity] = useState('month'); // 'week'|'month'|'year'
    const [revenueUserIds, setRevenueUserIds] = useState([]);              // [] = all users (aggregate)
    const [revenueByUser, setRevenueByUser] = useState(null);
    // Client-side filters for the loaded transactions table (last 100 txns).
    const [txnSearch, setTxnSearch] = useState('');         // matches user email
    const [txnPlan, setTxnPlan] = useState('all');          // plan_code
    const [txnStatus, setTxnStatus] = useState('all');      // status
    const [txnRange, setTxnRange] = useState('all');        // 'today'|'7d'|'30d'|'all'
    const [topSpenders, setTopSpenders] = useState([]);
    const [revUserMenuOpen, setRevUserMenuOpen] = useState(false);
    const revUserMenuRef = useRef(null);
    const [profile, setProfile] = useState(null);
    const [loading, setLoading] = useState({});
    const [error, setError] = useState(null);

    // Delete confirmation modal target: { type: 'project'|'image'|'file', id, name }.
    const [deleteTarget, setDeleteTarget] = useState(null);
    const [deleting, setDeleting] = useState(false);

    // Logs level filter (null = all).
    const [logLevel, setLogLevel] = useState(null);

    // Detail modals + file preview lightbox.
    const [projectDetail, setProjectDetail] = useState(null); // { loading, data, error }
    const [imageDetail, setImageDetail] = useState(null);     // { loading, data, error, url, view }
    const [filePreview, setFilePreview] = useState(null);     // { url, name }

    // Knowledge Base management.
    const [kbStyles, setKbStyles] = useState([]);
    const [kbFamilies, setKbFamilies] = useState([]);
    const [kbSuggestions, setKbSuggestions] = useState([]);
    const [kbTab, setKbTab] = useState('styles');           // 'styles' | 'families' | 'suggestions'
    const [kbSearch, setKbSearch] = useState('');
    const [kbFamilyFilter, setKbFamilyFilter] = useState('all');
    const [kbEditing, setKbEditing] = useState(null);       // style form draft or null
    const [kbSaving, setKbSaving] = useState(false);
    const [kbFormError, setKbFormError] = useState(null);
    const [kbDeleteStyle, setKbDeleteStyle] = useState(null); // style pending delete confirm
    const [newFamily, setNewFamily] = useState({ id: '', name: '' });

    const { logout } = useAuth();
    const navigate = useNavigate();
    const handleLogout = () => {
        logout();
        navigate('/');
    };

    const t = translations[lang];

    // Explicit SVG tick so axis numbers are reliably white in dark mode
    // (passing tick={{ fill }} did not always apply in this recharts build).
    const renderAxisTick = useCallback((props) => {
        const { x, y, payload, textAnchor } = props;
        const isX = textAnchor === 'middle';
        return (
            <text
                x={x}
                y={y}
                dy={isX ? 14 : 4}
                textAnchor={textAnchor || (isX ? 'middle' : 'end')}
                fill={theme === 'dark' ? '#ffffff' : '#475569'}
                fontSize={11}
                fontWeight="bold"
            >
                {payload?.value}
            </text>
        );
    }, [theme]);

    // Generic loader that tracks per-resource loading state and surfaces errors.
    const load = useCallback(async (key, fn, setter) => {
        setLoading(prev => ({ ...prev, [key]: true }));
        try {
            setter(await fn());
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(prev => ({ ...prev, [key]: false }));
        }
    }, []);

    const loadLogs = useCallback(() => {
        load('logs', () => adminGetLogs(200, logLevel), (d) => setLogs(d.logs || []));
    }, [load, logLevel]);

    const loadAll = useCallback(() => {
        setError(null);
        load('stats', adminGetStats, (d) => setStats(d));
        load('users', adminGetUsers, (d) => setUsers(d.users || []));
        load('projects', adminGetProjects, (d) => setProjects(d.projects || []));
        load('images', adminGetImages, (d) => setImages(d.images || []));
        load('agents', adminGetAgents, (d) => setAgents(d.agents || []));
        load('files', adminGetFiles, (d) => setFiles(d.files || []));
    }, [load]);

    // Aggregate (all users) vs per-user comparison depends on the selection.
    const loadRevenue = useCallback(() => {
        if (revenueUserIds.length > 0) {
            load('revenueByUser', () => adminGetRevenueByUser(revenueUserIds, revenueGranularity), (d) => setRevenueByUser(d));
        } else {
            load('revenue', () => adminGetRevenue(revenueGranularity), (d) => setRevenue(d));
        }
    }, [load, revenueGranularity, revenueUserIds]);

    // Transactions + leaderboard don't depend on granularity/user selection.
    const loadRevenueAux = useCallback(() => {
        load('revenueTxns', () => adminGetTransactions(null, 100), (d) => setRevenueTxns(d.transactions || []));
        load('topSpenders', () => adminGetTopSpenders(10), (d) => setTopSpenders(d.spenders || []));
    }, [load]);

    const loadKb = useCallback(() => {
        load('kbStyles', adminKbListStyles, (d) => setKbStyles(d.styles || []));
        load('kbFamilies', adminKbListFamilies, (d) => setKbFamilies(d.families || []));
        load('kbSuggestions', adminKbListSuggestions, (d) => setKbSuggestions(d.suggestions || []));
    }, [load]);

    const refreshAll = useCallback(() => {
        loadAll();
        loadLogs();
        loadKb();
    }, [loadAll, loadLogs, loadKb]);

    useEffect(() => {
        loadAll();
        loadKb();
        loadRevenueAux();
        getMe().then(setProfile).catch(() => setProfile(null));
    }, [loadAll, loadKb, loadRevenueAux]);

    // Re-fetch the revenue series whenever granularity / user selection changes.
    useEffect(() => {
        loadRevenue();
    }, [loadRevenue]);

    // Close the multi-user filter dropdown on outside click.
    useEffect(() => {
        const onClick = (e) => {
            if (revUserMenuRef.current && !revUserMenuRef.current.contains(e.target)) {
                setRevUserMenuOpen(false);
            }
        };
        document.addEventListener('mousedown', onClick);
        return () => document.removeEventListener('mousedown', onClick);
    }, []);

    // Reload logs whenever the level filter changes (and on first mount).
    useEffect(() => {
        loadLogs();
    }, [loadLogs]);

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (filterRef.current && !filterRef.current.contains(event.target)) {
                setIsFilterOpen(false);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    // ── Formatting + label helpers ──────────────────────────────────────────
    const locale = lang === 'vi' ? 'vi-VN' : 'en-US';
    const fmtDate = (s) => (s ? new Date(s).toLocaleDateString(locale) : '—');
    const fmtDateTime = (s) => (s ? new Date(s).toLocaleString(locale) : '—');
    const basename = (p) => (p || '').split(/[\\/]/).pop() || '—';

    const labelFor = useCallback((key) => {
        const map = {
            active: t.statusActive, inactive: t.statusInactive,
            admin: t.roleAdmin, user: t.roleUser,
            completed: t.statusCompleted, failed: t.statusFailed,
            pending: t.statusPending, processing: t.statusProcessing, queued: t.statusPending
        };
        return map[key] || key;
    }, [t]);

    // ── Derived dashboard data ──────────────────────────────────────────────
    const activeUsersCount = useMemo(() => users.filter(u => u.is_active).length, [users]);
    const totalRuns = useMemo(() => agents.reduce((s, a) => s + (a.total_runs || 0), 0), [agents]);

    const fileBreakdown = useMemo(
        () => (stats?.breakdown_by_type || []).map((b, i) => ({
            name: (b.extension || '?').toUpperCase(),
            value: b.count,
            color: PALETTE[i % PALETTE.length]
        })),
        [stats]
    );

    // Years that actually have uploads (for the chart year selector).
    const uploadYears = useMemo(() => {
        const ys = new Set([now.getFullYear()]);
        images.forEach((img) => { if (img.uploaded_at) ys.add(new Date(img.uploaded_at).getFullYear()); });
        return [...ys].sort((a, b) => b - a);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [images]);

    // Time-series driven by the chart controls:
    //  - monthly: 12 buckets (Jan..Dec) for the selected year
    //  - daily: one bucket per day of the selected month/year
    const performanceData = useMemo(() => {
        if (chartMode === 'daily') {
            const days = new Date(chartYear, chartMonth, 0).getDate();
            const buckets = new Array(days).fill(0);
            for (const img of images) {
                if (!img.uploaded_at) continue;
                const d = new Date(img.uploaded_at);
                if (d.getFullYear() === Number(chartYear) && d.getMonth() + 1 === Number(chartMonth)) {
                    buckets[d.getDate() - 1] += 1;
                }
            }
            return buckets.map((files, i) => ({ name: String(i + 1), files }));
        }
        const buckets = new Array(12).fill(0);
        for (const img of images) {
            if (!img.uploaded_at) continue;
            const d = new Date(img.uploaded_at);
            if (d.getFullYear() === Number(chartYear)) buckets[d.getMonth()] += 1;
        }
        return buckets.map((files, i) => ({
            name: new Date(Number(chartYear), i, 1).toLocaleString(locale, { month: 'short' }),
            files
        }));
    }, [images, locale, chartMode, chartYear, chartMonth]);

    const adminView = useMemo(() => {
        const claims = jwtClaims();
        return {
            name: claims.name || profile?.name || claims.email || 'Admin',
            role: profile?.role || claims.role || 'admin',
            picture: profile?.picture || null
        };
    }, [profile]);

    // Distinct file extensions present (for the file-type filter dropdown).
    const fileExtensions = useMemo(() => {
        const exts = new Set();
        files.forEach((f) => { if (f.extension) exts.add(f.extension.toLowerCase()); });
        return [...exts].sort();
    }, [files]);

    // Files after applying the type filter + size sort.
    const displayedFiles = useMemo(() => {
        let out = files;
        if (fileTypeFilter !== 'all') {
            out = out.filter((f) => (f.extension || '').toLowerCase() === fileTypeFilter);
        }
        if (fileSort !== 'none') {
            out = [...out].sort((a, b) =>
                fileSort === 'asc' ? a.size_bytes - b.size_bytes : b.size_bytes - a.size_bytes
            );
        }
        return out;
    }, [files, fileTypeFilter, fileSort]);

    // ── Mutations ───────────────────────────────────────────────────────────
    const handleToggleUser = async (user) => {
        const next = !user.is_active;
        setUsers(prev => prev.map(u => u.user_id === user.user_id ? { ...u, is_active: next } : u));
        try {
            await adminUpdateUserStatus(user.user_id, next);
        } catch (e) {
            setError(e.message);
            setUsers(prev => prev.map(u => u.user_id === user.user_id ? { ...u, is_active: !next } : u));
        }
    };

    const confirmDelete = async () => {
        if (!deleteTarget) return;
        setDeleting(true);
        try {
            if (deleteTarget.type === 'project') {
                await adminDeleteProject(deleteTarget.id);
                setProjects(prev => prev.filter(p => p.project_id !== deleteTarget.id));
            } else if (deleteTarget.type === 'file') {
                await adminDeleteFile(deleteTarget.id);
                setFiles(prev => prev.filter(f => f.file_id !== deleteTarget.id));
            } else {
                await adminDeleteImage(deleteTarget.id);
                setImages(prev => prev.filter(im => im.image_id !== deleteTarget.id));
            }
            setDeleteTarget(null);
        } catch (e) {
            setError(e.message);
        } finally {
            setDeleting(false);
        }
    };

    const handleRenameProject = async (projectId) => {
        const name = (editingProject?.value || '').trim();
        if (!name) { setEditingProject(null); return; }
        setRenamingId(projectId);
        try {
            const res = await adminRenameProject(projectId, name);
            setProjects(prev => prev.map(p => p.project_id === projectId ? { ...p, project_name: res.project_name } : p));
            setEditingProject(null);
        } catch (e) {
            setError(e.message);
        } finally {
            setRenamingId(null);
        }
    };

    // ── Detail modals + file preview ─────────────────────────────────────────
    const stemOf = (p) => {
        const b = basename(p);
        const i = b.lastIndexOf('.');
        return i > 0 ? b.slice(0, i) : b;
    };
    // File-ids referenced by a DB Image row — used to flag orphaned files.
    const referencedFileIds = useMemo(
        () => new Set(images.map(im => stemOf(im.image_path))),
        [images]
    );

    const openProjectDetail = async (projectId) => {
        setProjectDetail({ loading: true, data: null, error: null });
        try {
            const data = await adminGetProjectDetail(projectId);
            setProjectDetail({ loading: false, data, error: null });
        } catch (e) {
            setProjectDetail({ loading: false, data: null, error: e.message });
        }
    };

    const openImageDetail = async (imageId) => {
        setImageDetail({ loading: true, data: null, error: null, url: null, view: 'original' });
        try {
            const data = await adminGetImageDetail(imageId);
            let url = null;
            try { url = await adminGetImageRaw(imageId); } catch { /* preview optional */ }
            setImageDetail({ loading: false, data, error: null, url, view: 'original' });
        } catch (e) {
            setImageDetail({ loading: false, data: null, error: e.message, url: null, view: 'original' });
        }
    };

    const closeImageDetail = () => {
        if (imageDetail?.url) URL.revokeObjectURL(imageDetail.url);
        setImageDetail(null);
    };

    const openFilePreview = async (file) => {
        try {
            const url = await adminGetFileRaw(file.file_id);
            setFilePreview({ url, name: file.filename });
        } catch (e) {
            setError(e.message);
        }
    };

    const closeFilePreview = () => {
        if (filePreview?.url) URL.revokeObjectURL(filePreview.url);
        setFilePreview(null);
    };

    const filteredUsers = users.filter(user => {
        const name = (user.name || '').toLowerCase();
        const email = (user.email || '').toLowerCase();
        const term = searchTerm.toLowerCase();
        const matchesSearch = name.includes(term) || email.includes(term);
        const statusKey = user.is_active ? 'active' : 'inactive';
        const matchesFilter = statusFilter === "all" || statusKey === statusFilter;
        return matchesSearch && matchesFilter;
    });

    // ── Reusable presentational pieces ──────────────────────────────────────
    // Wrapped in useCallback so their function identity is stable across
    // re-renders. Without this, typing in the Users search box re-creates these
    // components on every keystroke, React remounts the subtree, and the input
    // loses focus — which made the search feel broken.
    const GlassCard = useCallback(({ children, className = "", hoverType = "blue" }) => {
        const hoverStyles = {
            blue: "hover:shadow-[0_0_30px_rgba(0,210,255,0.3)] hover:border-[#00d2ff]/60",
            purple: "hover:shadow-[0_0_30px_rgba(157,80,187,0.3)] hover:border-[#9d50bb]/60",
            green: "hover:shadow-[0_0_30px_rgba(34,197,94,0.3)] hover:border-green-500/60",
            orange: "hover:shadow-[0_0_30px_rgba(251,146,60,0.3)] hover:border-orange-500/60"
        };
        return (
            <div className={`
        relative overflow-hidden backdrop-blur-xl transition-all duration-500 group
        ${theme === 'dark'
                    ? 'bg-black/20 border-white/10 text-white'
                    : 'bg-white/80 border-gray-200 text-slate-900 shadow-sm'}
        border rounded-[24px] p-6 hover:-translate-y-1 ${hoverStyles[hoverType]} ${className}
      `}>
                <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none bg-gradient-to-br from-white/5 to-transparent"></div>
                {children}
            </div>
        );
    }, [theme]);

    const StatusBadge = useCallback(({ statusKey }) => {
        const styles = {
            active: "bg-green-500/10 text-green-400 border-green-500/20",
            inactive: "bg-red-500/10 text-red-400 border-red-500/20",
            admin: "bg-purple-500/10 text-purple-400 border-purple-500/20",
            user: "bg-blue-500/10 text-blue-400 border-blue-500/20",
            completed: "bg-green-500/10 text-green-400 border-green-500/20",
            failed: "bg-red-500/10 text-red-400 border-red-500/20",
            pending: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
            processing: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20"
        };
        return (
            <span className={`px-3 py-1 rounded-full text-[10px] font-extrabold uppercase border ${styles[statusKey] || styles.user}`}>
                {labelFor(statusKey)}
            </span>
        );
    }, [labelFor]);

    const EmptyRow = useCallback(({ colSpan, text, isLoading }) => (
        <tr>
            <td colSpan={colSpan} className="p-16 text-center opacity-40 font-medium">
                {isLoading
                    ? <span className="flex items-center justify-center gap-2"><Loader2 size={18} className="animate-spin text-[#00d2ff]" /> {t.loading}</span>
                    : text}
            </td>
        </tr>
    ), [t]);

    // ── Revenue ─────────────────────────────────────────────────────────────
    const renderRevenue = () => {
        const fmtVnd = (n) => `${(n || 0).toLocaleString(locale)}₫`;
        const tipColor = theme === 'dark' ? '#ffffff' : '#0b0e14';
        const axisColor = theme === 'dark' ? '#ffffff' : '#475569';
        const LINE_COLORS = ['#10b981', '#00d2ff', '#9d50bb', '#f59e0b', '#ef4444', '#22d3ee', '#a3e635', '#f472b6'];
        const userMode = revenueUserIds.length > 0;

        // ── Transactions table: distinct option lists + client-side filtering ──
        const planOptions = [{ value: 'all', label: t.allPlans }, ...[...new Set(revenueTxns.map((x) => x.plan_code).filter(Boolean))].map((p) => ({ value: p, label: p }))];
        const statusOptions = [{ value: 'all', label: t.allStatuses }, ...[...new Set(revenueTxns.map((x) => x.status).filter(Boolean))].map((s) => ({ value: s, label: s }))];
        const rangeOptions = [
            { value: 'all', label: t.allTime },
            { value: 'today', label: t.rangeToday },
            { value: '7d', label: t.range7d },
            { value: '30d', label: t.range30d },
        ];
        const rangeMs = { today: 86400000, '7d': 7 * 86400000, '30d': 30 * 86400000 };
        const now = Date.now();
        const filteredTxns = revenueTxns.filter((tx) => {
            if (txnSearch && !(tx.user_email || tx.user_id || '').toLowerCase().includes(txnSearch.toLowerCase())) return false;
            if (txnPlan !== 'all' && tx.plan_code !== txnPlan) return false;
            if (txnStatus !== 'all' && tx.status !== txnStatus) return false;
            if (txnRange !== 'all') {
                if (!tx.created_at) return false;
                if (now - new Date(tx.created_at).getTime() > rangeMs[txnRange]) return false;
            }
            return true;
        });

        const series = (revenue?.series || []).map((p) => ({
            name: p.period, net: p.net, gross: p.gross,
        }));

        // Per-user comparison: pivot each user's points into one row per period.
        const userSeries = revenueByUser?.series || [];
        const periodSet = new Set();
        userSeries.forEach((s) => (s.points || []).forEach((p) => periodSet.add(p.period)));
        const periods = [...periodSet].sort();
        const multiData = periods.map((per) => {
            const row = { name: per };
            userSeries.forEach((s) => {
                const pt = (s.points || []).find((p) => p.period === per);
                row[s.user_id] = pt ? pt.net : 0;
            });
            return row;
        });
        const userLabel = (s) => s.name || s.email || (s.user_id || '').slice(0, 8);
        const hasUserData = userMode && periods.length > 0;

        const granOptions = [
            { value: 'week', label: t.byWeek },
            { value: 'month', label: t.byMonth },
            { value: 'year', label: t.byYear },
        ];

        const cards = [
            { label: t.netRevenue, value: fmtVnd(revenue?.total_net), icon: DollarSign, color: 'text-green-400', bg: 'bg-green-500/20', hover: 'green' },
            { label: t.grossRevenue, value: fmtVnd(revenue?.total_gross), icon: Wallet, color: 'text-[#00d2ff]', bg: 'bg-blue-500/20', hover: 'blue' },
            { label: t.txnCount, value: (revenue?.total_txns ?? 0).toLocaleString(locale), icon: BarChart3, color: 'text-[#9d50bb]', bg: 'bg-purple-500/20', hover: 'purple' },
            { label: t.activeSubs, value: (revenue?.active_subscriptions ?? 0).toLocaleString(locale), icon: Coins, color: 'text-orange-400', bg: 'bg-orange-500/20', hover: 'orange' },
        ];
        return (
            <div className="space-y-6 animate-in fade-in duration-500">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                    {cards.map((c, i) => (
                        <GlassCard key={i} hoverType={c.hover} className="flex flex-col justify-between">
                            <div className="flex justify-between items-start">
                                <div className="min-w-0">
                                    <p className="text-sm opacity-60 uppercase font-bold tracking-wider">{c.label}</p>
                                    <h3 className={`text-2xl font-extrabold mt-1 ${c.color} truncate`}>{c.value}</h3>
                                </div>
                                <div className={`p-3 ${c.bg} rounded-2xl flex-shrink-0`}>
                                    <c.icon className={c.color} size={24} />
                                </div>
                            </div>
                        </GlassCard>
                    ))}
                </div>

                <GlassCard hoverType="blue" className="min-h-[360px]">
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
                        <h4 className="text-lg font-bold flex items-center gap-2">
                            <Activity size={20} className="text-[#00d2ff]" /> {t.revenue}
                        </h4>
                        <div className="flex items-center gap-2 flex-wrap">
                            <FancySelect
                                theme={theme}
                                value={revenueGranularity}
                                onChange={(v) => setRevenueGranularity(v)}
                                align="right"
                                widthClass="w-[130px]"
                                options={granOptions}
                            />
                            {/* Multi-user filter (empty selection = aggregate). */}
                            <div className="relative" ref={revUserMenuRef}>
                                <button
                                    type="button"
                                    onClick={() => setRevUserMenuOpen((o) => !o)}
                                    className={`flex items-center justify-between gap-2 px-3 py-2 rounded-xl border text-xs font-bold w-[180px] transition-all
                                        ${theme === 'dark'
                                            ? 'bg-white/5 border-white/10 text-white hover:border-[#00d2ff]/50 hover:bg-white/10'
                                            : 'bg-white border-slate-200 text-slate-900 hover:border-blue-400 hover:bg-blue-50/30 shadow-sm'}`}
                                >
                                    <span className="flex items-center gap-2 min-w-0">
                                        <Users size={14} className="opacity-50 flex-shrink-0" />
                                        <span className="truncate">{revenueUserIds.length === 0 ? t.allUsers : `${revenueUserIds.length} ${t.usersSelected}`}</span>
                                    </span>
                                    <ChevronDown size={14} className={`transition-transform duration-300 flex-shrink-0 ${revUserMenuOpen ? 'rotate-180' : ''}`} />
                                </button>
                                {revUserMenuOpen && (
                                    <div className={`absolute right-0 mt-2 w-[260px] max-h-72 overflow-y-auto custom-scrollbar rounded-2xl border backdrop-blur-2xl shadow-2xl z-[100] p-1.5 animate-in slide-in-from-top-2 duration-200
                                        ${theme === 'dark' ? 'bg-[#151921]/95 border-white/20 text-white' : 'bg-white/95 border-gray-200 text-slate-900'}`}>
                                        <button
                                            type="button"
                                            onClick={() => setRevenueUserIds([])}
                                            className={`w-full text-left px-3 py-2 rounded-xl text-xs font-bold transition-all duration-150
                                                ${revenueUserIds.length === 0
                                                    ? (theme === 'dark' ? 'bg-[#00d2ff]/20 text-[#00d2ff]' : 'bg-blue-500/10 text-blue-600')
                                                    : (theme === 'dark' ? 'hover:bg-white/5 opacity-80' : 'hover:bg-gray-100')}`}
                                        >
                                            {t.allUsers}
                                        </button>
                                        <div className={`my-1 border-t ${theme === 'dark' ? 'border-white/10' : 'border-gray-200'}`} />
                                        {users.map((u) => {
                                            const checked = revenueUserIds.includes(u.user_id);
                                            return (
                                                <button
                                                    key={u.user_id}
                                                    type="button"
                                                    onClick={() => setRevenueUserIds((prev) => checked ? prev.filter((id) => id !== u.user_id) : [...prev, u.user_id])}
                                                    className={`w-full flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-bold text-left transition-all duration-150
                                                        ${theme === 'dark' ? 'hover:bg-white/5' : 'hover:bg-gray-100'}`}
                                                >
                                                    <span className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0
                                                        ${checked ? 'bg-[#00d2ff] border-[#00d2ff]' : (theme === 'dark' ? 'border-white/30' : 'border-gray-300')}`}>
                                                        {checked && <Check size={11} className="text-white" />}
                                                    </span>
                                                    <span className="truncate">{u.name || u.email || u.user_id}</span>
                                                </button>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                    <div className="h-[280px] w-full">
                        {userMode ? (
                            !hasUserData ? (
                                <div className="h-full flex items-center justify-center opacity-40 text-sm font-medium">{t.noData}</div>
                            ) : (
                                <ResponsiveContainer width="100%" height="100%">
                                    <LineChart data={multiData}>
                                        <CartesianGrid strokeDasharray="3 3" stroke={theme === 'dark' ? '#ffffff05' : '#00000005'} vertical={false} />
                                        <XAxis dataKey="name" axisLine={false} tickLine={false} stroke={axisColor} tick={renderAxisTick} />
                                        <YAxis axisLine={false} tickLine={false} stroke={axisColor} tick={renderAxisTick} allowDecimals={false} />
                                        <Tooltip
                                            formatter={(v) => fmtVnd(v)}
                                            contentStyle={{ backgroundColor: theme === 'dark' ? 'rgba(11,14,20,0.95)' : 'rgba(255,255,255,0.95)', borderRadius: '16px', border: '1px solid rgba(0,210,255,0.2)' }}
                                            labelStyle={{ color: tipColor }}
                                            itemStyle={{ color: tipColor }}
                                        />
                                        <Legend wrapperStyle={{ fontSize: 11 }} />
                                        {userSeries.map((s, i) => (
                                            <Line key={s.user_id} type="monotone" dataKey={s.user_id} name={userLabel(s)} stroke={LINE_COLORS[i % LINE_COLORS.length]} strokeWidth={2} dot={false} />
                                        ))}
                                    </LineChart>
                                </ResponsiveContainer>
                            )
                        ) : series.length === 0 ? (
                            <div className="h-full flex items-center justify-center opacity-40 text-sm font-medium">{t.noData}</div>
                        ) : (
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={series}>
                                    <defs>
                                        <linearGradient id="colorRev" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                                            <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" stroke={theme === 'dark' ? '#ffffff05' : '#00000005'} vertical={false} />
                                    <XAxis dataKey="name" axisLine={false} tickLine={false} stroke={axisColor} tick={renderAxisTick} />
                                    <YAxis axisLine={false} tickLine={false} stroke={axisColor} tick={renderAxisTick} allowDecimals={false} />
                                    <Tooltip
                                        cursor={{ stroke: '#10b981', strokeWidth: 2 }}
                                        formatter={(v) => fmtVnd(v)}
                                        contentStyle={{ backgroundColor: theme === 'dark' ? 'rgba(11,14,20,0.95)' : 'rgba(255,255,255,0.95)', borderRadius: '16px', border: '1px solid rgba(16,185,129,0.2)' }}
                                        labelStyle={{ color: tipColor }}
                                        itemStyle={{ color: tipColor }}
                                    />
                                    <Area type="monotone" dataKey="net" stroke="#10b981" strokeWidth={3} fillOpacity={1} fill="url(#colorRev)" />
                                </AreaChart>
                            </ResponsiveContainer>
                        )}
                    </div>
                </GlassCard>

                <GlassCard hoverType="green">
                    <h4 className="text-lg font-bold mb-2 flex items-center gap-2">
                        <Trophy size={20} className="text-yellow-400" /> {t.topSpenders}
                    </h4>
                    <p className="text-xs opacity-50 mb-4 italic">{t.topSpendersDesc}</p>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead className="opacity-60 text-left">
                                <tr>
                                    <th className="py-2 pr-4">{t.rank}</th>
                                    <th className="py-2 pr-4">User</th>
                                    <th className="py-2 pr-4 text-right">{t.totalSpent}</th>
                                    <th className="py-2 pr-4 text-right">{t.txnCount}</th>
                                    <th className="py-2 text-right">{t.tokensCol}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {topSpenders.length === 0 ? (
                                    <tr><td colSpan={5} className="py-10 text-center opacity-40">{t.noData}</td></tr>
                                ) : topSpenders.map((s) => (
                                    <tr key={s.user_id} className="border-t border-white/5">
                                        <td className="py-2 pr-4 font-bold">#{s.rank}</td>
                                        <td className="py-2 pr-4">{s.name || s.email || s.user_id}</td>
                                        <td className="py-2 pr-4 text-right font-bold text-green-400">{fmtVnd(s.total_spent)}</td>
                                        <td className="py-2 pr-4 text-right">{(s.txn_count ?? 0).toLocaleString(locale)}</td>
                                        <td className="py-2 text-right">{(s.tokens_purchased ?? 0).toLocaleString(locale)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </GlassCard>

                <GlassCard hoverType="purple">
                    <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3 mb-4">
                        <h4 className="text-lg font-bold">{t.revenue} — {filteredTxns.length}</h4>
                        <div className="flex items-center gap-2 flex-wrap">
                            <input
                                type="text"
                                value={txnSearch}
                                onChange={(e) => setTxnSearch(e.target.value)}
                                placeholder={t.searchUser}
                                className={`px-3 py-2 rounded-xl border text-xs font-medium w-[180px] outline-none transition-all
                                    ${theme === 'dark' ? 'bg-white/5 border-white/10 text-white placeholder-white/40 focus:border-[#00d2ff]/50' : 'bg-white border-slate-200 text-slate-900 placeholder-slate-400 focus:border-blue-400 shadow-sm'}`}
                            />
                            <FancySelect theme={theme} value={txnRange} onChange={setTxnRange} align="right" widthClass="w-[130px]" options={rangeOptions} />
                            <FancySelect theme={theme} value={txnPlan} onChange={setTxnPlan} align="right" widthClass="w-[140px]" options={planOptions} />
                            <FancySelect theme={theme} value={txnStatus} onChange={setTxnStatus} align="right" widthClass="w-[140px]" options={statusOptions} />
                        </div>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead className="opacity-60 text-left">
                                <tr>
                                    <th className="py-2 pr-4">{t.colDate}</th>
                                    <th className="py-2 pr-4">{t.colUser}</th>
                                    <th className="py-2 pr-4">{t.colPlan}</th>
                                    <th className="py-2 pr-4">{t.colAmount}</th>
                                    <th className="py-2">{t.colStatus}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredTxns.length === 0 ? (
                                    <tr><td colSpan={5} className="py-10 text-center opacity-40">{t.noData}</td></tr>
                                ) : filteredTxns.map((tx) => (
                                    <tr key={tx.transaction_id} className="border-t border-white/5">
                                        <td className="py-2 pr-4">{tx.created_at ? new Date(tx.created_at).toLocaleString() : '—'}</td>
                                        <td className="py-2 pr-4">{tx.user_email || tx.user_id}</td>
                                        <td className="py-2 pr-4">{tx.plan_code || '—'}</td>
                                        <td className="py-2 pr-4">{fmtVnd(tx.amount)}</td>
                                        <td className="py-2 capitalize">{tx.status}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </GlassCard>
            </div>
        );
    };

    // ── Sections ────────────────────────────────────────────────────────────
    const renderDashboard = () => {
        const cards = [
            {
                label: t.totalFiles, value: (stats?.total_files ?? 0).toLocaleString(locale),
                sub: `${fileBreakdown.length} ${t.fileTypes}`, subColor: 'text-green-400',
                icon: FolderOpen, color: 'text-[#00d2ff]', bg: 'bg-blue-500/20', hover: 'blue'
            },
            {
                label: t.totalSize, value: stats?.total_size_human ?? '—',
                sub: `${t.storedAt}: ${stats?.upload_dir ?? '—'}`, subColor: 'text-blue-400',
                icon: Database, color: 'text-[#9d50bb]', bg: 'bg-purple-500/20', hover: 'purple'
            },
            {
                label: t.activeUsers, value: activeUsersCount.toLocaleString(locale),
                sub: `${users.length} ${t.usersTotal}`, subColor: 'text-green-400',
                icon: Users, color: 'text-green-400', bg: 'bg-green-500/20', hover: 'green'
            },
            {
                label: t.agents, value: displayAgents.length.toLocaleString(locale),
                sub: `${totalRuns.toLocaleString(locale)} ${t.runsLabel}`, subColor: 'text-orange-400',
                icon: Cpu, color: 'text-orange-400', bg: 'bg-orange-500/20', hover: 'orange'
            }
        ];

        return (
            <div className="space-y-6 animate-in fade-in duration-500">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                    {cards.map((c, i) => (
                        <GlassCard key={i} hoverType={c.hover} className="flex flex-col justify-between">
                            <div className="flex justify-between items-start">
                                <div className="min-w-0">
                                    <p className="text-sm opacity-60 uppercase font-bold tracking-wider">{c.label}</p>
                                    <h3 className={`text-3xl font-extrabold mt-1 ${c.color} transition-colors truncate`}>{c.value}</h3>
                                </div>
                                <div className={`p-3 ${c.bg} rounded-2xl group-hover:scale-110 transition-all duration-300 flex-shrink-0`}>
                                    <c.icon className={c.color} size={24} />
                                </div>
                            </div>
                            <div className={`mt-4 text-xs ${c.subColor} font-medium truncate`} title={c.sub}>{c.sub}</div>
                        </GlassCard>
                    ))}
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <GlassCard hoverType="blue" className="lg:col-span-2 min-h-[400px]">
                        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-6">
                            <div className="flex flex-col">
                                <h4 className="text-lg font-bold flex items-center gap-2">
                                    <Activity size={20} className="text-[#00d2ff]" />
                                    {t.systemPerformance}
                                </h4>
                                <p className="text-xs opacity-50 mt-1 ml-7">{t.performanceDesc}</p>
                            </div>
                            <div className="flex items-center gap-2 flex-wrap">
                                {/* Granularity toggle */}
                                <div className={`flex p-1 rounded-xl border ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-gray-100 border-gray-200'}`}>
                                    {[
                                        { id: 'monthly', label: t.byMonth },
                                        { id: 'daily', label: t.byDay }
                                    ].map((opt) => (
                                        <button
                                            key={opt.id}
                                            onClick={() => setChartMode(opt.id)}
                                            className={`px-3 py-1 rounded-lg text-[11px] font-extrabold uppercase tracking-wide transition-all
                                                ${chartMode === opt.id ? 'bg-gradient-to-r from-[#00d2ff] to-[#9d50bb] text-white' : 'opacity-60 hover:opacity-100'}`}
                                        >
                                            {opt.label}
                                        </button>
                                    ))}
                                </div>
                                {/* Year selector */}
                                <FancySelect
                                    theme={theme}
                                    value={chartYear}
                                    onChange={(v) => setChartYear(Number(v))}
                                    align="right"
                                    widthClass="w-[110px]"
                                    options={uploadYears.map((y) => ({ value: y, label: `${t.yearLabel} ${y}` }))}
                                />
                                {/* Month selector (daily mode only) */}
                                {chartMode === 'daily' && (
                                    <FancySelect
                                        theme={theme}
                                        value={chartMonth}
                                        onChange={(v) => setChartMonth(Number(v))}
                                        align="right"
                                        widthClass="w-[120px]"
                                        options={Array.from({ length: 12 }, (_, i) => ({ value: i + 1, label: `${t.monthLabel} ${i + 1}` }))}
                                    />
                                )}
                            </div>
                        </div>
                        <div className="h-[300px] w-full">
                            {performanceData.length === 0 ? (
                                <div className="h-full flex items-center justify-center opacity-40 text-sm font-medium">{t.noData}</div>
                            ) : (
                                <ResponsiveContainer width="100%" height="100%">
                                    <AreaChart data={performanceData}>
                                        <defs>
                                            <linearGradient id="colorFiles" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="5%" stopColor="#00d2ff" stopOpacity={0.4} />
                                                <stop offset="95%" stopColor="#00d2ff" stopOpacity={0} />
                                            </linearGradient>
                                        </defs>
                                        <CartesianGrid strokeDasharray="3 3" stroke={theme === 'dark' ? '#ffffff05' : '#00000005'} vertical={false} />
                                        <XAxis dataKey="name" axisLine={false} tickLine={false} stroke={theme === 'dark' ? '#ffffff' : '#475569'} tick={renderAxisTick} />
                                        <YAxis axisLine={false} tickLine={false} stroke={theme === 'dark' ? '#ffffff' : '#475569'} tick={renderAxisTick} allowDecimals={false} />
                                        <Tooltip
                                            cursor={{ stroke: '#00d2ff', strokeWidth: 2 }}
                                            contentStyle={{
                                                backgroundColor: theme === 'dark' ? 'rgba(11, 14, 20, 0.95)' : 'rgba(255, 255, 255, 0.95)',
                                                borderRadius: '16px', border: '1px solid rgba(0, 210, 255, 0.2)'
                                            }}
                                            labelStyle={{ color: theme === 'dark' ? '#ffffff' : '#0b0e14' }}
                                            itemStyle={{ color: theme === 'dark' ? '#ffffff' : '#0b0e14' }}
                                        />
                                        <Area type="monotone" dataKey="files" stroke="#00d2ff" strokeWidth={4} fillOpacity={1} fill="url(#colorFiles)" />
                                    </AreaChart>
                                </ResponsiveContainer>
                            )}
                        </div>
                    </GlassCard>

                    <GlassCard hoverType="purple">
                        <h4 className="text-lg font-bold mb-2">{t.fileBreakdown}</h4>
                        <p className="text-xs opacity-50 mb-6 italic">{t.fileBreakdownDesc}</p>
                        <div className="h-[250px] w-full relative">
                            {fileBreakdown.length === 0 ? (
                                <div className="h-full flex items-center justify-center opacity-40 text-sm font-medium">{t.noData}</div>
                            ) : (
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Pie
                                            data={fileBreakdown}
                                            cx="50%" cy="50%"
                                            innerRadius={70} outerRadius={95}
                                            paddingAngle={8}
                                            dataKey="value"
                                            stroke={theme === 'dark' ? '#0b0e14' : '#fff'}
                                            strokeWidth={2}
                                            onMouseEnter={(_, index) => setActivePie(index)}
                                            onMouseLeave={() => setActivePie(null)}
                                        >
                                            {fileBreakdown.map((entry, index) => (
                                                <Cell
                                                    key={`cell-${index}`}
                                                    fill={entry.color}
                                                    opacity={activePie === null || activePie === index ? 1 : 0.35}
                                                />
                                            ))}
                                        </Pie>
                                    </PieChart>
                                </ResponsiveContainer>
                            )}
                            {/* Centre overlay: shows the hovered slice (name + count) on top
                                of the total — the small detail box renders over the centre. */}
                            {fileBreakdown.length > 0 && (
                                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-center pointer-events-none w-28">
                                    {activePie !== null && fileBreakdown[activePie] ? (
                                        <>
                                            <span className="flex items-center justify-center gap-1.5 mb-0.5">
                                                <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: fileBreakdown[activePie].color }} />
                                                <span className="text-[11px] font-black uppercase tracking-tight">{fileBreakdown[activePie].name}</span>
                                            </span>
                                            <span className="text-2xl font-extrabold tracking-tighter text-[#00d2ff]">{fileBreakdown[activePie].value}</span>
                                        </>
                                    ) : (
                                        <>
                                            <span className="text-[10px] uppercase opacity-40 font-bold block">{t.totalCount}</span>
                                            <span className="text-2xl font-extrabold tracking-tighter">{stats?.total_files ?? 0}</span>
                                        </>
                                    )}
                                </div>
                            )}
                        </div>
                        <div className="mt-4 space-y-2">
                            {fileBreakdown.map((item, idx) => (
                                <div key={idx} className="flex justify-between items-center text-sm">
                                    <div className="flex items-center gap-2">
                                        <div className="w-2.5 h-2.5 rounded-full" style={{ background: item.color }}></div>
                                        <span className="opacity-70 font-medium">{item.name}</span>
                                    </div>
                                    <span className="font-bold">{item.value}</span>
                                </div>
                            ))}
                        </div>
                    </GlassCard>
                </div>
            </div>
        );
    };

    const renderUsers = () => (
        <GlassCard className="p-0 overflow-hidden">
            <div className="p-6 border-b border-white/10 flex justify-between items-center flex-wrap gap-4">
                <div className="relative flex-1 max-w-md">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 opacity-40" size={18} />
                    <input
                        type="text"
                        placeholder={t.search}
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className={`w-full pl-10 pr-4 py-2 rounded-xl outline-none border border-white/10 transition-all focus:border-[#00d2ff]/50 ${theme === 'dark' ? 'bg-white/5 text-white' : 'bg-gray-50 text-slate-900'}`}
                    />
                </div>

                <div className="flex gap-2 items-center">
                    <div className="relative" ref={filterRef}>
                        <button
                            onClick={() => setIsFilterOpen(!isFilterOpen)}
                            className={`flex items-center justify-between gap-3 px-4 py-2 rounded-xl border transition-all duration-300 min-w-[160px]
                ${theme === 'dark'
                                    ? 'bg-black/40 border-white/10 text-white hover:border-[#00d2ff]/50 hover:bg-white/5'
                                    : 'bg-white border-gray-200 text-slate-900 hover:border-blue-500/50 hover:bg-blue-50/30 shadow-sm'}
                ${isFilterOpen ? (theme === 'dark' ? 'border-[#00d2ff] ring-2 ring-[#00d2ff]/20' : 'border-blue-500 ring-2 ring-blue-500/10') : ''}`}
                        >
                            <div className="flex items-center gap-2">
                                <Filter size={14} className={statusFilter !== 'all' ? 'text-[#00d2ff]' : 'opacity-40'} />
                                <span className="text-xs font-black uppercase tracking-tight">
                                    {statusFilter === 'all' ? t.allStatus : (statusFilter === 'active' ? t.active : t.inactive)}
                                </span>
                            </div>
                            <ChevronDown size={14} className={`transition-transform duration-300 ${isFilterOpen ? 'rotate-180' : ''}`} />
                        </button>

                        {isFilterOpen && (
                            <div className={`absolute right-0 mt-2 w-full min-w-[180px] rounded-2xl border backdrop-blur-2xl shadow-2xl z-[100] p-1.5 animate-in slide-in-from-top-2 duration-200
                ${theme === 'dark'
                                    ? 'bg-[#151921]/95 border-white/20 text-white'
                                    : 'bg-white/95 border-gray-200 text-slate-900'}`}>
                                <p className="px-3 py-2 text-[10px] font-black uppercase opacity-40 tracking-widest">{t.filterBy}</p>
                                {[
                                    { value: 'all', label: t.allStatus, icon: FolderOpen },
                                    { value: 'active', label: t.active, icon: CheckCircle2, color: 'text-green-400' },
                                    { value: 'inactive', label: t.inactive, icon: XCircle, color: 'text-red-400' }
                                ].map((option) => (
                                    <button
                                        key={option.value}
                                        onClick={() => { setStatusFilter(option.value); setIsFilterOpen(false); }}
                                        className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-bold transition-all duration-200
                      ${statusFilter === option.value
                                                ? (theme === 'dark' ? 'bg-[#00d2ff]/20 text-[#00d2ff]' : 'bg-blue-500/10 text-blue-600')
                                                : (theme === 'dark' ? 'hover:bg-white/5 opacity-70 hover:opacity-100' : 'hover:bg-gray-100')}`}
                                    >
                                        <option.icon size={14} className={statusFilter === option.value ? '' : option.color || 'opacity-40'} />
                                        {option.label}
                                        {statusFilter === option.value && <div className="ml-auto w-1.5 h-1.5 rounded-full bg-current"></div>}
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>

                    <button
                        onClick={() => { setSearchTerm(""); setStatusFilter("all"); }}
                        className={`p-2 rounded-xl border transition-colors ${theme === 'dark' ? 'border-white/10 hover:bg-red-500/10 hover:text-red-400' : 'border-gray-200 hover:bg-red-50 hover:text-red-600'}`}
                        title={t.clearFilters}
                    >
                        <Trash2 size={18} />
                    </button>
                </div>
            </div>

            <div className="overflow-x-auto">
                <table className="w-full text-left">
                    <thead>
                        <tr className="bg-white/5 text-xs opacity-50 uppercase tracking-widest font-bold">
                            <th className="p-4">{t.name}</th>
                            <th className="p-4">{t.email}</th>
                            <th className="p-4">{t.role}</th>
                            <th className="p-4">{t.status}</th>
                            <th className="p-4">{t.createdAt}</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                        {filteredUsers.map((user) => (
                            <tr key={user.user_id} className="hover:bg-white/5 transition-colors">
                                <td className="p-4">
                                    <div className="flex items-center gap-3">
                                        <div className="w-9 h-9 rounded-full bg-gradient-to-br from-[#00d2ff] to-[#9d50bb] flex items-center justify-center font-bold text-xs text-white overflow-hidden flex-shrink-0">
                                            {user.picture
                                                ? <img src={user.picture} alt="" referrerPolicy="no-referrer" className="w-full h-full object-cover" />
                                                : (user.name || '?').charAt(0).toUpperCase()}
                                        </div>
                                        <span className="font-semibold">{user.name || '—'}</span>
                                    </div>
                                </td>
                                <td className="p-4 text-sm opacity-70">{user.email}</td>
                                <td className="p-4"><StatusBadge statusKey={user.role_name} /></td>
                                <td className="p-4">
                                    {user.role_name === 'admin' ? (
                                        <div className="inline-flex items-center gap-2 opacity-50" title={t.adminLockTip}>
                                            <Lock size={14} />
                                            <span className="text-[10px] font-bold uppercase">{t.statusActive}</span>
                                        </div>
                                    ) : (
                                        <div onClick={() => handleToggleUser(user)} className="relative inline-flex items-center cursor-pointer group">
                                            <div className={`w-10 h-5 rounded-full transition-all duration-300 ${user.is_active ? 'bg-[#00d2ff]' : 'bg-gray-600'}`}>
                                                <div className={`absolute top-[2px] left-[2px] bg-white rounded-full h-4 w-4 transition-all duration-300 shadow-md ${user.is_active ? 'translate-x-5' : 'translate-x-0'}`}></div>
                                            </div>
                                            <span className="ml-2 text-[10px] font-bold uppercase opacity-40 group-hover:opacity-100 transition-opacity">
                                                {user.is_active ? t.on : t.off}
                                            </span>
                                        </div>
                                    )}
                                </td>
                                <td className="p-4 text-sm opacity-70">{fmtDate(user.created_at)}</td>
                            </tr>
                        ))}
                        {filteredUsers.length === 0 && (
                            <EmptyRow colSpan={5} text={t.noUsers} isLoading={loading.users} />
                        )}
                    </tbody>
                </table>
            </div>
        </GlassCard>
    );

    // Only show agents the pipeline actually uses; render rich bilingual labels.
    const displayAgents = agents.filter((a) => AGENT_META[a.agent_name]);
    const renderAgents = () => (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {displayAgents.length === 0 ? (
                <GlassCard className="md:col-span-2 lg:col-span-3 text-center opacity-40 font-medium py-16">
                    {loading.agents
                        ? <span className="flex items-center justify-center gap-2"><Loader2 size={18} className="animate-spin text-[#00d2ff]" /> {t.loading}</span>
                        : t.noAgents}
                </GlassCard>
            ) : displayAgents.map((agent) => {
                const success = Math.round((agent.success_rate || 0) * 100);
                const meta = AGENT_META[agent.agent_name];
                const name = lang === 'vi' ? meta.vi : meta.en;
                const desc = lang === 'vi' ? meta.descVi : meta.descEn;
                return (
                    <GlassCard key={agent.agent_id} className="group" hoverType="orange">
                        <div className="flex justify-between items-start mb-4">
                            <div className="p-3 rounded-2xl bg-orange-500/10 text-orange-400 group-hover:scale-110 transition-transform">
                                <Cpu size={24} />
                            </div>
                            <div className="flex gap-1 items-center">
                                <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse"></div>
                                <span className="text-[10px] uppercase font-extrabold text-green-500">{t.liveLabel}</span>
                            </div>
                        </div>
                        <h4 className="text-xl font-bold group-hover:text-orange-400 transition-colors">{name}</h4>
                        <p className="text-sm opacity-60 mb-6 line-clamp-2">{desc}</p>
                        <div className="space-y-4">
                            <div>
                                <div className="flex justify-between text-xs mb-1.5">
                                    <span className="font-medium">{t.successRate}</span>
                                    <span className="font-bold">{success}%</span>
                                </div>
                                <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
                                    <div className="h-full bg-gradient-to-r from-green-400 to-[#00d2ff] transition-all duration-1000" style={{ width: `${success}%` }}></div>
                                </div>
                            </div>
                            <div className="flex justify-between items-center text-xs opacity-80 pt-3 border-t border-white/5">
                                <span>{t.runsLabel}: <span className="font-bold">{(agent.total_runs || 0).toLocaleString(locale)}</span></span>
                                <span>{t.avgLatency}: <span className="font-bold text-[#00d2ff]">{Math.round(agent.avg_latency_ms || 0)}ms</span></span>
                            </div>
                        </div>
                    </GlassCard>
                );
            })}
        </div>
    );

    const renderProjects = () => (
        <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {projects.length === 0 ? (
                    <GlassCard className="md:col-span-2 lg:col-span-3 text-center opacity-40 font-medium py-16">
                        {loading.projects
                            ? <span className="flex items-center justify-center gap-2"><Loader2 size={18} className="animate-spin text-[#00d2ff]" /> {t.loading}</span>
                            : t.noProjects}
                    </GlassCard>
                ) : projects.map((p) => {
                    const isEditing = editingProject?.id === p.project_id;
                    return (
                    <div key={p.project_id} onClick={() => !isEditing && openProjectDetail(p.project_id)} className={isEditing ? '' : 'cursor-pointer'} title={isEditing ? undefined : t.viewDetail}>
                        <GlassCard className="p-0 group overflow-hidden" hoverType="purple">
                            <div className="h-28 bg-gradient-to-br from-[#00d2ff]/20 to-[#9d50bb]/20 relative flex items-center justify-center">
                                <FolderOpen size={48} className="text-white/40 group-hover:scale-110 transition-transform duration-500" />
                                <div className="absolute top-4 left-4 text-[10px] font-bold uppercase tracking-widest opacity-60">
                                    {fmtDate(p.created_at)}
                                </div>
                                <div className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <Eye size={18} className="text-white/70" />
                                </div>
                            </div>
                            <div className="p-6">
                                {isEditing ? (
                                    <div className="flex items-center gap-2 mb-1" onClick={(e) => e.stopPropagation()}>
                                        <input
                                            autoFocus
                                            value={editingProject.value}
                                            onChange={(e) => setEditingProject({ id: p.project_id, value: e.target.value })}
                                            onKeyDown={(e) => { if (e.key === 'Enter') handleRenameProject(p.project_id); if (e.key === 'Escape') setEditingProject(null); }}
                                            className={`flex-1 min-w-0 px-2 py-1 rounded-lg border text-sm font-bold outline-none ${theme === 'dark' ? 'bg-white/10 border-[#00d2ff]/40 text-white' : 'bg-white border-blue-300 text-slate-900'}`}
                                        />
                                        <button onClick={() => handleRenameProject(p.project_id)} disabled={renamingId === p.project_id} className="p-1.5 rounded-lg bg-[#00d2ff]/15 text-[#00d2ff] hover:bg-[#00d2ff]/25" title={t.save}>
                                            {renamingId === p.project_id ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                                        </button>
                                        <button onClick={() => setEditingProject(null)} className="p-1.5 rounded-lg hover:bg-white/10" title={t.cancel}><X size={14} /></button>
                                    </div>
                                ) : (
                                    <h5 className="font-bold text-lg mb-1 truncate">{p.project_name || t.untitledProject}</h5>
                                )}
                                <p className="text-sm opacity-60 mb-4 line-clamp-2 min-h-[2.5rem]">{p.description || t.noDescription}</p>
                                <div className="flex justify-between items-center">
                                    <span className="text-xs opacity-50 truncate" title={p.user_email || p.user_id}>{t.ownerLabel}: {p.user_name || p.user_email || `${(p.user_id || '').slice(0, 8)}…`}</span>
                                    <div className="flex items-center gap-1 flex-shrink-0">
                                        <button
                                            onClick={(e) => { e.stopPropagation(); setEditingProject({ id: p.project_id, value: p.project_name || '' }); }}
                                            className="text-[#00d2ff] p-2 hover:bg-[#00d2ff]/10 rounded-lg transition-colors"
                                            title={t.rename}
                                        >
                                            <Pencil size={16} />
                                        </button>
                                        <button
                                            onClick={(e) => { e.stopPropagation(); setDeleteTarget({ type: 'project', id: p.project_id, name: p.project_name }); }}
                                            className="text-red-400 p-2 hover:bg-red-400/10 rounded-lg transition-colors"
                                        >
                                            <Trash2 size={16} />
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </GlassCard>
                    </div>
                    );
                })}
            </div>
        </div>
    );

    const renderImages = () => (
        <GlassCard className="p-0 overflow-hidden">
            <div className="overflow-x-auto">
                <table className="w-full text-left">
                    <thead>
                        <tr className="bg-white/5 text-xs opacity-50 uppercase tracking-widest font-bold">
                            <th className="p-4">{t.imageCol}</th>
                            <th className="p-4">{t.projectCol}</th>
                            <th className="p-4">{t.status}</th>
                            <th className="p-4">{t.uploadedAt}</th>
                            <th className="p-4 text-center">{t.actions}</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                        {images.map((img) => (
                            <tr
                                key={img.image_id}
                                onClick={() => openImageDetail(img.image_id)}
                                className="hover:bg-white/5 transition-colors cursor-pointer"
                                title={t.openImage}
                            >
                                <td className="p-4">
                                    <div className="flex items-center gap-3">
                                        <AdminThumb imageId={img.image_id} theme={theme} />
                                        <span className="font-semibold text-sm truncate max-w-[220px]" title={img.image_path}>{basename(img.image_path)}</span>
                                    </div>
                                </td>
                                <td className="p-4 text-sm opacity-70" title={img.project_id}>{(img.project_id || '').slice(0, 8)}…</td>
                                <td className="p-4"><StatusBadge statusKey={img.analysis_status} /></td>
                                <td className="p-4 text-sm opacity-70">{fmtDateTime(img.uploaded_at)}</td>
                                <td className="p-4 text-center">
                                    <div className="flex items-center justify-center gap-1">
                                        <button
                                            onClick={(e) => { e.stopPropagation(); openImageDetail(img.image_id); }}
                                            className="text-[#00d2ff] p-2 hover:bg-[#00d2ff]/10 rounded-lg transition-colors"
                                            title={t.viewDetail}
                                        >
                                            <Eye size={16} />
                                        </button>
                                        <button
                                            onClick={(e) => { e.stopPropagation(); setDeleteTarget({ type: 'image', id: img.image_id, name: basename(img.image_path) }); }}
                                            className="text-red-400 p-2 hover:bg-red-400/10 rounded-lg transition-colors"
                                            title={t.delete}
                                        >
                                            <Trash2 size={16} />
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                        {images.length === 0 && (
                            <EmptyRow colSpan={5} text={t.noImages} isLoading={loading.images} />
                        )}
                    </tbody>
                </table>
            </div>
        </GlassCard>
    );

    const renderFiles = () => (
        <GlassCard className="p-0 overflow-hidden">
            <div className="p-6 border-b border-white/10 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                <div className="flex items-center gap-3 text-sm font-bold opacity-70 min-w-0">
                    <HardDrive size={18} className="text-[#00d2ff] flex-shrink-0" />
                    <span className="whitespace-nowrap">{t.uploadDir}:</span>
                    <span className="font-mono opacity-80 truncate">{stats?.upload_dir ?? '—'}</span>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                    {/* Type filter */}
                    <FancySelect
                        theme={theme}
                        value={fileTypeFilter}
                        onChange={setFileTypeFilter}
                        icon={Filter}
                        align="right"
                        widthClass="w-[130px]"
                        options={[{ value: 'all', label: t.allTypes }, ...fileExtensions.map((ext) => ({ value: ext, label: ext.toUpperCase() }))]}
                    />
                    {/* Size sort */}
                    {[
                        { id: 'asc', label: t.sizeAsc },
                        { id: 'desc', label: t.sizeDesc }
                    ].map((opt) => (
                        <button
                            key={opt.id}
                            onClick={() => setFileSort(fileSort === opt.id ? 'none' : opt.id)}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-bold transition-all
                                ${fileSort === opt.id ? 'bg-[#00d2ff]/20 text-[#00d2ff] border-[#00d2ff]/40' : theme === 'dark' ? 'bg-white/5 border-white/10 opacity-70 hover:opacity-100' : 'bg-gray-50 border-gray-200 hover:bg-gray-100'}`}
                        >
                            <ArrowUpDown size={12} />{opt.label}
                        </button>
                    ))}
                </div>
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-left">
                    <thead>
                        <tr className="bg-white/5 text-xs opacity-50 uppercase tracking-widest font-bold">
                            <th className="p-4">{t.filename}</th>
                            <th className="p-4">{t.extension}</th>
                            <th className="p-4">{t.sizeCol}</th>
                            <th className="p-4">{t.modifiedAt}</th>
                            <th className="p-4">{t.status}</th>
                            <th className="p-4 text-center">{t.actions}</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                        {displayedFiles.map((f) => {
                            const orphan = !referencedFileIds.has(f.file_id);
                            return (
                                <tr key={f.file_id} className="hover:bg-white/5 transition-colors">
                                    <td className="p-4">
                                        <div className="flex items-center gap-3">
                                            <FileText size={18} className="text-[#00d2ff] flex-shrink-0" />
                                            <span className="font-semibold text-sm truncate max-w-[280px]" title={f.filename}>{f.filename}</span>
                                        </div>
                                    </td>
                                    <td className="p-4"><span className="px-2 py-0.5 rounded-md text-[10px] font-extrabold uppercase bg-white/5 border border-white/10">{f.extension || '?'}</span></td>
                                    <td className="p-4 text-sm opacity-70">{f.size_human}</td>
                                    <td className="p-4 text-sm opacity-70">{fmtDateTime(f.modified_at)}</td>
                                    <td className="p-4">
                                        {orphan ? (
                                            <span title={t.orphanTip} className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-[10px] font-extrabold uppercase border bg-yellow-500/10 text-yellow-400 border-yellow-500/20">
                                                <AlertTriangle size={12} /> {t.orphanBadge}
                                            </span>
                                        ) : (
                                            <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-[10px] font-extrabold uppercase border bg-green-500/10 text-green-400 border-green-500/20">
                                                <CheckCircle2 size={12} /> {t.linkedBadge}
                                            </span>
                                        )}
                                    </td>
                                    <td className="p-4 text-center">
                                        <div className="flex items-center justify-center gap-1">
                                            <button
                                                onClick={() => openFilePreview(f)}
                                                className="text-[#00d2ff] p-2 hover:bg-[#00d2ff]/10 rounded-lg transition-colors"
                                                title={t.preview}
                                            >
                                                <Eye size={16} />
                                            </button>
                                            {orphan ? (
                                                // Only orphan files (owned by no analysis) can be deleted
                                                // here; linked files are cleaned up by deleting their
                                                // analysis (in the Analysis tab).
                                                <button
                                                    onClick={() => setDeleteTarget({ type: 'file', id: f.file_id, name: f.filename })}
                                                    className="text-red-400 p-2 hover:bg-red-400/10 rounded-lg transition-colors"
                                                    title={t.delete}
                                                >
                                                    <Trash2 size={16} />
                                                </button>
                                            ) : (
                                                <span className="inline-flex items-center opacity-40 p-2" title={t.linkedDeleteTip}>
                                                    <Lock size={16} />
                                                </span>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            );
                        })}
                        {displayedFiles.length === 0 && (
                            <EmptyRow colSpan={6} text={t.noFiles} isLoading={loading.files} />
                        )}
                    </tbody>
                </table>
            </div>
        </GlassCard>
    );

    const renderLogs = () => (
        <GlassCard className="p-0 overflow-hidden min-h-[600px] flex flex-col">
            <div className="p-4 border-b border-white/10 flex justify-between items-center gap-3 flex-wrap bg-white/5">
                <span className="font-bold text-sm tracking-tight uppercase">{t.logsConsole}</span>
                <div className="flex gap-1">
                    {[
                        { value: null, label: t.allLevels },
                        { value: 'INFO', label: 'INFO' },
                        { value: 'WARNING', label: 'WARNING' },
                        { value: 'ERROR', label: 'ERROR' }
                    ].map((opt) => (
                        <button
                            key={opt.value || 'all'}
                            onClick={() => setLogLevel(opt.value)}
                            className={`px-3 py-1.5 rounded-lg text-[10px] font-extrabold uppercase tracking-wider transition-all border
                ${logLevel === opt.value
                                    ? 'bg-[#00d2ff]/20 text-[#00d2ff] border-[#00d2ff]/40'
                                    : theme === 'dark' ? 'border-white/10 opacity-60 hover:opacity-100 hover:bg-white/5' : 'border-gray-200 opacity-60 hover:opacity-100 hover:bg-gray-100'}`}
                        >
                            {opt.label}
                        </button>
                    ))}
                </div>
            </div>
            <div className="flex-1 overflow-y-auto font-mono text-[11px] p-5 space-y-3 leading-relaxed custom-scrollbar">
                {logs.length === 0 ? (
                    <div className="h-full flex items-center justify-center opacity-40 font-medium">
                        {loading.logs
                            ? <span className="flex items-center gap-2"><Loader2 size={16} className="animate-spin text-[#00d2ff]" /> {t.loading}</span>
                            : t.noLogs}
                    </div>
                ) : logs.map((log) => {
                    const level = (log.log_level || 'INFO').toUpperCase();
                    return (
                        <div key={log.log_id} className="flex gap-5 border-b border-white/5 pb-2 last:border-0 group">
                            <span className="opacity-30 w-36 group-hover:opacity-60 transition-opacity flex-shrink-0">{fmtDateTime(log.created_at)}</span>
                            <span className={`w-20 font-extrabold flex-shrink-0 ${level === 'ERROR' ? 'text-red-500' : level === 'WARNING' || level === 'WARN' ? 'text-yellow-500' : 'text-blue-500'}`}>
                                [{level}]
                            </span>
                            <span className="opacity-70 group-hover:opacity-100 transition-opacity break-all">{log.message}</span>
                        </div>
                    );
                })}
            </div>
        </GlassCard>
    );

    // ── Knowledge Base: form <-> entry conversion + handlers ───────────────
    const linesToList = (s) => s.split('\n').map((x) => x.trim()).filter(Boolean);
    const listToLines = (arr) => (arr || []).join('\n');
    const profileToLines = (obj) =>
        Object.entries(obj || {}).map(([k, v]) => `${k}: ${v}`).join('\n');
    const linesToProfile = (s) => {
        const out = {};
        s.split('\n').forEach((line) => {
            const idx = line.indexOf(':');
            if (idx > 0) {
                const k = line.slice(0, idx).trim();
                const v = line.slice(idx + 1).trim();
                if (k && v) out[k] = v;
            }
        });
        return out;
    };
    const emptyStyleDraft = (prefill = {}) => ({
        isNew: true, id: '', name: '', parent: '', aliases: '', region: '',
        period: '', defining_features: '', expected_profile: '', description: '',
        aat_id: '', wikidata_id: '', references: '', ...prefill,
    });
    const styleToDraft = (s) => ({
        isNew: false, id: s.id, name: s.name, parent: s.parent || '',
        aliases: listToLines(s.aliases), region: listToLines(s.region),
        period: s.period || '', defining_features: listToLines(s.defining_features),
        expected_profile: profileToLines(s.expected_profile), description: s.description || '',
        aat_id: s.aat_id || '', wikidata_id: s.wikidata_id || '', references: listToLines(s.references),
    });
    const draftToPayload = (d) => ({
        id: d.id.trim(), name: d.name.trim(), parent: d.parent || null,
        aliases: linesToList(d.aliases), region: linesToList(d.region),
        period: d.period.trim(), defining_features: linesToList(d.defining_features),
        expected_profile: linesToProfile(d.expected_profile), description: d.description.trim(),
        aat_id: d.aat_id.trim() || null, wikidata_id: d.wikidata_id.trim() || null,
        references: linesToList(d.references),
    });

    const saveKbStyle = async () => {
        if (!kbEditing) return;
        // Required fields the recognition pipeline actually relies on.
        const missing = [];
        if (!kbEditing.id.trim()) missing.push(t.kbId);
        if (!kbEditing.name.trim()) missing.push(t.kbName);
        if (!kbEditing.parent) missing.push(t.kbParent);
        if (!kbEditing.defining_features.trim()) missing.push(t.kbFeatures);
        if (!kbEditing.expected_profile.trim()) missing.push(t.kbProfile);
        if (missing.length) {
            setKbFormError(`${t.kbRequiredMissing} ${missing.join(', ')}`);
            return;
        }
        setKbSaving(true); setKbFormError(null);
        try {
            const payload = draftToPayload(kbEditing);
            if (kbEditing.isNew) await adminKbCreateStyle(payload);
            else await adminKbUpdateStyle(kbEditing.id, payload);
            setKbEditing(null);
            loadKb();
        } catch (e) { setKbFormError(e.message); }
        finally { setKbSaving(false); }
    };
    const confirmDeleteKbStyle = async () => {
        if (!kbDeleteStyle) return;
        try { await adminKbDeleteStyle(kbDeleteStyle.id); loadKb(); }
        catch (e) { setError(e.message); }
        finally { setKbDeleteStyle(null); }
    };
    const createKbFamily = async () => {
        if (!newFamily.id.trim() || !newFamily.name.trim()) return;
        try {
            await adminKbCreateFamily(newFamily.id.trim(), newFamily.name.trim());
            setNewFamily({ id: '', name: '' });
            loadKb();
        } catch (e) { setError(e.message); }
    };
    const deleteKbFamily = async (id) => {
        try { await adminKbDeleteFamily(id); loadKb(); }
        catch (e) { setError(e.message); }
    };
    const dismissSuggestion = async (name) => {
        try { await adminKbDismissSuggestion(name); loadKb(); }
        catch (e) { setError(e.message); }
    };
    const promoteSuggestion = (name) => {
        setKbTab('styles'); setKbFormError(null);
        setKbEditing(emptyStyleDraft({ name }));
    };

    const familyLabel = (id) => {
        const f = kbFamilies.find((x) => x.id === id);
        return f ? f.name : (id || '—');
    };
    const familyStyleCount = (id) => kbStyles.filter((s) => s.parent === id).length;

    const renderKnowledge = () => {
        const q = kbSearch.trim().toLowerCase();
        const filtered = kbStyles.filter((s) => {
            const matchesSearch = !q || s.name.toLowerCase().includes(q) ||
                s.id.toLowerCase().includes(q) ||
                (s.aliases || []).some((a) => a.toLowerCase().includes(q));
            const matchesFamily = kbFamilyFilter === 'all' || s.parent === kbFamilyFilter;
            return matchesSearch && matchesFamily;
        });
        const inputCls = `w-full px-3 py-2 rounded-xl border text-sm outline-none transition-all focus:border-[#00d2ff]/50 ${theme === 'dark' ? 'bg-white/5 border-white/10 text-white' : 'bg-gray-50 border-gray-200 text-slate-900'}`;
        const subTabs = [
            { id: 'styles', label: `${t.kbStylesTab} (${kbStyles.length})` },
            { id: 'families', label: `${t.kbFamiliesTab} (${kbFamilies.length})` },
            { id: 'suggestions', label: `${t.kbSuggestionsTab} (${kbSuggestions.length})` },
        ];
        return (
            <div className="space-y-6">
                {/* Sub-tab switcher */}
                <div className={`inline-flex p-1 rounded-xl border ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-gray-100 border-gray-200'}`}>
                    {subTabs.map((st) => (
                        <button key={st.id} onClick={() => setKbTab(st.id)}
                            className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${kbTab === st.id ? 'bg-[#00d2ff]/20 text-[#00d2ff]' : 'opacity-60 hover:opacity-100'}`}>
                            {st.label}
                        </button>
                    ))}
                </div>

                {kbTab === 'styles' && (
                    <GlassCard className="p-0 overflow-hidden">
                        <div className="p-6 border-b border-white/10 flex justify-between items-center flex-wrap gap-4">
                            <div className="relative flex-1 max-w-md">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 opacity-40" size={18} />
                                <input type="text" placeholder={t.search} value={kbSearch}
                                    onChange={(e) => setKbSearch(e.target.value)}
                                    className={`w-full pl-10 pr-4 py-2 rounded-xl outline-none border border-white/10 transition-all focus:border-[#00d2ff]/50 ${theme === 'dark' ? 'bg-white/5 text-white' : 'bg-gray-50 text-slate-900'}`} />
                            </div>
                            <div className="flex gap-2 items-center">
                                <FancySelect theme={theme} value={kbFamilyFilter} onChange={setKbFamilyFilter}
                                    align="right" widthClass="w-[200px]"
                                    options={[{ value: 'all', label: t.kbAllFamilies },
                                        ...kbFamilies.map((f) => ({ value: f.id, label: f.name }))]} />
                                <button onClick={() => { setKbFormError(null); setKbEditing(emptyStyleDraft()); }}
                                    className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[#00d2ff]/20 text-[#00d2ff] font-bold text-sm hover:bg-[#00d2ff]/30 transition-all">
                                    <Plus size={16} /> {t.addStyle}
                                </button>
                            </div>
                        </div>
                        {/* Common-source citation legend (collapsible) */}
                        <details className={`px-6 py-3 border-b text-sm ${theme === 'dark' ? 'border-white/10' : 'border-gray-200'}`}>
                            <summary className="cursor-pointer flex items-center gap-2 font-bold opacity-70 hover:opacity-100 select-none">
                                <BookOpen size={15} /> {t.kbSourcesLegend}
                            </summary>
                            <ul className="mt-3 space-y-2">
                                {Object.entries(SOURCE_CITATIONS).map(([key, cite]) => (
                                    <li key={key} className="text-xs leading-relaxed opacity-80">
                                        <span className="font-mono font-bold opacity-70">{key}</span> — {cite}
                                    </li>
                                ))}
                            </ul>
                        </details>
                        <table className="w-full text-left">
                            <thead>
                                <tr className={`text-[11px] uppercase tracking-widest ${theme === 'dark' ? 'opacity-40' : 'opacity-50'}`}>
                                    <th className="p-4 font-extrabold">{t.kbName}</th>
                                    <th className="p-4 font-extrabold">ID</th>
                                    <th className="p-4 font-extrabold">{t.kbParent}</th>
                                    <th className="p-4 font-extrabold text-right">{t.actions}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filtered.length > 0 ? filtered.map((s) => (
                                    <tr key={s.id} className="border-t border-white/5 hover:bg-white/5 transition-colors">
                                        <td className="p-4 font-bold">{s.name}</td>
                                        <td className="p-4 text-sm opacity-60 font-mono">{s.id}</td>
                                        <td className="p-4 text-sm opacity-70">{familyLabel(s.parent)}</td>
                                        <td className="p-4">
                                            <div className="flex justify-end gap-2">
                                                <button onClick={() => { setKbFormError(null); setKbEditing(styleToDraft(s)); }}
                                                    className={`p-2 rounded-lg border transition-colors ${theme === 'dark' ? 'border-white/10 hover:bg-[#00d2ff]/10 hover:text-[#00d2ff]' : 'border-gray-200 hover:bg-blue-50 hover:text-blue-600'}`}>
                                                    <Pencil size={15} />
                                                </button>
                                                <button onClick={() => setKbDeleteStyle(s)}
                                                    className={`p-2 rounded-lg border transition-colors ${theme === 'dark' ? 'border-white/10 hover:bg-red-500/10 hover:text-red-400' : 'border-gray-200 hover:bg-red-50 hover:text-red-600'}`}>
                                                    <Trash2 size={15} />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                )) : (
                                    <EmptyRow colSpan={4} text={t.kbNoStyles} isLoading={loading.kbStyles} />
                                )}
                            </tbody>
                        </table>
                    </GlassCard>
                )}

                {kbTab === 'families' && (
                    <GlassCard className="p-6">
                        <div className="flex flex-wrap gap-2 items-end mb-6">
                            <div className="flex-1 min-w-[140px]">
                                <label className="block text-[11px] uppercase tracking-widest opacity-50 font-extrabold mb-1">{t.familyId}</label>
                                <input type="text" value={newFamily.id} placeholder="e.g. modern"
                                    onChange={(e) => setNewFamily({ ...newFamily, id: e.target.value })}
                                    className={inputCls} />
                            </div>
                            <div className="flex-1 min-w-[140px]">
                                <label className="block text-[11px] uppercase tracking-widest opacity-50 font-extrabold mb-1">{t.familyName}</label>
                                <input type="text" value={newFamily.name}
                                    onChange={(e) => setNewFamily({ ...newFamily, name: e.target.value })}
                                    className={inputCls} />
                            </div>
                            <button onClick={createKbFamily}
                                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[#00d2ff]/20 text-[#00d2ff] font-bold text-sm hover:bg-[#00d2ff]/30 transition-all">
                                <Plus size={16} /> {t.addFamily}
                            </button>
                        </div>
                        <div className="space-y-2">
                            {kbFamilies.length > 0 ? kbFamilies.map((f) => {
                                const count = familyStyleCount(f.id);
                                return (
                                    <div key={f.id} className={`flex items-center justify-between p-3 rounded-xl border ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-gray-50 border-gray-200'}`}>
                                        <div>
                                            <span className="font-bold">{f.name}</span>
                                            <span className="ml-2 text-xs opacity-50 font-mono">{f.id}</span>
                                            <span className="ml-3 text-xs opacity-60">{count} {t.kbStylesInFamily}</span>
                                        </div>
                                        <button onClick={() => deleteKbFamily(f.id)} disabled={count > 0}
                                            title={count > 0 ? t.deleteFamilyBlocked : ''}
                                            className={`p-2 rounded-lg border transition-colors ${count > 0 ? 'opacity-30 cursor-not-allowed border-white/10' : theme === 'dark' ? 'border-white/10 hover:bg-red-500/10 hover:text-red-400' : 'border-gray-200 hover:bg-red-50 hover:text-red-600'}`}>
                                            {count > 0 ? <Lock size={15} /> : <Trash2 size={15} />}
                                        </button>
                                    </div>
                                );
                            }) : <p className="text-center opacity-40 py-10 font-medium">{t.kbNoFamilies}</p>}
                        </div>
                    </GlassCard>
                )}

                {kbTab === 'suggestions' && (
                    <GlassCard className="p-6">
                        <p className="text-sm opacity-60 mb-5">{t.kbSuggestionsDesc}</p>
                        <div className="space-y-2">
                            {kbSuggestions.length > 0 ? kbSuggestions.map((sg) => (
                                <div key={sg.name} className={`flex items-center justify-between p-3 rounded-xl border ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-gray-50 border-gray-200'}`}>
                                    <div className="flex items-center gap-3 min-w-0">
                                        <Inbox size={16} className="opacity-40 flex-shrink-0" />
                                        <span className="font-bold truncate">{sg.name}</span>
                                        <span className="text-xs opacity-50 flex-shrink-0">{sg.count} {t.seenCount}</span>
                                    </div>
                                    <div className="flex gap-2 flex-shrink-0">
                                        <button onClick={() => promoteSuggestion(sg.name)}
                                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#00d2ff]/20 text-[#00d2ff] font-bold text-xs hover:bg-[#00d2ff]/30 transition-all">
                                            <Plus size={14} /> {t.promoteToKb}
                                        </button>
                                        <button onClick={() => dismissSuggestion(sg.name)}
                                            className={`px-3 py-1.5 rounded-lg border font-bold text-xs transition-colors ${theme === 'dark' ? 'border-white/10 hover:bg-white/10' : 'border-gray-200 hover:bg-gray-100'}`}>
                                            {t.dismiss}
                                        </button>
                                    </div>
                                </div>
                            )) : <p className="text-center opacity-40 py-10 font-medium">{t.kbNoSuggestions}</p>}
                        </div>
                    </GlassCard>
                )}
            </div>
        );
    };

    const navItems = [
        { id: 'dashboard', icon: LayoutDashboard, label: t.dashboard },
        { id: 'users', icon: Users, label: t.users },
        { id: 'projects', icon: FolderOpen, label: t.projects },
        { id: 'images', icon: BarChart3, label: t.images },
        { id: 'agents', icon: Cpu, label: t.agents },
        { id: 'revenue', icon: Wallet, label: t.revenue },
        { id: 'knowledge', icon: BookOpen, label: t.knowledge },
        { id: 'apikeys', icon: KeyRound, label: t.apikeys },
        { id: 'content', icon: LayoutTemplate, label: t.content },
        { id: 'plans', icon: Package, label: t.plans },
        { id: 'logs', icon: FileText, label: t.logs },
        { id: 'files', icon: FolderTree, label: t.files }
    ];

    return (
        <div className={`min-h-screen transition-colors duration-500 font-['Inter']
      ${theme === 'dark' ? 'bg-[#0b0e14] text-white' : 'bg-[#f8fafc] text-slate-900'}`}>

            <div className="fixed inset-0 overflow-hidden pointer-events-none opacity-20">
                <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-[#00d2ff] blur-[150px] rounded-full"></div>
                <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-[#9d50bb] blur-[150px] rounded-full"></div>
            </div>

            {/* Sidebar */}
            <aside className={`fixed left-0 top-0 h-full transition-all duration-500 z-50 border-r border-white/10 backdrop-blur-2xl flex flex-col
        ${theme === 'dark' ? 'bg-black/40' : 'bg-white/80 shadow-xl'}
        ${isSidebarOpen ? 'w-64' : 'w-20'}`}>
                <div className="p-6 flex items-center gap-3 shrink-0">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#00d2ff] to-[#9d50bb] flex-shrink-0 flex items-center justify-center shadow-lg shadow-blue-500/20">
                        <ShieldCheck className="text-white" />
                    </div>
                    {isSidebarOpen && <span className="font-extrabold text-2xl tracking-tighter bg-gradient-to-r from-[#00d2ff] to-[#9d50bb] bg-clip-text text-transparent">ArchiAI</span>}
                </div>

                <nav className="flex-1 overflow-y-auto px-4 py-4 space-y-2 custom-scrollbar">
                    {navItems.map(item => (
                        <button
                            key={item.id}
                            onClick={() => setActiveSection(item.id)}
                            className={`w-full flex items-center gap-4 p-3 rounded-2xl transition-all relative group shrink-0
                ${activeSection === item.id
                                    ? 'bg-gradient-to-r from-[#00d2ff]/20 to-[#9d50bb]/20 text-[#00d2ff] font-bold shadow-sm'
                                    : 'hover:bg-white/5 opacity-60 hover:opacity-100'}`}
                        >
                            <item.icon size={22} className={activeSection === item.id ? 'text-[#00d2ff]' : ''} />
                            {isSidebarOpen && <span className="whitespace-nowrap">{item.label}</span>}
                            {!isSidebarOpen && (
                                <div className="absolute left-full ml-4 p-2 bg-black text-white text-[10px] font-bold rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-[100] uppercase tracking-widest border border-white/10">
                                    {item.label}
                                </div>
                            )}
                        </button>
                    ))}
                </nav>

                <div className="p-4 border-t border-white/10 shrink-0">
                    <button onClick={handleLogout} className="w-full flex items-center gap-4 p-3 rounded-2xl opacity-60 hover:opacity-100 hover:bg-red-500/10 hover:text-red-400 transition-all">
                        <LogOut size={22} />
                        {isSidebarOpen && <span className="font-bold">{t.logout}</span>}
                    </button>
                </div>
            </aside>

            {/* Main */}
            <main className={`transition-all duration-500 min-h-screen flex flex-col ${isSidebarOpen ? 'pl-64' : 'pl-20'}`}>
                <header className="h-20 border-b border-white/10 px-8 flex justify-between items-center sticky top-0 z-40 backdrop-blur-xl">
                    <div>
                        <h2 className="text-xl font-bold capitalize">{t[activeSection] || activeSection}</h2>
                        <p className="text-[10px] opacity-40 hidden sm:block font-bold tracking-widest uppercase">{t.adminLabel} / {t[activeSection] || activeSection}</p>
                    </div>

                    <div className="flex items-center gap-4">
                        <button
                            onClick={() => navigate('/app')}
                            className={`flex items-center gap-2 px-3 py-1.5 rounded-full border transition-all text-sm font-bold
                                ${theme === 'dark' ? 'border-white/10 bg-white/5 hover:bg-white/10' : 'border-slate-300 bg-slate-100 hover:bg-slate-200 text-slate-800'}`}
                            title={t.userMode}
                        >
                            <UserCog size={16} />
                            <span className="hidden sm:inline">{t.userMode}</span>
                        </button>

                        <button
                            onClick={refreshAll}
                            className={`p-2.5 rounded-full border border-white/10 transition-all ${theme === 'dark' ? 'bg-white/5 hover:bg-white/10' : 'bg-gray-100 hover:bg-gray-200'}`}
                            title={t.refresh}
                        >
                            <RefreshCw size={18} className={Object.values(loading).some(Boolean) ? 'animate-spin text-[#00d2ff]' : ''} />
                        </button>

                        <button onClick={toggleLang} className={`flex items-center gap-2 px-3 py-1.5 rounded-full border transition-all text-sm font-bold
                            ${theme === 'dark' ? 'border-white/10 bg-white/5 hover:bg-white/10' : 'border-slate-300 bg-slate-100 hover:bg-slate-200 text-slate-800'}`}>
                            <Globe size={16} />
                            <span className="hidden sm:inline">{lang === 'en' ? 'EN' : 'VI'}</span>
                        </button>

                        <button onClick={toggleTheme} className={`p-2 rounded-full border transition-all
                            ${theme === 'dark' ? 'border-white/10 bg-white/5 hover:bg-white/10' : 'border-slate-300 bg-slate-100 hover:bg-slate-200'}`}>
                            {theme === 'dark' ? <Sun size={18} className="text-yellow-400" /> : <Moon size={18} className="text-blue-600" />}
                        </button>

                        <button className="p-2.5 rounded-full border border-white/10 relative">
                            <Bell size={18} />
                        </button>

                        <div className="h-8 w-px bg-white/10 mx-2"></div>

                        <div className="flex items-center gap-3 pl-2 group">
                            <div className="text-right hidden sm:block">
                                <p className="text-sm font-bold leading-tight group-hover:text-[#00d2ff] transition-colors">{adminView.name}</p>
                                <p className="text-[10px] opacity-50 uppercase tracking-widest font-bold">{t.systemRoot}</p>
                            </div>
                            <div className="w-10 h-10 rounded-full bg-slate-800 border-2 border-[#00d2ff]/30 overflow-hidden shadow-lg shadow-blue-500/20 flex items-center justify-center font-black text-white">
                                {adminView.picture
                                    ? <img src={adminView.picture} alt="Avatar" referrerPolicy="no-referrer" className="w-full h-full object-cover" />
                                    : adminView.name.charAt(0).toUpperCase()}
                            </div>
                        </div>
                    </div>
                </header>

                {error && (
                    <div className="mx-8 mt-4 p-4 rounded-2xl bg-red-500/10 border border-red-500/30 text-red-400 font-medium text-sm flex items-center justify-between gap-4">
                        <span>⚠ {t.loadError}: {error}</span>
                        <button onClick={() => setError(null)} className="hover:text-red-300 font-black text-base flex-shrink-0">✕</button>
                    </div>
                )}

                <div className="p-8 max-w-7xl mx-auto w-full flex-1">
                    {activeSection === 'dashboard' && renderDashboard()}
                    {activeSection === 'users' && renderUsers()}
                    {activeSection === 'agents' && renderAgents()}
                    {activeSection === 'revenue' && renderRevenue()}
                    {activeSection === 'projects' && renderProjects()}
                    {activeSection === 'images' && renderImages()}
                    {activeSection === 'files' && renderFiles()}
                    {activeSection === 'knowledge' && renderKnowledge()}
                    {activeSection === 'apikeys' && <ApiKeysSection theme={theme} lang={lang} />}
                    {activeSection === 'content' && <ContentSection theme={theme} lang={lang} />}
                    {activeSection === 'plans' && <PlansSection theme={theme} lang={lang} />}
                    {activeSection === 'logs' && renderLogs()}
                </div>
                <SiteFooter />
            </main>

            {/* Delete confirmation modal */}
            {deleteTarget && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-in fade-in duration-300">
                    <div className={`max-w-md w-full p-8 rounded-[32px] border transition-all
             ${theme === 'dark' ? 'bg-[#0f1218] border-white/10 text-white' : 'bg-white border-gray-200 text-slate-900 shadow-2xl'}`}>
                        <h3 className="text-2xl font-bold mb-4">
                            {deleteTarget.type === 'project'
                                ? t.confirmDeleteProject
                                : deleteTarget.type === 'file'
                                    ? t.confirmDeleteFile
                                    : t.confirmDeleteImage}
                        </h3>
                        {deleteTarget.name && (
                            <p className="font-mono text-sm mb-3 px-3 py-2 rounded-lg bg-white/5 border border-white/10 break-all">{deleteTarget.name}</p>
                        )}
                        <p className="opacity-60 mb-8 leading-relaxed">{t.deleteConfirmDesc}</p>
                        <div className="flex gap-4">
                            <button
                                onClick={() => setDeleteTarget(null)}
                                disabled={deleting}
                                className={`flex-1 py-4 rounded-2xl font-extrabold transition-all disabled:opacity-50 ${theme === 'dark' ? 'bg-white/5 hover:bg-white/10' : 'bg-gray-100 hover:bg-gray-200'}`}
                            >
                                {t.cancel}
                            </button>
                            <button
                                onClick={confirmDelete}
                                disabled={deleting}
                                className="flex-1 py-4 bg-red-500 hover:bg-red-600 text-white rounded-2xl font-extrabold transition-all shadow-lg shadow-red-500/30 disabled:opacity-50 flex items-center justify-center gap-2"
                            >
                                {deleting && <Loader2 size={18} className="animate-spin" />}
                                {deleting ? t.deleting : t.delete}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* KB style delete confirmation */}
            {kbDeleteStyle && (
                <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-in fade-in duration-300">
                    <div className={`max-w-md w-full p-8 rounded-[32px] border ${theme === 'dark' ? 'bg-[#0f1218] border-white/10 text-white' : 'bg-white border-gray-200 text-slate-900 shadow-2xl'}`}>
                        <h3 className="text-2xl font-bold mb-4">{t.confirmDeleteStyle}</h3>
                        <p className="font-mono text-sm mb-3 px-3 py-2 rounded-lg bg-white/5 border border-white/10 break-all">{kbDeleteStyle.name} ({kbDeleteStyle.id})</p>
                        <p className={`text-xs mb-6 px-3 py-2 rounded-lg leading-relaxed ${theme === 'dark' ? 'bg-amber-500/10 text-amber-300' : 'bg-amber-50 text-amber-700'}`}>{t.kbDeleteImpact}</p>
                        <div className="flex gap-4">
                            <button onClick={() => setKbDeleteStyle(null)}
                                className={`flex-1 py-4 rounded-2xl font-extrabold transition-all ${theme === 'dark' ? 'bg-white/5 hover:bg-white/10' : 'bg-gray-100 hover:bg-gray-200'}`}>
                                {t.cancel}
                            </button>
                            <button onClick={confirmDeleteKbStyle}
                                className="flex-1 py-4 bg-red-500 hover:bg-red-600 text-white rounded-2xl font-extrabold transition-all shadow-lg shadow-red-500/30">
                                {t.delete}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* KB style editor modal */}
            {kbEditing && (() => {
                const fld = `w-full px-3 py-2 rounded-xl border text-sm outline-none transition-all focus:border-[#00d2ff]/50 ${theme === 'dark' ? 'bg-white/5 border-white/10 text-white' : 'bg-gray-50 border-gray-200 text-slate-900'}`;
                const lbl = "block text-[11px] uppercase tracking-widest opacity-50 font-extrabold mb-1";
                const helpCls = "text-[11px] opacity-50 mt-1 normal-case font-normal tracking-normal leading-snug";
                const req = <span className="text-red-400 ml-0.5">*</span>;
                const set = (k, v) => setKbEditing({ ...kbEditing, [k]: v });
                return (
                    <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-in fade-in duration-300">
                        <div className={`max-w-2xl w-full max-h-[88vh] flex flex-col rounded-[32px] border ${theme === 'dark' ? 'bg-[#0f1218] border-white/10 text-white' : 'bg-white border-gray-200 text-slate-900 shadow-2xl'}`}>
                            {/* Sticky header — stays put while the body scrolls */}
                            <div className={`flex justify-between items-center px-8 pt-7 pb-4 border-b flex-shrink-0 rounded-t-[32px] ${theme === 'dark' ? 'border-white/10 bg-[#0f1218]' : 'border-gray-200 bg-white'}`}>
                                <h3 className="text-2xl font-bold">{kbEditing.isNew ? t.newStyle : t.editStyle}</h3>
                                <button onClick={() => setKbEditing(null)} className="p-2 rounded-lg hover:bg-white/10 transition-colors" title={t.close}><X size={20} /></button>
                            </div>
                            {/* Scrollable body */}
                            <div className="px-8 py-6 overflow-y-auto custom-scrollbar flex-1">
                                {!kbEditing.isNew && (
                                    <p className={`text-xs mb-5 px-3 py-2 rounded-lg ${theme === 'dark' ? 'bg-amber-500/10 text-amber-300' : 'bg-amber-50 text-amber-700'}`}>{t.kbEditImpact}</p>
                                )}
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div>
                                        <label className={lbl}>{t.kbId}{req}</label>
                                        <input type="text" value={kbEditing.id} disabled={!kbEditing.isNew}
                                            title={!kbEditing.isNew ? t.kbIdImmutable : ''}
                                            onChange={(e) => set('id', e.target.value)}
                                            className={`${fld} font-mono ${!kbEditing.isNew ? 'opacity-50 cursor-not-allowed' : ''}`} />
                                    </div>
                                    <div>
                                        <label className={lbl}>{t.kbName}{req}</label>
                                        <input type="text" value={kbEditing.name} onChange={(e) => set('name', e.target.value)} className={fld} />
                                    </div>
                                    <div>
                                        <label className={lbl}>{t.kbParent}{req}</label>
                                        <select value={kbEditing.parent} onChange={(e) => set('parent', e.target.value)} className={fld}>
                                            <option value="">—</option>
                                            {kbFamilies.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label className={lbl}>{t.kbPeriod}</label>
                                        <input type="text" value={kbEditing.period} onChange={(e) => set('period', e.target.value)} className={fld} />
                                    </div>
                                    <div>
                                        <label className={lbl}>{t.kbAliases} <span className="opacity-40 normal-case">({t.kbListHint})</span></label>
                                        <textarea rows={2} value={kbEditing.aliases} onChange={(e) => set('aliases', e.target.value)} className={`${fld} resize-y`} />
                                    </div>
                                    <div>
                                        <label className={lbl}>{t.kbRegion} <span className="opacity-40 normal-case">({t.kbListHint})</span></label>
                                        <textarea rows={2} value={kbEditing.region} onChange={(e) => set('region', e.target.value)} className={`${fld} resize-y`} />
                                    </div>
                                    <div className="sm:col-span-2">
                                        <label className={lbl}>{t.kbFeatures}{req} <span className="opacity-40 normal-case">({t.kbListHint})</span></label>
                                        <textarea rows={3} value={kbEditing.defining_features} onChange={(e) => set('defining_features', e.target.value)} className={`${fld} resize-y`} />
                                    </div>
                                    <div className="sm:col-span-2">
                                        <label className={lbl}>{t.kbProfile}{req} <span className="opacity-40 normal-case">({t.kbProfileHint})</span></label>
                                        <textarea rows={3} value={kbEditing.expected_profile} onChange={(e) => set('expected_profile', e.target.value)} className={`${fld} resize-y font-mono`} />
                                        <p className={helpCls}>{t.kbProfileHelp}</p>
                                    </div>
                                    <div className="sm:col-span-2">
                                        <label className={lbl}>{t.kbDescription}</label>
                                        <textarea rows={2} value={kbEditing.description} onChange={(e) => set('description', e.target.value)} className={`${fld} resize-y`} />
                                    </div>
                                    <div>
                                        <div className="flex items-center justify-between">
                                            <label className={lbl}>AAT ID</label>
                                            {kbEditing.aat_id.trim() && (
                                                <a href={`https://vocab.getty.edu/page/aat/${kbEditing.aat_id.trim()}`} target="_blank" rel="noreferrer"
                                                    className="flex items-center gap-1 text-[11px] font-bold text-[#00d2ff] hover:underline mb-1">
                                                    {t.kbViewSource} <ExternalLink size={12} />
                                                </a>
                                            )}
                                        </div>
                                        <input type="text" value={kbEditing.aat_id} onChange={(e) => set('aat_id', e.target.value)} className={fld} />
                                        <p className={helpCls}>{t.kbAatHelp}</p>
                                    </div>
                                    <div>
                                        <div className="flex items-center justify-between">
                                            <label className={lbl}>Wikidata ID</label>
                                            {kbEditing.wikidata_id.trim() && (
                                                <a href={`https://www.wikidata.org/wiki/${kbEditing.wikidata_id.trim()}`} target="_blank" rel="noreferrer"
                                                    className="flex items-center gap-1 text-[11px] font-bold text-[#00d2ff] hover:underline mb-1">
                                                    {t.kbViewSource} <ExternalLink size={12} />
                                                </a>
                                            )}
                                        </div>
                                        <input type="text" value={kbEditing.wikidata_id} onChange={(e) => set('wikidata_id', e.target.value)} className={fld} />
                                        <p className={helpCls}>{t.kbWikidataHelp}</p>
                                    </div>
                                    <div className="sm:col-span-2">
                                        <label className={lbl}>{t.kbReferences} <span className="opacity-40 normal-case">({t.kbListHint})</span></label>
                                        <textarea rows={2} value={kbEditing.references} onChange={(e) => set('references', e.target.value)} className={`${fld} resize-y`} />
                                        <p className={helpCls}>{t.kbReferencesHelp}</p>
                                    </div>
                                </div>
                                {kbFormError && <p className="text-red-400 font-semibold text-sm mt-4">⚠ {kbFormError}</p>}
                            </div>
                            {/* Footer — stays put for easy access */}
                            <div className={`flex gap-4 px-8 py-5 border-t flex-shrink-0 rounded-b-[32px] ${theme === 'dark' ? 'border-white/10 bg-[#0f1218]' : 'border-gray-200 bg-white'}`}>
                                <button onClick={() => setKbEditing(null)} disabled={kbSaving}
                                    className={`flex-1 py-4 rounded-2xl font-extrabold transition-all disabled:opacity-50 ${theme === 'dark' ? 'bg-white/5 hover:bg-white/10' : 'bg-gray-100 hover:bg-gray-200'}`}>
                                    {t.cancel}
                                </button>
                                <button onClick={saveKbStyle} disabled={kbSaving}
                                    className="flex-1 py-4 bg-[#00d2ff] hover:bg-[#00bce6] text-[#0b0e14] rounded-2xl font-extrabold transition-all shadow-lg shadow-[#00d2ff]/30 disabled:opacity-50 flex items-center justify-center gap-2">
                                    {kbSaving && <Loader2 size={18} className="animate-spin" />}
                                    {t.save}
                                </button>
                            </div>
                        </div>
                    </div>
                );
            })()}

            {/* Project detail modal */}
            {projectDetail && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-in fade-in duration-300" onClick={() => setProjectDetail(null)}>
                    <div
                        onClick={(e) => e.stopPropagation()}
                        className={`max-w-2xl w-full max-h-[85vh] overflow-y-auto custom-scrollbar p-8 rounded-[32px] border
              ${theme === 'dark' ? 'bg-[#0f1218] border-white/10 text-white' : 'bg-white border-gray-200 text-slate-900 shadow-2xl'}`}
                    >
                        <div className="flex justify-between items-start mb-6">
                            <h3 className="text-2xl font-bold">{t.projectDetailTitle}</h3>
                            <button onClick={() => setProjectDetail(null)} className="p-2 rounded-lg hover:bg-white/10 transition-colors" title={t.close}><X size={20} /></button>
                        </div>
                        {projectDetail.loading ? (
                            <div className="py-16 text-center opacity-50"><Loader2 className="animate-spin mx-auto text-[#00d2ff]" size={28} /></div>
                        ) : projectDetail.error ? (
                            <p className="text-red-400 font-medium">{projectDetail.error}</p>
                        ) : projectDetail.data && (
                            <>
                                <h4 className="text-xl font-extrabold mb-1">{projectDetail.data.project_name || t.untitledProject}</h4>
                                <p className="opacity-60 text-sm mb-2">{projectDetail.data.description || t.noDescription}</p>
                                <div className="flex flex-wrap gap-4 text-xs opacity-50 font-bold mb-6">
                                    <span>{t.userIdLabel}: {(projectDetail.data.user_id || '').slice(0, 8)}…</span>
                                    <span>{t.createdAt}: {fmtDate(projectDetail.data.created_at)}</span>
                                    <span>{t.images}: {projectDetail.data.total_images}</span>
                                </div>
                                <div className="space-y-2">
                                    {(projectDetail.data.images || []).map((im) => (
                                        <button
                                            key={im.image_id}
                                            onClick={() => { setProjectDetail(null); openImageDetail(im.image_id); }}
                                            className={`w-full flex items-center gap-3 p-3 rounded-xl border text-left transition-all ${theme === 'dark' ? 'bg-white/5 border-white/10 hover:bg-white/10' : 'bg-gray-50 border-gray-200 hover:bg-gray-100'}`}
                                        >
                                            <ImageIcon size={18} className="opacity-40 flex-shrink-0" />
                                            <span className="flex-1 truncate text-sm font-semibold" title={im.image_path}>{basename(im.image_path)}</span>
                                            {im.style && <span className="text-xs font-bold text-[#00d2ff]">{im.style}{im.confidence != null ? ` ${(im.confidence * 100).toFixed(0)}%` : ''}</span>}
                                            <StatusBadge statusKey={im.analysis_status} />
                                            <Eye size={16} className="opacity-40 flex-shrink-0" />
                                        </button>
                                    ))}
                                    {(projectDetail.data.images || []).length === 0 && (
                                        <p className="py-8 text-center opacity-40 font-medium">{t.noImages}</p>
                                    )}
                                </div>
                            </>
                        )}
                    </div>
                </div>
            )}

            {/* Image analysis detail modal */}
            {imageDetail && (() => {
                const d = imageDetail.data || {};
                const useVi = lang === 'vi';
                const explanation = (useVi && d.explanation_vi) || d.explanation || '';
                const keyEvidence = (useVi && d.key_evidence_vi) || d.key_evidence || [];
                const composition = (useVi && d.composition_explanation_vi) || d.composition_explanation || '';
                const dist = (d.style_distribution && d.style_distribution.distribution) || {};
                const radar = Object.entries(dist)
                    .map(([style, p]) => ({ style, value: Math.round(p * 100) }))
                    .filter((r) => r.value > 0)
                    .sort((a, b) => b.value - a.value);
                const evidenceItems = ((useVi && d.evidence_sheet_vi && d.evidence_sheet_vi.items)
                    || (d.evidence_sheet && d.evidence_sheet.items)) || [];
                return (
                    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-in fade-in duration-300" onClick={closeImageDetail}>
                        <div
                            onClick={(e) => e.stopPropagation()}
                            className={`max-w-5xl w-full max-h-[90vh] overflow-y-auto custom-scrollbar p-6 lg:p-8 rounded-[32px] border
                ${theme === 'dark' ? 'bg-[#0f1218] border-white/10 text-white' : 'bg-white border-gray-200 text-slate-900 shadow-2xl'}`}
                        >
                            <div className="flex justify-between items-start mb-6">
                                <h3 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-[#00d2ff] to-[#9d50bb]">{t.imageDetailTitle}</h3>
                                <button onClick={closeImageDetail} className="p-2 rounded-lg hover:bg-white/10 transition-colors" title={t.close}><X size={20} /></button>
                            </div>

                            {imageDetail.loading ? (
                                <div className="py-20 text-center opacity-50"><Loader2 className="animate-spin mx-auto text-[#00d2ff]" size={32} /></div>
                            ) : imageDetail.error ? (
                                <p className="text-red-400 font-medium">{imageDetail.error}</p>
                            ) : (
                                <div className="space-y-6">
                                    {/* Top: original image + summary side by side */}
                                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                                        {/* Left: original image */}
                                        <div>
                                            <div className="rounded-2xl bg-black/30 overflow-hidden border border-white/10 flex items-center justify-center max-h-[60vh]">
                                                {imageDetail.url ? (
                                                    <img src={imageDetail.url} alt="preview" className="block max-w-full max-h-[60vh] object-contain" />
                                                ) : (
                                                    <div className="aspect-[4/3] w-full flex items-center justify-center opacity-30"><ImageIcon size={48} /></div>
                                                )}
                                            </div>
                                        </div>

                                        {/* Right: summary (style, confidence, distribution) */}
                                        <div className="space-y-5">
                                            {!d.style ? (
                                                <p className="opacity-50 font-medium py-8">{t.noAnalysis}</p>
                                            ) : (
                                                <>
                                                    <div className="flex items-center gap-2 flex-wrap">
                                                        {d.degraded && <span className="px-3 py-1 rounded-full text-[10px] font-extrabold uppercase bg-yellow-500/15 text-yellow-400 border border-yellow-500/20">{t.degradedBadge}</span>}
                                                        {d.uncertain && <span className="px-3 py-1 rounded-full text-[10px] font-extrabold uppercase bg-orange-500/15 text-orange-400 border border-orange-500/20">{t.uncertainBadge}</span>}
                                                    </div>
                                                    <div>
                                                        <p className="text-[10px] font-black uppercase tracking-widest opacity-50 mb-1">{t.styleLabel}</p>
                                                        <p className="text-3xl font-black">{d.style}</p>
                                                    </div>
                                                    <div className="grid grid-cols-2 gap-3">
                                                        <div className={`p-3 rounded-2xl border ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-blue-50 border-blue-100'}`}>
                                                            <p className="text-[10px] font-bold uppercase tracking-widest opacity-50 mb-1">{t.confidenceLabel}</p>
                                                            <p className="text-2xl font-black text-[#00d2ff]">{d.confidence != null ? `${(d.confidence * 100).toFixed(0)}%` : '—'}</p>
                                                        </div>
                                                        <div className={`p-3 rounded-2xl border ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-purple-50 border-purple-100'}`}>
                                                            <p className="text-[10px] font-bold uppercase tracking-widest opacity-50 mb-1">{t.processingLabel}</p>
                                                            <p className="text-lg font-black">{d.processing_time_ms ? `${(d.processing_time_ms / 1000).toFixed(1)}s` : '—'}</p>
                                                        </div>
                                                    </div>
                                                    {radar.length > 0 && (
                                                        <div>
                                                            <p className="text-[10px] font-black uppercase tracking-widest opacity-50 mb-2">{t.distributionLabel}</p>
                                                            <ResponsiveContainer width="100%" height={220}>
                                                                <RadarChart data={radar}>
                                                                    <PolarGrid stroke={theme === 'dark' ? 'rgba(255,255,255,0.12)' : '#e2e8f0'} />
                                                                    <PolarAngleAxis dataKey="style" tick={{ fontSize: 10, fill: theme === 'dark' ? '#9ca3af' : '#64748b' }} />
                                                                    <Radar dataKey="value" fill="#00d2ff" fillOpacity={0.35} stroke="#00d2ff" strokeWidth={2} />
                                                                    <Tooltip formatter={(v) => `${v}%`} contentStyle={{ background: theme === 'dark' ? '#0b0e14' : '#fff', border: '1px solid rgba(0,210,255,0.3)', borderRadius: 8 }} />
                                                                </RadarChart>
                                                            </ResponsiveContainer>
                                                        </div>
                                                    )}
                                                </>
                                            )}
                                        </div>
                                    </div>

                                    {/* Full-width details below (uses the empty space under the image) */}
                                    {d.style && (explanation || (composition && composition !== explanation) || keyEvidence.length > 0 || evidenceItems.length > 0) && (
                                        <div className="space-y-5 border-t border-white/10 pt-6">
                                            {explanation && (
                                                <p className="leading-relaxed italic border-l-4 border-[#9d50bb] pl-4 text-sm opacity-90">"{explanation}"</p>
                                            )}
                                            {composition && composition !== explanation && (
                                                <div>
                                                    <p className="text-[10px] font-black uppercase tracking-widest opacity-50 mb-1">{t.compositionLabel}</p>
                                                    <p className="text-sm opacity-80 leading-relaxed">{composition}</p>
                                                </div>
                                            )}
                                            {keyEvidence.length > 0 && (
                                                <div>
                                                    <p className="text-[10px] font-black uppercase tracking-widest opacity-50 mb-2">{t.evidenceLabel}</p>
                                                    <ul className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-1.5">
                                                        {keyEvidence.map((ev, i) => (
                                                            <li key={i} className="flex items-start gap-2 text-sm opacity-80"><span className="text-[#00d2ff] mt-0.5">▸</span><span>{ev}</span></li>
                                                        ))}
                                                    </ul>
                                                </div>
                                            )}
                                            {evidenceItems.length > 0 && (
                                                <div>
                                                    <p className="text-[10px] font-black uppercase tracking-widest opacity-50 mb-3">{t.evidenceSheetLabel} ({evidenceItems.length})</p>
                                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                                        {groupEvidenceByDimension(evidenceItems).map(({ dimension, items }) => {
                                                            const meta = DIMENSION_META[dimension];
                                                            const title = meta ? (lang === 'vi' ? meta.vi : meta.en) : dimension;
                                                            return (
                                                                <div key={dimension} className={`rounded-2xl border p-3.5 ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-slate-50 border-slate-200'}`}>
                                                                    <p className="text-[10px] font-black uppercase tracking-widest opacity-60 mb-2">
                                                                        {title}
                                                                    </p>
                                                                    <ul className="space-y-1.5">
                                                                        {items.map((it, i) => (
                                                                            <li key={i} className="text-xs leading-relaxed opacity-85 flex items-start gap-2">
                                                                                <span className="text-[#00d2ff] mt-0.5 flex-shrink-0">▸</span>
                                                                                <span>{it.feature}</span>
                                                                            </li>
                                                                        ))}
                                                                    </ul>
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                );
            })()}

            {/* File preview lightbox */}
            {filePreview && (
                <div className="fixed inset-0 z-[110] flex items-center justify-center p-6 bg-black/80 backdrop-blur-md animate-in fade-in duration-300" onClick={closeFilePreview}>
                    <button onClick={closeFilePreview} className="absolute top-6 right-6 p-2 rounded-lg text-white hover:bg-white/10 transition-colors" title={t.close}><X size={24} /></button>
                    <div onClick={(e) => e.stopPropagation()} className="max-w-[90vw] max-h-[85vh] flex flex-col items-center gap-3">
                        <img src={filePreview.url} alt={filePreview.name} className="max-w-full max-h-[80vh] object-contain rounded-2xl shadow-2xl" />
                        <span className="text-white/70 text-sm font-mono">{filePreview.name}</span>
                    </div>
                </div>
            )}

            <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
        body {
          font-family: 'Inter', sans-serif;
          overflow-x: hidden;
          -webkit-font-smoothing: antialiased;
        }
        .animate-in { animation: animateIn 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
        @keyframes animateIn {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .custom-scrollbar::-webkit-scrollbar { width: 4px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(0, 210, 255, 0.1); border-radius: 10px; }
        .custom-scrollbar:hover::-webkit-scrollbar-thumb { background: rgba(0, 210, 255, 0.3); }
        input:focus { box-shadow: 0 0 20px rgba(0, 210, 255, 0.1); }
      `}</style>
        </div>
    );
};

/* ════════════════════════════════════════════════════════════════════════
 *  API KEY MANAGEMENT  +  WEBSITE CMS
 *  Defined at module scope (stable component identity) so typing in their
 *  inputs never loses focus — see decision #85.
 * ════════════════════════════════════════════════════════════════════════ */

const SECTION_I18N = {
    en: {
        // API keys
        apiKeysTitle: "Provider API Keys",
        apiKeysSub: "Manage AI-provider keys without editing code or restarting.",
        addKey: "Add key", provider: "Provider", label: "Label", key: "API key",
        model: "Model (optional)", baseUrl: "Base URL (optional)", priority: "Priority",
        active: "Active", inactive: "Inactive", actions: "Actions", lastUsed: "Last used",
        save: "Save", cancel: "Cancel", edit: "Edit", del: "Delete", test: "Test",
        enable: "Enable", disable: "Disable", source: "Source", keyPlaceholderEdit: "Leave blank to keep current key",
        noKeys: "No keys yet — the system uses the .env keys until you add one.",
        confirmDelete: "Delete this key?", testing: "Testing…", inUse: "in use",
        helpModel: "Leave blank → use the default model from .env.",
        helpPriority: "Lower = higher priority; the active key with the smallest number is used. If two active keys share the same number, the one added earlier wins.",
        helpBaseUrl: "Override the API endpoint (DeepSeek/Grok/proxy). Blank → default.",
        helpLabel: "A name for you to recognise this key (e.g. \"Gemini main\", \"OpenAI backup\"). Free text — it does not affect anything.",
        modelDefault: "Default (.env)", modelCustom: "Custom…", modelCustomPlaceholder: "e.g. gpt-4o-mini",
        baseUrlInvalid: "Must start with http:// or https://",
        // CMS
        cmsTitle: "Website Content", cmsSub: "Edit page content, preview, then publish. Restore any previous version.",
        page: "Page", saveDraft: "Save draft", publish: "Publish", preview: "Preview",
        revisions: "Revisions", restore: "Restore", current: "current", rev: "Rev",
        savedDraft: "Draft saved.", published: "Published.", restored: "Restored.",
        en: "English", vi: "Vietnamese", saving: "Saving…",
        imageUrl: "Image URL",
        pageLanding: "Landing page", pageUser: "User dashboard",
        livePreview: "Live preview", openTab: "Open in new tab",
        previewHint: "Edits update the preview on blur. The live site only changes when you publish.",
        editing: "Editing",
        fromEnv: "from .env (read-only)",
        overrideHint: "The .env keys cannot be edited from here (they are the bootstrap fallback). Add a key for the same provider and it overrides the .env key automatically — the active key with the lowest priority number wins. No code change or restart needed.",
        bilingualNote: "Bilingual content — fill in both English and Vietnamese. A blank field falls back to the system default. The system does NOT auto-translate.",
        previewLangLabel: "Preview language",
        // Plans
        plansTitle: "Plan management", plansSub: "Edit the token amount and price of each plan/pack.",
        planName: "Name", planType: "Type", planPrice: "Price (VND)", planTokens: "Tokens",
        planDuration: "Duration (days)", planOrder: "Order", planActive: "Active", planActions: "Actions",
        planTokenPack: "Token pack", planSubscription: "Subscription", planCode: "Code", noPlans: "No plans yet.",
        addPlan: "Add plan", editPlan: "Edit plan", planSaved: "Plan saved.", planDurationHint: "Subscriptions only — leave blank for packs.",
    },
    vi: {
        apiKeysTitle: "Khóa API nhà cung cấp",
        apiKeysSub: "Quản lý khóa AI mà không cần sửa code hay khởi động lại.",
        addKey: "Thêm khóa", provider: "Nhà cung cấp", label: "Nhãn", key: "Khóa API",
        model: "Model (tùy chọn)", baseUrl: "Base URL (tùy chọn)", priority: "Ưu tiên",
        active: "Đang bật", inactive: "Đã tắt", actions: "Thao tác", lastUsed: "Dùng gần nhất",
        save: "Lưu", cancel: "Hủy", edit: "Sửa", del: "Xóa", test: "Kiểm tra",
        enable: "Bật", disable: "Tắt", source: "Nguồn", keyPlaceholderEdit: "Để trống để giữ khóa hiện tại",
        noKeys: "Chưa có khóa — hệ thống dùng khóa trong .env cho tới khi bạn thêm.",
        confirmDelete: "Xóa khóa này?", testing: "Đang kiểm tra…", inUse: "đang dùng",
        helpModel: "Để trống → dùng model mặc định trong .env.",
        helpPriority: "Số nhỏ = ưu tiên cao; hệ dùng key đang bật có số nhỏ nhất. Nếu hai key đang bật trùng số, key thêm TRƯỚC sẽ được ưu tiên.",
        helpBaseUrl: "Ghi đè endpoint API (DeepSeek/Grok/proxy). Để trống → mặc định.",
        helpLabel: "Tên để bạn nhận ra khóa này (vd \"Gemini chính\", \"OpenAI dự phòng\"). Nhập tùy ý — không ảnh hưởng gì.",
        modelDefault: "Mặc định (.env)", modelCustom: "Tùy chỉnh…", modelCustomPlaceholder: "vd: gpt-4o-mini",
        baseUrlInvalid: "Phải bắt đầu bằng http:// hoặc https://",
        cmsTitle: "Nội dung website", cmsSub: "Sửa nội dung, xem trước rồi xuất bản. Khôi phục bản cũ bất kỳ.",
        page: "Trang", saveDraft: "Lưu nháp", publish: "Xuất bản", preview: "Xem trước",
        revisions: "Phiên bản", restore: "Khôi phục", current: "hiện tại", rev: "Bản",
        savedDraft: "Đã lưu nháp.", published: "Đã xuất bản.", restored: "Đã khôi phục.",
        en: "Tiếng Anh", vi: "Tiếng Việt", saving: "Đang lưu…",
        imageUrl: "URL hình ảnh",
        pageLanding: "Trang chủ", pageUser: "Trang người dùng",
        livePreview: "Xem trước trực tiếp", openTab: "Mở tab mới",
        previewHint: "Sửa xong rời ô (blur) là preview cập nhật. Trang thật chỉ đổi khi bạn Xuất bản.",
        editing: "Đang sửa",
        fromEnv: "từ .env (chỉ đọc)",
        overrideHint: "Không sửa trực tiếp khóa .env tại đây (đó là khóa dự phòng khởi tạo). Hãy THÊM một khóa cho cùng nhà cung cấp — khóa đó tự động GHI ĐÈ khóa .env; khóa đang bật có số ưu tiên nhỏ nhất sẽ được dùng. Không cần sửa code hay khởi động lại.",
        bilingualNote: "Nội dung song ngữ — điền cả Tiếng Anh và Tiếng Việt. Ô để trống sẽ tự dùng bản mặc định của hệ thống. Hệ thống KHÔNG tự dịch.",
        previewLangLabel: "Ngôn ngữ xem trước",
        // Plans
        plansTitle: "Quản lý gói", plansSub: "Sửa số token và giá của từng gói/gói token.",
        planName: "Tên", planType: "Loại", planPrice: "Giá (VND)", planTokens: "Số token",
        planDuration: "Số ngày", planOrder: "Thứ tự", planActive: "Đang bật", planActions: "Thao tác",
        planTokenPack: "Gói token", planSubscription: "Gói thuê bao", planCode: "Mã", noPlans: "Chưa có gói nào.",
        addPlan: "Thêm gói", editPlan: "Sửa gói", planSaved: "Đã lưu gói.", planDurationHint: "Chỉ cho gói thuê bao — để trống với gói token.",
    },
};

// Editable content manifest per page. The backend stores a generic JSON blob;
// adding a field here is the only change needed to expose it (no backend edit).
const CMS_MANIFEST = {
    landing: [
        {
            section: { en: "Hero", vi: "Khối Hero" },
            fields: [
                { key: "hero-badge", type: "text", label: { en: "Badge", vi: "Nhãn" } },
                { key: "hero-title-1", type: "text", label: { en: "Title line 1", vi: "Tiêu đề dòng 1" } },
                { key: "hero-title-2", type: "text", label: { en: "Title line 2", vi: "Tiêu đề dòng 2" } },
                { key: "hero-desc", type: "textarea", label: { en: "Description", vi: "Mô tả" } },
                { key: "hero-cta-1", type: "text", label: { en: "CTA button 1", vi: "Nút CTA 1" } },
                { key: "hero-cta-2", type: "text", label: { en: "CTA button 2", vi: "Nút CTA 2" } },
            ],
        },
        {
            section: { en: "Features", vi: "Tính năng" },
            fields: [
                { key: "feat-title", type: "text", label: { en: "Section title", vi: "Tiêu đề mục" } },
                { key: "feat-desc", type: "textarea", label: { en: "Section intro", vi: "Giới thiệu mục" } },
                { key: "feat-1-h", type: "text", label: { en: "Card 1 title", vi: "Thẻ 1 tiêu đề" } },
                { key: "feat-1-p", type: "textarea", label: { en: "Card 1 text", vi: "Thẻ 1 nội dung" } },
                { key: "feat-2-h", type: "text", label: { en: "Card 2 title", vi: "Thẻ 2 tiêu đề" } },
                { key: "feat-2-p", type: "textarea", label: { en: "Card 2 text", vi: "Thẻ 2 nội dung" } },
                { key: "feat-3-h", type: "text", label: { en: "Card 3 title", vi: "Thẻ 3 tiêu đề" } },
                { key: "feat-3-p", type: "textarea", label: { en: "Card 3 text", vi: "Thẻ 3 nội dung" } },
                { key: "feat-4-h", type: "text", label: { en: "Card 4 title", vi: "Thẻ 4 tiêu đề" } },
                { key: "feat-4-p", type: "textarea", label: { en: "Card 4 text", vi: "Thẻ 4 nội dung" } },
            ],
        },
        {
            section: { en: "Call to action + Footer", vi: "Kêu gọi + Chân trang" },
            fields: [
                { key: "cta-title", type: "text", label: { en: "CTA title", vi: "Tiêu đề CTA" } },
                { key: "cta-p", type: "textarea", label: { en: "CTA text", vi: "Nội dung CTA" } },
                { key: "cta-btn", type: "text", label: { en: "CTA button", vi: "Nút CTA" } },
                { key: "footer-copyright", type: "text", label: { en: "Footer copyright", vi: "Bản quyền chân trang" } },
            ],
        },
    ],
    // Keys MUST match UserPage's I18N keys (missing ones fall back to defaults).
    user: [
        {
            section: { en: "Navigation / Header", vi: "Điều hướng / Header" },
            fields: [
                { key: "upload", type: "text", label: { en: "Upload tab", vi: "Tab Tải lên" } },
                { key: "analyze", type: "text", label: { en: "Analyze tab", vi: "Tab Phân tích" } },
                { key: "history", type: "text", label: { en: "History tab", vi: "Tab Lịch sử" } },
                { key: "profile", type: "text", label: { en: "Profile tab", vi: "Tab Hồ sơ" } },
                { key: "billing", type: "text", label: { en: "Billing tab", vi: "Tab Gói & Token" } },
                { key: "adminPanel", type: "text", label: { en: "Admin link", vi: "Liên kết Admin" } },
                { key: "logout", type: "text", label: { en: "Logout", vi: "Đăng xuất" } },
            ],
        },
        {
            section: { en: "Upload tab", vi: "Tab Tải lên" },
            fields: [
                { key: "dragDrop", type: "text", label: { en: "Drop prompt", vi: "Lời nhắc kéo thả" } },
                { key: "orBrowse", type: "text", label: { en: "Browse prompt", vi: "Lời nhắc chọn tệp" } },
                { key: "maxSize", type: "text", label: { en: "Max-size note", vi: "Ghi chú dung lượng" } },
                { key: "uploading", type: "text", label: { en: "Uploading…", vi: "Đang tải lên…" } },
                { key: "noFile", type: "text", label: { en: "No-file warning", vi: "Cảnh báo chưa có tệp" } },
                { key: "startAnalyze", type: "text", label: { en: "Analyze button", vi: "Nút phân tích" } },
            ],
        },
        {
            section: { en: "Analysis status", vi: "Trạng thái phân tích" },
            fields: [
                { key: "analysisStatus", type: "text", label: { en: "Status title", vi: "Tiêu đề trạng thái" } },
                { key: "processing", type: "text", label: { en: "Processing…", vi: "Đang xử lý…" } },
                { key: "completed", type: "text", label: { en: "Completed", vi: "Hoàn tất" } },
                { key: "processingLabel", type: "text", label: { en: "Processing label", vi: "Nhãn đang xử lý" } },
                { key: "aiVerified", type: "text", label: { en: "AI verified", vi: "AI đã xác minh" } },
                { key: "stepUploaded", type: "text", label: { en: "Step: uploaded", vi: "Bước: đã tải lên" } },
                { key: "stepUploadedDesc", type: "text", label: { en: "Step uploaded desc", vi: "Mô tả bước tải lên" } },
                { key: "stepProcessingDesc", type: "text", label: { en: "Step processing desc", vi: "Mô tả bước xử lý" } },
                { key: "stepDoneDesc", type: "text", label: { en: "Step done desc", vi: "Mô tả bước hoàn tất" } },
            ],
        },
        {
            section: { en: "Result block", vi: "Khối Kết quả" },
            fields: [
                { key: "result", type: "text", label: { en: "Result title", vi: "Tiêu đề kết quả" } },
                { key: "style", type: "text", label: { en: "Style label", vi: "Nhãn phong cách" } },
                { key: "confidence", type: "text", label: { en: "Confidence label", vi: "Nhãn độ tin cậy" } },
                { key: "description", type: "textarea", label: { en: "Description label", vi: "Nhãn mô tả" } },
                { key: "sourceImage", type: "text", label: { en: "Source image", vi: "Ảnh gốc" } },
                { key: "keyEvidence", type: "text", label: { en: "Key evidence", vi: "Bằng chứng chính" } },
                { key: "styleDistribution", type: "text", label: { en: "Style distribution", vi: "Phân bố phong cách" } },
                { key: "evidenceSheet", type: "text", label: { en: "Evidence sheet", vi: "Phiếu bằng chứng" } },
                { key: "evidenceHelp", type: "textarea", label: { en: "Evidence help", vi: "Chú thích bằng chứng" } },
                { key: "compositionExplanation", type: "text", label: { en: "Composition explanation", vi: "Giải thích bố cục" } },
                { key: "perStyleWhy", type: "text", label: { en: "Why each style", vi: "Vì sao mỗi phong cách" } },
                { key: "role", type: "text", label: { en: "Role label", vi: "Nhãn vai trò" } },
                { key: "rolePrimary", type: "text", label: { en: "Primary role", vi: "Vai trò chính" } },
                { key: "roleSecondary", type: "text", label: { en: "Secondary role", vi: "Vai trò phụ" } },
                { key: "panelAgreement", type: "text", label: { en: "Panel agreement", vi: "Đồng thuận hội đồng" } },
                { key: "panelVerdicts", type: "text", label: { en: "Judge panel", vi: "Hội đồng giám khảo" } },
                { key: "uncertain", type: "text", label: { en: "Uncertain", vi: "Không chắc chắn" } },
                { key: "hybrid", type: "text", label: { en: "Hybrid / eclectic", vi: "Lai / pha trộn" } },
                { key: "suggestedStyles", type: "text", label: { en: "Suggests", vi: "Gợi ý" } },
                { key: "learnStyle", type: "text", label: { en: "Learn about style", vi: "Tìm hiểu phong cách" } },
                { key: "downloadPdf", type: "text", label: { en: "Download PDF", vi: "Tải PDF" } },
                { key: "clickReopen", type: "text", label: { en: "Click to re-open", vi: "Bấm để mở lại" } },
            ],
        },
        {
            section: { en: "History tab", vi: "Tab Lịch sử" },
            fields: [
                { key: "recentHistory", type: "text", label: { en: "History title", vi: "Tiêu đề lịch sử" } },
                { key: "searchStyle", type: "text", label: { en: "Search placeholder", vi: "Ô tìm kiếm" } },
                { key: "minConfidence", type: "text", label: { en: "Min confidence", vi: "Độ tin cậy tối thiểu" } },
                { key: "allYears", type: "text", label: { en: "All years", vi: "Tất cả năm" } },
                { key: "allMonths", type: "text", label: { en: "All months", vi: "Tất cả tháng" } },
                { key: "allDays", type: "text", label: { en: "All days", vi: "Tất cả ngày" } },
                { key: "monthLabel", type: "text", label: { en: "Month label", vi: "Nhãn tháng" } },
                { key: "dayLabel", type: "text", label: { en: "Day label", vi: "Nhãn ngày" } },
                { key: "noMatch", type: "text", label: { en: "No match", vi: "Không khớp" } },
                { key: "colImage", type: "text", label: { en: "Col: image", vi: "Cột: ảnh" } },
                { key: "colStyle", type: "text", label: { en: "Col: style", vi: "Cột: phong cách" } },
                { key: "colConfidence", type: "text", label: { en: "Col: confidence", vi: "Cột: độ tin cậy" } },
                { key: "colDate", type: "text", label: { en: "Col: date", vi: "Cột: ngày" } },
                { key: "colStatus", type: "text", label: { en: "Col: status", vi: "Cột: trạng thái" } },
                { key: "loadingHistory", type: "text", label: { en: "Loading history", vi: "Đang tải lịch sử" } },
                { key: "noHistory", type: "textarea", label: { en: "Empty history", vi: "Lịch sử trống" } },
            ],
        },
        {
            section: { en: "Profile tab", vi: "Tab Hồ sơ" },
            fields: [
                { key: "userInfo", type: "text", label: { en: "Profile title", vi: "Tiêu đề hồ sơ" } },
                { key: "theme", type: "text", label: { en: "Appearance", vi: "Giao diện" } },
                { key: "language", type: "text", label: { en: "Language", vi: "Ngôn ngữ" } },
            ],
        },
        {
            section: { en: "Plans & Tokens tab", vi: "Tab Gói & Token" },
            fields: [
                { key: "currentPlan", type: "text", label: { en: "Current plan", vi: "Gói hiện tại" } },
                { key: "noPlan", type: "text", label: { en: "Free plan", vi: "Gói miễn phí" } },
                { key: "balanceLabel", type: "text", label: { en: "Balance", vi: "Số dư" } },
                { key: "tokenPacks", type: "text", label: { en: "Token packs", vi: "Gói token" } },
                { key: "subscriptions", type: "text", label: { en: "Subscriptions", vi: "Gói thuê bao" } },
                { key: "perAnalysis", type: "text", label: { en: "Per analysis", vi: "Mỗi lần phân tích" } },
                { key: "tokensWord", type: "text", label: { en: "Tokens word", vi: "Từ 'token'" } },
                { key: "buyNow", type: "text", label: { en: "Buy now", vi: "Mua ngay" } },
                { key: "daysWord", type: "text", label: { en: "Days word", vi: "Từ 'ngày'" } },
                { key: "billingHistory", type: "text", label: { en: "Payment history", vi: "Lịch sử thanh toán" } },
                { key: "tokenLedger", type: "text", label: { en: "Token activity", vi: "Hoạt động token" } },
                { key: "noTransactions", type: "text", label: { en: "No transactions", vi: "Chưa có giao dịch" } },
                { key: "noLedger", type: "text", label: { en: "No token activity", vi: "Chưa có hoạt động token" } },
                { key: "colAmount", type: "text", label: { en: "Col: amount", vi: "Cột: số tiền" } },
                { key: "colPlan", type: "text", label: { en: "Col: plan", vi: "Cột: gói" } },
                { key: "insufficientTokens", type: "textarea", label: { en: "Out of tokens", vi: "Hết token" } },
                { key: "total", type: "text", label: { en: "Total", vi: "Tổng" } },
                { key: "proceedPay", type: "text", label: { en: "Proceed to payment", vi: "Tiến hành thanh toán" } },
            ],
        },
    ],
};

// Which iframe route renders each editable page (for the live preview).
const CMS_PREVIEW_ROUTE = { landing: '/?preview=1', user: '/app?preview=1' };

// Common model names per provider (suggestions; "Custom…" allows anything).
const PROVIDER_MODELS = {
    gemini: ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.0-flash'],
    openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4.1', 'gpt-4.1-mini'],
    deepseek: ['deepseek-chat', 'deepseek-reasoner'],
    xai: ['grok-4.20-0309-non-reasoning', 'grok-4.3'],
};
// Providers where a custom Base URL is meaningful (others ignore it).
const PROVIDER_USES_BASE_URL = ['openai', 'deepseek', 'xai'];

function _panelCls(theme) {
    return theme === 'dark'
        ? 'bg-black/20 border-white/10'
        : 'bg-white/80 border-gray-200';
}
function _inputCls(theme) {
    return `w-full px-3 py-2 rounded-xl border text-sm outline-none transition-all
        ${theme === 'dark'
            ? 'bg-white/5 border-white/10 text-white placeholder-white/30 focus:border-[#00d2ff]/60'
            : 'bg-white border-gray-300 text-slate-900 placeholder-slate-400 focus:border-[#00d2ff]'}`;
}

function ApiKeysSection({ theme, lang }) {
    const tr = SECTION_I18N[lang] || SECTION_I18N.en;
    const [keys, setKeys] = useState([]);
    const [providers, setProviders] = useState([]);
    const [busy, setBusy] = useState(false);
    const [msg, setMsg] = useState(null);
    const [testing, setTesting] = useState(null);
    const blankForm = {
        key_id: null, provider: 'gemini', label: '', api_key: '',
        model_override: '', base_url_override: '', priority: 100, is_active: true,
    };
    const [form, setForm] = useState(null); // null = modal closed
    const [modelCustom, setModelCustom] = useState(false); // model field in free-text mode

    const load = async () => {
        setBusy(true);
        try {
            const [k, p] = await Promise.all([adminGetApiKeys(), adminGetApiKeyProviders()]);
            setKeys(k.keys || []);
            setProviders(p.providers || []);
        } catch (e) { setMsg({ type: 'err', text: e.message }); }
        finally { setBusy(false); }
    };
    useEffect(() => { load(); }, []);

    const openCreate = () => { setModelCustom(false); setForm({ ...blankForm }); };
    const openEdit = (k) => {
        setModelCustom(false);
        setForm({
            key_id: k.key_id, provider: k.provider, label: k.label, api_key: '',
            model_override: '', base_url_override: '', priority: k.priority, is_active: k.is_active,
        });
    };
    // Base URL must be a URL when provided.
    const baseUrlInvalid = (u) => !!u && !/^https?:\/\//i.test(u.trim());

    const submit = async () => {
        setBusy(true); setMsg(null);
        try {
            if (form.key_id) {
                const body = {
                    label: form.label, priority: Number(form.priority), is_active: form.is_active,
                    model_override: form.model_override || null, base_url_override: form.base_url_override || null,
                };
                if (form.api_key) body.api_key = form.api_key;
                await adminUpdateApiKey(form.key_id, body);
            } else {
                await adminCreateApiKey({
                    provider: form.provider, label: form.label, api_key: form.api_key,
                    model_override: form.model_override || null, base_url_override: form.base_url_override || null,
                    priority: Number(form.priority), is_active: form.is_active,
                });
            }
            setForm(null);
            await load();
        } catch (e) { setMsg({ type: 'err', text: e.message }); }
        finally { setBusy(false); }
    };

    const toggle = async (k) => {
        try { await adminToggleApiKey(k.key_id, !k.is_active); await load(); }
        catch (e) { setMsg({ type: 'err', text: e.message }); }
    };
    const remove = async (k) => {
        if (!window.confirm(tr.confirmDelete)) return;
        try { await adminDeleteApiKey(k.key_id); await load(); }
        catch (e) { setMsg({ type: 'err', text: e.message }); }
    };
    const test = async (k) => {
        setTesting(k.key_id);
        try {
            const r = await adminTestStoredApiKey(k.key_id);
            setMsg({ type: r.ok ? 'ok' : 'err', text: `${k.label}: ${r.detail}` });
        } catch (e) { setMsg({ type: 'err', text: e.message }); }
        finally { setTesting(null); }
    };
    const testForm = async () => {
        setTesting('form');
        try {
            const r = await adminTestApiKey({
                provider: form.provider, api_key: form.api_key,
                model_override: form.model_override || null, base_url_override: form.base_url_override || null,
            });
            setMsg({ type: r.ok ? 'ok' : 'err', text: r.detail });
        } catch (e) { setMsg({ type: 'err', text: e.message }); }
        finally { setTesting(null); }
    };

    return (
        <div className="space-y-6 animate-in">
            <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="max-w-2xl">
                    <h3 className="text-2xl font-extrabold">{tr.apiKeysTitle}</h3>
                    <p className="text-sm opacity-50">{tr.apiKeysSub}</p>
                    <p className="text-xs opacity-50 mt-1 leading-snug">{tr.overrideHint}</p>
                </div>
                <button onClick={openCreate}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl font-bold text-white bg-gradient-to-r from-[#00d2ff] to-[#9d50bb] hover:opacity-90 transition">
                    <Plus size={18} /> {tr.addKey}
                </button>
            </div>

            {msg && (
                <div className={`p-3 rounded-xl text-sm font-medium border
                    ${msg.type === 'ok' ? 'bg-green-500/10 border-green-500/30 text-green-400'
                        : 'bg-red-500/10 border-red-500/30 text-red-400'}`}>
                    {msg.text}
                </div>
            )}

            {/* Provider source summary */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {providers.map(p => (
                    <div key={p.provider} className={`p-4 rounded-2xl border ${_panelCls(theme)}`}>
                        <div className="text-xs uppercase tracking-widest opacity-50 font-bold">{p.provider}</div>
                        <div className="mt-1 flex items-center gap-2">
                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase border
                                ${p.source === 'db' ? 'bg-[#00d2ff]/10 text-[#00d2ff] border-[#00d2ff]/30'
                                    : p.source === 'env' ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                                        : 'bg-red-500/10 text-red-400 border-red-500/30'}`}>
                                {p.source}
                            </span>
                            <span className="text-[10px] opacity-50">{p.active_key_count} {tr.inUse}</span>
                        </div>
                        <div className="mt-1 text-xs opacity-60 truncate">{p.model}</div>
                        {p.masked_key && (
                            <div className="mt-1 font-mono text-xs opacity-70">{p.masked_key}</div>
                        )}
                        {p.source === 'env' && (
                            <div className="mt-0.5 text-[10px] opacity-50">{tr.fromEnv}</div>
                        )}
                    </div>
                ))}
            </div>

            {/* Keys table */}
            <div className={`rounded-2xl border overflow-hidden ${_panelCls(theme)}`}>
                <table className="w-full text-sm">
                    <thead className={theme === 'dark' ? 'bg-white/5' : 'bg-slate-100'}>
                        <tr className="text-left">
                            <th className="px-4 py-3 font-bold">{tr.provider}</th>
                            <th className="px-4 py-3 font-bold">{tr.label}</th>
                            <th className="px-4 py-3 font-bold">{tr.key}</th>
                            <th className="px-4 py-3 font-bold">{tr.model}</th>
                            <th className="px-4 py-3 font-bold">{tr.priority}</th>
                            <th className="px-4 py-3 font-bold">{tr.active}</th>
                            <th className="px-4 py-3 font-bold text-right">{tr.actions}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {keys.length === 0 && (
                            <tr><td colSpan={7} className="px-4 py-8 text-center opacity-50">{tr.noKeys}</td></tr>
                        )}
                        {keys.map(k => (
                            <tr key={k.key_id} className="border-t border-white/5">
                                <td className="px-4 py-3 font-mono uppercase text-xs">{k.provider}</td>
                                <td className="px-4 py-3">{k.label}</td>
                                <td className="px-4 py-3 font-mono opacity-70">{k.masked_key}</td>
                                <td className="px-4 py-3 opacity-60 text-xs">{k.model}</td>
                                <td className="px-4 py-3">{k.priority}</td>
                                <td className="px-4 py-3">
                                    <button onClick={() => toggle(k)}
                                        className={`px-2 py-1 rounded-full text-[10px] font-extrabold uppercase border
                                            ${k.is_active ? 'bg-green-500/10 text-green-400 border-green-500/30'
                                                : 'bg-red-500/10 text-red-400 border-red-500/30'}`}>
                                        {k.is_active ? tr.active : tr.inactive}
                                    </button>
                                </td>
                                <td className="px-4 py-3">
                                    <div className="flex items-center justify-end gap-2">
                                        <button onClick={() => test(k)} title={tr.test}
                                            className="p-1.5 rounded-lg hover:bg-white/10 transition">
                                            {testing === k.key_id ? <Loader2 size={16} className="animate-spin" /> : <FlaskConical size={16} />}
                                        </button>
                                        <button onClick={() => openEdit(k)} title={tr.edit}
                                            className="p-1.5 rounded-lg hover:bg-white/10 transition"><Pencil size={16} /></button>
                                        <button onClick={() => remove(k)} title={tr.del}
                                            className="p-1.5 rounded-lg hover:bg-red-500/10 hover:text-red-400 transition"><Trash2 size={16} /></button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* Create/edit modal — portalled to <body> so no section stacking
                context (animate-in transforms) lets the header overlap it. */}
            {form && createPortal(
                <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-in fade-in duration-300">
                    {/* Connection-test result floats above the modal card so it is
                        never hidden behind the overlay while adding a key. */}
                    {msg && (
                        <div className={`fixed top-6 left-1/2 -translate-x-1/2 z-[210] max-w-md w-[90%] px-4 py-3 rounded-xl text-sm font-medium border shadow-2xl animate-in slide-in-from-top-2 duration-200
                            ${msg.type === 'ok' ? 'bg-green-500/15 border-green-500/40 text-green-300'
                                : 'bg-red-500/15 border-red-500/40 text-red-300'}`}>
                            {msg.text}
                        </div>
                    )}
                    <div className={`max-w-2xl w-full max-h-[88vh] flex flex-col rounded-[32px] border
                        ${theme === 'dark' ? 'bg-[#0f1218] border-white/10 text-white' : 'bg-white border-gray-200 text-slate-900 shadow-2xl'}`}>
                        {/* Sticky header */}
                        <div className={`flex justify-between items-center px-8 pt-7 pb-4 border-b flex-shrink-0 rounded-t-[32px] ${theme === 'dark' ? 'border-white/10 bg-[#0f1218]' : 'border-gray-200 bg-white'}`}>
                            <h3 className="text-2xl font-bold">{form.key_id ? tr.edit : tr.addKey}</h3>
                            <button onClick={() => setForm(null)} className="p-2 rounded-lg hover:bg-white/10 transition-colors"><X size={20} /></button>
                        </div>
                        {/* Scrollable body */}
                        <div className="px-8 py-6 overflow-y-auto custom-scrollbar flex-1 space-y-4">
                            {!form.key_id && (
                                <div>
                                    <label className="text-xs font-bold opacity-60 block mb-1">{tr.provider}</label>
                                    <FancySelect
                                        value={form.provider}
                                        onChange={(v) => { setModelCustom(false); setForm({ ...form, provider: v, model_override: '', base_url_override: '' }); }}
                                        options={[
                                            { value: 'gemini', label: 'Gemini (Google)' },
                                            { value: 'openai', label: 'OpenAI (GPT)' },
                                            { value: 'deepseek', label: 'DeepSeek' },
                                            { value: 'xai', label: 'xAI (Grok)' },
                                        ]}
                                        theme={theme}
                                        widthClass="w-full"
                                        panelWidthClass="w-full"
                                    />
                                </div>
                            )}
                            <div>
                                <label className="text-xs font-bold opacity-60">{tr.label}</label>
                                <input value={form.label} onChange={e => setForm({ ...form, label: e.target.value })} className={_inputCls(theme)} />
                                <p className="text-[11px] opacity-50 mt-1">{tr.helpLabel}</p>
                            </div>
                            <div>
                                <label className="text-xs font-bold opacity-60">{tr.key}</label>
                                <input type="password" value={form.api_key} onChange={e => setForm({ ...form, api_key: e.target.value })}
                                    placeholder={form.key_id ? tr.keyPlaceholderEdit : ''} className={_inputCls(theme)} />
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="text-xs font-bold opacity-60 block mb-1">{tr.model}</label>
                                    {(() => {
                                        const known = PROVIDER_MODELS[form.provider] || [];
                                        const isCustom = modelCustom || (!!form.model_override && !known.includes(form.model_override));
                                        return (
                                            <FancySelect
                                                value={isCustom ? '__custom__' : (form.model_override || '')}
                                                onChange={(v) => {
                                                    if (v === '__custom__') { setModelCustom(true); setForm({ ...form, model_override: '' }); }
                                                    else { setModelCustom(false); setForm({ ...form, model_override: v }); }
                                                }}
                                                options={[
                                                    { value: '', label: tr.modelDefault },
                                                    ...known.map(m => ({ value: m, label: m })),
                                                    { value: '__custom__', label: tr.modelCustom },
                                                ]}
                                                theme={theme}
                                                widthClass="w-full"
                                                panelWidthClass="w-full"
                                            />
                                        );
                                    })()}
                                    {(modelCustom || (!!form.model_override && !(PROVIDER_MODELS[form.provider] || []).includes(form.model_override))) && (
                                        <input value={form.model_override} placeholder={tr.modelCustomPlaceholder}
                                            onChange={e => setForm({ ...form, model_override: e.target.value })} className={`${_inputCls(theme)} mt-2`} />
                                    )}
                                    <p className="text-[11px] opacity-50 mt-1">{tr.helpModel}</p>
                                </div>
                                <div>
                                    <label className="text-xs font-bold opacity-60">{tr.priority}</label>
                                    <input type="number" value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })} className={_inputCls(theme)} />
                                    <p className="text-[11px] opacity-50 mt-1">{tr.helpPriority}</p>
                                </div>
                            </div>
                            {PROVIDER_USES_BASE_URL.includes(form.provider) && (
                                <div>
                                    <label className="text-xs font-bold opacity-60">{tr.baseUrl}</label>
                                    <input value={form.base_url_override} onChange={e => setForm({ ...form, base_url_override: e.target.value })}
                                        className={`${_inputCls(theme)} ${baseUrlInvalid(form.base_url_override) ? 'border-red-500/60' : ''}`} />
                                    {baseUrlInvalid(form.base_url_override)
                                        ? <p className="text-[11px] text-red-400 mt-1">{tr.baseUrlInvalid}</p>
                                        : <p className="text-[11px] opacity-50 mt-1">{tr.helpBaseUrl}</p>}
                                </div>
                            )}
                            <label className="flex items-center gap-2 text-sm">
                                <input type="checkbox" checked={form.is_active} onChange={e => setForm({ ...form, is_active: e.target.checked })} />
                                {tr.active}
                            </label>
                        </div>
                        {/* Sticky footer */}
                        <div className={`flex items-center justify-between gap-4 px-8 py-5 border-t flex-shrink-0 rounded-b-[32px] ${theme === 'dark' ? 'border-white/10 bg-[#0f1218]' : 'border-gray-200 bg-white'}`}>
                            <button onClick={testForm} disabled={!form.api_key || testing === 'form'}
                                className="flex items-center gap-2 px-4 py-3 rounded-2xl border border-white/10 hover:bg-white/10 disabled:opacity-40 transition text-sm font-extrabold">
                                {testing === 'form' ? <Loader2 size={16} className="animate-spin" /> : <FlaskConical size={16} />} {tr.test}
                            </button>
                            <div className="flex gap-3">
                                <button onClick={() => setForm(null)}
                                    className={`px-5 py-3 rounded-2xl font-extrabold transition-all ${theme === 'dark' ? 'bg-white/5 hover:bg-white/10' : 'bg-gray-100 hover:bg-gray-200'}`}>{tr.cancel}</button>
                                <button onClick={submit} disabled={busy || !form.label || (!form.key_id && !form.api_key) || baseUrlInvalid(form.base_url_override)}
                                    className="flex items-center gap-2 px-5 py-3 bg-[#00d2ff] hover:bg-[#00bce6] text-[#0b0e14] rounded-2xl font-extrabold transition-all shadow-lg shadow-[#00d2ff]/30 disabled:opacity-50">
                                    <Save size={16} /> {tr.save}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>,
                document.body,
            )}
        </div>
    );
}

function ContentSection({ theme, lang }) {
    const tr = SECTION_I18N[lang] || SECTION_I18N.en;
    const [page, setPage] = useState('landing');
    const [content, setContent] = useState({ en: {}, vi: {} });
    const [baseRev, setBaseRev] = useState(0);
    const [revisions, setRevisions] = useState([]);
    const [busy, setBusy] = useState(false);
    const [msg, setMsg] = useState(null);
    // Editor shows BOTH languages per field; this only controls which language
    // the preview iframe renders.
    const [previewLang, setPreviewLang] = useState(lang === 'vi' ? 'vi' : 'en');
    const [box, setBox] = useState({ w: 0, h: 0 }); // preview pane size (px)

    const iframeRef = useRef(null);
    const paneRef = useRef(null);
    const contentRef = useRef(content);
    useEffect(() => { contentRef.current = content; }, [content]);

    const DESIGN_W = 1280; // logical width the page is rendered at, then scaled down
    const scale = box.w > 0 ? box.w / DESIGN_W : 0.5;

    // Push the current (unsaved) edits into the preview iframe — never the server.
    const postToPreview = useCallback(() => {
        const win = iframeRef.current && iframeRef.current.contentWindow;
        if (!win) return;
        win.postMessage(
            { source: 'archi-cms', page, content: contentRef.current, lang: previewLang },
            window.location.origin,
        );
    }, [page, previewLang]);

    const load = useCallback(async (p) => {
        setBusy(true); setMsg(null);
        try {
            const [d, r] = await Promise.all([adminGetCmsDraft(p), adminGetCmsRevisions(p)]);
            setContent({ en: (d.content && d.content.en) || {}, vi: (d.content && d.content.vi) || {} });
            setBaseRev(d.base_revision_no || 0);
            setRevisions(r.revisions || []);
        } catch (e) { setMsg({ type: 'err', text: e.message }); }
        finally { setBusy(false); }
    }, []);
    useEffect(() => { load(page); }, [page, load]);

    // Re-push to the preview when the preview language changes or freshly-loaded
    // content arrives (E4 — keeps the iframe in sync after a page switch).
    useEffect(() => { postToPreview(); }, [previewLang, content, postToPreview]);

    // The iframe announces readiness (handles the load race) → send current edits.
    useEffect(() => {
        const onMsg = (e) => {
            if (e.origin !== window.location.origin) return;
            if (e.data && e.data.source === 'archi-cms-ready') postToPreview();
        };
        window.addEventListener('message', onMsg);
        return () => window.removeEventListener('message', onMsg);
    }, [postToPreview]);

    // Measure the preview pane so the iframe can be scaled to a true-ratio miniature.
    useEffect(() => {
        if (!paneRef.current) return;
        const measure = () => {
            const r = paneRef.current.getBoundingClientRect();
            setBox({ w: r.width, h: r.height });
        };
        measure();
        const ro = new ResizeObserver(measure);
        ro.observe(paneRef.current);
        return () => ro.disconnect();
    }, []);

    const setField = (l, key, val) => setContent(c => ({ ...c, [l]: { ...c[l], [key]: val } }));
    const commit = () => postToPreview(); // on blur / Enter

    const saveDraft = async () => {
        setBusy(true); setMsg(null);
        try { await adminSaveCmsDraft(page, content, baseRev); setMsg({ type: 'ok', text: tr.savedDraft }); }
        catch (e) { setMsg({ type: 'err', text: e.message }); }
        finally { setBusy(false); }
    };
    const publish = async () => {
        setBusy(true); setMsg(null);
        try {
            await adminSaveCmsDraft(page, content, baseRev);
            await adminPublishCms(page);
            setMsg({ type: 'ok', text: tr.published });
            await load(page);
        } catch (e) { setMsg({ type: 'err', text: e.message }); }
        finally { setBusy(false); }
    };
    const restore = async (n) => {
        setBusy(true); setMsg(null);
        try { await adminRestoreCms(page, n); setMsg({ type: 'ok', text: tr.restored }); await load(page); }
        catch (e) { setMsg({ type: 'err', text: e.message }); }
        finally { setBusy(false); }
    };

    const manifest = CMS_MANIFEST[page] || [];
    const pageName = page === 'user' ? tr.pageUser : tr.pageLanding;

    return (
        <div className="space-y-5 animate-in">
            {/* Toolbar */}
            <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex items-center gap-3 flex-wrap">
                    <FancySelect
                        value={page}
                        onChange={setPage}
                        icon={LayoutTemplate}
                        options={[
                            { value: 'landing', label: tr.pageLanding },
                            { value: 'user', label: tr.pageUser },
                        ]}
                        theme={theme}
                        widthClass="min-w-[180px]"
                        panelWidthClass="min-w-[200px]"
                    />
                    <div>
                        <p className="text-[10px] uppercase tracking-widest opacity-40 font-bold">{tr.editing}</p>
                        <h3 className="text-lg font-extrabold leading-tight">{pageName}</h3>
                    </div>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[10px] uppercase tracking-widest opacity-40 font-bold">{tr.previewLangLabel}</span>
                    <div className={`flex rounded-xl overflow-hidden border ${theme === 'dark' ? 'border-white/10' : 'border-gray-300'}`}>
                        {['en', 'vi'].map(l => (
                            <button key={l} onClick={() => setPreviewLang(l)}
                                className={`px-3 py-2 text-sm font-bold ${previewLang === l ? 'bg-[#00d2ff]/20 text-[#00d2ff]' : 'opacity-60'}`}>
                                {tr[l]}
                            </button>
                        ))}
                    </div>
                    <button onClick={saveDraft} disabled={busy} className="flex items-center gap-2 px-3 py-2 rounded-xl border border-white/10 hover:bg-white/10 disabled:opacity-40 transition text-sm font-bold">
                        <Save size={16} /> {tr.saveDraft}
                    </button>
                    <button onClick={publish} disabled={busy}
                        className="flex items-center gap-2 px-4 py-2 rounded-xl font-bold text-white bg-gradient-to-r from-[#00d2ff] to-[#9d50bb] disabled:opacity-40 transition">
                        {busy ? <Loader2 size={16} className="animate-spin" /> : <Power size={16} />} {tr.publish}
                    </button>
                </div>
            </div>

            {msg && (
                <div className={`p-3 rounded-xl text-sm font-medium border
                    ${msg.type === 'ok' ? 'bg-green-500/10 border-green-500/30 text-green-400'
                        : 'bg-red-500/10 border-red-500/30 text-red-400'}`}>
                    {msg.text}
                </div>
            )}

            <div className={`p-3 rounded-xl text-xs leading-snug border ${theme === 'dark' ? 'bg-amber-500/10 border-amber-500/20 text-amber-300' : 'bg-amber-50 border-amber-200 text-amber-700'}`}>
                {tr.bilingualNote}
            </div>

            <div className="grid lg:grid-cols-2 gap-6 items-start">
                {/* ── Editor (left) — both languages per field ── */}
                <div className="space-y-5">
                    {manifest.map(group => (
                        <div key={group.section.en} className={`p-5 rounded-2xl border ${_panelCls(theme)}`}>
                            <h4 className="font-extrabold mb-4">{group.section[lang] || group.section.en}</h4>
                            <div className="space-y-4">
                                {group.fields.map(f => (
                                    <div key={f.key}>
                                        <label className="text-xs font-bold opacity-60">{f.label[lang] || f.label.en}</label>
                                        <div className="grid grid-cols-2 gap-3 mt-1">
                                            {['en', 'vi'].map(l => (
                                                <div key={l}>
                                                    <span className="text-[10px] uppercase font-extrabold tracking-widest opacity-40">{l}</span>
                                                    {f.type === 'textarea' ? (
                                                        <textarea rows={3} value={content[l][f.key] || ''}
                                                            onChange={e => setField(l, f.key, e.target.value)} onBlur={commit} className={_inputCls(theme)} />
                                                    ) : f.type === 'image' ? (
                                                        <>
                                                            <input value={content[l][f.key] || ''} placeholder={tr.imageUrl}
                                                                onChange={e => setField(l, f.key, e.target.value)} onBlur={commit}
                                                                onKeyDown={e => e.key === 'Enter' && commit()} className={_inputCls(theme)} />
                                                            {content[l][f.key] && (
                                                                <img src={content[l][f.key]} alt="" className="mt-2 max-h-32 rounded-lg border border-white/10" />
                                                            )}
                                                        </>
                                                    ) : (
                                                        <input value={content[l][f.key] || ''}
                                                            onChange={e => setField(l, f.key, e.target.value)} onBlur={commit}
                                                            onKeyDown={e => e.key === 'Enter' && commit()} className={_inputCls(theme)} />
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ))}

                    {/* Revisions */}
                    <div className={`p-5 rounded-2xl border ${_panelCls(theme)}`}>
                        <h4 className="font-extrabold mb-4 flex items-center gap-2"><History size={18} /> {tr.revisions}</h4>
                        <div className="space-y-2">
                            {revisions.length === 0 && <p className="text-sm opacity-50">—</p>}
                            {revisions.map(r => (
                                <div key={r.revision_no} className="flex items-center justify-between gap-2 text-sm">
                                    <span className="opacity-70">
                                        {tr.rev} {r.revision_no}
                                        {r.is_current && <span className="ml-2 text-[10px] uppercase font-bold text-[#00d2ff]">{tr.current}</span>}
                                    </span>
                                    {!r.is_current && (
                                        <button onClick={() => restore(r.revision_no)} disabled={busy}
                                            className="px-2 py-1 rounded-lg text-xs font-bold border border-white/10 hover:bg-white/10 transition">
                                            {tr.restore}
                                        </button>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                {/* ── Live preview (right, sticky) ── */}
                <div className="lg:sticky lg:top-24">
                    <div className="flex items-center justify-between mb-2">
                        <h4 className="font-extrabold flex items-center gap-2"><Eye size={16} /> {tr.livePreview}</h4>
                        <button onClick={() => window.open(CMS_PREVIEW_ROUTE[page], '_blank')}
                            className="flex items-center gap-1.5 text-xs font-bold opacity-60 hover:opacity-100 transition">
                            <ExternalLink size={14} /> {tr.openTab}
                        </button>
                    </div>
                    <div ref={paneRef}
                        className={`relative w-full rounded-2xl border overflow-hidden h-[72vh] ${_panelCls(theme)}`}>
                        {box.w > 0 && (
                            <iframe
                                ref={iframeRef}
                                title="cms-preview"
                                src={CMS_PREVIEW_ROUTE[page]}
                                onLoad={postToPreview}
                                style={{
                                    width: DESIGN_W,
                                    height: box.h / scale,
                                    border: 0,
                                    transform: `scale(${scale})`,
                                    transformOrigin: 'top left',
                                }}
                            />
                        )}
                    </div>
                    <p className="text-[11px] opacity-50 mt-2">{tr.previewHint}</p>
                </div>
            </div>
        </div>
    );
}

// ── Plan management (token amount / price per plan) ───────────────────────────
function PlansSection({ theme, lang }) {
    const tr = SECTION_I18N[lang] || SECTION_I18N.en;
    const [plans, setPlans] = useState([]);
    const [busy, setBusy] = useState(false);
    const [msg, setMsg] = useState(null);
    const [form, setForm] = useState(null); // editing draft or null

    const load = async () => {
        setBusy(true);
        try { const r = await adminGetBillingPlans(); setPlans(r.plans || []); }
        catch (e) { setMsg({ type: 'err', text: e.message }); }
        finally { setBusy(false); }
    };
    useEffect(() => { load(); }, []);

    const openEdit = (p) => setForm({
        plan_id: p.plan_id, plan_code: p.plan_code, plan_name: p.plan_name, plan_type: p.plan_type,
        price_amount: p.price_amount, token_amount: p.token_amount,
        duration_days: p.duration_days ?? '', sort_order: p.sort_order, is_active: p.is_active,
    });
    const openCreate = () => setForm({
        plan_id: null, plan_code: '', plan_name: '', plan_type: 'token_pack',
        price_amount: 0, token_amount: 0, duration_days: '', sort_order: 0, is_active: true,
    });

    const submit = async () => {
        setBusy(true); setMsg(null);
        try {
            const common = {
                plan_name: form.plan_name,
                price_amount: Number(form.price_amount),
                token_amount: Number(form.token_amount),
                duration_days: form.duration_days === '' ? null : Number(form.duration_days),
                sort_order: Number(form.sort_order),
            };
            if (form.plan_id) {
                await adminUpdatePlan(form.plan_id, { ...common, is_active: form.is_active });
            } else {
                await adminCreatePlan({ ...common, plan_code: form.plan_code, plan_type: form.plan_type });
            }
            setForm(null);
            setMsg({ type: 'ok', text: tr.planSaved });
            await load();
        } catch (e) { setMsg({ type: 'err', text: e.message }); }
        finally { setBusy(false); }
    };
    const toggle = async (p) => {
        try {
            if (p.is_active) await adminDeactivatePlan(p.plan_id);
            else await adminUpdatePlan(p.plan_id, { is_active: true });
            await load();
        } catch (e) { setMsg({ type: 'err', text: e.message }); }
    };

    return (
        <div className="space-y-6 animate-in">
            <div className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                    <h3 className="text-2xl font-extrabold">{tr.plansTitle}</h3>
                    <p className="text-sm opacity-50">{tr.plansSub}</p>
                </div>
                <button onClick={openCreate}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl font-bold text-white bg-gradient-to-r from-[#00d2ff] to-[#9d50bb] hover:opacity-90 transition">
                    <Plus size={18} /> {tr.addPlan}
                </button>
            </div>

            {msg && (
                <div className={`p-3 rounded-xl text-sm font-medium border
                    ${msg.type === 'ok' ? 'bg-green-500/10 border-green-500/30 text-green-400' : 'bg-red-500/10 border-red-500/30 text-red-400'}`}>
                    {msg.text}
                </div>
            )}

            <div className={`rounded-2xl border overflow-hidden ${_panelCls(theme)}`}>
                <table className="w-full text-sm">
                    <thead className={theme === 'dark' ? 'bg-white/5' : 'bg-slate-100'}>
                        <tr className="text-left">
                            <th className="px-4 py-3 font-bold">{tr.planName}</th>
                            <th className="px-4 py-3 font-bold">{tr.planType}</th>
                            <th className="px-4 py-3 font-bold">{tr.planPrice}</th>
                            <th className="px-4 py-3 font-bold">{tr.planTokens}</th>
                            <th className="px-4 py-3 font-bold">{tr.planDuration}</th>
                            <th className="px-4 py-3 font-bold">{tr.planActive}</th>
                            <th className="px-4 py-3 font-bold text-right">{tr.planActions}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {plans.length === 0 && <tr><td colSpan={7} className="px-4 py-8 text-center opacity-50">{tr.noPlans}</td></tr>}
                        {plans.map(p => (
                            <tr key={p.plan_id} className="border-t border-white/5">
                                <td className="px-4 py-3">{p.plan_name}</td>
                                <td className="px-4 py-3 text-xs opacity-70">{p.plan_type === 'subscription' ? tr.planSubscription : tr.planTokenPack}</td>
                                <td className="px-4 py-3">{new Intl.NumberFormat('vi-VN').format(p.price_amount)}</td>
                                <td className="px-4 py-3">{p.token_amount}</td>
                                <td className="px-4 py-3">{p.duration_days ?? '—'}</td>
                                <td className="px-4 py-3">
                                    <button onClick={() => toggle(p)}
                                        className={`px-2 py-1 rounded-full text-[10px] font-extrabold uppercase border
                                            ${p.is_active ? 'bg-green-500/10 text-green-400 border-green-500/30' : 'bg-red-500/10 text-red-400 border-red-500/30'}`}>
                                        {p.is_active ? tr.active : tr.inactive}
                                    </button>
                                </td>
                                <td className="px-4 py-3 text-right">
                                    <button onClick={() => openEdit(p)} title={tr.edit}
                                        className="p-1.5 rounded-lg hover:bg-white/10 transition"><Pencil size={16} /></button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {form && createPortal(
                <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-in fade-in duration-300">
                    <div className={`max-w-2xl w-full max-h-[88vh] flex flex-col rounded-[32px] border ${theme === 'dark' ? 'bg-[#0f1218] border-white/10 text-white' : 'bg-white border-gray-200 text-slate-900 shadow-2xl'}`}>
                        <div className={`flex justify-between items-center px-8 pt-7 pb-4 border-b flex-shrink-0 rounded-t-[32px] ${theme === 'dark' ? 'border-white/10 bg-[#0f1218]' : 'border-gray-200 bg-white'}`}>
                            <h3 className="text-2xl font-bold">{form.plan_id ? tr.editPlan : tr.addPlan}</h3>
                            <button onClick={() => setForm(null)} className="p-2 rounded-lg hover:bg-white/10 transition-colors"><X size={20} /></button>
                        </div>
                        <div className="px-8 py-6 overflow-y-auto custom-scrollbar flex-1 space-y-4">
                            {!form.plan_id && (
                                <div className="grid grid-cols-2 gap-3">
                                    <div>
                                        <label className="text-xs font-bold opacity-60">{tr.planCode}</label>
                                        <input value={form.plan_code} onChange={e => setForm({ ...form, plan_code: e.target.value })} className={_inputCls(theme)} />
                                    </div>
                                    <div>
                                        <label className="text-xs font-bold opacity-60 block mb-1">{tr.planType}</label>
                                        <FancySelect value={form.plan_type} onChange={v => setForm({ ...form, plan_type: v })}
                                            options={[{ value: 'token_pack', label: tr.planTokenPack }, { value: 'subscription', label: tr.planSubscription }]}
                                            theme={theme} widthClass="w-full" panelWidthClass="w-full" />
                                    </div>
                                </div>
                            )}
                            <div>
                                <label className="text-xs font-bold opacity-60">{tr.planName}</label>
                                <input value={form.plan_name} onChange={e => setForm({ ...form, plan_name: e.target.value })} className={_inputCls(theme)} />
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="text-xs font-bold opacity-60">{tr.planPrice}</label>
                                    <input type="number" min={0} value={form.price_amount} onChange={e => setForm({ ...form, price_amount: e.target.value })} className={_inputCls(theme)} />
                                </div>
                                <div>
                                    <label className="text-xs font-bold opacity-60">{tr.planTokens}</label>
                                    <input type="number" min={0} value={form.token_amount} onChange={e => setForm({ ...form, token_amount: e.target.value })} className={_inputCls(theme)} />
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="text-xs font-bold opacity-60">{tr.planDuration}</label>
                                    <input type="number" min={0} value={form.duration_days} onChange={e => setForm({ ...form, duration_days: e.target.value })} className={_inputCls(theme)} />
                                    <p className="text-[11px] opacity-50 mt-1">{tr.planDurationHint}</p>
                                </div>
                                <div>
                                    <label className="text-xs font-bold opacity-60">{tr.planOrder}</label>
                                    <input type="number" value={form.sort_order} onChange={e => setForm({ ...form, sort_order: e.target.value })} className={_inputCls(theme)} />
                                </div>
                            </div>
                            {form.plan_id && (
                                <label className="flex items-center gap-2 text-sm">
                                    <input type="checkbox" checked={form.is_active} onChange={e => setForm({ ...form, is_active: e.target.checked })} />
                                    {tr.planActive}
                                </label>
                            )}
                        </div>
                        <div className={`flex items-center justify-end gap-3 px-8 py-5 border-t flex-shrink-0 rounded-b-[32px] ${theme === 'dark' ? 'border-white/10 bg-[#0f1218]' : 'border-gray-200 bg-white'}`}>
                            <button onClick={() => setForm(null)}
                                className={`px-5 py-3 rounded-2xl font-extrabold transition-all ${theme === 'dark' ? 'bg-white/5 hover:bg-white/10' : 'bg-gray-100 hover:bg-gray-200'}`}>{tr.cancel}</button>
                            <button onClick={submit} disabled={busy || !form.plan_name || (!form.plan_id && !form.plan_code)}
                                className="flex items-center gap-2 px-5 py-3 bg-[#00d2ff] hover:bg-[#00bce6] text-[#0b0e14] rounded-2xl font-extrabold transition-all shadow-lg shadow-[#00d2ff]/30 disabled:opacity-50">
                                <Save size={16} /> {tr.save}
                            </button>
                        </div>
                    </div>
                </div>,
                document.body,
            )}
        </div>
    );
}

export default App;
