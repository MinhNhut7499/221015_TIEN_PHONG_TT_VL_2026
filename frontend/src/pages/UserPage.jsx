import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
    Upload,
    Cpu,
    History,
    User,
    ChevronLeft,
    ChevronRight,
    Sun,
    Moon,
    Globe,
    LogOut,
    Image as ImageIcon,
    CheckCircle,
    Loader2,
    Trash2,
    ExternalLink,
    Search,
    Menu,
    ShieldCheck,
    Layers,
    Users as UsersIcon,
    Sliders,
    Calendar,
    AlertTriangle,
    FileDown,
    BookOpen,
    ChevronDown,
    Wallet,
    CreditCard,
    Sparkles,
    Coins
} from 'lucide-react';
import {
    RadarChart,
    Radar,
    PolarGrid,
    PolarAngleAxis,
    ResponsiveContainer,
    Tooltip
} from 'recharts';
import {
    uploadImage, analyzeImage, getHistory, getMe, getHistoryDetail, getHistoryImageObjectUrl,
    billingGetWallet, billingGetPlans, billingGetTransactions, billingGetLedger, billingCheckout,
    getPublishedContent, getCmsDraftContent, deleteAccount,
} from '../utils/api';
import { useAuth } from '../context/AuthContext';
import { useApp } from '../context/AppContext';
import FancySelect from '../components/FancySelect';
import StyleKnowledgeCard from '../components/StyleKnowledgeCard';
import AnalysisChat from '../components/AnalysisChat';
import { exportAnalysisPdf } from '../utils/exportPdf';

