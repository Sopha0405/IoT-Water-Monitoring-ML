export function ActionPopcard({ title, description, children, confirmLabel, danger, loading, onConfirm, onClose }) {
  return (
    <div className="popcard-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="popcard" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
        <header className="popcard-head">
          <h2>{title}</h2>
          <button type="button" className="icon-action" onClick={onClose} aria-label="Cerrar">x</button>
        </header>
        {description && <p className="popcard-description">{description}</p>}
        <div className="popcard-body">{children}</div>
        <footer className="popcard-actions">
          <button type="button" className="secondary-action" onClick={onClose} disabled={loading}>Cancelar</button>
          {onConfirm && (
            <button type="button" className={danger ? 'danger-action' : 'primary-action'} onClick={onConfirm} disabled={loading}>
              {loading ? 'Procesando...' : confirmLabel}
            </button>
          )}
        </footer>
      </section>
    </div>
  );
}
