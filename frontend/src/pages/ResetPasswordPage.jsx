// =============================================================================
// pages/ResetPasswordPage.jsx — Set a new password from an emailed link
// =============================================================================
import React, { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { resetPassword } from '../utils/api';
import { Sun, Moon, Globe, KeyRound, Loader2, CheckCircle2, Eye, EyeOff } from 'lucide-react';

const I18N = {
    en: {
        title: 'Reset password',
        subtitle: 'Choose a new password for your account.',
        password: 'New password',
        confirm: 'Confirm new password',
        submit: 'Update password',
        saving: 'Updating...',
        doneTitle: 'Password updated',
        doneBody: 'Your password has been changed. You can now sign in.',
        toLogin: 'Go to sign in',
        passwordHint: 'At least 8 characters.',
        mismatch: 'Passwords do not match.',
        tooShort: 'Password must be at least 8 characters.',
        noToken: 'Invalid or missing reset link. Please request a new one.',
        request: 'Request a new link',
        showPw: 'Show password',
        hidePw: 'Hide password',
    },
    vi: {
        title: 'Đặt lại mật khẩu',
        subtitle: 'Chọn mật khẩu mới cho tài khoản của bạn.',
        password: 'Mật khẩu mới',
        confirm: 'Xác nhận mật khẩu mới',
        submit: 'Cập nhật mật khẩu',
        saving: 'Đang cập nhật...',
        doneTitle: 'Đã cập nhật mật khẩu',
        doneBody: 'Mật khẩu của bạn đã được thay đổi. Bạn có thể đăng nhập ngay.',
        toLogin: 'Đến trang đăng nhập',
        passwordHint: 'Tối thiểu 8 ký tự.',
        mismatch: 'Mật khẩu xác nhận không khớp.',
        tooShort: 'Mật khẩu phải có ít nhất 8 ký tự.',
        noToken: 'Liên kết đặt lại không hợp lệ hoặc thiếu. Vui lòng yêu cầu liên kết mới.',
        request: 'Yêu cầu liên kết mới',
        showPw: 'Hiện mật khẩu',
        hidePw: 'Ẩn mật khẩu',
    },
};

export default function ResetPasswordPage() {
    const { theme, lang, toggleTheme, toggleLang } = useApp();
    const isDark = theme === 'dark';
    const t = I18N[lang];
    const navigate = useNavigate();
    const [params] = useSearchParams();
    const token = params.get('token') || '';

    const [password, setPassword] = useState('');
    const [confirm, setConfirm] = useState('');
    const [showPw, setShowPw] = useState(false);
    const [showConfirm, setShowConfirm] = useState(false);
    const [busy, setBusy] = useState(false);
    const [done, setDone] = useState(false);
    const [error, setError] = useState(null);

    const inputCls = `w-full px-4 py-2.5 pr-11 rounded-xl border text-sm outline-none transition-all focus:border-[#00d2ff]/60 ${isDark ? 'bg-white/5 border-white/10 text-white' : 'bg-gray-50 border-gray-200 text-slate-900'}`;
    const labelCls = `block text-xs font-bold mb-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`;
    const toggleBtnCls = `absolute right-3 top-1/2 -translate-y-1/2 opacity-60 hover:opacity-100 transition-opacity ${isDark ? 'text-gray-300' : 'text-gray-500'}`;

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (password.length < 8) { setError(t.tooShort); return; }
        if (password !== confirm) { setError(t.mismatch); return; }
        setBusy(true);
        setError(null);
        try {
            await resetPassword(token, password);
            setDone(true);
        } catch (err) {
            setError(err.message || 'Error');
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className={`min-h-screen w-full flex items-center justify-center p-6 transition-colors duration-700 ${isDark ? 'bg-[#050505] text-gray-100' : 'bg-gray-50 text-gray-900'}`}>
            <div className="fixed inset-0 overflow-hidden pointer-events-none">
                <div className={`absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full blur-[120px] ${isDark ? 'bg-blue-600/10' : 'bg-blue-400/10'}`} />
                <div className={`absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full blur-[120px] ${isDark ? 'bg-indigo-600/10' : 'bg-indigo-400/10'}`} />
            </div>

            <div className="fixed top-6 right-6 z-50 flex items-center gap-2">
                <button onClick={toggleLang} className={`flex items-center gap-2 px-3 py-1.5 rounded-full border transition-all text-sm font-bold ${isDark ? 'border-white/10 bg-white/5 text-gray-100 hover:bg-white/10' : 'border-slate-300 bg-white hover:bg-slate-100 text-slate-800'}`}>
                    <Globe size={16} /><span>{lang === 'en' ? 'EN' : 'VI'}</span>
                </button>
                <button onClick={toggleTheme} className={`p-2 rounded-full border transition-all ${isDark ? 'border-white/10 bg-white/5 hover:bg-white/10' : 'border-slate-300 bg-white hover:bg-slate-100'}`}>
                    {isDark ? <Sun size={18} className="text-yellow-400" /> : <Moon size={18} className="text-blue-600" />}
                </button>
            </div>

            <main className="relative z-10 w-full flex justify-center">
                <div className={`w-full max-w-md p-8 rounded-3xl backdrop-blur-xl transition-all duration-500 border ${isDark ? 'bg-gray-900/40 border-gray-700 shadow-[0_0_50px_-12px_rgba(59,130,246,0.3)]' : 'bg-white/70 border-white/50 shadow-2xl'}`}>
                    <div className="flex flex-col items-center text-center space-y-5">
                        <div className={`p-4 rounded-2xl ${isDark ? 'bg-blue-500/10' : 'bg-blue-50'}`}>
                            {done ? <CheckCircle2 size={40} className="text-green-500" /> : <KeyRound size={40} className="text-blue-500" />}
                        </div>

                        {!token ? (
                            <>
                                <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{t.title}</h1>
                                <p className="text-red-400 text-sm">{t.noToken}</p>
                                <button onClick={() => navigate('/forgot-password')} className="w-full py-3 bg-[#00d2ff] hover:bg-[#00bce6] text-[#0b0e14] rounded-xl font-extrabold transition-all">{t.request}</button>
                            </>
                        ) : done ? (
                            <>
                                <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{t.doneTitle}</h1>
                                <p className={isDark ? 'text-gray-400' : 'text-gray-500'}>{t.doneBody}</p>
                                <button onClick={() => navigate('/login')} className="w-full py-3 bg-[#00d2ff] hover:bg-[#00bce6] text-[#0b0e14] rounded-xl font-extrabold transition-all">{t.toLogin}</button>
                            </>
                        ) : (
                            <>
                                <div className="space-y-1">
                                    <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{t.title}</h1>
                                    <p className={isDark ? 'text-gray-400' : 'text-gray-500'}>{t.subtitle}</p>
                                </div>
                                {error && <div className="w-full p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">{error}</div>}
                                <form onSubmit={handleSubmit} className="w-full space-y-3 text-left">
                                    <div>
                                        <label className={labelCls}>{t.password}</label>
                                        <div className="relative">
                                            <input type={showPw ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" className={inputCls} />
                                            <button type="button" onClick={() => setShowPw((v) => !v)} className={toggleBtnCls} title={showPw ? t.hidePw : t.showPw} aria-label={showPw ? t.hidePw : t.showPw}>
                                                {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
                                            </button>
                                        </div>
                                        <p className="text-[11px] opacity-50 mt-1">{t.passwordHint}</p>
                                    </div>
                                    <div>
                                        <label className={labelCls}>{t.confirm}</label>
                                        <div className="relative">
                                            <input type={showConfirm ? 'text' : 'password'} value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" className={inputCls} />
                                            <button type="button" onClick={() => setShowConfirm((v) => !v)} className={toggleBtnCls} title={showConfirm ? t.hidePw : t.showPw} aria-label={showConfirm ? t.hidePw : t.showPw}>
                                                {showConfirm ? <EyeOff size={18} /> : <Eye size={18} />}
                                            </button>
                                        </div>
                                    </div>
                                    <button type="submit" disabled={busy} className="w-full py-3 bg-[#00d2ff] hover:bg-[#00bce6] text-[#0b0e14] rounded-xl font-extrabold transition-all shadow-lg shadow-[#00d2ff]/30 disabled:opacity-50 flex items-center justify-center gap-2">
                                        {busy && <Loader2 size={18} className="animate-spin" />}
                                        {busy ? t.saving : t.submit}
                                    </button>
                                </form>
                            </>
                        )}
                    </div>
                </div>
            </main>
        </div>
    );
}
