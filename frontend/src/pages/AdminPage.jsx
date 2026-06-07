import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
    LayoutDashboard, Users, FolderOpen, Image as ImageIcon,
    Cpu, FileText, FolderTree, Sun, Moon, Languages,
    Search, Bell, LogOut, Trash2, CheckCircle2, XCircle,
    MoreVertical, Filter, Activity, Database, ShieldCheck,
    ChevronDown, Loader2, RefreshCw, HardDrive
} from 'lucide-react';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
    ResponsiveContainer, PieChart, Pie, Cell, AreaChart, Area
} from 'recharts';
import {
    adminGetStats, adminGetUsers, adminGetProjects, adminGetImages,
    adminGetAgents, adminGetLogs, adminGetFiles,
    adminUpdateUserStatus, adminDeleteProject, adminDeleteImage, getMe
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
        images: "Images",
        agents: "Agents",
        logs: "System Logs",
        files: "File Browser",
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
        performanceDesc: "Number of images uploaded per month (from the database).",
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
        deleteConfirmDesc: "This action cannot be undone. All related records will be permanently removed.",
        cancel: "Cancel",
        delete: "Delete",
        deleting: "Deleting..."
    },
    vi: {
        // nav + chrome
        dashboard: "Bảng điều khiển",
        users: "Người dùng",
        projects: "Dự án",
        images: "Hình ảnh",
        agents: "Tác tử AI",
        logs: "Nhật ký hệ thống",
        files: "Trình duyệt tệp",
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
        performanceDesc: "Số ảnh được tải lên mỗi tháng (lấy từ cơ sở dữ liệu).",
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
        deleteConfirmDesc: "Hành động này không thể hoàn tác. Mọi bản ghi liên quan sẽ bị xóa vĩnh viễn.",
        cancel: "Hủy",
        delete: "Xóa",
        deleting: "Đang xóa..."
    }
};

// Colour palette for the file-type pie chart (cycled by extension index).
const PALETTE = ['#00d2ff', '#9d50bb', '#6366f1', '#f43f5e', '#22c55e', '#f59e0b', '#14b8a6'];

/**
 * ADMIN DASHBOARD — all data is fetched live from the /admin API (DB-backed).
 */
