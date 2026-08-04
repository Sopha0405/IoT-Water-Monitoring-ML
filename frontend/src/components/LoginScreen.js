import { Logo } from './Logo';

export function LoginScreen({
  onLogin,
  loading,
  error,
}) {
  return (
    <main className="login-screen">
      <form className="login-card" onSubmit={onLogin}>
        <div className="login-brand">
          <Logo size={30} />
        </div>
        <p className="login-tagline">Monitoreo hidrico inteligente</p>
        <label>
          Correo electronico
          <div className="input-shell">
            <span className="material-symbols-outlined" aria-hidden="true">mail</span>
            <input name="email" type="email" placeholder="usuario@correo.com" required />
          </div>
        </label>
        <label>
          Contrasena
          <div className="input-shell">
            <span className="material-symbols-outlined" aria-hidden="true">lock</span>
            <input name="password" type="password" placeholder="********" required />
          </div>
        </label>
        {error && <div className="form-error">{error}</div>}
        <button type="submit" disabled={loading}>{loading ? 'Validando...' : 'Iniciar sesion'}</button>
      </form>
    </main>
  );
}
