import { useCallback, useEffect, useState } from 'react';

import './App.css';
import { DashboardLayout } from './components/DashboardLayout';
import { LoginScreen } from './components/LoginScreen';
import { useTheme } from './hooks/useTheme';
import { apiRequest } from './lib/api';
import { ControlPanel } from './pages/ControlPanel';
import { AlertsPage } from './pages/AlertsPage';
import { ConfigurationPage } from './pages/ConfigurationPage';
import { MLModelAdminPage } from './pages/MLModelAdminPage';
import { SensorManagement } from './pages/SensorManagement';
import { UserManagement } from './pages/UserManagement';
import { canAccessSection, hasAdminAccess } from './lib/constants';

const pathToSection = {
  '/': 'dashboard',
  '/alerts': 'alerts',
  '/admin/ml-model': 'ml-model',
  '/users': 'users',
  '/sensors': 'sensors',
  '/settings': 'settings',
};

const sectionToPath = Object.fromEntries(Object.entries(pathToSection).map(([path, section]) => [section, path]));

function App() {
  const { theme, toggleTheme } = useTheme();
  const [token, setToken] = useState(() => localStorage.getItem('water_token') || '');
  const [currentUser, setCurrentUser] = useState(null);
  const [active, setActive] = useState(() => pathToSection[window.location.pathname] || 'dashboard');
  const [loginError, setLoginError] = useState('');
  const [loginLoading, setLoginLoading] = useState(false);
  const [twoFactorChallenge, setTwoFactorChallenge] = useState(null);

  const loadCurrentUser = useCallback(async (nextToken = token) => {
    const user = await apiRequest('/api/v1/users/me', { token: nextToken });
    setCurrentUser(user);
    return user;
  }, [token]);

  useEffect(() => {
    if (!token) return;
    loadCurrentUser().catch(() => {
      localStorage.removeItem('water_token');
      setToken('');
      setCurrentUser(null);
    });
  }, [token, loadCurrentUser]);

  useEffect(() => {
    const path = sectionToPath[active] || '/';
    if (window.location.pathname !== path) {
      window.history.pushState({}, '', path);
    }
  }, [active]);

  useEffect(() => {
    const handlePopState = () => setActive(pathToSection[window.location.pathname] || 'dashboard');
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const role = currentUser?.role_id === 3 ? 'admin' : currentUser?.role_id === 2 ? 'tecnico' : 'supervisor';

  useEffect(() => {
    if (currentUser && !canAccessSection(role, active)) {
      setActive('dashboard');
    }
  }, [active, currentUser, role]);

  async function handleLogin(event) {
    event.preventDefault();
    setLoginLoading(true);
    setLoginError('');
    try {
      const form = new FormData(event.currentTarget);
      const data = await apiRequest('/api/v1/auth/login', {
        method: 'POST',
        body: {
          email: form.get('email'),
          password: form.get('password'),
        },
      });
      if (data.requires_2fa) {
        setTwoFactorChallenge(data);
        return;
      }
      localStorage.setItem('water_token', data.access_token);
      setToken(data.access_token);
      setCurrentUser(data.user);
      setActive('dashboard');
    } catch (err) {
      setLoginError(err.message);
    } finally {
      setLoginLoading(false);
    }
  }

  async function handleVerifyCode(event) {
    event.preventDefault();
    if (!twoFactorChallenge) return;
    setLoginLoading(true);
    setLoginError('');
    try {
      const form = new FormData(event.currentTarget);
      const data = await apiRequest('/api/v1/auth/verify-2fa', {
        method: 'POST',
        body: {
          challenge_id: twoFactorChallenge.challenge_id,
          code: form.get('code'),
        },
      });
      localStorage.setItem('water_token', data.access_token);
      setToken(data.access_token);
      setCurrentUser(data.user);
      setTwoFactorChallenge(null);
      setActive('dashboard');
    } catch (err) {
      setLoginError(err.message);
    } finally {
      setLoginLoading(false);
    }
  }

  function resetTwoFactor() {
    setTwoFactorChallenge(null);
    setLoginError('');
  }

  function logout() {
    localStorage.removeItem('water_token');
    setToken('');
    setCurrentUser(null);
    setActive('dashboard');
  }

  if (!token || !currentUser) {
    return (
      <LoginScreen
        onLogin={handleLogin}
        onVerifyCode={handleVerifyCode}
        onBackToLogin={resetTwoFactor}
        loading={loginLoading}
        error={loginError}
        challenge={twoFactorChallenge}
      />
    );
  }

  return (
    <DashboardLayout
      active={active}
      setActive={setActive}
      role={role}
      user={currentUser}
      token={token}
      onLogout={logout}
      theme={theme}
      onToggleTheme={toggleTheme}
    >
      {active === 'dashboard' && <ControlPanel token={token} currentUser={currentUser} />}
      {active === 'users' && <UserManagement token={token} currentUser={currentUser} />}
      {active === 'sensors' && <SensorManagement token={token} currentUser={currentUser} />}
      {active === 'alerts' && <AlertsPage token={token} currentUser={currentUser} />}
      {active === 'ml-model' && hasAdminAccess(currentUser) && <MLModelAdminPage token={token} />}
      {active === 'settings' && <ConfigurationPage />}
    </DashboardLayout>
  );
}

export default App;
