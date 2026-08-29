// =============================================================================
// pages/ForgotPasswordPage.jsx — Request a password-reset link
// =============================================================================
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { forgotPassword } from '../utils/api';
import { Sun, Moon, Globe, KeyRound, Loader2, MailCheck } from 'lucide-react';

const I18N = {
    en: {
        back: 'Sign in',
        title: 'Forgot password',
        subtitle: 'Enter your email and we will send a reset link.',
        email: 'Email',
        submit: 'Send reset link',
        sending: 'Sending...',
        sentTitle: 'Check your email',
        sentBody: 'If an account exists for that email, a reset link has been sent. The link expires in 30 minutes.',
        required: 'Please enter your email.',
        backToLogin: 'Back to sign in',
    },
    vi: {
        back: 'Đăng nhập',
        title: 'Quên mật khẩu',
        subtitle: 'Nhập email của bạn, chúng tôi sẽ gửi liên kết đặt lại.',
        email: 'Email',
        submit: 'Gửi liên kết đặt lại',
        sending: 'Đang gửi...',
        sentTitle: 'Kiểm tra email của bạn',
        sentBody: 'Nếu email tồn tại, một liên kết đặt lại đã được gửi. Liên kết hết hạn sau 30 phút.',
        required: 'Vui lòng nhập email.',
        backToLogin: 'Quay lại đăng nhập',
    },
};

export default function ForgotPasswordPage() {
    const { theme, lang, toggleTheme, toggleLang } = useApp();
    const isDark = theme === 'dark';
    const t = I18N[lang];
    const navigate = useNavigate();

    const [email, setEmail] = useState('');
    const [busy, setBusy] = useState(false);
    const [sent, setSent] = useState(false);
    const [error, setError] = useState(null);

    const inputCls = `w-full px-4 py-2.5 rounded-xl border text-sm outline-none transition-all focus:border-[#00d2ff]/60 ${isDark ? 'bg-white/5 border-white/10 text-white' : 'bg-gray-50 border-gray-200 text-slate-900'}`;

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!email.trim()) { setError(t.required); return; }
        setBusy(true);
        setError(null);
        try {
            await forgotPassword(email.trim());
            setSent(true);
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

            <button onClick={() => navigate('/login')} className={`fixed top-6 left-6 px-4 py-2 rounded-full text-sm font-medium transition-all z-50 ${isDark ? 'bg-gray-800 text-gray-300 border border-gray-700 hover:text-white' : 'bg-white text-gray-600 border border-gray-200 hover:text-gray-900'}`}>
                ← {t.back}
            </button>

            <main className="relative z-10 w-full flex justify-center">
                <div className={`w-full max-w-md p-8 rounded-3xl backdrop-blur-xl transition-all duration-500 border ${isDark ? 'bg-gray-900/40 border-gray-700 shadow-[0_0_50px_-12px_rgba(59,130,246,0.3)]' : 'bg-white/70 border-white/50 shadow-2xl'}`}>
                    <div className="flex flex-col items-center text-center space-y-5">
                        <div className={`p-4 rounded-2xl ${isDark ? 'bg-blue-500/10' : 'bg-blue-50'}`}>
                            {sent ? <MailCheck size={40} className="text-green-500" /> : <KeyRound size={40} className="text-blue-500" />}
                        </div>

                        {sent ? (
                            <>
                                <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{t.sentTitle}</h1>
                                <p className={isDark ? 'text-gray-400' : 'text-gray-500'}>{t.sentBody}</p>
                                <button onClick={() => navigate('/login')} className="w-full py-3 bg-[#00d2ff] hover:bg-[#00bce6] text-[#0b0e14] rounded-xl font-extrabold transition-all">
                                    {t.backToLogin}
                                </button>
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
                                        <label className={`block text-xs font-bold mb-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{t.email}</label>
                                        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" className={inputCls} />
                                    </div>
                                    <button type="submit" disabled={busy} className="w-full py-3 bg-[#00d2ff] hover:bg-[#00bce6] text-[#0b0e14] rounded-xl font-extrabold transition-all shadow-lg shadow-[#00d2ff]/30 disabled:opacity-50 flex items-center justify-center gap-2">
                                        {busy && <Loader2 size={18} className="animate-spin" />}
                                        {busy ? t.sending : t.submit}
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