const App = () => {
    const [theme, setTheme] = useState(localStorage.getItem('theme') || 'dark');
    const [lang, setLang] = useState(localStorage.getItem('lang') || 'en');
    const [activeSection, setActiveSection] = useState('dashboard');
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);

    const [searchTerm, setSearchTerm] = useState("");
    const [statusFilter, setStatusFilter] = useState("all");
    const [isFilterOpen, setIsFilterOpen] = useState(false);
    const filterRef = useRef(null);

    // Live data from the backend.
    const [stats, setStats] = useState(null);
    const [users, setUsers] = useState([]);
    const [projects, setProjects] = useState([]);
    const [images, setImages] = useState([]);
    const [agents, setAgents] = useState([]);
    const [logs, setLogs] = useState([]);
    const [files, setFiles] = useState([]);
    const [profile, setProfile] = useState(null);
    const [loading, setLoading] = useState({});
    const [error, setError] = useState(null);

    // Delete confirmation modal target: { type: 'project'|'image', id, name }.
    const [deleteTarget, setDeleteTarget] = useState(null);
    const [deleting, setDeleting] = useState(false);

    const { logout } = useAuth();
    const navigate = useNavigate();
    const handleLogout = () => {
        logout();
        navigate('/');
    };

    const t = translations[lang];

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

    const loadAll = useCallback(() => {
        setError(null);
        load('stats', adminGetStats, (d) => setStats(d));
        load('users', adminGetUsers, (d) => setUsers(d.users || []));
        load('projects', adminGetProjects, (d) => setProjects(d.projects || []));
        load('images', adminGetImages, (d) => setImages(d.images || []));
        load('agents', adminGetAgents, (d) => setAgents(d.agents || []));
        load('logs', () => adminGetLogs(200), (d) => setLogs(d.logs || []));
        load('files', adminGetFiles, (d) => setFiles(d.files || []));
    }, [load]);

    useEffect(() => {
        loadAll();
        getMe().then(setProfile).catch(() => setProfile(null));
    }, [loadAll]);

    useEffect(() => {
        document.documentElement.classList.toggle('dark', theme === 'dark');
        localStorage.setItem('theme', theme);
    }, [theme]);

    useEffect(() => {
        localStorage.setItem('lang', lang);
    }, [lang]);

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (filterRef.current && !filterRef.current.contains(event.target)) {
                setIsFilterOpen(false);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const toggleTheme = () => setTheme(theme === 'dark' ? 'light' : 'dark');
    const toggleLang = () => setLang(lang === 'en' ? 'vi' : 'en');

    // ── Formatting + label helpers ──────────────────────────────────────────
    const locale = lang === 'vi' ? 'vi-VN' : 'en-US';
    const fmtDate = (s) => (s ? new Date(s).toLocaleDateString(locale) : '—');
    const fmtDateTime = (s) => (s ? new Date(s).toLocaleString(locale) : '—');
    const basename = (p) => (p || '').split(/[\\/]/).pop() || '—';

    const labelFor = (key) => {
        const map = {
            active: t.statusActive, inactive: t.statusInactive,
            admin: t.roleAdmin, user: t.roleUser,
            completed: t.statusCompleted, failed: t.statusFailed,
            pending: t.statusPending, processing: t.statusProcessing, queued: t.statusPending
        };
        return map[key] || key;
    };

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

    // Real time-series: group images by upload month (last 6 buckets present).
    const performanceData = useMemo(() => {
        const buckets = {};
        for (const img of images) {
            if (!img.uploaded_at) continue;
            const d = new Date(img.uploaded_at);
            const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
            buckets[key] = (buckets[key] || 0) + 1;
        }
        return Object.keys(buckets).sort().slice(-6).map((k) => {
            const [y, m] = k.split('-');
            const label = new Date(Number(y), Number(m) - 1, 1)
                .toLocaleString(locale, { month: 'short' });
            return { name: label, files: buckets[k] };
        });
    }, [images, locale]);

    const adminView = useMemo(() => {
        const claims = jwtClaims();
        return {
            name: claims.name || profile?.name || claims.email || 'Admin',
            role: profile?.role || claims.role || 'admin',
            picture: profile?.picture || null
        };
    }, [profile]);

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
    const GlassCard = ({ children, className = "", hoverType = "blue" }) => {
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
    };

    const StatusBadge = ({ statusKey }) => {
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
    };

    const EmptyRow = ({ colSpan, text, isLoading }) => (
        <tr>
            <td colSpan={colSpan} className="p-16 text-center opacity-40 font-medium">
                {isLoading
                    ? <span className="flex items-center justify-center gap-2"><Loader2 size={18} className="animate-spin text-[#00d2ff]" /> {t.loading}</span>
                    : text}
            </td>
        </tr>
    );

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
                label: t.agents, value: agents.length.toLocaleString(locale),
                sub: `${totalRuns.toLocaleString(locale)} ${t.runsLabel}`, subColor: 'text-orange-400',
                icon: Cpu, color: 'text-orange-400', bg: 'bg-orange-500/20', hover: 'orange'
            }
        ];

        const CustomPieTooltip = ({ active, payload }) => {
            if (active && payload && payload.length) {
                const data = payload[0].payload;
                return (
                    <div className={`p-4 rounded-2xl border-2 shadow-2xl backdrop-blur-md
            ${theme === 'dark'
                            ? 'bg-[#151921]/95 border-[#00d2ff]/40 text-white'
                            : 'bg-white/95 border-gray-200 text-slate-900'}`}>
                        <div className="flex items-center gap-2 mb-1">
                            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: data.color }}></div>
                            <span className="font-black text-sm uppercase tracking-tighter">{data.name}</span>
                        </div>
                        <div className="flex justify-between items-baseline gap-4">
                            <span className="text-[10px] opacity-60 uppercase font-bold">{t.totalCount}</span>
                            <span className="text-xl font-black text-[#00d2ff]">{data.value}</span>
                        </div>
                    </div>
                );
            }
            return null;
        };

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
                        <div className="flex flex-col mb-6">
                            <h4 className="text-lg font-bold flex items-center gap-2">
                                <Activity size={20} className="text-[#00d2ff]" />
                                {t.systemPerformance}
                            </h4>
                            <p className="text-xs opacity-50 mt-1 ml-7">{t.performanceDesc}</p>
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
                                        <XAxis dataKey="name" axisLine={false} tickLine={false} stroke={theme === 'dark' ? '#666' : '#999'} fontSize={11} dy={10} fontWeight="bold" />
                                        <YAxis axisLine={false} tickLine={false} stroke={theme === 'dark' ? '#666' : '#999'} fontSize={11} fontWeight="bold" allowDecimals={false} />
                                        <Tooltip
                                            cursor={{ stroke: '#00d2ff', strokeWidth: 2 }}
                                            contentStyle={{
                                                backgroundColor: theme === 'dark' ? 'rgba(11, 14, 20, 0.95)' : 'rgba(255, 255, 255, 0.95)',
                                                borderRadius: '16px', border: '1px solid rgba(0, 210, 255, 0.2)'
                                            }}
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
                                        <Pie data={fileBreakdown} cx="50%" cy="50%" innerRadius={70} outerRadius={95} paddingAngle={8} dataKey="value" stroke={theme === 'dark' ? '#0b0e14' : '#fff'} strokeWidth={2}>
                                            {fileBreakdown.map((entry, index) => (
                                                <Cell key={`cell-${index}`} fill={entry.color} />
                                            ))}
                                        </Pie>
                                        <Tooltip content={<CustomPieTooltip />} />
                                    </PieChart>
                                </ResponsiveContainer>
                            )}
                            {fileBreakdown.length > 0 && (
                                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-center pointer-events-none">
                                    <span className="text-[10px] uppercase opacity-40 font-bold block">{t.totalCount}</span>
                                    <span className="text-2xl font-extrabold tracking-tighter">{stats?.total_files ?? 0}</span>
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
                                    <div onClick={() => handleToggleUser(user)} className="relative inline-flex items-center cursor-pointer group">
                                        <div className={`w-10 h-5 rounded-full transition-all duration-300 ${user.is_active ? 'bg-[#00d2ff]' : 'bg-gray-600'}`}>
                                            <div className={`absolute top-[2px] left-[2px] bg-white rounded-full h-4 w-4 transition-all duration-300 shadow-md ${user.is_active ? 'translate-x-5' : 'translate-x-0'}`}></div>
                                        </div>
                                        <span className="ml-2 text-[10px] font-bold uppercase opacity-40 group-hover:opacity-100 transition-opacity">
                                            {user.is_active ? t.on : t.off}
                                        </span>
                                    </div>
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

    const renderAgents = () => (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {agents.length === 0 ? (
                <GlassCard className="md:col-span-2 lg:col-span-3 text-center opacity-40 font-medium py-16">
                    {loading.agents
                        ? <span className="flex items-center justify-center gap-2"><Loader2 size={18} className="animate-spin text-[#00d2ff]" /> {t.loading}</span>
                        : t.noAgents}
                </GlassCard>
            ) : agents.map((agent) => {
                const success = Math.round((agent.success_rate || 0) * 100);
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
                        <h4 className="text-xl font-bold group-hover:text-orange-400 transition-colors">{agent.agent_name}</h4>
                        <p className="text-sm opacity-60 mb-6 line-clamp-2">{agent.description || t.noDescription}</p>
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
                ) : projects.map((p) => (
                    <GlassCard key={p.project_id} className="p-0 group overflow-hidden" hoverType="purple">
                        <div className="h-28 bg-gradient-to-br from-[#00d2ff]/20 to-[#9d50bb]/20 relative flex items-center justify-center">
                            <FolderOpen size={48} className="text-white/40 group-hover:scale-110 transition-transform duration-500" />
                            <div className="absolute top-4 left-4 text-[10px] font-bold uppercase tracking-widest opacity-60">
                                {fmtDate(p.created_at)}
                            </div>
                        </div>
                        <div className="p-6">
                            <h5 className="font-bold text-lg mb-1 truncate">{p.project_name || t.untitledProject}</h5>
                            <p className="text-sm opacity-60 mb-4 line-clamp-2 min-h-[2.5rem]">{p.description || t.noDescription}</p>
                            <div className="flex justify-between items-center">
                                <span className="text-xs opacity-50 truncate" title={p.user_id}>{t.userIdLabel}: {(p.user_id || '').slice(0, 8)}…</span>
                                <button
                                    onClick={() => setDeleteTarget({ type: 'project', id: p.project_id, name: p.project_name })}
                                    className="text-red-400 p-2 hover:bg-red-400/10 rounded-lg transition-colors flex-shrink-0"
                                >
                                    <Trash2 size={16} />
                                </button>
                            </div>
                        </div>
                    </GlassCard>
                ))}
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
                            <tr key={img.image_id} className="hover:bg-white/5 transition-colors">
                                <td className="p-4">
                                    <div className="flex items-center gap-3">
                                        <div className={`w-12 h-10 rounded-lg flex items-center justify-center border flex-shrink-0 ${theme === 'dark' ? 'bg-white/5 border-white/10' : 'bg-slate-100 border-slate-200'}`}>
                                            <ImageIcon size={18} className="opacity-40" />
                                        </div>
                                        <span className="font-semibold text-sm truncate max-w-[220px]" title={img.image_path}>{basename(img.image_path)}</span>
                                    </div>
                                </td>
                                <td className="p-4 text-sm opacity-70" title={img.project_id}>{(img.project_id || '').slice(0, 8)}…</td>
                                <td className="p-4"><StatusBadge statusKey={img.analysis_status} /></td>
                                <td className="p-4 text-sm opacity-70">{fmtDateTime(img.uploaded_at)}</td>
                                <td className="p-4 text-center">
                                    <button
                                        onClick={() => setDeleteTarget({ type: 'image', id: img.image_id, name: basename(img.image_path) })}
                                        className="text-red-400 p-2 hover:bg-red-400/10 rounded-lg transition-colors"
                                    >
                                        <Trash2 size={16} />
                                    </button>
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
            <div className="p-6 border-b border-white/10 flex items-center gap-3 text-sm font-bold opacity-70">
                <HardDrive size={18} className="text-[#00d2ff]" />
                {t.uploadDir}: <span className="font-mono opacity-80">{stats?.upload_dir ?? '—'}</span>
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-left">
                    <thead>
                        <tr className="bg-white/5 text-xs opacity-50 uppercase tracking-widest font-bold">
                            <th className="p-4">{t.filename}</th>
                            <th className="p-4">{t.extension}</th>
                            <th className="p-4">{t.sizeCol}</th>
                            <th className="p-4">{t.modifiedAt}</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                        {files.map((f) => (
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
                            </tr>
                        ))}
                        {files.length === 0 && (
                            <EmptyRow colSpan={4} text={t.noFiles} isLoading={loading.files} />
                        )}
                    </tbody>
                </table>
            </div>
        </GlassCard>
    );

    const renderLogs = () => (
        <GlassCard className="p-0 overflow-hidden min-h-[600px] flex flex-col">
            <div className="p-4 border-b border-white/10 flex justify-between items-center bg-white/5">
                <span className="font-bold text-sm tracking-tight uppercase">{t.logsConsole}</span>
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

    const navItems = [
        { id: 'dashboard', icon: LayoutDashboard, label: t.dashboard },
        { id: 'users', icon: Users, label: t.users },
        { id: 'projects', icon: FolderOpen, label: t.projects },
        { id: 'images', icon: ImageIcon, label: t.images },
        { id: 'agents', icon: Cpu, label: t.agents },
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
            <main className={`transition-all duration-500 min-h-screen ${isSidebarOpen ? 'pl-64' : 'pl-20'}`}>
                <header className="h-20 border-b border-white/10 px-8 flex justify-between items-center sticky top-0 z-40 backdrop-blur-xl">
                    <div>
                        <h2 className="text-xl font-bold capitalize">{t[activeSection] || activeSection}</h2>
                        <p className="text-[10px] opacity-40 hidden sm:block font-bold tracking-widest uppercase">{t.adminLabel} / {t[activeSection] || activeSection}</p>
                    </div>

                    <div className="flex items-center gap-4">
                        <button
                            onClick={loadAll}
                            className={`p-2.5 rounded-full border border-white/10 transition-all ${theme === 'dark' ? 'bg-white/5 hover:bg-white/10' : 'bg-gray-100 hover:bg-gray-200'}`}
                            title={t.refresh}
                        >
                            <RefreshCw size={18} className={Object.values(loading).some(Boolean) ? 'animate-spin text-[#00d2ff]' : ''} />
                        </button>

                        <button
                            onClick={toggleLang}
                            className={`flex items-center gap-2 px-3 py-1.5 rounded-full border border-white/10 text-xs font-bold transition-all ${theme === 'dark' ? 'hover:bg-white/10' : 'hover:bg-gray-100'}`}
                        >
                            <Languages size={14} />
                            {lang === 'en' ? 'English' : 'Tiếng Việt'}
                        </button>

                        <button
                            onClick={toggleTheme}
                            className={`p-2.5 rounded-full border border-white/10 transition-all ${theme === 'dark' ? 'bg-white/5 hover:bg-white/10 text-yellow-400' : 'bg-gray-100 hover:bg-gray-200 text-blue-600'}`}
                        >
                            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
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

                <div className="p-8 max-w-7xl mx-auto">
                    {activeSection === 'dashboard' && renderDashboard()}
                    {activeSection === 'users' && renderUsers()}
                    {activeSection === 'agents' && renderAgents()}
                    {activeSection === 'projects' && renderProjects()}
                    {activeSection === 'images' && renderImages()}
                    {activeSection === 'files' && renderFiles()}
                    {activeSection === 'logs' && renderLogs()}
                </div>
            </main>

            {/* Delete confirmation modal */}
            {deleteTarget && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-in fade-in duration-300">
                    <div className={`max-w-md w-full p-8 rounded-[32px] border transition-all
             ${theme === 'dark' ? 'bg-[#0f1218] border-white/10 text-white' : 'bg-white border-gray-200 text-slate-900 shadow-2xl'}`}>
                        <h3 className="text-2xl font-bold mb-4">
                            {deleteTarget.type === 'project' ? t.confirmDeleteProject : t.confirmDeleteImage}
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

export default App;
