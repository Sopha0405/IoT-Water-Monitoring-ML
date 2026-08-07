import { Logo } from './Logo';

export function LoginScreen({
  onLogin,
  onVerifyCode,
  onBackToLogin,
  loading,
  error,
  challenge,
}) {
  return (
    <main className="login-screen">
      <form className="login-card" onSubmit={challenge ? onVerifyCode : onLogin}>
        <div className="login-brand">
          <Logo size={30} />
        </div>
        <p className="login-tagline">Monitoreo hidrico inteligente</p>

        {!challenge && (
          <>
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
          </>
        )}

        {challenge && (
          <>
            <p className="login-secondary">
              Enviamos un codigo por WhatsApp al numero {challenge.phone_hint || 'registrado'}.
            </p>
            <label>
              Codigo de verificacion
              <div className="input-shell">
                <span className="material-symbols-outlined" aria-hidden="true">pin</span>
                <input name="code" inputMode="numeric" pattern="[0-9]{6}" maxLength="6" placeholder="000000" required autoFocus />
              </div>
            </label>
          </>
        )}

        {error && <div className="form-error">{error}</div>}
        <button type="submit" disabled={loading}>
          {loading ? 'Validando...' : challenge ? 'Verificar codigo' : 'Iniciar sesion'}
        </button>
        {challenge && (
          <button className="login-link-button" type="button" onClick={onBackToLogin} disabled={loading}>
            Cambiar credenciales
          </button>
        )}
      </form>
    </main>
  );
}
