// =============================================================================
// pages/RegisterPage.jsx — Email/password registration (with email verification)
// =============================================================================
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useApp } from '../context/AppContext';
import { Sun, Moon, Globe, ShieldCheck, Loader2, Eye, EyeOff, MailCheck } from 'lucide-react';

const I18N = {
    en: {
        back: 'Sign in',
        title: 'Create account',
        name: 'Full name',
        email: 'Email',
        password: 'Password',
        confirm: 'Confirm password',
        submit: 'Sign up',
        creating: 'Sending verification...',
        haveAccount: 'Already have an account?',
        signIn: 'Sign in',
        passwordHint: 'At least 8 characters.',
        mismatch: 'Passwords do not match.',
        required: 'Please fill in all fields.',
        tooShort: 'Password must be at least 8 characters.',
        sentTitle: 'Verify your email',
        sentBody: 'We sent a verification link to your email. Click it to activate your account. The link expires in 24 hours.',
        backToLogin: 'Back to sign in',
        showPw: 'Show password',
        hidePw: 'Hide password',
    },
    vi: {
        back: 'Đăng nhập',
        title: 'Tạo tài khoản',
        name: 'Họ và tên',
        email: 'Email',
        password: 'Mật khẩu',
        confirm: 'Xác nhận mật khẩu',
        submit: 'Đăng ký',
        creating: 'Đang gửi xác minh...',
        haveAccount: 'Đã có tài khoản?',
        signIn: 'Đăng nhập',
        passwordHint: 'Tối thiểu 8 ký tự.',
        mismatch: 'Mật khẩu xác nhận không khớp.',
        required: 'Vui lòng điền đầy đủ thông tin.',
        tooShort: 'Mật khẩu phải có ít nhất 8 ký tự.',
        sentTitle: 'Xác minh email của bạn',
        sentBody: 'Chúng tôi đã gửi liên kết xác minh tới email của bạn. Hãy bấm vào liên kết để kích hoạt tài khoản. Liên kết hết hạn sau 24 giờ.',
        backToLogin: 'Quay lại đăng nhập',
        showPw: 'Hiện mật khẩu',
        hidePw: 'Ẩn mật khẩu',
    },
};

