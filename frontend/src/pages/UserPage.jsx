import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
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
    Plus,
    Clock,
    Menu,
    ShieldCheck,
    Box,
    Flame
} from 'lucide-react';
import {
    RadarChart,
    Radar,
    PolarGrid,
    PolarAngleAxis,
    ResponsiveContainer,
    Tooltip
} from 'recharts';
import { uploadImage, analyzeImage, getHistory, getMe } from '../utils/api';
import { useAuth } from '../context/AuthContext';

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
        logout: "Logout",
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
        joined: "Joined",
        theme: "Appearance",
        language: "Language",
        sourceImage: "Source Image",
        viewOriginal: "Original",
        viewBoxes: "Detections",
        viewHeatmap: "Heatmap",
        keyEvidence: "Key Evidence",
        styleDistribution: "Style Distribution",
        componentsDetected: "Components Detected",
        compositionExplanation: "Composition Explanation",
        aiVerified: "AI Verified",
        processingLabel: "Processing",
        stepUploaded: "Image Uploaded",
        stepUploadedDesc: "Successful pre-processing",
        stepProcessingDesc: "Extracting structural features",
        stepDoneDesc: "Ready to view findings",
        role: "Role",
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
        logout: "Đăng xuất",
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
        joined: "Ngày tham gia",
        theme: "Giao diện",
        language: "Ngôn ngữ",
        sourceImage: "Ảnh gốc",
        viewOriginal: "Ảnh gốc",
        viewBoxes: "Thành phần",
        viewHeatmap: "Heatmap",
        keyEvidence: "Bằng chứng chính",
        styleDistribution: "Phân bố phong cách",
        componentsDetected: "Thành phần phát hiện",
        compositionExplanation: "Giải thích tổ hợp",
        aiVerified: "AI Xác thực",
        processingLabel: "Xử lý",
        stepUploaded: "Đã tải ảnh lên",
        stepUploadedDesc: "Tiền xử lý thành công",
        stepProcessingDesc: "Đang trích xuất đặc trưng kết cấu",
        stepDoneDesc: "Sẵn sàng xem kết quả",
        role: "Vai trò",
        stats: {
            total: "Đã phân tích",
            bestConfidence: "Độ tin cậy cao nhất",
            accuracy: "Độ tin cậy TB"
        }
    }
};

