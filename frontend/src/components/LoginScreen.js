export function LoginScreen({ onLogin, loading, error }) {
  return (
    <main className="login-screen">
      <form className="login-card" onSubmit={onLogin}>
        <div className="brand-mark">
          <span className="material-symbols-outlined" aria-hidden="true">water_drop</span>
        </div>
        <h1>AquaSense</h1>
        <p>Monitoreo hidrico</p>
        <label>
          Correo electronico
          <div className="input-shell">
            <span className="material-symbols-outlined" aria-hidden="true">mail</span>
            <input name="email" type="email" placeholder="usuario@sofia.com" required />
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
        <button type="submit" disabled={loading}>{loading ? 'Conectando...' : 'Iniciar sesion'}</button>
      </form>
    </main>
  );
}
