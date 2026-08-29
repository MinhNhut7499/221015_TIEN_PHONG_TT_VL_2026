// =============================================================================
// pages/LoginPage.jsx — Google OAuth Login
// =============================================================================
import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { GoogleLogin } from '@react-oauth/google';
import { useAuth } from '../context/AuthContext';
import { useApp } from '../context/AppContext';
import { Sun, Moon, Globe, ShieldCheck, Loader2, Eye, EyeOff } from 'lucide-react';

// ── Hybrid mobile app (Cloud-Sync Polling) login helpers ────────────────────
// In the Flutter WebView the @react-oauth/google popup cannot complete, so the
// web registers a session, asks the app to open Google in a Chrome Custom Tab,
// and polls the backend until the token is stored. App mode is detected by the
// cookie the app sets BEFORE page load (reliable even if the JS channel is
// injected late) OR the FlutterBridge channel itself.
const APP_SESSION_TTL_MS = 10 * 60 * 1000; // mirrors LOGIN_SESSION_TTL_MIN

function isAppMode() {
    if (typeof window === 'undefined') return false;
    if (window.FlutterBridge && typeof window.FlutterBridge.postMessage === 'function') return true;
    return typeof document !== 'undefined' && document.cookie.includes('viewappmobie=true');
}

function genUuidV4() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        const v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
}

// Resolve once the JS channel is available (cookie may signal app mode before
// the bridge is injected); reject after timeoutMs.
function waitForFlutterBridge(timeoutMs = 2000, stepMs = 100) {
    return new Promise((resolve, reject) => {
        const ready = () => window.FlutterBridge && typeof window.FlutterBridge.postMessage === 'function';
        if (ready()) return resolve();
        let waited = 0;
        const id = setInterval(() => {
            if (ready()) {
                clearInterval(id);
                resolve();
            } else if ((waited += stepMs) >= timeoutMs) {
                clearInterval(id);
                reject(new Error('bridge_timeout'));
            }
        }, stepMs);
    });
}

const I18N = {
    en: {
        back: 'Home',
        welcome: 'Welcome back',
        subtitle: 'Sign in to access the ArchiAI system',
        authenticating: 'Authenticating...',
        googleFail: 'Google sign-in failed. Please try again.',
        loginFail: 'Sign-in failed',
        emailLabel: 'Email',
        passwordLabel: 'Password',
        signIn: 'Sign in',
        or: 'or',
        forgot: 'Forgot password?',
        noAccount: "Don't have an account?",
        register: 'Sign up',
        emailRequired: 'Please enter your email and password.',
        showPw: 'Show password',
        hidePw: 'Hide password',
        appSignIn: 'Sign in with Google',
        appWaiting: 'Waiting for sign-in in the app...',
        appBridgeFail: 'Could not reach the app. Please try again.',
        appExpired: 'The login session expired. Please try again.',
        appTimeout: 'Timed out waiting for sign-in. Please try again.',
    },
    vi: {
        back: 'Trang chủ',
        welcome: 'Chào mừng trở lại',
        subtitle: 'Đăng nhập để truy cập hệ thống ArchiAI',
        authenticating: 'Đang xác thực...',
        googleFail: 'Google đăng nhập thất bại. Vui lòng thử lại.',
        loginFail: 'Đăng nhập thất bại',
        emailLabel: 'Email',
        passwordLabel: 'Mật khẩu',
        signIn: 'Đăng nhập',
        or: 'hoặc',
        forgot: 'Quên mật khẩu?',
        noAccount: 'Chưa có tài khoản?',
        register: 'Đăng ký',
        emailRequired: 'Vui lòng nhập email và mật khẩu.',
        showPw: 'Hiện mật khẩu',
        hidePw: 'Ẩn mật khẩu',
        appSignIn: 'Đăng nhập với Google',
        appWaiting: 'Đang chờ đăng nhập trong ứng dụng...',
        appBridgeFail: 'Không kết nối được ứng dụng. Vui lòng thử lại.',
        appExpired: 'Phiên đăng nhập đã hết hạn. Vui lòng thử lại.',
        appTimeout: 'Hết thời gian chờ đăng nhập. Vui lòng thử lại.',
    },
};

