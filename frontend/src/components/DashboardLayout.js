import { useState } from 'react';

import { Logo } from './Logo';

const menuItems = [
  { id: 'dashboard', label: 'Panel general', icon: 'dashboard' },
  { id: 'sensors', label: 'Dispositivos', icon: 'sensors' },
  { id: 'alerts', label: 'Alertas', icon: 'notifications' },
  { id: 'ml-model', label: 'Gestion del modelo', icon: 'model_training', adminOnly: true },
  { id: 'users', label: 'Usuarios', icon: 'group' },
  { id: 'settings', label: 'Configuracion', icon: 'settings' },
];

const roleLabels = {
  admin: 'Administrador',
  tecnico: 'Tecnico',
  supervisor: 'Supervisor',
};

function initialsFor(user) {
  const source = user?.name || user?.email || '';
  const parts = source.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
}

export function DashboardLayout({ active, setActive, role, user, onLogout, children, theme, onToggleTheme }) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const visibleItems = menuItems.filter((item) => (
    !(role === 'tecnico' && item.id === 'users') && (!item.adminOnly || role === 'admin')
  ));
  const currentItem = visibleItems.find((item) => item.id === active);

  function selectSection(id) {
    setActive(id);
    setMobileNavOpen(false);
  }

  return (
    <main className={`dashboard-shell ${mobileNavOpen ? 'nav-open' : ''}`}>
      <aside className="sidebar">
        <div className="side-brand">
          <Logo size={22} />
        </div>
        <nav>
          {visibleItems.map((item) => (
            <button
              className={active === item.id ? 'active' : ''}
              key={item.id}
              onClick={() => selectSection(item.id)}
            >
              <span className="material-symbols-outlined" aria-hidden="true">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>
        <button className="logout-action" onClick={onLogout}>
          <span className="material-symbols-outlined" aria-hidden="true">logout</span>
          Cerrar sesion
        </button>
      </aside>

      {mobileNavOpen && (
        <div
          className="sidebar-backdrop"
          role="presentation"
          onClick={() => setMobileNavOpen(false)}
        />
      )}

      <div className="main-column">
        <header className="app-header">
          <button
            className="mobile-menu-button"
            type="button"
            aria-label="Abrir menu de navegacion"
            onClick={() => setMobileNavOpen((value) => !value)}
          >
            <span className="material-symbols-outlined" aria-hidden="true">menu</span>
          </button>
          <div className="app-header-title">
            <span className="app-header-breadcrumb">Indatta</span>
            <strong>{currentItem?.label || 'Panel general'}</strong>
          </div>
          <div className="app-header-actions">
            <button
              className="header-icon-button"
              type="button"
              onClick={onToggleTheme}
              aria-label={theme === 'dark' ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro'}
              title={theme === 'dark' ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro'}
            >
              <span className="material-symbols-outlined" aria-hidden="true">
                {theme === 'dark' ? 'light_mode' : 'dark_mode'}
              </span>
            </button>
            <div className="app-header-user">
              <div className="app-header-user-info">
                <strong>{user?.name || user?.email}</strong>
                <span>{roleLabels[role] || 'Usuario'}</span>
              </div>
              <div className="user-avatar" aria-hidden="true">{initialsFor(user)}</div>
            </div>
          </div>
        </header>
        <section className="content-area">{children}</section>
      </div>
    </main>
  );
}