export default function RegisterPage() {
    const { theme, lang, toggleTheme, toggleLang } = useApp();
    const isDark = theme === 'dark';
    const t = I18N[lang];
    const navigate = useNavigate();
    const { registerWithEmail, isAuthenticated, role, loading } = useAuth();

    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirm, setConfirm] = useState('');
    const [showPw, setShowPw] = useState(false);
    const [showConfirm, setShowConfirm] = useState(false);
    const [busy, setBusy] = useState(false);
    const [sent, setSent] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (!loading && isAuthenticated) {
            navigate(role === 'admin' ? '/admin' : '/app', { replace: true });
        }
    }, [isAuthenticated, role, loading, navigate]);

    const inputCls = `w-full px-4 py-2.5 rounded-xl border text-sm outline-none transition-all focus:border-[#00d2ff]/60 ${isDark ? 'bg-white/5 border-white/10 text-white' : 'bg-gray-50 border-gray-200 text-slate-900'}`;
    const labelCls = `block text-xs font-bold mb-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`;
    const toggleBtnCls = `absolute right-3 top-1/2 -translate-y-1/2 opacity-60 hover:opacity-100 transition-opacity ${isDark ? 'text-gray-300' : 'text-gray-500'}`;

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!name.trim() || !email.trim() || !password || !confirm) {
            setError(t.required);
            return;
        }
        if (password.length < 8) { setError(t.tooShort); return; }
        if (password !== confirm) { setError(t.mismatch); return; }
        setBusy(true);
        setError(null);
        try {
            await registerWithEmail(name.trim(), email.trim(), password);
            setSent(true);
        } catch (err) {
            setError(err.message || 'Đăng ký thất bại');
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

            <button onClick={() => navigate('/login')} className={`fixed top-6 left-6 px-4 py-2 rounded-full text-sm font-medium transition-all z-50 ${isDark ? 'bg-gray-800 text-gray-300 border border-gray-700 hover:text-white' : 'bg-white text-gray-600 border border-gray-200 hover:text-gray-900'}`}>
                ← {t.back}
            </button>

            <main className="relative z-10 w-full flex justify-center">
                <div className={`w-full max-w-md p-8 rounded-3xl backdrop-blur-xl transition-all duration-500 border ${isDark ? 'bg-gray-900/40 border-gray-700 shadow-[0_0_50px_-12px_rgba(59,130,246,0.3)]' : 'bg-white/70 border-white/50 shadow-2xl'}`}>
                    <div className="flex flex-col items-center text-center space-y-5">
                        <div className="flex items-center gap-3">
                            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-[#00d2ff] to-[#9d50bb] flex items-center justify-center shadow-lg shadow-blue-500/20">
                                <ShieldCheck className="text-white" />
                            </div>
                            <span className="font-extrabold text-2xl tracking-tighter bg-gradient-to-r from-[#00d2ff] to-[#9d50bb] bg-clip-text text-transparent">ArchiAI</span>
                        </div>

                        {sent ? (
                            <>
                                <div className={`p-4 rounded-2xl ${isDark ? 'bg-blue-500/10' : 'bg-blue-50'}`}>
                                    <MailCheck size={40} className="text-green-500" />
                                </div>
                                <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{t.sentTitle}</h1>
                                <p className={isDark ? 'text-gray-400' : 'text-gray-500'}>{t.sentBody}</p>
                                <button onClick={() => navigate('/login')} className="w-full py-3 bg-[#00d2ff] hover:bg-[#00bce6] text-[#0b0e14] rounded-xl font-extrabold transition-all">
                                    {t.backToLogin}
                                </button>
                            </>
                        ) : (
                            <>
                                <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{t.title}</h1>

                                {error && (
                                    <div className="w-full p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">{error}</div>
                                )}

                                <form onSubmit={handleSubmit} className="w-full space-y-3 text-left">
                                    <div>
                                        <label className={labelCls}>{t.name}</label>
                                        <input type="text" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" className={inputCls} />
                                    </div>
                                    <div>
                                        <label className={labelCls}>{t.email}</label>
                                        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" className={inputCls} />
                                    </div>
                                    <div>
                                        <label className={labelCls}>{t.password}</label>
                                        <div className="relative">
                                            <input type={showPw ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" className={`${inputCls} pr-11`} />
                                            <button type="button" onClick={() => setShowPw((v) => !v)} className={toggleBtnCls} title={showPw ? t.hidePw : t.showPw} aria-label={showPw ? t.hidePw : t.showPw}>
                                                {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
                                            </button>
                                        </div>
                                        <p className="text-[11px] opacity-50 mt-1">{t.passwordHint}</p>
                                    </div>
                                    <div>
                                        <label className={labelCls}>{t.confirm}</label>
                                        <div className="relative">
                                            <input type={showConfirm ? 'text' : 'password'} value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" className={`${inputCls} pr-11`} />
                                            <button type="button" onClick={() => setShowConfirm((v) => !v)} className={toggleBtnCls} title={showConfirm ? t.hidePw : t.showPw} aria-label={showConfirm ? t.hidePw : t.showPw}>
                                                {showConfirm ? <EyeOff size={18} /> : <Eye size={18} />}
                                            </button>
                                        </div>
                                    </div>
                                    <button type="submit" disabled={busy}
                                        className="w-full py-3 bg-[#00d2ff] hover:bg-[#00bce6] text-[#0b0e14] rounded-xl font-extrabold transition-all shadow-lg shadow-[#00d2ff]/30 disabled:opacity-50 flex items-center justify-center gap-2">
                                        {busy && <Loader2 size={18} className="animate-spin" />}
                                        {busy ? t.creating : t.submit}
                                    </button>
                                </form>

                                <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                                    {t.haveAccount}{' '}
                                    <button type="button" onClick={() => navigate('/login')} className="font-bold text-[#00d2ff] hover:underline">{t.signIn}</button>
                                </p>
                            </>
                        )}
                    </div>
                </div>
            </main>
        </div>
    );
}