export default function LoginPage() {
    const { theme, lang, toggleTheme, toggleLang } = useApp();
    const isDarkMode = theme === 'dark';
    const t = I18N[lang];
    const [isLoading, setIsLoading] = useState(false);
    const [authError, setAuthError] = useState(null);
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [showPw, setShowPw] = useState(false);
    const navigate = useNavigate();
    const { loginWithGoogle, loginWithEmail, loginWithTokens, isAuthenticated, role, loading } = useAuth();
    const [appMode] = useState(() => isAppMode());
    const pollRef = useRef(null);
    const mountedRef = useRef(true);

    const stopPolling = () => {
        if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
        }
    };

    // Stop polling and avoid state updates after the page unmounts.
    useEffect(() => {
        mountedRef.current = true;
        return () => {
            mountedRef.current = false;
            stopPolling();
        };
    }, []);

    // If already logged in, redirect
    useEffect(() => {
        if (!loading && isAuthenticated) {
            navigate(role === 'admin' ? '/admin' : '/app', { replace: true });
        }
    }, [isAuthenticated, role, loading, navigate]);

    // Hybrid app login: register a session, ask the app to open Google, then
    // poll until the backend stores the token against the session.
    const handleAppGoogleLogin = async () => {
        setIsLoading(true);
        setAuthError(null);
        const sessionId = genUuidV4();
        try {
            const res = await fetch('/auth/login-session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId }),
            });
            if (!res.ok) throw new Error('session');

            await waitForFlutterBridge();
            window.FlutterBridge.postMessage('GOOGLE_LOGIN:' + sessionId);

            const startedAt = Date.now();
            pollRef.current = setInterval(async () => {
                if (Date.now() - startedAt > APP_SESSION_TTL_MS) {
                    stopPolling();
                    if (mountedRef.current) {
                        setIsLoading(false);
                        setAuthError(t.appTimeout);
                    }
                    return;
                }
                try {
                    const r = await fetch(`/auth/login-session/${sessionId}`);
                    if (!r.ok) return; // transient — keep polling
                    const data = await r.json();
                    if (data.status === 'completed') {
                        stopPolling();
                        const result = loginWithTokens(data);
                        navigate(result.role === 'admin' ? '/admin' : '/app', { replace: true });
                    } else if (data.status === 'expired') {
                        stopPolling();
                        if (mountedRef.current) {
                            setIsLoading(false);
                            setAuthError(t.appExpired);
                        }
                    }
                } catch {
                    // network blip — keep polling
                }
            }, 2000);
        } catch (err) {
            stopPolling();
            setIsLoading(false);
            setAuthError(err.message === 'bridge_timeout' ? t.appBridgeFail : t.loginFail);
        }
    };

    const handleGoogleSuccess = async (credentialResponse) => {
        setIsLoading(true);
        setAuthError(null);

        try {
            const data = await loginWithGoogle(credentialResponse.credential);
            // Redirect based on role returned from backend
            navigate(data.role === 'admin' ? '/admin' : '/app', { replace: true });
        } catch (err) {
            setAuthError(err.message || t.loginFail);
        } finally {
            setIsLoading(false);
        }
    };

    const handleGoogleError = () => {
        setAuthError(t.googleFail);
    };

    const handleEmailLogin = async (e) => {
        e.preventDefault();
        if (!email.trim() || !password) {
            setAuthError(t.emailRequired);
            return;
        }
        setIsLoading(true);
        setAuthError(null);
        try {
            const data = await loginWithEmail(email.trim(), password);
            navigate(data.role === 'admin' ? '/admin' : '/app', { replace: true });
        } catch (err) {
            setAuthError(err.message || t.loginFail);
        } finally {
            setIsLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-[#050505]">
                <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
            </div>
        );
    }

    return (
        <div className={`min-h-screen w-full flex items-center justify-center p-6 transition-colors duration-700 ${
            isDarkMode ? 'bg-[#050505] text-gray-100 selection:bg-blue-500/30' : 'bg-gray-50 text-gray-900'
        }`}>
            {/* Background effects */}
            <div className="fixed inset-0 overflow-hidden pointer-events-none">
                <div className={`absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full blur-[120px] transition-opacity duration-1000 ${isDarkMode ? 'bg-blue-600/10' : 'bg-blue-400/10'}`} />
                <div className={`absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full blur-[120px] transition-opacity duration-1000 ${isDarkMode ? 'bg-indigo-600/10' : 'bg-indigo-400/10'}`} />
            </div>

            {/* Language + theme toggles (consistent with the User page) */}
            <div className="fixed top-6 right-6 z-50 flex items-center gap-2">
                <button onClick={toggleLang} className={`flex items-center gap-2 px-3 py-1.5 rounded-full border transition-all text-sm font-bold
                    ${isDarkMode ? 'border-white/10 bg-white/5 text-gray-100 hover:bg-white/10' : 'border-slate-300 bg-white hover:bg-slate-100 text-slate-800'}`}>
                    <Globe size={16} />
                    <span>{lang === 'en' ? 'EN' : 'VI'}</span>
                </button>
                <button onClick={toggleTheme} className={`p-2 rounded-full border transition-all
                    ${isDarkMode ? 'border-white/10 bg-white/5 hover:bg-white/10' : 'border-slate-300 bg-white hover:bg-slate-100'}`}>
                    {isDarkMode ? <Sun size={18} className="text-yellow-400" /> : <Moon size={18} className="text-blue-600" />}
                </button>
            </div>

            {/* Back to landing */}
            <button onClick={() => navigate('/')}
                className={`fixed top-6 left-6 px-4 py-2 rounded-full text-sm font-medium transition-all z-50 ${isDarkMode ? 'bg-gray-800 text-gray-300 border border-gray-700 hover:text-white' : 'bg-white text-gray-600 border border-gray-200 hover:text-gray-900'}`}>
                ← {t.back}
            </button>

            <main className="relative z-10 w-full flex justify-center">
                <div className={`w-full max-w-md p-8 rounded-3xl backdrop-blur-xl transition-all duration-500 border ${
                    isDarkMode
                        ? 'bg-gray-900/40 border-gray-700 shadow-[0_0_50px_-12px_rgba(59,130,246,0.3)]'
                        : 'bg-white/70 border-white/50 shadow-2xl'
                }`}>
                    <div className="flex flex-col items-center text-center space-y-6">
                        {/* Logo */}
                        <div className="flex items-center gap-3 mb-2">
                            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-[#00d2ff] to-[#9d50bb] flex items-center justify-center shadow-lg shadow-blue-500/20">
                                <ShieldCheck className="text-white" />
                            </div>
                            <span className="font-extrabold text-2xl tracking-tighter bg-gradient-to-r from-[#00d2ff] to-[#9d50bb] bg-clip-text text-transparent">
                                ArchiAI
                            </span>
                        </div>

                        <div className="space-y-2">
                            <h1 className={`text-3xl font-bold tracking-tight ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                                {t.welcome}
                            </h1>
                            <p className={isDarkMode ? 'text-gray-400' : 'text-gray-500'}>
                                {t.subtitle}
                            </p>
                        </div>

                        {authError && (
                            <div className="w-full p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                                {authError}
                            </div>
                        )}

                        {/* Email / password form */}
                        <form onSubmit={handleEmailLogin} className="w-full space-y-3 text-left">
                            <div>
                                <label className={`block text-xs font-bold mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>{t.emailLabel}</label>
                                <input
                                    type="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    autoComplete="email"
                                    className={`w-full px-4 py-2.5 rounded-xl border text-sm outline-none transition-all focus:border-[#00d2ff]/60 ${isDarkMode ? 'bg-white/5 border-white/10 text-white' : 'bg-gray-50 border-gray-200 text-slate-900'}`}
                                />
                            </div>
                            <div>
                                <div className="flex items-center justify-between mb-1">
                                    <label className={`block text-xs font-bold ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>{t.passwordLabel}</label>
                                    <button type="button" onClick={() => navigate('/forgot-password')}
                                        className="text-xs font-semibold text-[#00d2ff] hover:underline">
                                        {t.forgot}
                                    </button>
                                </div>
                                <div className="relative">
                                    <input
                                        type={showPw ? 'text' : 'password'}
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        autoComplete="current-password"
                                        className={`w-full px-4 py-2.5 pr-11 rounded-xl border text-sm outline-none transition-all focus:border-[#00d2ff]/60 ${isDarkMode ? 'bg-white/5 border-white/10 text-white' : 'bg-gray-50 border-gray-200 text-slate-900'}`}
                                    />
                                    <button type="button" onClick={() => setShowPw((v) => !v)}
                                        title={showPw ? t.hidePw : t.showPw} aria-label={showPw ? t.hidePw : t.showPw}
                                        className={`absolute right-3 top-1/2 -translate-y-1/2 opacity-60 hover:opacity-100 transition-opacity ${isDarkMode ? 'text-gray-300' : 'text-gray-500'}`}>
                                        {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
                                    </button>
                                </div>
                            </div>
                            <button type="submit" disabled={isLoading}
                                className="w-full py-3 bg-[#00d2ff] hover:bg-[#00bce6] text-[#0b0e14] rounded-xl font-extrabold transition-all shadow-lg shadow-[#00d2ff]/30 disabled:opacity-50 flex items-center justify-center gap-2">
                                {isLoading ? <Loader2 size={18} className="animate-spin" /> : null}
                                {isLoading ? t.authenticating : t.signIn}
                            </button>
                        </form>

                        <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                            {t.noAccount}{' '}
                            <button type="button" onClick={() => navigate('/register')}
                                className="font-bold text-[#00d2ff] hover:underline">
                                {t.register}
                            </button>
                        </p>

                        {/* Divider */}
                        <div className="w-full flex items-center gap-3">
                            <div className={`flex-1 h-px ${isDarkMode ? 'bg-white/10' : 'bg-gray-200'}`} />
                            <span className={`text-xs uppercase tracking-widest ${isDarkMode ? 'text-gray-500' : 'text-gray-400'}`}>{t.or}</span>
                            <div className={`flex-1 h-px ${isDarkMode ? 'bg-white/10' : 'bg-gray-200'}`} />
                        </div>

                        <div className="w-full flex justify-center">
                            {appMode ? (
                                // Google brand guidelines: the button stays white in dark mode too.
                                <button
                                    type="button"
                                    onClick={handleAppGoogleLogin}
                                    disabled={isLoading}
                                    className="flex items-center justify-center gap-3 w-[300px] py-2.5 rounded-full bg-white text-[#3c4043] font-medium border border-[#dadce0] shadow-sm hover:shadow transition-all disabled:opacity-60"
                                >
                                    {isLoading ? (
                                        <Loader2 size={18} className="animate-spin text-[#3c4043]" />
                                    ) : (
                                        <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
                                            <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.71-1.57 2.68-3.89 2.68-6.62z" />
                                            <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.81.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z" />
                                            <path fill="#FBBC05" d="M3.97 10.72a5.41 5.41 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33z" />
                                            <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.89 11.42 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z" />
                                        </svg>
                                    )}
                                    <span>{isLoading ? t.appWaiting : t.appSignIn}</span>
                                </button>
                            ) : (
                                <GoogleLogin
                                    onSuccess={handleGoogleSuccess}
                                    onError={handleGoogleError}
                                    theme={isDarkMode ? 'filled_blue' : 'outline'}
                                    size="large"
                                    shape="pill"
                                    width="300"
                                    text="signin_with"
                                    locale={lang}
                                />
                            )}
                        </div>

                    </div>
                </div>
            </main>

            <div className="fixed bottom-8 left-0 right-0 flex justify-center pointer-events-none">
                <p className={`text-[10px] font-mono tracking-widest uppercase opacity-30 ${isDarkMode ? 'text-white' : 'text-black'}`}>
                    ArchiAI AUTH v3.0.0
                </p>
            </div>
        </div>
    );
}
