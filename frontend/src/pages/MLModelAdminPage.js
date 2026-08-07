import { Fragment, useCallback, useEffect, useState } from 'react';

import { ActionPopcard } from '../components/ActionPopcard';
import { MetricCard } from '../components/MetricCard';
import { ModelComparisonChart } from '../components/ModelComparisonChart';
import { Pill } from '../components/Pill';
import {
  getModelAdminStatus,
  prepareDatasetFromInflux,
  promoteCandidate,
  rejectCandidate,
  rollbackModel,
  startTraining,
} from '../services/mlAdminService';

const metricKeys = ['precision', 'recall', 'f1', 'fpr'];
const metricLabels = {
  precision: 'Precision',
  recall: 'Recall',
  f1: 'F1-score',
  fpr: 'Tasa de falsas alertas',
};
const defaultTrainingSteps = [
  { key: 'querying_telemetry', name: 'Consulta de telemetria', description: 'Lecturas obtenidas desde InfluxDB.' },
  { key: 'validating', name: 'Validacion de lecturas', description: 'Ordenamiento, duplicados, timestamps y caudal.' },
  { key: 'building_windows', name: 'Construccion de ventanas', description: 'Ventanas de 60 lecturas consecutivas por dispositivo.' },
  { key: 'extracting_features', name: 'Extraccion de caracteristicas', description: 'Feature set oficial de 24 variables.' },
  { key: 'splitting', name: 'Preparacion temporal', description: 'Split temporal sin fuga de informacion futura.' },
  { key: 'integrating_feedback', name: 'Retroalimentacion', description: 'Uso de revision humana cuando exista.' },
  { key: 'training', name: 'Entrenamiento', description: 'Isolation Forest genera candidate.joblib.' },
  { key: 'evaluating', name: 'Evaluacion', description: 'Evaluacion del candidato sobre test temporal.' },
  { key: 'generating_candidate', name: 'Generacion del candidato', description: 'Validacion de archivo, schema y prediccion de prueba.' },
  { key: 'comparing', name: 'Comparacion con activo', description: 'Comparacion contra active.joblib y decision manual.' },
];
const laPazFormatter = new Intl.DateTimeFormat('es-BO', {
  timeZone: 'America/La_Paz',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});

function formatDate(value) {
  if (!value) return '-';
  return laPazFormatter.format(new Date(value));
}

function formatPercent(value) {
  return typeof value === 'number'
    ? `${(value * 100).toLocaleString('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} %`
    : 'No disponible';
}

function formatThreshold(value) {
  return typeof value === 'number'
    ? value.toLocaleString('es-BO', { minimumFractionDigits: 6, maximumFractionDigits: 6 })
    : '-';
}

function shortHash(value) {
  if (!value) return '-';
  return value.length > 24 ? `${value.slice(0, 15)}...${value.slice(-7)}` : value;
}

function recommendationLabel(value) {
  const labels = {
    manual_review: 'Revision manual',
    promote_candidate: 'Promocion viable',
    promotion_blocked: 'Promocion bloqueada',
  };
  return labels[value] || value || '-';
}

function badgeFor(model, emptyLabel) {
  if (!model?.exists) return { tone: 'warning', label: emptyLabel };
  if (model.errors?.length) return { tone: 'danger', label: 'Invalido' };
  if (model.warnings?.length || model.recommendation === 'manual_review') return { tone: 'warning', label: 'Revision manual' };
  return { tone: 'info', label: model.status === 'active' ? 'Activo' : 'Candidato listo' };
}

function isRunningJob(job) {
  return Boolean(job?.status && !['completed', 'failed', 'cancelled'].includes(job.status));
}

function buildTrainingSteps(job) {
  const backendSteps = Array.isArray(job?.steps) ? job.steps : [];
  const source = backendSteps.length ? backendSteps : defaultTrainingSteps;
  if (!job) return [];
  const completed = Number(job.completed_steps || 0);
  const runningIndex = Math.min(completed, source.length - 1);
  return source.map((step, index) => {
    const status = step.status || (
      job.status === 'failed' && index === runningIndex ? 'failed'
        : index < completed ? 'completed'
          : isRunningJob(job) && index === runningIndex ? 'running'
            : 'pending'
    );
    return { ...step, status };
  });
}

function MetricRow({ metrics }) {
  return metricKeys.map((key) => (
    <Fragment key={key}>
      <dt>{metricLabels[key]}</dt>
      <dd>{formatPercent(metrics?.[key])}</dd>
    </Fragment>
  ));
}