function jwtClaims() {
    try {
        const token = localStorage.getItem('archi_access_token');
        if (!token) return {};
        const [, payload] = token.split('.');
        // Decode base64url AND interpret the bytes as UTF-8 so names with
        // diacritics (e.g. Vietnamese) are not mangled into mojibake.
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

const I18N = {
    en: {
        upload: "Upload",
        analyze: "Analyze",
        history: "History",
        profile: "Profile",
        billing: "Plans & Tokens",
        adminPanel: "Admin panel",
        logout: "Logout",
        dangerZone: "Danger Zone",
        deleteAccount: "Delete account",
        deleteAccountDesc: "Permanently delete your account, uploaded images and analysis history. Anonymised payment records are kept for accounting only. This cannot be undone.",
        deleteModalTitle: "Delete your account?",
        deleteModalBody: "This permanently removes your profile, images and analysis history. Type DELETE to confirm.",
        deleteConfirmWord: "DELETE",
        deleteTypeToConfirm: "Type DELETE to confirm",
        deleteLearnMore: "Learn how deletion works",
        deleting: "Deleting…",
        currentPlan: "Current plan",
        noPlan: "Free",
        tokenPacks: "Token packs",
        subscriptions: "Subscriptions",
        perAnalysis: "/ analysis",
        tokensWord: "tokens",
        buyNow: "Buy now",
        daysWord: "days",
        billingHistory: "Payment history",
        tokenLedger: "Token activity",
        noTransactions: "No transactions yet.",
        noLedger: "No token activity yet.",
        redirecting: "Redirecting to payment...",
        colAmount: "Amount",
        colPlan: "Plan",
        insufficientTokens: "You are out of tokens. Buy a pack or upgrade your plan below.",
        balanceLabel: "Balance",
        confirmTitle: "Review your order",
        youGet: "What you get",
        total: "Total",
        proceedPay: "Proceed to payment",
        cancel: "Cancel",
        secureNote: "You'll be redirected to VNPay's secure page to complete payment. We never see your card or bank details.",
        featTokens: "tokens added to your wallet",
        featNeverExpire: "Tokens never expire",
        featDuration: "days of tier access",
        featDiscount: "lower cost per analysis",
        dragDrop: "Drag and drop architectural photo here",
        orBrowse: "or click to browse files",
        maxSize: "Max size: 10MB (JPG, PNG, WEBP)",
        uploading: "Uploading...",
        analysisStatus: "Analysis Status",
        processing: "Processing AI analysis...",
        completed: "Analysis Completed",
        result: "Analysis Result",
        style: "Architectural Style",
        confidence: "Confidence",
        description: "Description",
        noFile: "Please upload a file first",
        startAnalyze: "Analyze Image",
        recentHistory: "Recent History",
        userInfo: "User Information",
        theme: "Appearance",
        language: "Language",
        sourceImage: "Source Image",
        keyEvidence: "Key Evidence",
        styleDistribution: "Style Distribution",
        evidenceSheet: "Evidence (12 dimensions)",
        evidenceHelp: "Concrete features the AI observed in each structural dimension.",
        compositionExplanation: "Composition Explanation",
        aiVerified: "AI Verified",
        processingLabel: "Processing",
        stepUploaded: "Image Uploaded",
        stepUploadedDesc: "Successful pre-processing",
        stepProcessingDesc: "Extracting structural features",
        stepDoneDesc: "Ready to view findings",
        role: "Role",
        perStyleWhy: "Why each style",
        rolePrimary: "Primary",
        roleSecondary: "Secondary",
        panelAgreement: "Panel agreement",
        panelVerdicts: "Judge panel",
        uncertain: "Uncertain",
        hybrid: "Hybrid / eclectic",
        suggestedStyles: "Suggests",
        searchStyle: "Search style...",
        minConfidence: "Min confidence",
        allProjects: "All projects",
        allYears: "All years",
        allMonths: "All months",
        allDays: "All days",
        monthLabel: "Month",
        dayLabel: "Day",
        noMatch: "No analyses match your filters.",
        colImage: "Image",
        colStyle: "Style",
        colConfidence: "Confidence",
        colDate: "Date",
        colStatus: "Status",
        loadingHistory: "Loading history...",
        noHistory: "No analysis history yet. Upload an image to get started.",
        clickReopen: "Click to re-open analysis",
        downloadPdf: "Download PDF",
        learnStyle: "Learn about this style",
        stats: {
            total: "Total Analyzed",
            bestConfidence: "Best Confidence",
            accuracy: "Avg. Confidence"
        }
    },
    vi: {
        upload: "Tải lên",
        analyze: "Phân tích",
        history: "Lịch sử",
        profile: "Hồ sơ",
        billing: "Gói & Token",
        adminPanel: "Trang quản trị",
        logout: "Đăng xuất",
        dangerZone: "Vùng nguy hiểm",
        deleteAccount: "Xóa tài khoản",
        deleteAccountDesc: "Xóa vĩnh viễn tài khoản, ảnh đã tải lên và lịch sử phân tích của bạn. Bản ghi thanh toán được giữ ở dạng ẩn danh chỉ phục vụ kế toán. Thao tác này không thể hoàn tác.",
        deleteModalTitle: "Xóa tài khoản của bạn?",
        deleteModalBody: "Thao tác này xóa vĩnh viễn hồ sơ, ảnh và lịch sử phân tích của bạn. Gõ XÓA để xác nhận.",
        deleteConfirmWord: "XÓA",
        deleteTypeToConfirm: "Gõ XÓA để xác nhận",
        deleteLearnMore: "Tìm hiểu cách xóa dữ liệu",
        deleting: "Đang xóa…",
        currentPlan: "Gói hiện tại",
        noPlan: "Miễn phí",
        tokenPacks: "Gói token",
        subscriptions: "Gói thuê bao",
        perAnalysis: "/ lần phân tích",
        tokensWord: "token",
        buyNow: "Mua ngay",
        daysWord: "ngày",
        billingHistory: "Lịch sử thanh toán",
        tokenLedger: "Biến động token",
        noTransactions: "Chưa có giao dịch nào.",
        noLedger: "Chưa có biến động token.",
        redirecting: "Đang chuyển tới trang thanh toán...",
        colAmount: "Số tiền",
        colPlan: "Gói",
        insufficientTokens: "Bạn đã hết token. Hãy mua gói token hoặc nâng cấp bên dưới.",
        balanceLabel: "Số dư",
        confirmTitle: "Xem lại đơn hàng",
        youGet: "Bạn nhận được",
        total: "Tổng cộng",
        proceedPay: "Tiến hành thanh toán",
        cancel: "Hủy",
        secureNote: "Bạn sẽ được chuyển sang trang an toàn của VNPay để hoàn tất thanh toán. Chúng tôi không bao giờ thấy thông tin thẻ/ngân hàng của bạn.",
        featTokens: "token được cộng vào ví",
        featNeverExpire: "Token không bao giờ hết hạn",
        featDuration: "ngày sử dụng gói",
        featDiscount: "chi phí mỗi lần phân tích thấp hơn",
        dragDrop: "Kéo thả ảnh kiến trúc vào đây",
        orBrowse: "hoặc click để chọn tệp",
        maxSize: "Tối đa: 10MB (JPG, PNG, WEBP)",
        uploading: "Đang tải lên...",
        analysisStatus: "Trạng thái phân tích",
        processing: "Đang xử lý AI...",
        completed: "Phân tích hoàn tất",
        result: "Kết quả phân tích",
        style: "Phong cách kiến trúc",
        confidence: "Độ tin cậy",
        description: "Mô tả",
        noFile: "Vui lòng tải lên một tệp trước",
        startAnalyze: "Phân tích hình ảnh",
        recentHistory: "Lịch sử gần đây",
        userInfo: "Thông tin người dùng",
        theme: "Giao diện",
        language: "Ngôn ngữ",
        sourceImage: "Ảnh gốc",
        keyEvidence: "Bằng chứng chính",
        styleDistribution: "Phân bố phong cách",
        evidenceSheet: "Bằng chứng (12 chiều)",
        evidenceHelp: "Các đặc trưng cụ thể mà AI quan sát được ở từng chiều cấu trúc.",
        compositionExplanation: "Giải thích tổ hợp",
        aiVerified: "AI Xác thực",
        processingLabel: "Xử lý",
        stepUploaded: "Đã tải ảnh lên",
        stepUploadedDesc: "Tiền xử lý thành công",
        stepProcessingDesc: "Đang trích xuất đặc trưng kết cấu",
        stepDoneDesc: "Sẵn sàng xem kết quả",
        role: "Vai trò",
        perStyleWhy: "Vì sao mỗi phong cách",
        rolePrimary: "Chính",
        roleSecondary: "Phụ",
        panelAgreement: "Đồng thuận hội đồng",
        panelVerdicts: "Hội đồng giám khảo",
        uncertain: "Chưa chắc chắn",
        hybrid: "Lai / pha trộn",
        suggestedStyles: "Gợi ý",
        searchStyle: "Tìm phong cách...",
        minConfidence: "Độ tin cậy tối thiểu",
        allProjects: "Tất cả dự án",
        allYears: "Tất cả năm",
        allMonths: "Tất cả tháng",
        allDays: "Tất cả ngày",
        monthLabel: "Tháng",
        dayLabel: "Ngày",
        noMatch: "Không có phân tích nào khớp bộ lọc.",
        colImage: "Ảnh",
        colStyle: "Phong cách",
        colConfidence: "Độ tin cậy",
        colDate: "Ngày",
        colStatus: "Trạng thái",
        loadingHistory: "Đang tải lịch sử...",
        noHistory: "Chưa có lịch sử phân tích. Tải ảnh lên để bắt đầu.",
        clickReopen: "Bấm để xem lại phân tích",
        downloadPdf: "Tải báo cáo PDF",
        learnStyle: "Tìm hiểu phong cách này",
        stats: {
            total: "Đã phân tích",
            bestConfidence: "Độ tin cậy cao nhất",
            accuracy: "Độ tin cậy TB"
        }
    }
};

// Metadata for the 12 evidence-sheet dimensions Agent A fills in: an icon and a
// bilingual label so the raw dimension keys render as a meaningful grid.
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
    diagnostic: { icon: '🔍', en: 'Diagnostic', vi: 'Chẩn đoán' }
};

const App = () => {
    const { theme, lang, toggleTheme, toggleLang } = useApp();
    const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(localStorage.getItem('archi_sidebar') === 'true');
    const [activeSection, setActiveSection] = useState('upload');
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

    const [uploadedFile, setUploadedFile] = useState(null);
    const [isUploading, setIsUploading] = useState(false);
    const [analysisStatus, setAnalysisStatus] = useState('idle');
    const [analysisResult, setAnalysisResult] = useState(null);
    // True while the deferred Vietnamese translation is being fetched + cached
    // (drives the small "translating" chip on the result).
    const [translating, setTranslating] = useState(false);
    const [fileId, setFileId] = useState(null);
    const [historyItems, setHistoryItems] = useState([]);
    const [historyLoading, setHistoryLoading] = useState(false);
    const [error, setError] = useState(null);
    const [profile, setProfile] = useState(null);
    // Billing / token wallet state.
    const [wallet, setWallet] = useState(null);
    const [plans, setPlans] = useState([]);
    const [transactions, setTransactions] = useState([]);
    const [ledger, setLedger] = useState([]);
    const [billingLoading, setBillingLoading] = useState(false);
    const [buyingPlanId, setBuyingPlanId] = useState(null);
    const [confirmPlan, setConfirmPlan] = useState(null); // plan pending checkout confirmation
    const [openingId, setOpeningId] = useState(null);
    const [cardStyle, setCardStyle] = useState(null); // style name shown in the knowledge card modal
    // Accordion open-state (compact-by-default). Empty → fall back to defaults
    // (per-style: primary open; dimensions: collapsed). Reset on each new result.
    const [openStyles, setOpenStyles] = useState({});
    const [openDims, setOpenDims] = useState({});

    // History filters.
    const [styleQuery, setStyleQuery] = useState('');
    const [minConf, setMinConf] = useState(0);
    const [filterYear, setFilterYear] = useState('all');
    const [filterMonth, setFilterMonth] = useState('all');
    const [filterDay, setFilterDay] = useState('all');
    const [filterProject, setFilterProject] = useState('all');
    const [thumbs, setThumbs] = useState({}); // { image_id: objectUrl }

    const { logout } = useAuth();
    const navigate = useNavigate();

    // Admin-managed CMS content for this page (published in normal use; live
    // draft via postMessage in ?preview=1 mode). Merged over the I18N defaults.
    const [cmsOverride, setCmsOverride] = useState(null);
    const [previewLang, setPreviewLang] = useState(null);
    const isPreview = new URLSearchParams(window.location.search).get('preview') === '1';
    // Once a live edit arrives via postMessage, the parent owns the content; a
    // late self-fetch must not clobber it (E3).
    const liveRef = useRef(false);

    useEffect(() => {
        const load = isPreview ? getCmsDraftContent : getPublishedContent;
        load('user').then((res) => {
            if (res && res.content && !liveRef.current) setCmsOverride(res.content);
        }).catch(() => {});
    }, [isPreview]);

    useEffect(() => {
        if (!isPreview) return;
        const onMsg = (e) => {
            if (e.origin !== window.location.origin) return;
            if (e.data && e.data.source === 'archi-cms') {
                if (e.data.page && e.data.page !== 'user') return; // ignore other-page edits (E4)
                liveRef.current = true;
                if (e.data.content) setCmsOverride(e.data.content);
                if (e.data.lang) setPreviewLang(e.data.lang);
            }
        };
        window.addEventListener('message', onMsg);
        window.parent && window.parent.postMessage({ source: 'archi-cms-ready' }, window.location.origin);
        return () => window.removeEventListener('message', onMsg);
    }, [isPreview]);

    const effLang = previewLang || lang;
    const t = useMemo(() => {
        const base = I18N[effLang];
        const ov = (cmsOverride && cmsOverride[effLang]) || {};
        const out = { ...base };
        for (const k in ov) {
            const v = ov[k];
            if (v != null && v !== '') out[k] = v; // empty → fall back to default (E2)
        }
        return out;
    }, [effLang, cmsOverride]);
    const dark = theme === 'dark';
    // Architectural style names stay in English in both languages (proper nouns).
    const styleLabel = useCallback((style) => style, []);

    const handleLogout = () => {
        logout();
        navigate('/');
    };

    // Self-service account deletion (Danger Zone). Requires typing the confirm
    // word; on success the session is cleared and the user is sent to landing.
    const [showDeleteModal, setShowDeleteModal] = useState(false);
    const [deleteConfirmText, setDeleteConfirmText] = useState('');
    const [deletingAccount, setDeletingAccount] = useState(false);
    const [deleteError, setDeleteError] = useState(null);

    const handleDeleteAccount = async () => {
        setDeletingAccount(true);
        setDeleteError(null);
        try {
            await deleteAccount();
            logout();
            navigate('/');
        } catch (err) {
            setDeleteError(err.message);
            setDeletingAccount(false);
        }
    };

    // Real upload-section stats derived from analysis history.
    const stats = useMemo(() => {
        const confidences = historyItems
            .map((i) => i.confidence)
            .filter((c) => typeof c === 'number');
        const avg = confidences.length
            ? Math.round((confidences.reduce((a, b) => a + b, 0) / confidences.length) * 100)
            : null;
        const best = confidences.length ? Math.round(Math.max(...confidences) * 100) : null;
        return {
            total: historyItems.length,
            best: best != null ? `${best}%` : '—',
            avg: avg != null ? `${avg}%` : '—'
        };
    }, [historyItems]);

    // Radar uses the final open-vocabulary mixture distribution.
    const radarData = useMemo(() => {
        const finalDist = analysisResult?.style_distribution?.distribution;
        if (!finalDist || !Object.keys(finalDist).length) return [];
        return Object.entries(finalDist)
            .map(([style, prob]) => ({ style: styleLabel(style), value: Math.round(prob * 100) }))
            .filter((d) => d.value > 0)
            .sort((a, b) => b.value - a.value);
    }, [analysisResult, styleLabel]);

    // User profile for header + profile section: DB (/auth/me) first, JWT fallback.
    const userView = useMemo(() => {
        const claims = jwtClaims();
        return {
            name: claims.name || profile?.name || claims.email || 'User',
            email: profile?.email || claims.email || '—',
            picture: profile?.picture || null,
            role: profile?.role || claims.role || 'user'
        };
    }, [profile]);

    // Localised narrative fields: prefer the *_vi translations in Vietnamese.
    const localized = useMemo(() => {
        if (!analysisResult) return null;
        const useVi = lang === 'vi';
        return {
            explanation: (useVi && analysisResult.explanation_vi) || analysisResult.explanation,
            keyEvidence: (useVi && analysisResult.key_evidence_vi) || analysisResult.key_evidence,
            composition:
                (useVi && analysisResult.composition_explanation_vi) ||
                analysisResult.composition_explanation
        };
    }, [analysisResult, lang]);

    // Per-style "why": each style in the mixture (primary first, then secondary)
    // with its role badge, % and the evidence bullets that justify it.
    const perStyleData = useMemo(() => {
        const dist = analysisResult?.style_distribution;
        const evidence = (lang === 'vi' && analysisResult?.evidence_per_style_vi)
            || analysisResult?.evidence_per_style;
        if (!dist?.distribution || !evidence) return [];
        const primary = dist.primary;
        const ordered = Object.entries(dist.distribution)
            .filter(([s]) => evidence[s]?.length)
            .sort((a, b) => b[1] - a[1])
            .sort((a, b) => (a[0] === primary ? -1 : b[0] === primary ? 1 : 0));
        return ordered.map(([style, prob]) => ({
            style,
            pct: Math.round(prob * 100),
            isPrimary: style === primary,
            bullets: evidence[style]
        }));
    }, [analysisResult, lang]);

    // The 12-dimension evidence sheet grouped by dimension (in canonical order).
    // Prefer the Vietnamese sheet (feature/note translated) when in VI mode.
    const evidenceByDimension = useMemo(() => {
        const items = ((lang === 'vi' && analysisResult?.evidence_sheet_vi?.items)
            || analysisResult?.evidence_sheet?.items);
        if (!items?.length) return [];
        const order = Object.keys(DIMENSION_META);
        const grouped = {};
        for (const it of items) {
            const key = it.dimension || 'diagnostic';
            (grouped[key] = grouped[key] || []).push(it);
        }
        const known = order.filter((d) => grouped[d]).map((d) => ({ dimension: d, items: grouped[d] }));
        const extra = Object.keys(grouped)
            .filter((d) => !order.includes(d))
            .map((d) => ({ dimension: d, items: grouped[d] }));
        return [...known, ...extra];
    }, [analysisResult, lang]);

    useEffect(() => {
        localStorage.setItem('archi_sidebar', isSidebarCollapsed);
    }, [isSidebarCollapsed]);

    // Collapse all cards back to their defaults whenever a new analysis loads.
    useEffect(() => {
        setOpenStyles({});
        setOpenDims({});
    }, [analysisResult]);

    const loadHistory = useCallback(() => {
        setHistoryLoading(true);
        getHistory()
            .then(data => setHistoryItems(data.items || []))
            .catch(err => setError(err.message))
            .finally(() => setHistoryLoading(false));
    }, []);

    // Load history once on mount so the upload-section stats have real data.
    useEffect(() => {
        loadHistory();
    }, [loadHistory]);

    // Refresh history after a successful analysis so stats stay current.
    useEffect(() => {
        if (analysisStatus === 'completed') loadHistory();
    }, [analysisStatus, loadHistory]);

    // Fetch the authenticated user's profile from the DB (avatar/name/email).
    useEffect(() => {
        getMe()
            .then(setProfile)
            .catch(() => setProfile(null));
    }, []);

    // ── Billing / token wallet ────────────────────────────────────────────────
    const loadBilling = useCallback(() => {
        setBillingLoading(true);
        Promise.all([
            billingGetWallet().catch(() => null),
            billingGetPlans().catch(() => ({ plans: [] })),
            billingGetTransactions().catch(() => ({ transactions: [] })),
            billingGetLedger().catch(() => ({ entries: [] })),
        ]).then(([w, p, tx, lg]) => {
            if (w) setWallet(w);
            setPlans((p && p.plans) || []);
            setTransactions((tx && tx.transactions) || []);
            setLedger((lg && lg.entries) || []);
        }).finally(() => setBillingLoading(false));
    }, []);

    // Wallet on mount so the header balance chip is always populated.
    useEffect(() => {
        billingGetWallet().then(setWallet).catch(() => setWallet(null));
    }, []);

    // Full billing data only when the user opens the Plans & Tokens tab.
    useEffect(() => {
        if (activeSection === 'billing') loadBilling();
    }, [activeSection, loadBilling]);

    // Balance changes after an analysis → refresh the wallet chip.
    useEffect(() => {
        if (analysisStatus === 'completed') {
            billingGetWallet().then(setWallet).catch(() => {});
        }
    }, [analysisStatus]);

    const handleBuy = async (planId) => {
        if (isPreview) return; // CMS preview: interactive but never start a real checkout
        setBuyingPlanId(planId);
        setError(null);
        try {
            const res = await billingCheckout(planId);
            window.location.href = res.redirect_url;  // off to the gateway
        } catch (err) {
            setError(err.message);
            setBuyingPlanId(null);
        }
    };

    const formatVnd = (n) => new Intl.NumberFormat('vi-VN').format(n || 0) + '₫';

    // Lazily fetch resized thumbnails for completed history rows (cached by id).
    useEffect(() => {
        let cancelled = false;
        const completed = historyItems.filter((i) => i.analysis_status === 'completed');
        completed.forEach((item) => {
            if (thumbs[item.image_id]) return;
            getHistoryImageObjectUrl(item.image_id)
                .then((url) => {
                    if (cancelled) { URL.revokeObjectURL(url); return; }
                    setThumbs((prev) => (prev[item.image_id] ? prev : { ...prev, [item.image_id]: url }));
                })
                .catch(() => { /* thumbnail optional */ });
        });
        return () => { cancelled = true; };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [historyItems]);

    const handleFileUpload = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        setIsUploading(true);
        setError(null);
        const preview = URL.createObjectURL(file);
        try {
            const data = await uploadImage(file);
            setFileId(data.file_id);
            setUploadedFile({
                id: data.file_id,
                name: data.original_filename,
                preview,
                size: (data.size_bytes / (1024 * 1024)).toFixed(2) + ' MB'
            });
            setAnalysisStatus('pending');
            setAnalysisResult(null);
            setActiveSection('analyze');
        } catch (err) {
            setError(err.message);
        } finally {
            setIsUploading(false);
        }
    };

    const startAnalysis = async () => {
        if (!fileId) return;
        setAnalysisStatus('processing');
        setError(null);
        try {
            const result = await analyzeImage(fileId);
            setAnalysisResult(result);
            setAnalysisStatus('completed');
            // The Vietnamese translation is produced off the critical path: when
            // the backend signals it is pending, fetch the detail (which makes the
            // server translate + cache it) so the *_vi fields appear a moment
            // later. Best-effort — keep English if it fails.
            if (result.translation_pending && result.image_id) {
                setTranslating(true);
                try {
                    const detail = await getHistoryDetail(result.image_id);
                    setAnalysisResult(detail);
                } catch {
                    /* keep the English result if the translation fetch fails */
                } finally {
                    setTranslating(false);
                }
            }
        } catch (err) {
            setAnalysisStatus('pending');
            setError(err.message);
            // Out of tokens → guide the user straight to the Plans & Tokens tab.
            if (/insufficient token/i.test(err.message || '')) {
                setActiveSection('billing');
            }
        }
    };

    // Re-open a past analysis: fetch its stored result + original image.
    const openHistoryItem = async (item) => {
        if (item.analysis_status !== 'completed') return;
        setOpeningId(item.image_id);
        setError(null);
        try {
            const [detail, imageUrl] = await Promise.all([
                getHistoryDetail(item.image_id),
                getHistoryImageObjectUrl(item.image_id).catch(() => null),
            ]);
            setAnalysisResult(detail);
            setUploadedFile({ id: detail.file_id, name: detail.file_id, preview: imageUrl });
            setFileId(detail.file_id ?? null);
            setAnalysisStatus('completed');
            setActiveSection('analyze');
        } catch (err) {
            setError(err.message);
        } finally {
            setOpeningId(null);
        }
    };

    // ── History filtering ────────────────────────────────────────────────────
    const availableYears = useMemo(() => {
        const ys = new Set();
        historyItems.forEach((i) => { if (i.uploaded_at) ys.add(new Date(i.uploaded_at).getFullYear()); });
        return [...ys].sort((a, b) => b - a);
    }, [historyItems]);

    const availableProjects = useMemo(() => {
        const ps = new Set();
        historyItems.forEach((i) => { if (i.project_name) ps.add(i.project_name); });
        return [...ps].sort();
    }, [historyItems]);

    const filteredHistory = useMemo(() => {
        return historyItems.filter((item) => {
            if (styleQuery && !(item.style || '').toLowerCase().includes(styleQuery.toLowerCase())) return false;
            if (minConf > 0 && !(typeof item.confidence === 'number' && item.confidence >= minConf)) return false;
            if (filterProject !== 'all' && item.project_name !== filterProject) return false;
            if (item.uploaded_at) {
                const d = new Date(item.uploaded_at);
                if (filterYear !== 'all' && d.getFullYear() !== Number(filterYear)) return false;
                if (filterMonth !== 'all' && d.getMonth() + 1 !== Number(filterMonth)) return false;
                if (filterDay !== 'all' && d.getDate() !== Number(filterDay)) return false;
            } else if (filterYear !== 'all' || filterMonth !== 'all' || filterDay !== 'all') {
                return false;
            }
            return true;
        });
    }, [historyItems, styleQuery, minConf, filterProject, filterYear, filterMonth, filterDay]);

    // Result-quality badges shown next to the style verdict.
    const resultBadges = useMemo(() => {
        if (!analysisResult) return [];
        const out = [];
        if (analysisResult.uncertain) out.push({ label: t.uncertain, cls: 'bg-orange-500/15 text-orange-400 border-orange-500/30', icon: AlertTriangle });
        if (analysisResult.hybrid) out.push({ label: t.hybrid, cls: 'bg-purple-500/15 text-[#9d50bb] border-purple-500/30', icon: Layers });
        if (typeof analysisResult.panel_agreement === 'number') {
            out.push({ label: `${t.panelAgreement}: ${(analysisResult.panel_agreement * 100).toFixed(0)}%`, cls: 'bg-[#00d2ff]/15 text-[#00d2ff] border-[#00d2ff]/30', icon: UsersIcon });
        }
        return out;
    }, [analysisResult, t]);

    const NavItem = ({ id, icon: Icon, label }) => {
        const isActive = activeSection === id;
        const activeStyles = dark
            ? 'bg-white/10 text-white border-r-4 border-[#00d2ff]'
            : 'bg-blue-50 text-blue-600 border-r-4 border-blue-600';
        const inactiveStyles = dark
            ? 'text-gray-400 hover:bg-white/5 hover:text-white'
            : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900';
        return (
            <button
                onClick={() => { setActiveSection(id); setIsMobileMenuOpen(false); }}
                className={`w-full flex items-center gap-4 px-4 py-3.5 rounded-xl transition-all duration-200 group ${isActive ? activeStyles : inactiveStyles}`}
            >
                <Icon size={22} className={`transition-transform group-hover:scale-110 ${isActive ? 'scale-110' : ''}`} />
                {(!isSidebarCollapsed || isMobileMenuOpen) && <span className="font-semibold tracking-tight">{label}</span>}
            </button>
        );
    };

    // Shared hover-lift wrapper class for all major cards (matches Admin's feel).
    const cardHover = dark
        ? 'transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_0_30px_rgba(0,210,255,0.15)] hover:border-[#00d2ff]/40'
        : 'transition-all duration-300 hover:-translate-y-1 hover:shadow-2xl hover:border-blue-300';

    const panelBlock = dark ? 'bg-white/5 border-white/10' : 'bg-white border-slate-300 shadow-sm';
    const labelCls = `text-xs font-black uppercase tracking-widest mb-2 ${dark ? 'text-gray-400' : 'text-slate-500'}`;

    return (
        <div className={`min-h-screen font-inter transition-colors duration-500 ${dark ? 'bg-[#0b0e14] text-gray-100' : 'bg-white text-slate-950'}`}>

            {/* Mesh Gradients Background */}
            <div className="fixed inset-0 overflow-hidden pointer-events-none">
                <div className={`absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full opacity-20 blur-[120px] transition-colors duration-500 ${dark ? 'bg-[#00d2ff]' : 'bg-blue-300'}`} />
                <div className={`absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full opacity-20 blur-[120px] transition-colors duration-500 ${dark ? 'bg-[#9d50bb]' : 'bg-purple-300'}`} />
            </div>

            {isMobileMenuOpen && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 lg:hidden" onClick={() => setIsMobileMenuOpen(false)} />
            )}

            {/* SIDEBAR */}
            <aside className={`fixed left-0 top-0 h-screen z-50 border-r transition-all duration-300 ease-in-out backdrop-blur-xl
          ${dark ? 'border-white/5 bg-black/10' : 'border-slate-200 bg-white/95'}
          ${isSidebarCollapsed ? 'w-20' : 'w-64'}
          ${isMobileMenuOpen ? 'translate-x-0 w-64' : '-translate-x-full lg:translate-x-0'}`}
            >
                <div className="flex flex-col h-full p-4">
                    <div className="flex items-center gap-3 mb-10 px-2 h-10 overflow-hidden">
                        <div className="w-10 h-10 flex-shrink-0 rounded-xl bg-gradient-to-br from-[#00d2ff] to-[#9d50bb] flex items-center justify-center shadow-lg shadow-blue-500/20">
                            <ShieldCheck className="text-white" />
                        </div>
                        {(!isSidebarCollapsed || isMobileMenuOpen) && (
                            <span className="font-extrabold text-2xl tracking-tighter bg-gradient-to-r from-[#00d2ff] to-[#9d50bb] bg-clip-text text-transparent">
                                ArchiAI
                            </span>
                        )}
                    </div>

                    <nav className="flex-1 space-y-2">
                        <NavItem id="upload" icon={Upload} label={t.upload} />
                        <NavItem id="analyze" icon={Cpu} label={t.analyze} />
                        <NavItem id="history" icon={History} label={t.history} />
                        <NavItem id="billing" icon={Wallet} label={t.billing} />
                        <NavItem id="profile" icon={User} label={t.profile} />
                    </nav>

                    <div className="mt-auto pt-6 border-t border-white/10">
                        <button
                            onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
                            className={`hidden lg:flex w-full items-center gap-4 px-4 py-3 rounded-xl transition-all group ${dark ? 'text-gray-400 hover:text-white' : 'text-slate-600 hover:text-slate-950'}`}
                        >
                            {isSidebarCollapsed ? <ChevronRight size={22} /> : <ChevronLeft size={22} />}
                            {!isSidebarCollapsed && <span className="font-medium">Collapse</span>}
                        </button>
                        <button onClick={handleLogout} className="w-full flex items-center gap-4 px-4 py-3 rounded-xl text-red-500 hover:bg-red-500/10 transition-all">
                            <LogOut size={22} />
                            {(!isSidebarCollapsed || isMobileMenuOpen) && <span className="font-medium">{t.logout}</span>}
                        </button>
                    </div>
                </div>
            </aside>

            {/* MAIN CONTENT */}
            <main className={`transition-all duration-300 min-h-screen flex flex-col ${isSidebarCollapsed ? 'lg:ml-20' : 'lg:ml-64'}`}>

                {/* HEADER */}
                <header className={`sticky top-0 z-30 h-16 border-b backdrop-blur-md px-4 lg:px-8 flex items-center justify-between transition-colors
          ${dark ? 'border-white/5 bg-transparent' : 'border-slate-300 bg-white/60'}`}>
                    <div className="flex items-center gap-4">
                        <button onClick={() => setIsMobileMenuOpen(true)} className={`p-2 rounded-lg lg:hidden ${dark ? 'hover:bg-white/10' : 'hover:bg-slate-200'}`}>
                            <Menu size={24} />
                        </button>
                        <h2 className={`text-lg font-bold tracking-tight capitalize ${dark ? 'text-white' : 'text-slate-950'}`}>
                            {t[activeSection]}
                        </h2>
                    </div>

                    <div className="flex items-center gap-2 lg:gap-4">
                        {wallet && (
                            <button
                                onClick={() => setActiveSection('billing')}
                                title={t.billing}
                                className={`flex items-center gap-2 px-3 py-1.5 rounded-full border transition-all text-sm font-bold
                ${dark ? 'border-amber-400/30 bg-amber-400/10 text-amber-300 hover:bg-amber-400/20' : 'border-amber-400/40 bg-amber-50 text-amber-700 hover:bg-amber-100'}`}>
                                <Coins size={16} />
                                <span>{wallet.token_balance}</span>
                            </button>
                        )}
                        {userView.role === 'admin' && (
                            <button onClick={() => navigate('/admin')} title={t.adminPanel}
                                className={`flex items-center gap-2 px-3 py-1.5 rounded-full border transition-all text-sm font-bold
                ${dark ? 'border-[#9d50bb]/30 bg-[#9d50bb]/10 text-[#cda9e0] hover:bg-[#9d50bb]/20' : 'border-purple-300 bg-purple-50 text-purple-700 hover:bg-purple-100'}`}>
                                <ShieldCheck size={16} />
                                <span className="hidden sm:inline">{t.adminPanel}</span>
                            </button>
                        )}
                        <button onClick={toggleLang} className={`flex items-center gap-2 px-3 py-1.5 rounded-full border transition-all text-sm font-bold
                ${dark ? 'border-white/10 bg-white/5 hover:bg-white/10' : 'border-slate-300 bg-slate-100 hover:bg-slate-200 text-slate-800'}`}>
                            <Globe size={16} />
                            <span className="hidden sm:inline">{lang === 'en' ? 'EN' : 'VI'}</span>
                        </button>

                        <button onClick={toggleTheme} className={`p-2 rounded-full border transition-all
                ${dark ? 'border-white/10 bg-white/5 hover:bg-white/10' : 'border-slate-300 bg-slate-100 hover:bg-slate-200'}`}>
                            {dark ? <Sun size={18} className="text-yellow-400" /> : <Moon size={18} className="text-blue-600" />}
                        </button>

                        <div className="h-9 w-9 rounded-full bg-gradient-to-br from-[#00d2ff] to-[#9d50bb] p-[2px]">
                            <div className="h-full w-full rounded-full bg-gray-900 flex items-center justify-center overflow-hidden text-white font-black text-sm">
                                {userView.picture
                                    ? <img src={userView.picture} alt="Avatar" referrerPolicy="no-referrer" className="w-full h-full object-cover" />
                                    : <span>{userView.name.charAt(0).toUpperCase()}</span>}
                            </div>
                        </div>
                    </div>
                </header>

                {error && (
                    <div className="mx-4 lg:mx-8 mt-4 p-4 rounded-2xl bg-red-500/10 border border-red-500/30 text-red-400 font-medium text-sm flex items-center justify-between gap-4">
                        <span>⚠ {error}</span>
                        <button onClick={() => setError(null)} className="hover:text-red-300 font-black text-base flex-shrink-0">✕</button>
                    </div>
                )}

                {/* SECTION: CONTENT */}
                <div className="flex-1 p-4 lg:p-8 w-full max-w-[1600px] mx-auto">

                    {/* ── UPLOAD (compact, fits one viewport) ── */}
                    {activeSection === 'upload' && (
                        <div className="flex flex-col gap-5 animate-in fade-in slide-in-from-bottom-4 duration-500">
                            <div className="grid grid-cols-3 gap-4 flex-shrink-0">
                                {[
                                    { label: t.stats.total, val: String(stats.total), text: "text-[#00d2ff]" },
                                    { label: t.stats.bestConfidence, val: stats.best, text: "text-[#9d50bb]" },
                                    { label: t.stats.accuracy, val: stats.avg, text: "text-[#00d2ff]" }
                                ].map((stat, idx) => (
                                    <div key={idx} className={`group p-4 rounded-2xl border backdrop-blur-md cursor-pointer ${panelBlock} ${cardHover}`}>
                                        <p className={`text-[11px] mb-1 font-bold uppercase tracking-widest ${dark ? 'text-gray-400' : 'text-slate-500'}`}>{stat.label}</p>
                                        <p className={`text-3xl font-black ${stat.text} group-hover:scale-105 transition-transform origin-left`}>{stat.val}</p>
                                    </div>
                                ))}
                            </div>

                            {/* Main Upload Box — sized to fit the viewport without page scroll */}
                            <div className={`relative group p-1 rounded-[32px] bg-gradient-to-r from-[#00d2ff]/30 to-[#9d50bb]/30 overflow-hidden h-[58vh] min-h-[300px] ${cardHover}`}>
                                <div className={`relative h-full rounded-[28px] border-2 border-dashed flex flex-col items-center justify-center p-6 transition-all duration-500
                  ${dark ? 'bg-[#0b0e14]/90 border-white/10 hover:border-[#00d2ff]/40' : 'bg-white border-slate-300 hover:border-blue-400'}`}>
                                    {isUploading ? (
                                        <div className="flex flex-col items-center animate-pulse">
                                            <div className="w-16 h-16 rounded-full border-4 border-[#00d2ff] border-t-transparent animate-spin mb-4" />
                                            <p className="text-lg font-bold">{t.uploading}</p>
                                        </div>
                                    ) : (
                                        <>
                                            <div className={`w-20 h-20 mb-5 rounded-3xl flex items-center justify-center border transition-all duration-500 group-hover:rotate-6
                        ${dark ? 'bg-white/5 border-white/10' : 'bg-blue-50 border-blue-100'}`}>
                                                <Upload className="text-[#00d2ff]" size={40} />
                                            </div>
                                            <h3 className={`text-xl lg:text-2xl font-black mb-2 text-center ${dark ? 'text-white' : 'text-slate-950'}`}>{t.dragDrop}</h3>
                                            <p className={`mb-6 text-center font-medium ${dark ? 'text-gray-400' : 'text-slate-600'}`}>{t.maxSize}</p>
                                            <label className="cursor-pointer px-8 py-4 rounded-2xl bg-gradient-to-r from-[#00d2ff] to-[#9d50bb] text-white font-extrabold shadow-xl hover:scale-105 active:scale-95 transition-all">
                                                {t.orBrowse}
                                                <input type="file" className="hidden" accept="image/*" onChange={handleFileUpload} />
                                            </label>
                                        </>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* ── ANALYZE (full-width, restructured blocks) ── */}
                    {activeSection === 'analyze' && (
                        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 space-y-6">

                            {/* Top row: image + analyze control + status */}
                            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                                {/* Source image */}
                                <div className={`lg:col-span-5 p-6 rounded-[28px] border backdrop-blur-md ${panelBlock} ${cardHover}`}>
                                    <div className="flex items-center justify-between mb-4">
                                        <h3 className={`font-bold text-lg flex items-center gap-2 ${dark ? 'text-white' : 'text-slate-950'}`}>
                                            <ImageIcon size={20} className="text-[#00d2ff]" />
                                            {t.sourceImage}
                                        </h3>
                                        {uploadedFile && (
                                            <button onClick={() => { setUploadedFile(null); setFileId(null); setAnalysisStatus('idle'); setAnalysisResult(null); }} className="text-red-500 hover:text-red-400 p-2 rounded-lg hover:bg-red-500/10 transition-colors">
                                                <Trash2 size={18} />
                                            </button>
                                        )}
                                    </div>
                                    <div className="rounded-2xl bg-black/20 overflow-hidden relative border border-white/5 flex items-center justify-center max-h-[50vh]">
                                        {uploadedFile ? (
                                            <div className="relative inline-block leading-none">
                                                <img src={uploadedFile.preview} className="block max-w-full max-h-[50vh] w-auto h-auto object-contain" alt="Preview" />
                                                {analysisStatus === 'processing' && (
                                                    <div className="absolute inset-0 bg-gradient-to-b from-transparent via-[#00d2ff]/40 to-transparent animate-[scan_2s_ease-in-out_infinite]" />
                                                )}
                                                <style>{`@keyframes scan { 0% { transform: translateY(-100%);} 100% { transform: translateY(100%);} }`}</style>
                                            </div>
                                        ) : (
                                            <div className="aspect-[4/3] w-full flex flex-col items-center justify-center gap-4 text-gray-500">
                                                <ImageIcon size={48} className="opacity-20" />
                                                <p className="font-semibold">{t.noFile}</p>
                                            </div>
                                        )}
                                    </div>
                                    <button
                                        disabled={!uploadedFile || analysisStatus === 'processing'}
                                        onClick={startAnalysis}
                                        className={`mt-5 w-full py-4 rounded-2xl flex items-center justify-center gap-3 font-black text-lg transition-all
                      ${!uploadedFile || analysisStatus === 'processing'
                                                ? 'bg-gray-800 text-gray-500 cursor-not-allowed opacity-50'
                                                : 'bg-gradient-to-r from-[#00d2ff] to-[#9d50bb] text-white shadow-2xl hover:scale-[1.02] active:scale-95'}`}
                                    >
                                        {analysisStatus === 'processing' ? <Loader2 size={24} className="animate-spin" /> : <Cpu size={24} />}
                                        {t.startAnalyze}
                                    </button>
                                </div>

                                {/* BLOCK 1: Style + Description */}
                                <div className={`lg:col-span-7 p-6 lg:p-8 rounded-[28px] border backdrop-blur-md ${panelBlock} ${cardHover}`}>
                                    {analysisStatus === 'completed' && analysisResult ? (
                                        <div className="space-y-5">
                                            <div className="flex items-center justify-between flex-wrap gap-3">
                                                <h3 className="text-xl font-black bg-clip-text text-transparent bg-gradient-to-r from-[#00d2ff] to-[#9d50bb]">{t.result}</h3>
                                                <div className="flex items-center gap-2">
                                                    <button
                                                        onClick={() => exportAnalysisPdf(analysisResult, uploadedFile?.preview, lang)}
                                                        title={t.downloadPdf}
                                                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-black uppercase tracking-wider border transition-colors ${dark ? 'bg-white/5 border-white/10 text-gray-200 hover:bg-[#00d2ff]/10 hover:border-[#00d2ff]/40' : 'bg-slate-50 border-slate-200 text-slate-700 hover:bg-blue-50 hover:border-blue-300'}`}
                                                    >
                                                        <FileDown size={13} />{t.downloadPdf}
                                                    </button>
                                                    <span className="px-4 py-1.5 rounded-full bg-green-500/20 text-green-500 text-xs font-black border border-green-500/20 tracking-wider uppercase">{t.aiVerified}</span>
                                                </div>
                                            </div>
                                            <div>
                                                <p className={labelCls}>{t.style}</p>
                                                <button
                                                    onClick={() => setCardStyle(analysisResult.style)}
                                                    title={t.learnStyle}
                                                    className={`group inline-flex items-center gap-2 text-left text-4xl font-black transition-colors ${dark ? 'text-white hover:text-[#00d2ff]' : 'text-slate-950 hover:text-blue-600'}`}
                                                >
                                                    {styleLabel(analysisResult.style)}
                                                    <BookOpen size={20} className="opacity-40 group-hover:opacity-100 transition-opacity flex-shrink-0" />
                                                </button>
                                            </div>
                                            {translating && lang === 'vi' && (
                                                <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#00d2ff]/10 text-[#00d2ff] text-xs font-bold border border-[#00d2ff]/30">
                                                    <Loader2 size={14} className="animate-spin" />
                                                    Đang tạo bản tiếng Việt…
                                                </div>
                                            )}
                                            {resultBadges.length > 0 && (
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    {resultBadges.map((b, i) => (
                                                        <span key={i} className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-black uppercase tracking-wider border ${b.cls}`}>
                                                            <b.icon size={12} />{b.label}
                                                        </span>
                                                    ))}
                                                </div>
                                            )}
                                            <div className="grid grid-cols-2 gap-4">
                                                <div className={`p-4 rounded-2xl border ${dark ? 'bg-white/5 border-white/10' : 'bg-blue-50 border-blue-100'}`}>
                                                    <p className="text-xs text-slate-500 font-bold uppercase tracking-widest mb-1">{t.confidence}</p>
                                                    <p className="text-2xl font-black text-[#00d2ff]">{(analysisResult.confidence * 100).toFixed(0)}%</p>
                                                </div>
                                                <div className={`p-4 rounded-2xl border ${dark ? 'bg-white/5 border-white/10' : 'bg-purple-50 border-purple-100'}`}>
                                                    <p className="text-xs text-slate-500 font-bold uppercase tracking-widest mb-1">{t.processingLabel}</p>
                                                    <p className={`text-lg font-black ${dark ? 'text-white' : 'text-purple-700'}`}>{(analysisResult.processing_time_ms / 1000).toFixed(1)}s</p>
                                                </div>
                                            </div>
                                            <div>
                                                <p className={labelCls}>{t.description}</p>
                                                <p className={`leading-relaxed italic border-l-4 border-[#9d50bb] pl-4 font-medium ${dark ? 'text-gray-300' : 'text-slate-700'}`}>
                                                    "{localized?.explanation}"
                                                </p>
                                            </div>
                                            {localized?.composition && localized.composition !== localized.explanation && (
                                                <div>
                                                    <p className={labelCls}>{t.compositionExplanation}</p>
                                                    <p className={`leading-relaxed font-medium ${dark ? 'text-gray-300' : 'text-slate-700'}`}>{localized.composition}</p>
                                                </div>
                                            )}
                                        </div>
                                    ) : (
                                        <div className="h-full flex flex-col">
                                            <h3 className={`font-black text-xl mb-6 ${dark ? 'text-white' : 'text-slate-950'}`}>{t.analysisStatus}</h3>
                                            <div className="space-y-6 flex-1">
                                                {[
                                                    { step: 1, label: t.stepUploaded, desc: t.stepUploadedDesc, active: analysisStatus !== 'idle' },
                                                    { step: 2, label: t.processing, desc: t.stepProcessingDesc, active: analysisStatus === 'processing', loading: analysisStatus === 'processing' },
                                                    { step: 3, label: t.completed, desc: t.stepDoneDesc, active: analysisStatus === 'completed', done: true }
                                                ].map((step, i) => (
                                                    <div key={i} className="flex items-center gap-5 relative">
                                                        {i < 2 && <div className={`absolute top-10 left-5 w-[2px] h-8 ${step.active ? 'bg-[#00d2ff]' : 'bg-white/10'}`} />}
                                                        <div className={`w-10 h-10 rounded-full flex items-center justify-center border-2 transition-all duration-500 z-10
                              ${step.active ? 'bg-[#00d2ff] border-[#00d2ff] text-white' : 'border-white/10 text-gray-500'}`}>
                                                            {step.done && analysisStatus === 'completed' ? <CheckCircle size={20} /> : step.loading ? <Loader2 size={20} className="animate-spin" /> : <span className="font-bold text-sm">{step.step}</span>}
                                                        </div>
                                                        <div>
                                                            <p className={`font-extrabold ${step.active && !dark ? 'text-blue-600' : step.active ? 'text-white' : 'text-gray-500'}`}>{step.label}</p>
                                                            <p className="text-sm text-gray-400 font-medium">{step.desc}</p>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* BLOCK: 12-dimension evidence sheet (compact cards, expand for full note) */}
                            {analysisStatus === 'completed' && evidenceByDimension.length > 0 && (
                                <div className={`p-6 lg:p-8 rounded-[28px] border backdrop-blur-md ${panelBlock} ${cardHover}`}>
                                    <p className={labelCls}>{t.evidenceSheet}</p>
                                    <p className="text-xs text-gray-400 mb-4 font-medium">{t.evidenceHelp}</p>
                                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 items-start">
                                        {evidenceByDimension.map(({ dimension, items }) => {
                                            const meta = DIMENSION_META[dimension];
                                            const title = meta ? (lang === 'vi' ? meta.vi : meta.en) : dimension;
                                            const isOpen = openDims[dimension] ?? false;
                                            return (
                                                <div
                                                    key={dimension}
                                                    className={`rounded-2xl border transition-colors ${dark ? 'bg-white/5 border-white/10' : 'bg-slate-50 border-slate-200'}`}
                                                >
                                                    <button
                                                        onClick={() => setOpenDims((p) => ({ ...p, [dimension]: !isOpen }))}
                                                        className="w-full flex items-center gap-2 text-left p-4"
                                                    >
                                                        <span className={`font-black text-sm uppercase tracking-wide ${dark ? 'text-white' : 'text-slate-950'}`}>{title}</span>
                                                        <ChevronDown size={15} className={`ml-auto flex-shrink-0 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                                                    </button>
                                                    {isOpen && (
                                                        <div className="space-y-2 px-4 pb-4">
                                                            {items.map((it, i) => (
                                                                <div key={i}>
                                                                    <p className={`text-sm font-bold ${dark ? 'text-[#00d2ff]' : 'text-blue-600'}`}>{it.feature || '—'}</p>
                                                                    {it.suggested_styles?.length > 0 && (
                                                                        <p className="text-[11px] font-medium text-[#9d50bb] mt-0.5">
                                                                            {t.suggestedStyles}: {it.suggested_styles.join(', ')}
                                                                        </p>
                                                                    )}
                                                                    {it.note && (
                                                                        <p className="text-xs text-gray-400 mt-0.5 leading-snug">{it.note}</p>
                                                                    )}
                                                                </div>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            )}

                            {/* BLOCK 2 + BLOCK 3 side by side */}
                            {analysisStatus === 'completed' && (perStyleData.length > 0 || radarData.length > 0) && (
                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                                    {/* BLOCK 2: Why each style */}
                                    {(perStyleData.length > 0 || localized?.keyEvidence?.length > 0) && (
                                        <div className={`p-6 lg:p-8 rounded-[28px] border backdrop-blur-md ${panelBlock} ${cardHover}`}>
                                            <p className={labelCls}>{perStyleData.length > 0 ? t.perStyleWhy : t.keyEvidence}</p>
                                            {perStyleData.length > 0 ? (
                                                <div className="space-y-3">
                                                    {perStyleData.map((ps) => {
                                                        const isOpen = openStyles[ps.style] ?? ps.isPrimary;
                                                        return (
                                                            <div key={ps.style} className={`rounded-2xl border overflow-hidden ${ps.isPrimary ? 'border-[#00d2ff]/40 bg-[#00d2ff]/5' : dark ? 'border-white/10 bg-white/5' : 'border-slate-200 bg-slate-50'}`}>
                                                                <button
                                                                    onClick={() => setOpenStyles((p) => ({ ...p, [ps.style]: !isOpen }))}
                                                                    className="w-full flex items-center gap-2 flex-wrap text-left p-4"
                                                                >
                                                                    <span
                                                                        role="button"
                                                                        tabIndex={0}
                                                                        onClick={(e) => { e.stopPropagation(); setCardStyle(ps.style); }}
                                                                        title={t.learnStyle}
                                                                        className={`group inline-flex items-center gap-1 font-black transition-colors ${dark ? 'text-white hover:text-[#00d2ff]' : 'text-slate-950 hover:text-blue-600'}`}
                                                                    >
                                                                        {ps.style}
                                                                        <BookOpen size={13} className="opacity-30 group-hover:opacity-100 transition-opacity" />
                                                                    </span>
                                                                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider border ${ps.isPrimary ? 'bg-[#00d2ff]/20 text-[#00d2ff] border-[#00d2ff]/30' : 'bg-[#9d50bb]/15 text-[#9d50bb] border-[#9d50bb]/30'}`}>
                                                                        {ps.isPrimary ? t.rolePrimary : t.roleSecondary}
                                                                    </span>
                                                                    <span className="ml-auto text-sm font-black text-[#00d2ff]">{ps.pct}%</span>
                                                                    <ChevronDown size={16} className={`flex-shrink-0 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                                                                </button>
                                                                {isOpen && (
                                                                    <ul className="space-y-1.5 px-4 pb-4">
                                                                        {ps.bullets.map((b, i) => (
                                                                            <li key={i} className={`flex items-start gap-2 text-sm font-medium ${dark ? 'text-gray-300' : 'text-slate-700'}`}>
                                                                                <span className="text-[#00d2ff] mt-0.5 flex-shrink-0">▸</span>
                                                                                <span>{b}</span>
                                                                            </li>
                                                                        ))}
                                                                    </ul>
                                                                )}
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            ) : (
                                                <ul className="space-y-2">
                                                    {localized.keyEvidence.map((ev, i) => (
                                                        <li key={i} className={`flex items-start gap-2 text-sm font-medium ${dark ? 'text-gray-300' : 'text-slate-700'}`}>
                                                            <span className="text-[#00d2ff] mt-0.5 flex-shrink-0">▸</span>
                                                            <span>{ev}</span>
                                                        </li>
                                                    ))}
                                                </ul>
                                            )}
                                        </div>
                                    )}

                                    {/* BLOCK 3: Distribution + panel */}
                                    {radarData.length > 0 && (
                                        <div className={`p-6 lg:p-8 rounded-[28px] border backdrop-blur-md ${panelBlock} ${cardHover}`}>
                                            <p className={labelCls}>{t.styleDistribution}</p>
                                            <ResponsiveContainer width="100%" height={280}>
                                                <RadarChart data={radarData}>
                                                    <PolarGrid stroke={dark ? 'rgba(255,255,255,0.12)' : '#e2e8f0'} />
                                                    <PolarAngleAxis dataKey="style" tick={{ fontSize: 11, fill: dark ? '#9ca3af' : '#64748b' }} />
                                                    <Radar dataKey="value" fill="#00d2ff" fillOpacity={0.35} stroke="#00d2ff" strokeWidth={2} />
                                                    <Tooltip formatter={(v) => `${v}%`} contentStyle={{ background: dark ? '#0b0e14' : '#fff', border: '1px solid rgba(0,210,255,0.3)', borderRadius: 8 }} />
                                                </RadarChart>
                                            </ResponsiveContainer>
                                            {/* Compact distribution bars */}
                                            <div className="mt-3 space-y-2">
                                                {radarData.slice(0, 6).map((d) => (
                                                    <div key={d.style} className="flex items-center gap-3">
                                                        <span className="text-xs font-bold w-32 truncate" title={d.style}>{d.style}</span>
                                                        <div className="flex-1 h-2 rounded-full bg-white/10 overflow-hidden">
                                                            <div className="h-full bg-gradient-to-r from-[#00d2ff] to-[#9d50bb]" style={{ width: `${d.value}%` }} />
                                                        </div>
                                                        <span className="text-xs font-black text-[#00d2ff] w-10 text-right">{d.value}%</span>
                                                    </div>
                                                ))}
                                            </div>
                                            {analysisResult?.panel_verdicts?.length > 0 && (
                                                <div className="mt-5">
                                                    <p className={labelCls}>{t.panelVerdicts}</p>
                                                    <div className="flex flex-wrap gap-2">
                                                        {analysisResult.panel_verdicts.map((v, i) => (
                                                            <span key={i} className={`px-3 py-1.5 rounded-full text-xs font-bold border ${v.failed ? 'bg-red-500/10 text-red-400 border-red-500/20' : dark ? 'bg-white/5 border-white/10' : 'bg-slate-50 border-slate-200'}`}>
                                                                {v.judge}{!v.failed && v.style_distribution?.primary ? ` · ${v.style_distribution.primary}` : ''}
                                                            </span>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* BLOCK: Grounded Q&A about this analysis */}
                            {analysisStatus === 'completed' && analysisResult?.image_id && (
                                <AnalysisChat imageId={analysisResult.image_id} theme={theme} lang={lang} />
                            )}
                        </div>
                    )}

                    {/* ── HISTORY ── */}
                    {activeSection === 'history' && (
                        <div className={`rounded-[28px] border backdrop-blur-md overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500
              ${panelBlock}`}>
                            <div className="p-6 border-b border-white/5 flex flex-col gap-4">
                                <h3 className={`text-xl font-black ${dark ? 'text-white' : 'text-slate-950'}`}>{t.recentHistory}</h3>
                                <div className="flex flex-col lg:flex-row lg:items-center gap-3 flex-wrap">
                                    {/* Style search */}
                                    <div className={`flex items-center gap-2 rounded-xl px-3 py-2 border ${dark ? 'bg-white/5 border-white/10' : 'bg-slate-100 border-slate-200'}`}>
                                        <Search size={16} className="text-gray-400" />
                                        <input type="text" value={styleQuery} onChange={(e) => setStyleQuery(e.target.value)} placeholder={t.searchStyle} className="bg-transparent border-none outline-none text-sm w-44 font-medium" />
                                    </div>
                                    {/* Confidence slider */}
                                    <div className={`flex items-center gap-3 rounded-xl px-3 py-2 border ${dark ? 'bg-white/5 border-white/10' : 'bg-slate-100 border-slate-200'}`}>
                                        <Sliders size={16} className="text-gray-400" />
                                        <span className="text-xs font-bold whitespace-nowrap">{t.minConfidence}: {Math.round(minConf * 100)}%</span>
                                        <input type="range" min="0" max="1" step="0.05" value={minConf} onChange={(e) => setMinConf(Number(e.target.value))} className="w-28 accent-[#00d2ff]" />
                                    </div>
                                    {/* Project filter */}
                                    <FancySelect
                                        theme={theme}
                                        value={filterProject}
                                        onChange={setFilterProject}
                                        widthClass="w-[160px]"
                                        options={[{ value: 'all', label: t.allProjects }, ...availableProjects.map((p) => ({ value: p, label: p }))]}
                                    />
                                    {/* Date filters */}
                                    <div className="flex items-center gap-2">
                                        <Calendar size={16} className="text-gray-400 flex-shrink-0" />
                                        <FancySelect
                                            theme={theme}
                                            value={filterYear}
                                            onChange={setFilterYear}
                                            icon={null}
                                            widthClass="w-[120px]"
                                            options={[{ value: 'all', label: t.allYears }, ...availableYears.map((y) => ({ value: y, label: String(y) }))]}
                                        />
                                        <FancySelect
                                            theme={theme}
                                            value={filterMonth}
                                            onChange={setFilterMonth}
                                            widthClass="w-[120px]"
                                            options={[{ value: 'all', label: t.allMonths }, ...Array.from({ length: 12 }, (_, i) => ({ value: i + 1, label: `${t.monthLabel} ${i + 1}` }))]}
                                        />
                                        <FancySelect
                                            theme={theme}
                                            value={filterDay}
                                            onChange={setFilterDay}
                                            widthClass="w-[110px]"
                                            options={[{ value: 'all', label: t.allDays }, ...Array.from({ length: 31 }, (_, i) => ({ value: i + 1, label: `${t.dayLabel} ${i + 1}` }))]}
                                        />
                                    </div>
                                </div>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-left">
                                    <thead className={dark ? 'bg-white/5' : 'bg-slate-50'}>
                                        <tr>
                                            <th className="px-6 py-4 text-xs font-black uppercase tracking-widest text-gray-400">{t.colImage}</th>
                                            <th className="px-6 py-4 text-xs font-black uppercase tracking-widest text-gray-400">{t.colStyle}</th>
                                            <th className="px-6 py-4 text-xs font-black uppercase tracking-widest text-gray-400">{t.colConfidence}</th>
                                            <th className="px-6 py-4 text-xs font-black uppercase tracking-widest text-gray-400">{t.colDate}</th>
                                            <th className="px-6 py-4 text-xs font-black uppercase tracking-widest text-gray-400 text-right">{t.colStatus}</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-white/5">
                                        {historyLoading ? (
                                            <tr>
                                                <td colSpan={5} className="px-6 py-12 text-center text-gray-400 font-medium">
                                                    <Loader2 className="animate-spin mx-auto mb-2 text-[#00d2ff]" size={28} />
                                                    {t.loadingHistory}
                                                </td>
                                            </tr>
                                        ) : historyItems.length === 0 ? (
                                            <tr>
                                                <td colSpan={5} className="px-6 py-12 text-center text-gray-400 font-medium">{t.noHistory}</td>
                                            </tr>
                                        ) : filteredHistory.length === 0 ? (
                                            <tr>
                                                <td colSpan={5} className="px-6 py-12 text-center text-gray-400 font-medium">{t.noMatch}</td>
                                            </tr>
                                        ) : filteredHistory.map((item) => {
                                            const isOpenable = item.analysis_status === 'completed';
                                            const isOpening = openingId === item.image_id;
                                            const thumb = thumbs[item.image_id];
                                            return (
                                                <tr
                                                    key={item.image_id}
                                                    onClick={() => isOpenable && openHistoryItem(item)}
                                                    title={isOpenable ? t.clickReopen : undefined}
                                                    className={`group transition-colors ${isOpenable ? 'cursor-pointer hover:bg-[#00d2ff]/[0.06]' : 'opacity-80'}`}
                                                >
                                                    <td className="px-6 py-3">
                                                        <div className={`w-16 h-12 rounded-lg flex items-center justify-center border overflow-hidden ${dark ? 'bg-white/5 border-white/10' : 'bg-slate-100 border-slate-200'}`}>
                                                            {isOpening ? <Loader2 size={18} className="animate-spin text-[#00d2ff]" />
                                                                : thumb ? <img src={thumb} alt="" className="w-full h-full object-cover" />
                                                                    : <ImageIcon size={20} className="text-gray-400" />}
                                                        </div>
                                                    </td>
                                                    <td className={`px-6 py-3 font-black ${dark ? 'text-gray-200' : 'text-slate-900'}`}>
                                                        {item.style ?? (item.analysis_status === 'pending' ? '…' : '—')}
                                                    </td>
                                                    <td className="px-6 py-3 text-sm font-bold text-[#00d2ff]">
                                                        {item.confidence != null ? `${(item.confidence * 100).toFixed(0)}%` : '—'}
                                                    </td>
                                                    <td className="px-6 py-3 text-gray-400 text-sm font-medium">
                                                        {item.uploaded_at ? new Date(item.uploaded_at).toLocaleString(lang === 'vi' ? 'vi-VN' : 'en-US') : '—'}
                                                    </td>
                                                    <td className="px-6 py-3 text-right">
                                                        <div className="flex items-center justify-end gap-3">
                                                            <span className={`inline-block px-3 py-1 rounded-full text-xs font-black uppercase tracking-wider border
                                                                ${item.analysis_status === 'completed' ? 'bg-green-500/15 text-green-400 border-green-500/30' :
                                                                    item.analysis_status === 'failed' ? 'bg-red-500/15 text-red-400 border-red-500/30' :
                                                                        'bg-yellow-500/15 text-yellow-400 border-yellow-500/30'}`}>
                                                                {item.analysis_status}
                                                            </span>
                                                            {isOpenable && <ExternalLink size={16} className="text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" />}
                                                        </div>
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {/* ── BILLING (Plans & Tokens) ── */}
                    {activeSection === 'billing' && (
                        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 space-y-8">
                            {/* Wallet summary */}
                            <div className={`p-6 rounded-[28px] border backdrop-blur-md flex flex-wrap items-center justify-between gap-6 ${panelBlock} ${cardHover}`}>
                                <div className="flex items-center gap-4">
                                    <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center shadow-lg">
                                        <Coins className="text-white" size={28} />
                                    </div>
                                    <div>
                                        <p className={labelCls}>{t.balanceLabel}</p>
                                        <p className={`text-3xl font-black ${dark ? 'text-white' : 'text-slate-950'}`}>
                                            {wallet ? wallet.token_balance : '—'} <span className="text-base font-bold opacity-60">{t.tokensWord}</span>
                                        </p>
                                    </div>
                                </div>
                                <div className="text-right">
                                    <p className={labelCls}>{t.currentPlan}</p>
                                    <p className={`text-lg font-bold capitalize ${dark ? 'text-white' : 'text-slate-950'}`}>
                                        {wallet?.current_plan_code || t.noPlan}
                                    </p>
                                    {typeof wallet?.cost_per_analysis === 'number' && (
                                        <p className="text-xs opacity-60 mt-1">
                                            {wallet.cost_per_analysis} {t.tokensWord} {t.perAnalysis}
                                        </p>
                                    )}
                                </div>
                            </div>

                            {error && /insufficient token/i.test(error) && (
                                <div className="p-4 rounded-xl border border-amber-500/30 bg-amber-500/10 text-amber-500 font-semibold flex items-center gap-2">
                                    <AlertTriangle size={18} /> {t.insufficientTokens}
                                </div>
                            )}

                            {/* Plans grid */}
                            {['token_pack', 'subscription'].map((kind) => {
                                const list = plans.filter((p) => p.plan_type === kind && p.price_amount > 0);
                                if (list.length === 0) return null;
                                return (
                                    <div key={kind}>
                                        <h3 className={`text-lg font-black mb-4 flex items-center gap-2 ${dark ? 'text-white' : 'text-slate-950'}`}>
                                            {kind === 'token_pack' ? <CreditCard size={20} /> : <Sparkles size={20} />}
                                            {kind === 'token_pack' ? t.tokenPacks : t.subscriptions}
                                        </h3>
                                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                                            {list.map((p) => (
                                                <div key={p.plan_id} className={`p-6 rounded-2xl border flex flex-col ${panelBlock} ${cardHover}`}>
                                                    <p className={`text-lg font-black ${dark ? 'text-white' : 'text-slate-950'}`}>{p.plan_name}</p>
                                                    <p className="text-2xl font-black my-2 text-[#00d2ff]">{formatVnd(p.price_amount)}</p>
                                                    <p className="text-sm opacity-70">+{p.token_amount} {t.tokensWord}</p>
                                                    {p.duration_days && (
                                                        <p className="text-xs opacity-60 mt-1">{p.duration_days} {t.daysWord}</p>
                                                    )}
                                                    {p.benefits?.cost_per_analysis != null && (
                                                        <p className="text-xs opacity-60 mt-1">{p.benefits.cost_per_analysis} {t.tokensWord} {t.perAnalysis}</p>
                                                    )}
                                                    <button
                                                        onClick={() => setConfirmPlan(p)}
                                                        disabled={buyingPlanId === p.plan_id}
                                                        className="mt-4 w-full rounded-xl bg-gradient-to-r from-[#00d2ff] to-[#9d50bb] text-white font-bold py-2.5 disabled:opacity-60 hover:opacity-90 transition">
                                                        {buyingPlanId === p.plan_id ? t.redirecting : t.buyNow}
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                );
                            })}

                            {/* Transaction history */}
                            <div className={`rounded-[28px] border backdrop-blur-md overflow-hidden ${panelBlock}`}>
                                <div className="p-5 border-b border-white/5">
                                    <h3 className={`font-black ${dark ? 'text-white' : 'text-slate-950'}`}>{t.billingHistory}</h3>
                                </div>
                                <div className="p-5 overflow-x-auto">
                                    {transactions.length === 0 ? (
                                        <p className="opacity-60 text-sm">{t.noTransactions}</p>
                                    ) : (
                                        <table className="w-full text-sm">
                                            <thead className="opacity-60 text-left">
                                                <tr>
                                                    <th className="py-2 pr-4">{t.colDate}</th>
                                                    <th className="py-2 pr-4">{t.colPlan}</th>
                                                    <th className="py-2 pr-4">{t.colAmount}</th>
                                                    <th className="py-2">{t.colStatus}</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {transactions.map((tx) => (
                                                    <tr key={tx.transaction_id} className="border-t border-white/5">
                                                        <td className="py-2 pr-4">{tx.created_at ? new Date(tx.created_at).toLocaleString() : '—'}</td>
                                                        <td className="py-2 pr-4">{tx.plan_code || '—'}</td>
                                                        <td className="py-2 pr-4">{formatVnd(tx.amount)}</td>
                                                        <td className="py-2 capitalize">{tx.status}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    )}
                                </div>
                            </div>

                            {/* Token activity (ledger) */}
                            <div className={`rounded-[28px] border backdrop-blur-md overflow-hidden ${panelBlock}`}>
                                <div className="p-5 border-b border-white/5">
                                    <h3 className={`font-black ${dark ? 'text-white' : 'text-slate-950'}`}>{t.tokenLedger}</h3>
                                </div>
                                <div className="p-5 overflow-x-auto">
                                    {ledger.length === 0 ? (
                                        <p className="opacity-60 text-sm">{t.noLedger}</p>
                                    ) : (
                                        <table className="w-full text-sm">
                                            <thead className="opacity-60 text-left">
                                                <tr>
                                                    <th className="py-2 pr-4">{t.colDate}</th>
                                                    <th className="py-2 pr-4">{t.tokensWord}</th>
                                                    <th className="py-2">{t.balanceLabel}</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {ledger.map((e, i) => (
                                                    <tr key={i} className="border-t border-white/5">
                                                        <td className="py-2 pr-4">{e.created_at ? new Date(e.created_at).toLocaleString() : '—'}</td>
                                                        <td className={`py-2 pr-4 font-bold ${e.delta >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                                                            {e.delta >= 0 ? '+' : ''}{e.delta} <span className="opacity-50 font-normal">({e.reason})</span>
                                                        </td>
                                                        <td className="py-2">{e.balance_after}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* ── PROFILE ── */}
                    {activeSection === 'profile' && (
                        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 grid grid-cols-1 lg:grid-cols-3 gap-8">
                            <div className={`p-8 rounded-[28px] border backdrop-blur-md text-center flex flex-col items-center ${panelBlock} ${cardHover}`}>
                                <div className="relative mb-6">
                                    <div className="w-32 h-32 rounded-full bg-gradient-to-br from-[#00d2ff] to-[#9d50bb] p-1 shadow-2xl">
                                        <div className="w-full h-full rounded-full bg-gray-900 flex items-center justify-center overflow-hidden text-white font-black text-5xl">
                                            {userView.picture
                                                ? <img src={userView.picture} referrerPolicy="no-referrer" className="w-full h-full object-cover" alt="Avatar" />
                                                : <span>{userView.name.charAt(0).toUpperCase()}</span>}
                                        </div>
                                    </div>
                                </div>
                                <h3 className={`text-2xl font-black mb-1 ${dark ? 'text-white' : 'text-slate-950'}`}>{userView.name}</h3>
                                <p className="text-[#00d2ff] font-bold italic text-sm mb-8 tracking-wide capitalize">{userView.role}</p>
                            </div>

                            <div className={`lg:col-span-2 p-8 rounded-[28px] border backdrop-blur-md ${panelBlock} ${cardHover}`}>
                                <h4 className={`text-xl font-black mb-8 ${dark ? 'text-white' : 'text-slate-950'}`}>{t.userInfo}</h4>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                                    {[
                                        { label: lang === 'vi' ? 'Họ tên' : 'Full Name', val: userView.name, icon: User },
                                        { label: "Email", val: userView.email },
                                        { label: t.role, val: userView.role }
                                    ].map((field, i) => (
                                        <div key={i} className="space-y-2">
                                            <label className="text-xs font-black text-slate-500 uppercase tracking-widest">{field.label}</label>
                                            <div className={`px-4 py-4 rounded-xl border flex items-center gap-3 font-semibold ${dark ? 'bg-white/5 border-white/10 text-white' : 'bg-slate-50 border-slate-200 text-slate-900'}`}>
                                                {field.icon && <field.icon size={18} className="text-[#00d2ff]" />}
                                                {field.val}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {/* ── DANGER ZONE ── */}
                            <div className={`lg:col-span-3 p-8 rounded-[28px] border ${dark ? 'bg-red-500/5 border-red-500/30' : 'bg-red-50 border-red-200'}`}>
                                <h4 className="text-xl font-black mb-2 flex items-center gap-2 text-red-500">
                                    <AlertTriangle size={20} /> {t.dangerZone}
                                </h4>
                                <p className={`text-sm mb-5 max-w-2xl leading-relaxed ${dark ? 'text-gray-400' : 'text-slate-600'}`}>
                                    {t.deleteAccountDesc}{' '}
                                    <Link to="/data-deletion" className="text-[#00d2ff] hover:underline font-semibold">{t.deleteLearnMore}</Link>
                                </p>
                                <button
                                    onClick={() => { setDeleteConfirmText(''); setDeleteError(null); setShowDeleteModal(true); }}
                                    className="px-5 py-3 rounded-xl font-bold text-white bg-red-600 hover:bg-red-700 transition-colors flex items-center gap-2">
                                    <Trash2 size={18} /> {t.deleteAccount}
                                </button>
                            </div>
                        </div>
                    )}
                </div>

                {/* FOOTER */}
                <footer className={`p-6 border-t flex flex-col md:flex-row justify-between items-center gap-4 text-xs font-bold uppercase tracking-widest ${dark ? 'border-white/5 text-gray-500' : 'border-slate-200 text-slate-500'}`}>
                    <p>{lang === 'vi' ? '© 2026 ArchiAI — Nhận dạng Kiến trúc Mở (Open-Vocabulary)' : '© 2026 ArchiAI — Open-Vocabulary Architecture Recognition'}</p>
                    <div className="flex items-center gap-6">
                        <Link to="/privacy" className="hover:text-[#00d2ff]">{lang === 'vi' ? 'Quyền riêng tư' : 'Privacy'}</Link>
                        <Link to="/terms" className="hover:text-[#00d2ff]">{lang === 'vi' ? 'Điều khoản' : 'Terms'}</Link>
                    </div>
                </footer>
            </main>

            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap" rel="stylesheet" />

            {/* Order review modal — last step before VNPay's hosted page */}
            {confirmPlan && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-in fade-in duration-200"
                     onClick={() => buyingPlanId ? null : setConfirmPlan(null)}>
                    <div onClick={(e) => e.stopPropagation()}
                         className={`max-w-md w-full p-7 rounded-3xl border ${dark ? 'bg-[#0f1218] border-white/10 text-white' : 'bg-white border-slate-200 text-slate-900 shadow-2xl'}`}>
                        <h3 className="text-2xl font-black mb-1">{t.confirmTitle}</h3>
                        <p className="text-lg font-bold text-[#00d2ff] mb-5">{confirmPlan.plan_name}</p>

                        <div className={`rounded-2xl border p-4 mb-5 ${dark ? 'bg-white/5 border-white/10' : 'bg-slate-50 border-slate-200'}`}>
                            <p className={labelCls}>{t.youGet}</p>
                            <ul className="space-y-2 text-sm">
                                {confirmPlan.token_amount > 0 && (
                                    <li className="flex items-center gap-2"><CheckCircle size={16} className="text-emerald-500" /> +{confirmPlan.token_amount} {t.featTokens}</li>
                                )}
                                {confirmPlan.plan_type === 'token_pack' && (
                                    <li className="flex items-center gap-2"><CheckCircle size={16} className="text-emerald-500" /> {t.featNeverExpire}</li>
                                )}
                                {confirmPlan.duration_days && (
                                    <li className="flex items-center gap-2"><CheckCircle size={16} className="text-emerald-500" /> {confirmPlan.duration_days} {t.featDuration}</li>
                                )}
                                {confirmPlan.benefits?.cost_per_analysis != null && (
                                    <li className="flex items-center gap-2"><CheckCircle size={16} className="text-emerald-500" /> {confirmPlan.benefits.cost_per_analysis} {t.tokensWord} {t.perAnalysis} ({t.featDiscount})</li>
                                )}
                            </ul>
                        </div>

                        <div className="flex items-center justify-between mb-5">
                            <span className="font-bold uppercase text-xs tracking-widest opacity-60">{t.total}</span>
                            <span className="text-2xl font-black">{formatVnd(confirmPlan.price_amount)}</span>
                        </div>

                        <p className="text-xs opacity-60 mb-5 leading-relaxed">{t.secureNote}</p>

                        <div className="flex gap-3">
                            <button onClick={() => setConfirmPlan(null)} disabled={!!buyingPlanId}
                                className={`flex-1 py-3 rounded-xl font-bold disabled:opacity-50 ${dark ? 'bg-white/5 hover:bg-white/10' : 'bg-slate-100 hover:bg-slate-200'}`}>
                                {t.cancel}
                            </button>
                            <button onClick={() => handleBuy(confirmPlan.plan_id)} disabled={!!buyingPlanId}
                                className="flex-1 py-3 rounded-xl bg-gradient-to-r from-[#00d2ff] to-[#9d50bb] text-white font-bold disabled:opacity-60 hover:opacity-90 flex items-center justify-center gap-2">
                                {buyingPlanId ? <><Loader2 size={16} className="animate-spin" /> {t.redirecting}</> : <><CreditCard size={16} /> {t.proceedPay}</>}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Account-deletion confirmation — requires typing the confirm word */}
            {showDeleteModal && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-in fade-in duration-200"
                     onClick={() => deletingAccount ? null : setShowDeleteModal(false)}>
                    <div onClick={(e) => e.stopPropagation()}
                         className={`max-w-md w-full p-7 rounded-3xl border ${dark ? 'bg-[#0f1218] border-red-500/30 text-white' : 'bg-white border-red-200 text-slate-900 shadow-2xl'}`}>
                        <h3 className="text-2xl font-black mb-3 flex items-center gap-2 text-red-500">
                            <AlertTriangle size={22} /> {t.deleteModalTitle}
                        </h3>
                        <p className={`text-sm mb-5 leading-relaxed ${dark ? 'text-gray-300' : 'text-slate-600'}`}>{t.deleteModalBody}</p>
                        <input
                            type="text"
                            value={deleteConfirmText}
                            onChange={(e) => setDeleteConfirmText(e.target.value)}
                            placeholder={t.deleteTypeToConfirm}
                            autoFocus
                            className={`w-full px-4 py-3 rounded-xl border mb-4 font-semibold outline-none focus:border-red-500 ${dark ? 'bg-white/5 border-white/10 text-white' : 'bg-slate-50 border-slate-200 text-slate-900'}`}
                        />
                        {deleteError && <p className="text-sm text-red-500 mb-4">{deleteError}</p>}
                        <div className="flex gap-3">
                            <button onClick={() => setShowDeleteModal(false)} disabled={deletingAccount}
                                className={`flex-1 py-3 rounded-xl font-bold disabled:opacity-50 ${dark ? 'bg-white/5 hover:bg-white/10' : 'bg-slate-100 hover:bg-slate-200'}`}>
                                {t.cancel}
                            </button>
                            <button onClick={handleDeleteAccount}
                                disabled={deletingAccount || deleteConfirmText.trim().toUpperCase() !== t.deleteConfirmWord.toUpperCase()}
                                className="flex-1 py-3 rounded-xl bg-red-600 text-white font-bold disabled:opacity-50 hover:bg-red-700 flex items-center justify-center gap-2">
                                {deletingAccount ? <><Loader2 size={16} className="animate-spin" /> {t.deleting}</> : <><Trash2 size={16} /> {t.deleteAccount}</>}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            <StyleKnowledgeCard styleName={cardStyle} theme={theme} lang={lang} onClose={() => setCardStyle(null)} />
        </div>
    );
};

export default App;
