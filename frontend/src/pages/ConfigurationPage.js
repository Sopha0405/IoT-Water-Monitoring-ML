const sections = [
  {
    icon: 'dashboard',
    title: 'Resumen',
    text: 'Consulta consumo, sensores activos y lectura en tiempo real por piso.',
  },
  {
    icon: 'sensors',
    title: 'Sensores',
    text: 'Revisa estado, ultima lectura y fecha del ultimo dato recibido.',
  },
  {
    icon: 'notifications',
    title: 'Alertas',
    text: 'Riesgos de 50 a 85 se muestran como posible fuga. Desde 85 requieren atencion.',
  },
  {
    icon: 'group',
    title: 'Usuarios',
    text: 'Administra accesos, roles y pisos asignados al personal autorizado.',
  },
];

const notes = [
  'PB corresponde al sensor Wokwi.',
  'Piso 1 y Piso 3 corresponden a simuladores Python.',
  'Los registros normales no aparecen en alertas.',
  'Las anomalias se agrupan cada 5 minutos para evitar duplicados.',
];

export function ConfigurationPage() {
  return (
    <>
      <header className="page-header">
        <div>
          <h1>Configuracion</h1>
          <p>Guia rapida del sistema.</p>
        </div>
      </header>

      <section className="settings-grid">
        {sections.map((item) => (
          <article className="settings-card" key={item.title}>
            <span className="material-symbols-outlined" aria-hidden="true">{item.icon}</span>
            <div>
              <h2>{item.title}</h2>
              <p>{item.text}</p>
            </div>
          </article>
        ))}
      </section>

      <section className="panel settings-panel">
        <div className="panel-heading">
          <div>
            <h2>Criterios de operacion</h2>
            <p>Reglas principales usadas por el sistema.</p>
          </div>
        </div>
        <ul className="settings-list">
          {notes.map((note) => (
            <li key={note}>
              <span className="material-symbols-outlined" aria-hidden="true">check_circle</span>
              {note}
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