export function MLModelAdminPage({ token }) {
  const [status, setStatus] = useState(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [dialog, setDialog] = useState(null);
  const [reason, setReason] = useState('');
  const [datasetOptions, setDatasetOptions] = useState({
    periodType: 'last_complete_month',
    format: 'parquet',
    useFeedback: false,
  });

  const loadData = useCallback(async () => {
    setLoading(true);
    setMessage('');
    setError('');
    try {
      const adminStatus = await getModelAdminStatus(token);
      if (process.env.NODE_ENV === 'development') {
        console.debug('ML admin status DTO', adminStatus);
      }
      setStatus(adminStatus);
    } catch (err) {
      setError(`No fue posible completar la operacion: ${err.message}`);
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    const hasRunningJob = (status?.retraining_jobs || []).some((job) => (
      job.status && !['completed', 'failed', 'cancelled', 'validating_export'].includes(job.status)
    ));
    if (!hasRunningJob) return undefined;
    const timer = setInterval(loadData, 4000);
    return () => clearInterval(timer);
  }, [loadData, status]);

  async function prepareDataset() {
    setLoading(true);
    setMessage('');
    setError('');
    try {
      const job = await prepareDatasetFromInflux(token, datasetOptions);
      setMessage(`Dataset preparado. Trabajo ${job.jobId}.`);
      await loadData();
    } catch (err) {
      setError(`No fue posible completar la operacion: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function runAction() {
    setLoading(true);
    setMessage('');
    setError('');
    try {
      const firstJob = status?.retraining_jobs?.[0]?.jobId;
      if (dialog === 'train') await startTraining(token, firstJob);
      if (dialog === 'promote') await promoteCandidate(token, firstJob || null, reason || 'Promocion manual aprobada desde gestion del modelo.');
      if (dialog === 'reject') await rejectCandidate(token, firstJob || null, reason);
      if (dialog === 'rollback') await rollbackModel(token, status?.active?.version);
      setDialog(null);
      setReason('');
      await loadData();
      setMessage('Operacion enviada al backend.');
    } catch (err) {
      setError(`No fue posible completar la operacion: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  const active = status?.active;
  const candidate = status?.candidate;
  const summaryModel = candidate?.exists ? candidate : active;
  const summaryLabel = candidate?.exists ? 'candidato' : 'activo';
  const activeBadge = badgeFor(active, 'Sin activo');
  const candidateBadge = badgeFor(candidate, 'Sin candidato');
  const jobs = status?.retraining_jobs || [];
  const currentJob = jobs[0];
  const trainingSteps = buildTrainingSteps(currentJob);
  const totalTrainingSteps = currentJob?.total_steps || trainingSteps.length || 10;
  const completedTrainingSteps = Math.min(currentJob?.completed_steps || 0, totalTrainingSteps);
  const trainingProgress = currentJob
    ? Math.round((completedTrainingSteps / totalTrainingSteps) * 100)
    : 0;
  const currentTrainingStep = trainingSteps.find((step) => step.status === 'running')
    || trainingSteps.find((step) => step.status === 'failed')
    || trainingSteps[Math.min(completedTrainingSteps, trainingSteps.length - 1)];

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Gestion del modelo</h1>
          <p>Rendimiento del modelo activo, candidato en evaluacion e historial de reentrenamientos.</p>
        </div>
        <div className="header-actions">
          <button className="secondary-action" onClick={loadData} disabled={loading}>
            {loading ? 'Actualizando...' : 'Actualizar'}
          </button>
          <button className="accent-action" onClick={prepareDataset} disabled={loading}>Preparar dataset</button>
        </div>
      </header>

      {loading && !status && <div className="status-banner">Cargando estado del modelo...</div>}
      {error && <div className="form-error page-error">{error}</div>}
      {message && <div className="status-banner success">{message}</div>}

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Seleccion y preparacion del dataset</h2>
            <p>La telemetria se consulta desde InfluxDB usando el bucket y measurement configurados en el backend.</p>
          </div>
        </div>
        <div className="inline-form">
          <label>
            Periodo
            <select value={datasetOptions.periodType} onChange={(event) => setDatasetOptions({ ...datasetOptions, periodType: event.target.value })}>
              <option value="last_30_days">Ultimos 30 dias</option>
              <option value="last_complete_month">Ultimo mes completo</option>
              <option value="last_60_days">Ultimos 60 dias</option>
              <option value="last_two_complete_months">Ultimos dos meses completos</option>
            </select>
          </label>
          <label>
            Formato
            <select value={datasetOptions.format} onChange={(event) => setDatasetOptions({ ...datasetOptions, format: event.target.value })}>
              <option value="parquet">Parquet</option>
              <option value="csv">CSV</option>
            </select>
          </label>
          <label className="inline-check">
            <input type="checkbox" checked={datasetOptions.useFeedback} onChange={(event) => setDatasetOptions({ ...datasetOptions, useFeedback: event.target.checked })} />
            Usar retroalimentacion revisada
          </label>
        </div>
      </section>

      <section className="metrics-grid">
        <MetricCard label={`Precision (${summaryLabel})`} value={formatPercent(summaryModel?.metrics?.precision)} tone="blue" />
        <MetricCard label={`Recall (${summaryLabel})`} value={formatPercent(summaryModel?.metrics?.recall)} tone="ok" />
        <MetricCard label={`F1-score (${summaryLabel})`} value={formatPercent(summaryModel?.metrics?.f1)} tone="ok" />
        <MetricCard label={`Tasa de falsas alertas (${summaryLabel})`} value={formatPercent(summaryModel?.metrics?.fpr)} tone="warning" />
      </section>

      <section className="panel chart-panel model-compare-panel">
        <div className="panel-heading">
          <div>
            <h2>Modelo activo vs candidato</h2>
            <p>Comparativa de metricas de desempeno entre el modelo en produccion y el candidato en evaluacion.</p>
          </div>
          <div className="model-compare-legend">
            <span><i className="active-mark" /> Activo</span>
            <span><i className="candidate-mark" /> Candidato</span>
          </div>
        </div>
        <ModelComparisonChart active={active} candidate={candidate} />
      </section>

      <section className="model-grid">
        <article className="panel model-panel">
          <div className="panel-heading">
            <div>
              <h2>Modelo activo</h2>
              <p>{active?.version || 'Sin version registrada'}</p>
            </div>
            <Pill tone={activeBadge.tone}>{activeBadge.label}</Pill>
          </div>
          <dl className="detail-list">
            <dt>Threshold</dt><dd>{formatThreshold(active?.threshold)}</dd>
            <MetricRow metrics={active?.metrics} />
            <dt>Entrenamiento</dt><dd>{formatDate(active?.trained_at)}</dd>
            <dt>Promocion</dt><dd>{formatDate(active?.promoted_at)}</dd>
            <dt>Hash</dt><dd title={active?.sha256 || ''}>{shortHash(active?.sha256)}</dd>
          </dl>
        </article>

        <article className="panel model-panel">
          <div className="panel-heading">
            <div>
              <h2>Modelo candidato</h2>
              <p>{candidate?.version || 'Sin candidato registrado'}</p>
            </div>
            <Pill tone={candidateBadge.tone}>{candidateBadge.label}</Pill>
          </div>
          <dl className="detail-list">
            <dt>Threshold</dt><dd>{formatThreshold(candidate?.threshold)}</dd>
            <MetricRow metrics={candidate?.metrics} />
            <dt>PR-AUC</dt><dd>{formatPercent(candidate?.metrics?.pr_auc)}</dd>
            <dt>ROC-AUC</dt><dd>{formatPercent(candidate?.metrics?.roc_auc)}</dd>
            <dt>Entrenamiento</dt><dd>{formatDate(candidate?.trained_at)}</dd>
            <dt>Schema</dt><dd>{candidate?.schema_version || '-'}</dd>
            <dt>Pipeline</dt><dd>{candidate?.pipeline_version || '-'}</dd>
            <dt>Features</dt><dd>{candidate?.feature_count ?? '-'}</dd>
            <dt>Hash</dt><dd title={candidate?.sha256 || ''}>{shortHash(candidate?.sha256)}</dd>
            <dt>Recomendacion</dt><dd>{recommendationLabel(candidate?.recommendation)}</dd>
            <dt>Advertencias</dt>
            <dd>{candidate?.warnings?.length ? candidate.warnings.join(', ') : candidate?.exists ? 'Sin advertencias' : '-'}</dd>
            <dt>Errores</dt>
            <dd>{candidate?.errors?.length ? candidate.errors.join(', ') : candidate?.exists ? 'Sin errores' : '-'}</dd>
          </dl>
        </article>
      </section>

      <section className="panel table-panel">
        <h2>Trabajos de reentrenamiento ({jobs.length})</h2>
        <table>
          <thead>
            <tr>
              <th>Trabajo</th>
              <th>Dataset</th>
              <th>Periodo</th>
              <th>Estado</th>
              <th>Progreso</th>
              <th>Paso actual</th>
              <th>Error</th>
              <th>Candidato</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.jobId || job.id}>
                <td>{job.jobId || job.id}</td>
                <td>{job.sourcePath || job.dataset || '-'}</td>
                <td>{job.period ? `${formatDate(job.period.start)} - ${formatDate(job.period.end)}` : '-'}</td>
                <td><Pill tone={job.status === 'failed' ? 'danger' : 'neutral'}>{job.status || '-'}</Pill></td>
                <td>{job.progress ?? '-'}</td>
                <td>{job.currentStep || job.step || '-'}</td>
                <td>{job.error || '-'}</td>
                <td>{job.candidateVersion || candidate?.version || '-'}</td>
              </tr>
            ))}
            {!jobs.length && <tr><td colSpan="8">No se encontraron registros para el periodo seleccionado.</td></tr>}
          </tbody>
        </table>
      </section>

        {currentJob && (
          <section className="training-progress-card">
            <div className="training-progress-copy">
              <strong>{isRunningJob(currentJob) ? 'Reentrenamiento en proceso' : currentJob.status === 'completed' ? 'Reentrenamiento completado' : 'Proceso detenido'}</strong>
              <span>{currentTrainingStep?.name || 'Esperando etapa'} · {currentTrainingStep?.description || 'Preparando informacion del trabajo.'}</span>
            </div>
            <div className="training-progress-value">{trainingProgress}%</div>
            <div className="training-progress-track" aria-label="Progreso de reentrenamiento">
              <span style={{ width: `${trainingProgress}%` }} />
            </div>
          </section>
        )}
        {!currentJob && <div className="empty-chart">Prepare un dataset e inicie el reentrenamiento para ver el progreso.</div>}

      {currentJob?.candidate && (
        <section className="panel model-panel">
          <div className="panel-heading">
            <div>
              <h2>Nuevo modelo candidato</h2>
              <p>{currentJob.candidate.candidate_id || currentJob.candidate.version}</p>
            </div>
            <Pill tone="info">Validado</Pill>
          </div>
          <dl className="detail-list">
            <dt>Archivo</dt><dd>{currentJob.candidate.path}</dd>
            <dt>Features</dt><dd>{currentJob.candidate.features_count} ({currentJob.candidate.feature_schema_version})</dd>
            <dt>Pipeline</dt><dd>{currentJob.candidate.pipeline_version}</dd>
            <dt>Threshold</dt><dd>{formatThreshold(currentJob.candidate.threshold)}</dd>
            <dt>Contaminacion</dt><dd>{currentJob.candidate.contamination ?? 'No disponible'}</dd>
            <dt>Tamano</dt><dd>{currentJob.candidate.file_size_bytes ? `${currentJob.candidate.file_size_bytes} bytes` : '-'}</dd>
            <dt>Prediccion prueba</dt><dd>{currentJob.candidate.test_prediction_ok ? 'Correcta' : 'No disponible'}</dd>
          </dl>
        </section>
      )}

      <section className="admin-actions">
        <button className="secondary-action" onClick={() => setDialog('train')} disabled={loading || !jobs.length}>Iniciar reentrenamiento</button>
        <button className="primary-action" onClick={() => setDialog('promote')} disabled={loading || !status?.can_promote}>Promover modelo candidato</button>
        <button className="secondary-action" onClick={() => setDialog('reject')} disabled={loading || !status?.can_reject}>Rechazar candidato</button>
        <button className="danger-action" onClick={() => setDialog('rollback')} disabled={loading || !status?.can_rollback}>Revertir a version anterior</button>
      </section>

      {dialog && (
        <ActionPopcard
          title="Confirmar decision"
          description="La accion se ejecuta en FastAPI; React no accede a PostgreSQL ni a archivos joblib."
          confirmLabel="Confirmar"
          danger={dialog === 'rollback' || dialog === 'reject'}
          loading={loading}
          onConfirm={runAction}
          onClose={() => setDialog(null)}
        >
          <label>
            Motivo
            <textarea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Motivo administrativo" />
          </label>
        </ActionPopcard>
      )}
    </>
  );
}
