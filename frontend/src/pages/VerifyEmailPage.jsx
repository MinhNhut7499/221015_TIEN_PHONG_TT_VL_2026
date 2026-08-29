// =============================================================================
// pages/VerifyEmailPage.jsx — Complete registration from the emailed link
// =============================================================================
import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useApp } from '../context/AppContext';
import { Sun, Moon, Globe, ShieldCheck, Loader2, CheckCircle2, XCircle } from 'lucide-react';

const I18N = {
    en: {
        verifying: 'Verifying your account...',
        doneTitle: 'Account verified',
        doneBody: 'Your account is now active. Redirecting...',
        failTitle: 'Verification failed',
        noToken: 'Invalid or missing verification link.',
        register: 'Back to sign up',
        toLogin: 'Go to sign in',
    },
    vi: {
        verifying: 'Đang xác minh tài khoản...',
        doneTitle: 'Đã xác minh tài khoản',
        doneBody: 'Tài khoản của bạn đã được kích hoạt. Đang chuyển hướng...',
        failTitle: 'Xác minh thất bại',
        noToken: 'Liên kết xác minh không hợp lệ hoặc bị thiếu.',
        register: 'Quay lại đăng ký',
        toLogin: 'Đến trang đăng nhập',
    },
};

export default function VerifyEmailPage() {
    const { theme, lang, toggleTheme, toggleLang } = useApp();
    const isDark = theme === 'dark';
    const t = I18N[lang];
    const navigate = useNavigate();
    const [params] = useSearchParams();
    const token = params.get('token') || '';
    const { verifyWithEmail } = useAuth();

    const [status, setStatus] = useState(token ? 'verifying' : 'error');
    const [error, setError] = useState(token ? null : I18N[lang].noToken);
    const ran = useRef(false);

    useEffect(() => {
        if (!token || ran.current) return;
        ran.current = true; // guard against React StrictMode double-invoke
        (async () => {
            try {
                const data = await verifyWithEmail(token);
                setStatus('done');
                setTimeout(() => navigate(data.role === 'admin' ? '/admin' : '/app', { replace: true }), 1500);
            } catch (err) {
                setError(err.message || 'Error');
                setStatus('error');
            }
        })();
    }, [token, verifyWithEmail, navigate]);

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
                        <div className="flex items-center gap-3">
                            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-[#00d2ff] to-[#9d50bb] flex items-center justify-center shadow-lg shadow-blue-500/20">
                                <ShieldCheck className="text-white" />
                            </div>
                            <span className="font-extrabold text-2xl tracking-tighter bg-gradient-to-r from-[#00d2ff] to-[#9d50bb] bg-clip-text text-transparent">ArchiAI</span>
                        </div>

                        {status === 'verifying' && (
                            <div className="flex items-center gap-2 text-blue-500 py-6">
                                <Loader2 className="animate-spin" size={24} />
                                <span className="font-medium">{t.verifying}</span>
                            </div>
                        )}

                        {status === 'done' && (
                            <>
                                <div className={`p-4 rounded-2xl ${isDark ? 'bg-green-500/10' : 'bg-green-50'}`}>
                                    <CheckCircle2 size={40} className="text-green-500" />
                                </div>
                                <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{t.doneTitle}</h1>
                                <p className={isDark ? 'text-gray-400' : 'text-gray-500'}>{t.doneBody}</p>
                            </>
                        )}

                        {status === 'error' && (
                            <>
                                <div className={`p-4 rounded-2xl ${isDark ? 'bg-red-500/10' : 'bg-red-50'}`}>
                                    <XCircle size={40} className="text-red-500" />
                                </div>
                                <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{t.failTitle}</h1>
                                <p className="text-red-400 text-sm">{error}</p>
                                <div className="w-full flex gap-3">
                                    <button onClick={() => navigate('/register')} className={`flex-1 py-3 rounded-xl font-extrabold transition-all ${isDark ? 'bg-white/5 hover:bg-white/10' : 'bg-gray-100 hover:bg-gray-200'}`}>{t.register}</button>
                                    <button onClick={() => navigate('/login')} className="flex-1 py-3 bg-[#00d2ff] hover:bg-[#00bce6] text-[#0b0e14] rounded-xl font-extrabold transition-all">{t.toLogin}</button>
                                </div>
                            </>
                        )}
                    </div>
                </div>
            </main>
        </div>
    );
}
