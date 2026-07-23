const menuItems = [
  { id: 'dashboard', label: 'Resumen', icon: 'dashboard' },
  { id: 'users', label: 'Usuarios', icon: 'group' },
  { id: 'sensors', label: 'Sensores', icon: 'sensors' },
  { id: 'alerts', label: 'Alertas', icon: 'notifications' },
  { id: 'settings', label: 'Configuracion', icon: 'settings' },
];

export function DashboardLayout({ active, setActive, role, user, onLogout, children }) {
  const visibleItems = menuItems.filter((item) => !(role === 'tecnico' && item.id === 'users'));

  return (
    <main className="dashboard-shell">
      <aside className="sidebar">
        <div className="side-brand">
          <div className="brand-mark small">A</div>
          <div>
            <strong>AquaSense</strong>
            <span>Edificio Sofia</span>
            <em>{role === 'tecnico' ? 'Tecnico' : 'Supervisor'}</em>
          </div>
        </div>
        <nav>
          {visibleItems.map((item) => (
            <button
              className={active === item.id ? 'active' : ''}
              key={item.id}
              onClick={() => setActive(item.id)}
            >
              <span className="material-symbols-outlined" aria-hidden="true">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>
        <div className="session-user">{user?.email}</div>
        <button className="logout-action" onClick={onLogout}>
          <span className="material-symbols-outlined" aria-hidden="true">logout</span>
          Cerrar Sesion
        </button>
      </aside>
      <section className="content-area">{children}</section>
    </main>
  );
}
