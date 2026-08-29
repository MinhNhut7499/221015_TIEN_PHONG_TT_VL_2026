import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { loginEmail, registerEmail, verifyEmail } from '../utils/api';

const AuthContext = createContext(null);

const TOKEN_KEY = 'archi_access_token';
const REFRESH_KEY = 'archi_refresh_token';

function parseJwtPayload(token) {
  try {
    const [, payload] = token.split('.');
    return JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [role, setRole] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
      const payload = parseJwtPayload(token);
      if (payload && payload.exp * 1000 > Date.now()) {
        setIsAuthenticated(true);
        setRole(payload.role ?? null);
      } else {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(REFRESH_KEY);
      }
    }
    setLoading(false);
  }, []);

  const loginWithGoogle = useCallback(async (googleIdToken) => {
    const res = await fetch('/auth/google', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ credential: googleIdToken }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Xác thực thất bại');
    }
    const data = await res.json();
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(REFRESH_KEY, data.refresh_token);
    const payload = parseJwtPayload(data.access_token);
    const userRole = payload?.role ?? null;
    setIsAuthenticated(true);
    setRole(userRole);
    return { role: userRole };
  }, []);

  const applyTokens = useCallback((data) => {
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(REFRESH_KEY, data.refresh_token);
    const payload = parseJwtPayload(data.access_token);
    const userRole = payload?.role ?? null;
    setIsAuthenticated(true);
    setRole(userRole);
    return { role: userRole };
  }, []);

  const loginWithEmail = useCallback(async (email, password) => {
    const data = await loginEmail({ email, password });
    return applyTokens(data);
  }, [applyTokens]);

  // Log in from an already-issued JWT pair (hybrid app polling login: the web
  // claims the token via GET /auth/login-session/{id} after the app finishes
  // Google OAuth in a Chrome Custom Tab).
  const loginWithTokens = useCallback((data) => applyTokens(data), [applyTokens]);

  // Registration no longer logs in immediately — it sends a verification email.
  // The account is created (and the user logged in) only after verifyWithEmail.
  const registerWithEmail = useCallback(async (name, email, password) => {
    return registerEmail({ email, password, name });
  }, []);

  const verifyWithEmail = useCallback(async (token) => {
    const data = await verifyEmail(token);
    return applyTokens(data);
  }, [applyTokens]);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    setIsAuthenticated(false);
    setRole(null);
  }, []);

  return (
    <AuthContext.Provider value={{ isAuthenticated, role, loading, loginWithGoogle, loginWithEmail, loginWithTokens, registerWithEmail, verifyWithEmail, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
