import { useCallback, useEffect, useState } from 'react';

import './App.css';
import { DashboardLayout } from './components/DashboardLayout';
import { LoginScreen } from './components/LoginScreen';
import { apiRequest } from './lib/api';
import { ControlPanel } from './pages/ControlPanel';
import { AlertsPage } from './pages/AlertsPage';
import { ConfigurationPage } from './pages/ConfigurationPage';
import { SensorManagement } from './pages/SensorManagement';
import { UserManagement } from './pages/UserManagement';

function App() {
  const [token, setToken] = useState(() => localStorage.getItem('water_token') || '');
  const [currentUser, setCurrentUser] = useState(null);
  const [active, setActive] = useState('dashboard');
  const [loginError, setLoginError] = useState('');
  const [loginLoading, setLoginLoading] = useState(false);

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
        loading={loginLoading}
        error={loginError}
      />
    );
  }

  const role = currentUser.role_id === 2 ? 'tecnico' : 'supervisor';

  return (
    <DashboardLayout
      active={active}
      setActive={setActive}
      role={role}
      user={currentUser}
      onLogout={logout}
    >
      {active === 'dashboard' && <ControlPanel token={token} />}
      {active === 'users' && <UserManagement token={token} currentUser={currentUser} />}
      {active === 'sensors' && <SensorManagement token={token} />}
      {active === 'alerts' && <AlertsPage token={token} />}
      {active === 'settings' && <ConfigurationPage />}
    </DashboardLayout>
  );
}

export default App;
