import { Fragment, useCallback, useEffect, useState } from 'react';

import { ActionPopcard } from '../components/ActionPopcard';
import { MetricCard } from '../components/MetricCard';
import { Pill } from '../components/Pill';
import {
  getModelAdminStatus,
  getModelHistory,
  prepareDatasetFromInflux,
  promoteCandidate,
  rejectCandidate,
  rollbackModel,
  startTraining,
} from '../services/mlAdminService';

const metricKeys = ['precision', 'recall', 'f1', 'fpr'];
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
    : '-';
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

function MetricRow({ metrics }) {
  return metricKeys.map((key) => (
    <Fragment key={key}>
      <dt>{key.toUpperCase()}</dt>
      <dd>{formatPercent(metrics?.[key])}</dd>
    </Fragment>
  ));
}

export function MLModelAdminPage({ token }) {
  const [status, setStatus] = useState(null);
  const [history, setHistory] = useState([]);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [dialog, setDialog] = useState(null);
  const [reason, setReason] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    setMessage('');
    setError('');
    try {
      const [adminStatus, modelHistory] = await Promise.all([
        getModelAdminStatus(token),
        getModelHistory(token),
      ]);
      if (process.env.NODE_ENV === 'development') {
        console.debug('ML admin status DTO', adminStatus);
      }
      setStatus(adminStatus);
      setHistory(Array.isArray(modelHistory) ? modelHistory : []);
    } catch (err) {
      setError(err.message);
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function prepareDataset() {
    setLoading(true);
    setMessage('');
    setError('');
    try {
      const job = await prepareDatasetFromInflux(token);
      setMessage(`Dataset preparado. Trabajo ${job.jobId}.`);
      await loadData();
    } catch (err) {
      setError(err.message);
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
      if (dialog === 'promote') await promoteCandidate(token, firstJob || null, reason);
      if (dialog === 'reject') await rejectCandidate(token, firstJob || null, reason);
      if (dialog === 'rollback') await rollbackModel(token, status?.active?.version);
      setDialog(null);
      setReason('');
      await loadData();
      setMessage('Operacion enviada al backend.');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const active = status?.active;
  const candidate = status?.candidate;
  const activeBadge = badgeFor(active, 'Sin activo');
  const candidateBadge = badgeFor(candidate, 'Sin candidato');
  const jobs = status?.retraining_jobs || [];

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Administracion del modelo ML</h1>
          <p>Gestion manual del artefacto activo, candidato, historial y trabajos de reentrenamiento.</p>
        </div>
        <div className="header-actions">
          <button className="secondary-action" onClick={loadData} disabled={loading}>
            {loading ? 'Actualizando...' : 'Actualizar'}
          </button>
          <button className="primary-action" onClick={prepareDataset} disabled={loading}>Preparar dataset</button>
        </div>
      </header>

      {loading && !status && <div className="status-banner">Cargando estado del modelo...</div>}
      {error && <div className="form-error page-error">{error}</div>}
      {message && <div className="status-banner success">{message}</div>}

      <section className="metrics-grid">
        <MetricCard label="Precision candidato" value={formatPercent(candidate?.metrics?.precision)} tone="blue" />
        <MetricCard label="Recall candidato" value={formatPercent(candidate?.metrics?.recall)} tone="ok" />
        <MetricCard label="F1 candidato" value={formatPercent(candidate?.metrics?.f1)} tone="ok" />
        <MetricCard label="FPR candidato" value={formatPercent(candidate?.metrics?.fpr)} tone="warning" />
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
            {!jobs.length && <tr><td colSpan="8">No hay trabajos registrados.</td></tr>}
          </tbody>
        </table>
      </section>

      <section className="panel table-panel">
        <h2>Historial ({history.length})</h2>
        <table>
          <thead>
            <tr>
              <th>Version</th>
              <th>Decision</th>
              <th>Administrador</th>
              <th>Fecha</th>
              <th>Motivo</th>
            </tr>
          </thead>
          <tbody>
            {history.map((item) => (
              <tr key={`${item.version}-${item.date || item.created_at}`}>
                <td>{item.version || '-'}</td>
                <td>{item.status || item.action || '-'}</td>
                <td>{item.admin || item.responsible || '-'}</td>
                <td>{formatDate(item.date || item.created_at || item.promoted_at)}</td>
                <td>{item.reason || '-'}</td>
              </tr>
            ))}
            {!history.length && <tr><td colSpan="5">No hay historial disponible desde la API.</td></tr>}
          </tbody>
        </table>
      </section>

      <section className="admin-actions">
        <button onClick={() => setDialog('train')} disabled={loading || !jobs.length}>Entrenar</button>
        <button onClick={() => setDialog('promote')} disabled={loading || !status?.can_promote}>Promover candidato</button>
        <button onClick={() => setDialog('reject')} disabled={loading || !status?.can_reject}>Rechazar candidato</button>
        <button className="danger-action" onClick={() => setDialog('rollback')} disabled={loading || !status?.can_rollback}>Rollback</button>
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
