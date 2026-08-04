import { useState } from 'react';

const sections = [
  {
    icon: 'dashboard',
    title: 'Resumen',
    text: 'Consulta el caudal en tiempo real, el consumo estimado y el estado de conexion de cada sensor por piso.',
  },
  {
    icon: 'sensors',
    title: 'Sensores',
    text: 'Revisa el estado (activo, inactivo, en mantenimiento), la ultima lectura recibida y la fecha de calibracion.',
  },
  {
    icon: 'notifications',
    title: 'Alertas',
    text: 'Un riesgo entre 50% y 85% se marca como posible fuga; desde 85% se considera critico y requiere atencion inmediata.',
  },
  {
    icon: 'group',
    title: 'Usuarios',
    text: 'Administra accesos, roles (Administrador, Supervisor, Tecnico) y el piso asignado a cada persona del equipo.',
  },
];

const notes = [
  'El sensor de Planta Baja (PB) corresponde al dispositivo fisico Wokwi.',
  'Piso 1 y Piso 3 usan simuladores de datos en Python para pruebas.',
  'Las lecturas normales no generan alertas ni aparecen en el listado.',
  'Las anomalias se agrupan en ventanas de 5 minutos para evitar alertas duplicadas.',
];

const roleGuides = {
  admin: {
    label: 'Administrador',
    icon: 'admin_panel_settings',
    steps: [
      {
        title: 'Revisa el Resumen al iniciar sesion',
        text: 'Es la vista principal: caudal en vivo, ultima lectura por sensor y estado de conexion de InfluxDB.',
      },
      {
        title: 'Gestiona usuarios y permisos',
        text: 'En "Usuarios" puedes crear cuentas, asignar el rol correcto y limitar el acceso por piso cuando corresponda.',
      },
      {
        title: 'Da seguimiento a las alertas criticas',
        text: 'En "Alertas" filtra por piso o estado, revisa las graficas de distribucion y marca cada caso como fuga confirmada o falsa alerta.',
      },
      {
        title: 'Administra el modelo de Machine Learning',
        text: 'En "Modelo ML" puedes preparar datasets, entrenar un candidato, comparar sus metricas contra el modelo activo y promoverlo o rechazarlo.',
      },
      {
        title: 'Ajusta el tema visual',
        text: 'Usa el boton de tema en la barra lateral para alternar entre modo claro y oscuro segun tu preferencia.',
      },
    ],
  },
  supervisor: {
    label: 'Supervisor',
    icon: 'supervisor_account',
    steps: [
      {
        title: 'Monitorea tu piso asignado',
        text: 'El Resumen muestra el caudal y consumo estimado del piso que tienes asignado.',
      },
      {
        title: 'Atiende las alertas de tu area',
        text: 'Revisa la seccion Alertas, filtra por piso y gestiona cada caso: reconocer, poner en revision, confirmar o cerrar.',
      },
      {
        title: 'Consulta el historial de caudal',
        text: 'La tabla inferior del Resumen muestra el consumo por hora para detectar patrones inusuales.',
      },
    ],
  },
  tecnico: {
    label: 'Tecnico',
    icon: 'build',
    steps: [
      {
        title: 'Verifica el estado de los sensores',
        text: 'En "Sensores" confirma que cada dispositivo este activo y revisa la fecha de la ultima calibracion.',
      },
      {
        title: 'Atiende alertas de tipo tecnico',
        text: 'Casos como "Sensor Offline" o fallas de conexion requieren tu revision fisica en campo.',
      },
      {
        title: 'Registra observaciones',
        text: 'Al gestionar una alerta, deja comentarios claros: esto queda guardado para el historial y ayuda a auditar el caso.',
      },
    ],
  },
};

const faqs = [
  {
    q: '¿Que significa el color de una alerta?',
    a: 'Rojo indica prioridad critica (riesgo mayor a 80%), naranja indica prioridad media (60-80%) y verde indica prioridad baja.',
  },
  {
    q: '¿Por que veo "Datos demo" en el Resumen?',
    a: 'Significa que InfluxDB no devolvio telemetria real para el piso o filtro seleccionado; se muestran datos de referencia mientras se restablece la conexion.',
  },
  {
    q: '¿Como cambio entre tema claro y oscuro?',
    a: 'Con el boton ubicado justo debajo del logo en la barra lateral. La preferencia se guarda en tu navegador.',
  },
  {
    q: '¿Quien puede promover un modelo candidato?',
    a: 'Unicamente el rol Administrador tiene acceso a "Modelo ML" y a las acciones de entrenar, promover, rechazar o revertir.',
  },
];

export function ConfigurationPage() {
  const [role, setRole] = useState('admin');
  const guide = roleGuides[role];

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Configuracion</h1>
          <p>Guia rapida del sistema y referencia de como usar cada seccion.</p>
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
            <h2>Guia de usuario</h2>
            <p>Pasos recomendados segun tu rol dentro del sistema.</p>
          </div>
        </div>
        <div className="guide-role-tabs">
          {Object.entries(roleGuides).map(([key, item]) => (
            <button
              key={key}
              className={role === key ? 'active' : ''}
              onClick={() => setRole(key)}
              type="button"
            >
              <span className="material-symbols-outlined" aria-hidden="true" style={{ fontSize: 16, verticalAlign: 'middle', marginRight: 6 }}>
                {item.icon}
              </span>
              {item.label}
            </button>
          ))}
        </div>
        <ol className="guide-steps">
          {guide.steps.map((step) => (
            <li key={step.title}>
              <div>
                <strong>{step.title}</strong>
                <span>{step.text}</span>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="panel settings-panel">
        <div className="panel-heading">
          <div>
            <h2>Preguntas frecuentes</h2>
            <p>Dudas comunes sobre alertas, temas visuales y el modelo ML.</p>
          </div>
        </div>
        <div className="guide-faq">
          {faqs.map((item) => (
            <div className="guide-faq-item" key={item.q}>
              <strong>{item.q}</strong>
              <p>{item.a}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="panel table-panel">
        <h2>Criterios de operacion</h2>
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