const App = () => {
    const [theme, setTheme] = useState(localStorage.getItem('archi_theme') || 'dark');
    const [lang, setLang] = useState(localStorage.getItem('archi_lang') || 'en');
    const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(localStorage.getItem('archi_sidebar') === 'true');
    const [activeSection, setActiveSection] = useState('upload');
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

    const [uploadedFile, setUploadedFile] = useState(null);
    const [isUploading, setIsUploading] = useState(false);
    const [analysisStatus, setAnalysisStatus] = useState('idle');
    const [analysisResult, setAnalysisResult] = useState(null);
    const [fileId, setFileId] = useState(null);
    const [historyItems, setHistoryItems] = useState([]);
    const [historyLoading, setHistoryLoading] = useState(false);
    const [error, setError] = useState(null);
    const [viewMode, setViewMode] = useState('original');
    const [imgNatural, setImgNatural] = useState(null);
    const [profile, setProfile] = useState(null);

    const { logout } = useAuth();
    const navigate = useNavigate();

    const t = I18N[lang];
    // Architectural style names stay in English in both languages (proper nouns).
    const styleLabel = useCallback((style) => style, []);

    const handleLogout = () => {
        logout();
        navigate('/');
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

    // Radar uses Agent 7's final mixture when present; falls back to averaging
    // the per-component Agent 2 distributions for backward compatibility.
    const radarData = useMemo(() => {
        const finalDist = analysisResult?.style_distribution?.distribution;
        if (finalDist && Object.keys(finalDist).length) {
            return Object.entries(finalDist)
                .map(([style, prob]) => ({ style: styleLabel(style), value: Math.round(prob * 100) }))
                .filter((d) => d.value > 0)
                .sort((a, b) => b.value - a.value);
        }
        if (!analysisResult?.components?.length) return [];
        const totals = {};
        const count = analysisResult.components.length;
        for (const comp of analysisResult.components) {
            const dist = comp.agent2?.style_distribution ?? {};
            for (const [style, prob] of Object.entries(dist)) {
                totals[style] = (totals[style] || 0) + prob;
            }
        }
        return Object.entries(totals)
            .map(([style, sum]) => ({ style: styleLabel(style), value: Math.round((sum / count) * 100) }))
            .sort((a, b) => b.value - a.value);
    }, [analysisResult, styleLabel]);

    // User profile for header + profile section: DB (/auth/me) first, JWT fallback.
    const userView = useMemo(() => {
        const claims = jwtClaims();
        // Name comes from the JWT first: it is fresh from Google and encoded
        // correctly, whereas the DB round-trip can corrupt diacritics. Email /
        // picture / role are ASCII-safe so the DB (/auth/me) is preferred.
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

    useEffect(() => {
        localStorage.setItem('archi_theme', theme);
        document.documentElement.classList.toggle('dark', theme === 'dark');
    }, [theme]);

    useEffect(() => {
        localStorage.setItem('archi_lang', lang);
    }, [lang]);

    useEffect(() => {
        localStorage.setItem('archi_sidebar', isSidebarCollapsed);
    }, [isSidebarCollapsed]);

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

    const toggleTheme = () => setTheme(prev => prev === 'dark' ? 'light' : 'dark');
    const toggleLang = () => setLang(prev => prev === 'en' ? 'vi' : 'en');

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
        } catch (err) {
            setAnalysisStatus('pending');
            setError(err.message);
        }
    };

    const NavItem = ({ id, icon: Icon, label }) => {
        const isActive = activeSection === id;
        const activeStyles = theme === 'dark'
            ? 'bg-white/10 text-white border-r-4 border-[#00d2ff]'
            : 'bg-blue-50 text-blue-600 border-r-4 border-blue-600';

        const inactiveStyles = theme === 'dark'
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

    return (
        <div className={`min-h-screen font-inter transition-colors duration-500 ${theme === 'dark' ? 'bg-[#0b0e14] text-gray-100' : 'bg-white text-slate-950'}`}>

            {/* Mesh Gradients Background */}
            <div className="fixed inset-0 overflow-hidden pointer-events-none">
                <div className={`absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full opacity-20 blur-[120px] transition-colors duration-500 ${theme === 'dark' ? 'bg-[#00d2ff]' : 'bg-blue-300'}`} />
                <div className={`absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full opacity-20 blur-[120px] transition-colors duration-500 ${theme === 'dark' ? 'bg-[#9d50bb]' : 'bg-purple-300'}`} />
            </div>

            {isMobileMenuOpen && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 lg:hidden" onClick={() => setIsMobileMenuOpen(false)} />
            )}

            {/* SIDEBAR */}
            <aside className={`fixed left-0 top-0 h-screen z-50 border-r transition-all duration-300 ease-in-out backdrop-blur-xl
          ${theme === 'dark' ? 'border-white/5 bg-black/10' : 'border-slate-200 bg-white/95'}
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
                        <NavItem id="profile" icon={User} label={t.profile} />
                    </nav>

                    <div className="mt-auto pt-6 border-t border-white/10">
                        <button
                            onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
                            className={`hidden lg:flex w-full items-center gap-4 px-4 py-3 rounded-xl transition-all group ${theme === 'dark' ? 'text-gray-400 hover:text-white' : 'text-slate-600 hover:text-slate-950'}`}
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
          ${theme === 'dark' ? 'border-white/5 bg-transparent' : 'border-slate-300 bg-white/60'}`}>
                    <div className="flex items-center gap-4">
                        <button onClick={() => setIsMobileMenuOpen(true)} className={`p-2 rounded-lg lg:hidden ${theme === 'dark' ? 'hover:bg-white/10' : 'hover:bg-slate-200'}`}>
                            <Menu size={24} />
                        </button>
                        <h2 className={`text-lg font-bold tracking-tight capitalize ${theme === 'dark' ? 'text-white' : 'text-slate-950'}`}>
                            {t[activeSection]}
                        </h2>
                    </div>

                    <div className="flex items-center gap-2 lg:gap-4">
                        <button onClick={toggleLang} className={`flex items-center gap-2 px-3 py-1.5 rounded-full border transition-all text-sm font-bold
                ${theme === 'dark' ? 'border-white/10 bg-white/5 hover:bg-white/10' : 'border-slate-300 bg-slate-100 hover:bg-slate-200 text-slate-800'}`}>
                            <Globe size={16} />
                            <span className="hidden sm:inline">{lang === 'en' ? 'EN' : 'VI'}</span>
                        </button>

                        <button onClick={toggleTheme} className={`p-2 rounded-full border transition-all
                ${theme === 'dark' ? 'border-white/10 bg-white/5 hover:bg-white/10' : 'border-slate-300 bg-slate-100 hover:bg-slate-200'}`}>
                            {theme === 'dark' ? <Sun size={18} className="text-yellow-400" /> : <Moon size={18} className="text-blue-600" />}
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
                <div className="flex-1 p-4 lg:p-8 max-w-7xl mx-auto w-full">

                    { }
                    {activeSection === 'upload' && (
                        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                                {/* Stats Summary Cards with Enhanced Hover Effects */}
                                {[
                                    { label: t.stats.total, val: String(stats.total), color: "from-[#00d2ff]/20 to-[#00d2ff]/5", text: "text-[#00d2ff]", border: "hover:border-[#00d2ff]/50" },
                                    { label: t.stats.bestConfidence, val: stats.best, color: "from-[#9d50bb]/20 to-[#9d50bb]/5", text: "text-[#9d50bb]", border: "hover:border-[#9d50bb]/50" },
                                    { label: t.stats.accuracy, val: stats.avg, color: "from-[#00d2ff]/20 to-[#00d2ff]/5", text: "text-[#00d2ff]", border: "hover:border-[#00d2ff]/50" }
                                ].map((stat, idx) => (
                                    <div key={idx} className={`group p-6 rounded-3xl border backdrop-blur-md transition-all duration-500 cursor-pointer
                    ${theme === 'dark'
                                            ? `bg-white/5 border-white/10 ${stat.border} hover:shadow-[0_0_30px_rgba(0,210,255,0.1)]`
                                            : `bg-white border-slate-200 shadow-sm hover:shadow-2xl hover:border-slate-300`
                                        } hover:-translate-y-2`}>
                                        <p className={`text-sm mb-2 transition-colors font-bold uppercase tracking-widest ${theme === 'dark' ? 'text-gray-400' : 'text-slate-500'} group-hover:${stat.text}`}>{stat.label}</p>
                                        <p className={`text-4xl font-black ${stat.text} group-hover:scale-110 transition-transform origin-left duration-300`}>{stat.val}</p>
                                    </div>
                                ))}
                            </div>

                            {/* Main Upload Box */}
                            <div className={`relative group p-1 rounded-[40px] bg-gradient-to-r from-[#00d2ff]/30 to-[#9d50bb]/30 overflow-hidden`}>
                                <div className={`relative rounded-[36px] border-2 border-dashed p-12 lg:p-20 flex flex-col items-center justify-center transition-all duration-500 
                  ${theme === 'dark' ? 'bg-[#0b0e14]/90 border-white/10 hover:border-[#00d2ff]/40' : 'bg-white border-slate-300 hover:border-blue-400'}`}>

                                    {isUploading ? (
                                        <div className="flex flex-col items-center animate-pulse">
                                            <div className="w-20 h-20 rounded-full border-4 border-[#00d2ff] border-t-transparent animate-spin mb-6" />
                                            <p className="text-xl font-bold">{t.uploading}</p>
                                        </div>
                                    ) : (
                                        <>
                                            <div className={`w-24 h-24 mb-8 rounded-3xl flex items-center justify-center border transition-all duration-500 group-hover:rotate-6
                        ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-blue-50 border-blue-100'}`}>
                                                <Upload className="text-[#00d2ff]" size={48} />
                                            </div>
                                            <h3 className={`text-2xl lg:text-3xl font-black mb-4 text-center ${theme === 'dark' ? 'text-white' : 'text-slate-950'}`}>{t.dragDrop}</h3>
                                            <p className={`mb-10 text-center max-w-md font-medium ${theme === 'dark' ? 'text-gray-400' : 'text-slate-600'}`}>{t.maxSize}</p>

                                            <label className="cursor-pointer px-10 py-5 rounded-2xl bg-gradient-to-r from-[#00d2ff] to-[#9d50bb] text-white font-extrabold text-lg shadow-xl hover:scale-105 active:scale-95 transition-all">
                                                {t.orBrowse}
                                                <input type="file" className="hidden" accept="image/*" onChange={handleFileUpload} />
                                            </label>
                                        </>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}

                    { }
                    {activeSection === 'analyze' && (
                        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 grid grid-cols-1 lg:grid-cols-2 gap-8">
                            <div className="space-y-6">
                                <div className={`p-6 rounded-[32px] border backdrop-blur-md overflow-hidden relative ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-white border-slate-300 shadow-xl'}`}>
                                    <div className="flex items-center justify-between mb-4">
                                        <h3 className={`font-bold text-lg flex items-center gap-2 ${theme === 'dark' ? 'text-white' : 'text-slate-950'}`}>
                                            <ImageIcon size={20} className="text-[#00d2ff]" />
                                            {t.sourceImage}
                                        </h3>
                                        {uploadedFile && (
                                            <button onClick={() => { setUploadedFile(null); setFileId(null); setAnalysisStatus('idle'); setAnalysisResult(null); setViewMode('original'); }} className="text-red-500 hover:text-red-400 p-2 rounded-lg hover:bg-red-500/10 transition-colors">
                                                <Trash2 size={18} />
                                            </button>
                                        )}
                                    </div>

                                    {/* View toggle: original / YOLO detection boxes / Grad-CAM heatmap */}
                                    {analysisStatus === 'completed' && analysisResult && (
                                        <div className={`flex gap-1 p-1 mb-4 rounded-xl border w-fit ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-slate-100 border-slate-200'}`}>
                                            {[
                                                { id: 'original', icon: ImageIcon, label: t.viewOriginal, enabled: true },
                                                { id: 'boxes', icon: Box, label: t.viewBoxes, enabled: (analysisResult.components || []).some(c => c.bounding_box) },
                                                { id: 'gradcam', icon: Flame, label: t.viewHeatmap, enabled: !!analysisResult.gradcam_b64 }
                                            ].map(({ id, icon: Icon, label, enabled }) => (
                                                <button
                                                    key={id}
                                                    disabled={!enabled}
                                                    onClick={() => setViewMode(id)}
                                                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all
                                                        ${!enabled ? 'opacity-30 cursor-not-allowed'
                                                            : viewMode === id ? 'bg-gradient-to-r from-[#00d2ff] to-[#9d50bb] text-white shadow'
                                                                : theme === 'dark' ? 'text-gray-300 hover:bg-white/10' : 'text-slate-600 hover:bg-white'}`}
                                                >
                                                    <Icon size={14} />
                                                    {label}
                                                </button>
                                            ))}
                                        </div>
                                    )}

                                    {/* Whole image fits in one view: scaled down to fit the box
                                        (aspect preserved), never cropped. The SVG overlay covers the
                                        displayed image exactly and maps box coords via viewBox. */}
                                    <div className="rounded-2xl bg-black/20 overflow-hidden relative border border-white/5 flex items-center justify-center max-h-[65vh]">
                                        {uploadedFile ? (
                                            <>
                                                {viewMode === 'gradcam' && analysisResult?.gradcam_b64 ? (
                                                    <img src={`data:image/png;base64,${analysisResult.gradcam_b64}`} className="block max-w-full max-h-[65vh] w-auto h-auto object-contain" alt="Grad-CAM heatmap" />
                                                ) : (
                                                    <div className="relative inline-block leading-none">
                                                        <img
                                                            src={uploadedFile.preview}
                                                            className="block max-w-full max-h-[65vh] w-auto h-auto object-contain"
                                                            alt="Preview"
                                                            onLoad={(e) => setImgNatural({ w: e.target.naturalWidth, h: e.target.naturalHeight })}
                                                        />
                                                        {viewMode === 'boxes' && imgNatural && analysisResult?.components?.length > 0 && (
                                                            <svg
                                                                className="absolute inset-0 w-full h-full pointer-events-none"
                                                                viewBox={`0 0 ${imgNatural.w} ${imgNatural.h}`}
                                                                preserveAspectRatio="none"
                                                            >
                                                                {analysisResult.components.filter(c => c.bounding_box).map((c) => {
                                                                    const b = c.bounding_box;
                                                                    return (
                                                                        <g key={c.component_id}>
                                                                            <rect
                                                                                x={b.x_min} y={b.y_min}
                                                                                width={b.x_max - b.x_min} height={b.y_max - b.y_min}
                                                                                fill="rgba(0,210,255,0.12)" stroke="#00d2ff"
                                                                                strokeWidth={Math.max(2, imgNatural.w / 300)}
                                                                            />
                                                                            <text
                                                                                x={b.x_min + 4} y={b.y_min + Math.max(16, imgNatural.h / 40)}
                                                                                fill="#00d2ff" fontWeight="bold"
                                                                                fontSize={Math.max(12, imgNatural.w / 45)}
                                                                            >
                                                                                {c.component_type} {(c.detection_confidence * 100).toFixed(0)}%
                                                                            </text>
                                                                        </g>
                                                                    );
                                                                })}
                                                            </svg>
                                                        )}
                                                    </div>
                                                )}
                                                {analysisStatus === 'processing' && (
                                                    <div className="absolute inset-0 bg-gradient-to-b from-transparent via-[#00d2ff]/40 to-transparent animate-[scan_2s_ease-in-out_infinite]" />
                                                )}
                                                <style>{`
                          @keyframes scan {
                            0% { transform: translateY(-100%); }
                            100% { transform: translateY(100%); }
                          }
                        `}</style>
                                            </>
                                        ) : (
                                            <div className="aspect-[4/3] w-full flex flex-col items-center justify-center gap-4 text-gray-500">
                                                <ImageIcon size={48} className="opacity-20" />
                                                <p className="font-semibold">{t.noFile}</p>
                                            </div>
                                        )}
                                    </div>
                                </div>

                                <button
                                    disabled={!uploadedFile || analysisStatus === 'processing'}
                                    onClick={startAnalysis}
                                    className={`w-full py-5 rounded-2xl flex items-center justify-center gap-3 font-black text-lg transition-all
                    ${!uploadedFile || analysisStatus === 'processing'
                                            ? 'bg-gray-800 text-gray-500 cursor-not-allowed opacity-50'
                                            : 'bg-gradient-to-r from-[#00d2ff] to-[#9d50bb] text-white shadow-2xl hover:scale-[1.02] active:scale-95'
                                        }`}
                                >
                                    {analysisStatus === 'processing' ? <Loader2 size={24} className="animate-spin" /> : <Cpu size={24} />}
                                    {t.startAnalyze}
                                </button>
                            </div>

                            {/* Status and Results */}
                            <div className="space-y-6">
                                <div className={`p-8 rounded-[32px] border backdrop-blur-md ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-white border-slate-300 shadow-xl'}`}>
                                    <h3 className={`font-black text-xl mb-8 ${theme === 'dark' ? 'text-white' : 'text-slate-950'}`}>{t.analysisStatus}</h3>
                                    <div className="space-y-8">
                                        {[
                                            { step: 1, label: t.stepUploaded, desc: t.stepUploadedDesc, active: analysisStatus !== 'idle' },
                                            { step: 2, label: t.processing, desc: t.stepProcessingDesc, active: analysisStatus === 'processing' || analysisStatus === 'completed', loading: analysisStatus === 'processing' },
                                            { step: 3, label: t.completed, desc: t.stepDoneDesc, active: analysisStatus === 'completed', done: true }
                                        ].map((step, i) => (
                                            <div key={i} className="flex items-center gap-5 relative">
                                                {i < 2 && <div className={`absolute top-10 left-5 w-[2px] h-10 ${step.active ? 'bg-[#00d2ff]' : 'bg-white/10'}`} />}
                                                <div className={`w-10 h-10 rounded-full flex items-center justify-center border-2 transition-all duration-500 z-10
                          ${step.active ? 'bg-[#00d2ff] border-[#00d2ff] text-white' : 'border-white/10 text-gray-500'}`}>
                                                    {step.done && analysisStatus === 'completed' ? <CheckCircle size={20} /> : step.loading ? <Loader2 size={20} className="animate-spin" /> : <span className="font-bold text-sm">{step.step}</span>}
                                                </div>
                                                <div>
                                                    <p className={`font-extrabold ${step.active && theme === 'light' ? 'text-blue-600' : step.active ? 'text-white' : 'text-gray-500'}`}>{step.label}</p>
                                                    <p className="text-sm text-gray-400 font-medium">{step.desc}</p>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                {analysisStatus === 'completed' && analysisResult && (
                                    <div className={`p-8 rounded-[32px] border bg-gradient-to-br from-white/5 to-[#00d2ff]/5 backdrop-blur-xl animate-in zoom-in-95 duration-500 ${theme === 'dark' ? 'border-white/10' : 'border-slate-300'}`}>
                                        <div className="flex items-center justify-between mb-8">
                                            <h3 className={`text-xl font-black bg-clip-text text-transparent bg-gradient-to-r from-[#00d2ff] to-[#9d50bb]`}>{t.result}</h3>
                                            <span className="px-4 py-1.5 rounded-full bg-green-500/20 text-green-500 text-xs font-black border border-green-500/20 tracking-wider uppercase">{t.aiVerified}</span>
                                        </div>
                                        <div className="space-y-6">
                                            <div>
                                                <p className={`text-xs font-black uppercase tracking-widest mb-2 ${theme === 'dark' ? 'text-gray-400' : 'text-slate-500'}`}>{t.style}</p>
                                                <p className={`text-3xl font-black ${theme === 'dark' ? 'text-white' : 'text-slate-950'}`}>{styleLabel(analysisResult.style)}</p>
                                            </div>
                                            <div className="grid grid-cols-2 gap-4">
                                                <div className={`p-4 rounded-2xl border ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-blue-50 border-blue-100'}`}>
                                                    <p className="text-xs text-slate-500 font-bold uppercase tracking-widest mb-1">{t.confidence}</p>
                                                    <p className="text-2xl font-black text-[#00d2ff]">{(analysisResult.confidence * 100).toFixed(0)}%</p>
                                                </div>
                                                <div className={`p-4 rounded-2xl border ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-purple-50 border-purple-100'}`}>
                                                    <p className="text-xs text-slate-500 font-bold uppercase tracking-widest mb-1">{t.processingLabel}</p>
                                                    <p className={`text-lg font-black ${theme === 'dark' ? 'text-white' : 'text-purple-700'}`}>{(analysisResult.processing_time_ms / 1000).toFixed(1)}s</p>
                                                </div>
                                            </div>
                                            <div>
                                                <p className={`text-xs font-black uppercase tracking-widest mb-3 ${theme === 'dark' ? 'text-gray-400' : 'text-slate-500'}`}>{t.description}</p>
                                                <p className={`leading-relaxed italic border-l-4 border-[#9d50bb] pl-4 font-medium ${theme === 'dark' ? 'text-gray-300' : 'text-slate-700'}`}>
                                                    "{localized?.explanation}"
                                                </p>
                                            </div>
                                            {localized?.composition && localized.composition !== localized.explanation && (
                                                <div>
                                                    <p className={`text-xs font-black uppercase tracking-widest mb-3 ${theme === 'dark' ? 'text-gray-400' : 'text-slate-500'}`}>{t.compositionExplanation}</p>
                                                    <p className={`leading-relaxed font-medium ${theme === 'dark' ? 'text-gray-300' : 'text-slate-700'}`}>{localized.composition}</p>
                                                </div>
                                            )}
                                            {localized?.keyEvidence?.length > 0 && (
                                                <div>
                                                    <p className={`text-xs font-black uppercase tracking-widest mb-3 ${theme === 'dark' ? 'text-gray-400' : 'text-slate-500'}`}>{t.keyEvidence}</p>
                                                    <ul className="space-y-2">
                                                        {localized.keyEvidence.map((ev, i) => (
                                                            <li key={i} className={`flex items-start gap-2 text-sm font-medium ${theme === 'dark' ? 'text-gray-300' : 'text-slate-700'}`}>
                                                                <span className="text-[#00d2ff] mt-0.5 flex-shrink-0">▸</span>
                                                                <span>{ev}</span>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                </div>
                                            )}
                                            {radarData.length > 0 && (
                                                <div>
                                                    <p className={`text-xs font-black uppercase tracking-widest mb-3 ${theme === 'dark' ? 'text-gray-400' : 'text-slate-500'}`}>{t.styleDistribution}</p>
                                                    <ResponsiveContainer width="100%" height={260}>
                                                        <RadarChart data={radarData}>
                                                            <PolarGrid stroke={theme === 'dark' ? 'rgba(255,255,255,0.12)' : '#e2e8f0'} />
                                                            <PolarAngleAxis dataKey="style" tick={{ fontSize: 10, fill: theme === 'dark' ? '#9ca3af' : '#64748b' }} />
                                                            <Radar dataKey="value" fill="#00d2ff" fillOpacity={0.35} stroke="#00d2ff" strokeWidth={2} />
                                                            <Tooltip formatter={(v) => `${v}%`} contentStyle={{ background: theme === 'dark' ? '#0b0e14' : '#fff', border: '1px solid rgba(0,210,255,0.3)', borderRadius: 8 }} />
                                                        </RadarChart>
                                                    </ResponsiveContainer>
                                                </div>
                                            )}
                                            {analysisResult.components?.length > 0 && (
                                                <div>
                                                    <p className={`text-xs font-black uppercase tracking-widest mb-3 ${theme === 'dark' ? 'text-gray-400' : 'text-slate-500'}`}>{t.componentsDetected} ({analysisResult.components.length})</p>
                                                    <div className="flex flex-wrap gap-2">
                                                        {analysisResult.components.map((c) => (
                                                            <span key={c.component_id} className={`px-3 py-1.5 rounded-full text-xs font-bold border ${theme === 'dark' ? 'bg-white/5 border-white/10 text-gray-300' : 'bg-slate-50 border-slate-200 text-slate-700'}`}>
                                                                {c.component_type} · {(c.detection_confidence * 100).toFixed(0)}%
                                                            </span>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    { }
                    {activeSection === 'history' && (
                        <div className={`rounded-[32px] border backdrop-blur-md overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500
              ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-white border-slate-300 shadow-xl'}`}>
                            <div className="p-8 border-b border-white/5 flex flex-col md:flex-row md:items-center justify-between gap-4">
                                <h3 className={`text-xl font-black ${theme === 'dark' ? 'text-white' : 'text-slate-950'}`}>{t.recentHistory}</h3>
                                <div className={`flex items-center gap-3 rounded-xl px-4 py-2 border ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-slate-100 border-slate-200'}`}>
                                    <Search size={18} className="text-gray-400" />
                                    <input type="text" placeholder="Filter..." className="bg-transparent border-none outline-none text-sm w-full md:w-64 font-medium" />
                                </div>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-left">
                                    <thead className={theme === 'dark' ? 'bg-white/5' : 'bg-slate-50'}>
                                        <tr>
                                            <th className="px-8 py-4 text-xs font-black uppercase tracking-widest text-gray-400">Image</th>
                                            <th className="px-8 py-4 text-xs font-black uppercase tracking-widest text-gray-400">Style</th>
                                            <th className="px-8 py-4 text-xs font-black uppercase tracking-widest text-gray-400">Confidence</th>
                                            <th className="px-8 py-4 text-xs font-black uppercase tracking-widest text-gray-400">Date</th>
                                            <th className="px-8 py-4 text-xs font-black uppercase tracking-widest text-gray-400 text-right">Status</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-white/5">
                                        {historyLoading ? (
                                            <tr>
                                                <td colSpan={5} className="px-8 py-12 text-center text-gray-400 font-medium">
                                                    <Loader2 className="animate-spin mx-auto mb-2 text-[#00d2ff]" size={28} />
                                                    Loading history...
                                                </td>
                                            </tr>
                                        ) : historyItems.length === 0 ? (
                                            <tr>
                                                <td colSpan={5} className="px-8 py-12 text-center text-gray-400 font-medium">
                                                    No analysis history yet. Upload an image to get started.
                                                </td>
                                            </tr>
                                        ) : historyItems.map((item) => (
                                            <tr key={item.image_id} className="group hover:bg-white/[0.02] transition-colors">
                                                <td className="px-8 py-4">
                                                    <div className={`w-16 h-10 rounded-lg flex items-center justify-center border ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-slate-100 border-slate-200'}`}>
                                                        <ImageIcon size={20} className="text-gray-400" />
                                                    </div>
                                                </td>
                                                <td className={`px-8 py-4 font-black ${theme === 'dark' ? 'text-gray-200' : 'text-slate-900'}`}>
                                                    {item.style ?? (item.analysis_status === 'pending' ? 'Processing...' : '—')}
                                                </td>
                                                <td className="px-8 py-4 text-sm font-bold text-[#00d2ff]">
                                                    {item.confidence != null ? `${(item.confidence * 100).toFixed(0)}%` : '—'}
                                                </td>
                                                <td className="px-8 py-4 text-gray-400 text-sm font-medium">
                                                    {item.uploaded_at ? new Date(item.uploaded_at).toLocaleString() : '—'}
                                                </td>
                                                <td className="px-8 py-4 text-right">
                                                    <span className={`inline-block px-3 py-1 rounded-full text-xs font-black uppercase tracking-wider border
                                                        ${item.analysis_status === 'completed' ? 'bg-green-500/15 text-green-400 border-green-500/30' :
                                                            item.analysis_status === 'failed' ? 'bg-red-500/15 text-red-400 border-red-500/30' :
                                                                'bg-yellow-500/15 text-yellow-400 border-yellow-500/30'}`}>
                                                        {item.analysis_status}
                                                    </span>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    { }
                    {activeSection === 'profile' && (
                        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 grid grid-cols-1 lg:grid-cols-3 gap-8">
                            <div className={`p-8 rounded-[32px] border backdrop-blur-md text-center flex flex-col items-center ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-white border-slate-300 shadow-xl'}`}>
                                <div className="relative mb-6">
                                    <div className="w-32 h-32 rounded-full bg-gradient-to-br from-[#00d2ff] to-[#9d50bb] p-1 shadow-2xl">
                                        <div className="w-full h-full rounded-full bg-gray-900 flex items-center justify-center overflow-hidden text-white font-black text-5xl">
                                            {userView.picture
                                                ? <img src={userView.picture} referrerPolicy="no-referrer" className="w-full h-full object-cover" alt="Avatar" />
                                                : <span>{userView.name.charAt(0).toUpperCase()}</span>}
                                        </div>
                                    </div>
                                </div>
                                <h3 className={`text-2xl font-black mb-1 ${theme === 'dark' ? 'text-white' : 'text-slate-950'}`}>{userView.name}</h3>
                                <p className="text-[#00d2ff] font-bold italic text-sm mb-8 tracking-wide capitalize">{userView.role}</p>
                            </div>

                            <div className={`lg:col-span-2 p-8 rounded-[32px] border backdrop-blur-md ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-white border-slate-300 shadow-xl'}`}>
                                <h4 className={`text-xl font-black mb-8 ${theme === 'dark' ? 'text-white' : 'text-slate-950'}`}>{t.userInfo}</h4>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                                    {[
                                        { label: lang === 'vi' ? 'Họ tên' : 'Full Name', val: userView.name, icon: User },
                                        { label: "Email", val: userView.email },
                                        { label: t.role, val: userView.role }
                                    ].map((field, i) => (
                                        <div key={i} className="space-y-2">
                                            <label className="text-xs font-black text-slate-500 uppercase tracking-widest">{field.label}</label>
                                            <div className={`px-4 py-4 rounded-xl border flex items-center gap-3 font-semibold ${theme === 'dark' ? 'bg-white/5 border-white/10 text-white' : 'bg-slate-50 border-slate-200 text-slate-900'}`}>
                                                {field.icon && <field.icon size={18} className="text-[#00d2ff]" />}
                                                {field.val}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* FOOTER */}
                <footer className={`p-8 border-t flex flex-col md:flex-row justify-between items-center gap-4 text-xs font-bold uppercase tracking-widest ${theme === 'dark' ? 'border-white/5 text-gray-500' : 'border-slate-200 text-slate-500'}`}>
                    <p>© 2026 ArchiAI — Design for the Future</p>
                    <div className="flex items-center gap-6">
                        <a href="#" className="hover:text-[#00d2ff]">Privacy</a>
                        <a href="#" className="hover:text-[#00d2ff]">Terms</a>
                        <a href="#" className="hover:text-[#00d2ff]">API Docs</a>
                    </div>
                </footer>
            </main>

            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap" rel="stylesheet" />
            <script src="https://cdn.tailwindcss.com"></script>
        </div>
    );
};

export default App;