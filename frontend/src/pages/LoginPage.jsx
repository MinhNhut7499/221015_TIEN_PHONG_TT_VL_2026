// =============================================================================
// pages/LoginPage.jsx — Google OAuth Login
// =============================================================================
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { GoogleLogin } from '@react-oauth/google';
import { useAuth } from '../context/AuthContext';
import { Sun, Moon, ShieldCheck, Loader2 } from 'lucide-react';

export default function LoginPage() {
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [authError, setAuthError] = useState(null);
  const navigate = useNavigate();
  const { loginWithGoogle, isAuthenticated, role, loading } = useAuth();

  // If already logged in, redirect
  useEffect(() => {
    if (!loading && isAuthenticated) {
      navigate(role === 'admin' ? '/admin' : '/app', { replace: true });
    }
  }, [isAuthenticated, role, loading, navigate]);

  const handleGoogleSuccess = async (credentialResponse) => {
    setIsLoading(true);
    setAuthError(null);

    try {
      const data = await loginWithGoogle(credentialResponse.credential);
      // Redirect based on role returned from backend
      navigate(data.role === 'admin' ? '/admin' : '/app', { replace: true });
    } catch (err) {
      setAuthError(err.message || 'Đăng nhập thất bại');
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleError = () => {
    setAuthError('Google đăng nhập thất bại. Vui lòng thử lại.');
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

      {/* Theme toggle */}
      <button onClick={() => setIsDarkMode(!isDarkMode)}
        className={`fixed top-6 right-6 p-3 rounded-full transition-all duration-300 shadow-lg z-50 ${isDarkMode ? 'bg-gray-800 text-yellow-400 border border-gray-700' : 'bg-white text-indigo-600 border border-gray-200'}`}>
        {isDarkMode ? <Sun size={20} /> : <Moon size={20} />}
      </button>

      {/* Back to landing */}
      <button onClick={() => navigate('/')}
        className={`fixed top-6 left-6 px-4 py-2 rounded-full text-sm font-medium transition-all z-50 ${isDarkMode ? 'bg-gray-800 text-gray-300 border border-gray-700 hover:text-white' : 'bg-white text-gray-600 border border-gray-200 hover:text-gray-900'}`}>
        ← Trang chủ
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

            <div className={`p-4 rounded-2xl ${isDarkMode ? 'bg-blue-500/10' : 'bg-blue-50'}`}>
              <ShieldCheck size={48} className="text-blue-500" />
            </div>

            <div className="space-y-2">
              <h1 className={`text-3xl font-bold tracking-tight ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                Chào mừng trở lại
              </h1>
              <p className={isDarkMode ? 'text-gray-400' : 'text-gray-500'}>
                Đăng nhập bằng Google để truy cập hệ thống ArchiAI
              </p>
            </div>

            {authError && (
              <div className="w-full p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                {authError}
              </div>
            )}

            {isLoading ? (
              <div className="flex items-center space-x-2 text-blue-500 py-8">
                <Loader2 className="animate-spin" size={24} />
                <span className="font-medium">Đang xác thực...</span>
              </div>
            ) : (
              <div className="w-full flex justify-center py-4">
                <GoogleLogin
                  onSuccess={handleGoogleSuccess}
                  onError={handleGoogleError}
                  theme={isDarkMode ? 'filled_blue' : 'outline'}
                  size="large"
                  shape="pill"
                  width="300"
                  text="signin_with"
                  locale="vi"
                />
              </div>
            )}

            <div className={`pt-4 text-xs ${isDarkMode ? 'text-gray-500' : 'text-gray-400'}`}>
              <p>Hệ thống sẽ tự động phân quyền dựa trên email của bạn.</p>
              <p className="mt-1 opacity-60">Bảo mật bởi Google OAuth 2.0</p>
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
