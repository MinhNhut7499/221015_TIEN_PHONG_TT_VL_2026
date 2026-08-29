import { Link } from 'react-router-dom';
import { useApp } from '../context/AppContext';

const T = {
    en: {
        tagline: '© 2026 ArchiAI — Open-Vocabulary Architecture Recognition',
        privacy: 'Privacy',
        terms: 'Terms',
        dataDeletion: 'Data Deletion',
        aiPolicy: 'AI Policy',
        support: 'Support',
    },
    vi: {
        tagline: '© 2026 ArchiAI — Nhận dạng Kiến trúc Mở (Open-Vocabulary)',
        privacy: 'Quyền riêng tư',
        terms: 'Điều khoản',
        dataDeletion: 'Xóa dữ liệu',
        aiPolicy: 'Chính sách AI',
        support: 'Hỗ trợ',
    },
};

/**
 * Shared bilingual site footer. Theme-aware via useApp(); links to the Privacy,
 * Terms, Data Deletion, AI Policy and Support pages.
 */
export default function SiteFooter({ className = '' }) {
    const { lang, theme } = useApp();
    const t = T[lang] || T.vi;
    const dark = theme === 'dark';
    const linkCls = `transition-colors hover:text-[#00d2ff] ${dark ? 'text-gray-400' : 'text-slate-500'}`;
    return (
        <footer className={`w-full border-t px-6 py-5 ${dark ? 'border-white/10' : 'border-slate-200'} ${className}`}>
            <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
                <p className={`text-xs sm:text-sm ${dark ? 'text-gray-500' : 'text-slate-500'}`}>{t.tagline}</p>
                <div className="flex items-center flex-wrap justify-center gap-x-5 gap-y-2 text-xs sm:text-sm font-medium">
                    <Link to="/privacy" className={linkCls}>{t.privacy}</Link>
                    <Link to="/terms" className={linkCls}>{t.terms}</Link>
                    <Link to="/data-deletion" className={linkCls}>{t.dataDeletion}</Link>
                    <Link to="/ai-policy" className={linkCls}>{t.aiPolicy}</Link>
                    <Link to="/support" className={linkCls}>{t.support}</Link>
                </div>
            </div>
        </footer>
    );
}
