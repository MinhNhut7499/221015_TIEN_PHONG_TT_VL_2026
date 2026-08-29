import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import LandingPage from './pages/LandingPage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import ForgotPasswordPage from './pages/ForgotPasswordPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import VerifyEmailPage from './pages/VerifyEmailPage';
import UserPage from './pages/UserPage';
import AdminPage from './pages/AdminPage';
import BillingResultPage from './pages/BillingResultPage';
import LegalPage from './pages/LegalPage';

// Admin is a superset of user, so admins are allowed on user routes (the
// "admin is a special user" rule). Pass `allow` as the list of roles that may
// enter; a user hitting an admin-only route is bounced to their own app.
function ProtectedRoute({ children, allow }) {
  const { isAuthenticated, role, loading } = useAuth();

  if (loading) return null;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (allow && !allow.includes(role)) {
    return <Navigate to={role === 'admin' ? '/admin' : '/app'} replace />;
  }
  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="/privacy" element={<LegalPage kind="privacy" />} />
        <Route path="/terms" element={<LegalPage kind="terms" />} />
        <Route path="/data-deletion" element={<LegalPage kind="dataDeletion" />} />
        <Route path="/support" element={<LegalPage kind="support" />} />
        <Route path="/ai-policy" element={<LegalPage kind="aiPolicy" />} />
        <Route
          path="/app"
          element={
            <ProtectedRoute allow={['user', 'admin']}>
              <UserPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin"
          element={
            <ProtectedRoute allow={['admin']}>
              <AdminPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/billing/result"
          element={
            <ProtectedRoute allow={['user', 'admin']}>
              <BillingResultPage />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
