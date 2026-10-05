import { useEffect, useId, useState } from 'react';
import { ApiError } from './api';
import { Alert } from './Forms';
import { formatDate, useResource } from './Observations';
import type { MetricPeriod, Monitor } from './types';
import './ProcessingFailures.css';

type Status = 'all' | 'exhausted' | 'expired';
interface ProcessingJob {
  job_id: string; monitor_id: string; config_version: number;
  status: Exclude<Status, 'all'>; scheduled_at: string; finished_at: string;
  execution_count: number; error_code: string | null;
}
interface ProcessingPage {
  items: ProcessingJob[]; total: number; from: string; to: string;
  computed_at: string; retention_days: 30;
}
interface Props {
  projectId: string; monitors: ReadonlyArray<Pick<Monitor, 'id' | 'name'>>;
  revision?: number; blocked?: boolean;
}
const codes: Record<string, string> = {
  internal_error: 'Falha interna do processamento',
  execution_crashed: 'Execução do processamento interrompida',
  pool_exhausted: 'Recursos de execução indisponíveis',
  blocked_destination: 'Destino bloqueado pela política de acesso',
  database_error: 'Falha no acesso ao banco de dados',
  insufficient_budget: 'Tempo disponível insuficiente para executar',
  deadline_exceeded: 'Prazo de processamento excedido',
  execution_limit: 'Limite de execuções de processamento atingido',
};
function jobReason(code: string | null) { return code && Object.hasOwn(codes, code) ? codes[code] : 'Não informado'; }
function loadError(error: unknown) {
  if (error instanceof ApiError && error.status === 401) return 'Entre novamente para consultar os registros do processamento.';
  if (error instanceof ApiError && error.status === 404) return 'Estes registros não estão disponíveis. Confira o projeto e o monitor selecionados.';
  return 'Não foi possível consultar os registros do processamento. Tente recarregar a lista.';
}

export function ProcessingFailures(props: Props) {
  const [expanded, setExpanded] = useState(false);
  const titleId = useId();
  return <section className="processing-failures" aria-labelledby={titleId}>
    <details onToggle={event => setExpanded(event.currentTarget.open)}>
      <summary><h2 id={titleId}>Falhas do processamento do Vigil</h2></summary>
      {expanded && <ProcessingList key={props.projectId} {...props} />}
    </details>
  </section>;
}

function ProcessingList({ projectId, monitors, revision = 0, blocked = false }: Props) {
  const [status, setStatus] = useState<Status>('all');
  const [period, setPeriod] = useState<MetricPeriod>('24h');
  const [monitorId, setMonitorId] = useState('');
  const [offset, setOffset] = useState(0);
  const [retry, setRetry] = useState(0);
  const id = useId();
  const monitorRemoved = monitorId !== '' && !monitors.some(monitor => monitor.id === monitorId);
  const selectedMonitorId = monitorRemoved ? '' : monitorId;
  const query = new URLSearchParams({ status, period, limit: '20', offset: String(monitorRemoved ? 0 : offset) });
  if (selectedMonitorId) query.set('monitor_id', selectedMonitorId);
  const { data, error, loading } = useResource<ProcessingPage>(`/projects/${projectId}/jobs?${query}`, revision + retry, undefined, blocked);
  useEffect(() => { if (monitorRemoved) { setMonitorId(''); setOffset(0); } }, [monitorRemoved]);
  useEffect(() => {
    if (data && !loading && offset > 0 && offset >= data.total) setOffset(data.total === 0 ? 0 : Math.floor((data.total - 1) / 20) * 20);
  }, [data, loading, offset]);
  const unavailable = loading || blocked;
  return <div className="processing-content">
    <p className="observation-note">Registros operacionais do Vigil, separados dos incidentes dos endpoints.</p>
    <div className="processing-filters">
      <label htmlFor={`${id}-status`}>Situação<select id={`${id}-status`} value={status} onChange={event => { setStatus(event.target.value as Status); setOffset(0); }}><option value="all">Todas</option><option value="exhausted">Execuções esgotadas</option><option value="expired">Prazo encerrado</option></select></label>
      <label htmlFor={`${id}-period`}>Período do agendamento<select id={`${id}-period`} value={period} onChange={event => { setPeriod(event.target.value as MetricPeriod); setOffset(0); }}><option value="24h">Últimas 24 horas</option><option value="7d">Últimos 7 dias</option><option value="30d">Últimos 30 dias</option></select></label>
      <label htmlFor={`${id}-monitor`}>Monitor<select id={`${id}-monitor`} value={selectedMonitorId} onChange={event => { setMonitorId(event.target.value); setOffset(0); }}><option value="">Todos os monitores</option>{monitors.map(monitor => <option key={monitor.id} value={monitor.id}>{monitor.name}</option>)}</select></label>
    </div>
    <p className="observation-note">A retenção prevista é de 30 dias, conforme o encerramento e a elegibilidade de cada registro. A janela de agendamento não representa cobertura completa. A lista pode mudar entre páginas.</p>
    <p className="observation-note">Execuções do processamento contam acionamentos técnicos do worker, não tentativas HTTP ao endpoint.</p>
    {blocked && <p className="quiet">A consulta aguarda a ação em andamento.</p>}
    {error ? <><Alert message={loadError(error)} /><button disabled={blocked} onClick={() => setRetry(value => value + 1)}>Recarregar lista</button></> : !data ? <p className="loading" role="status">{blocked ? 'Consulta adiada.' : 'Consultando registros do processamento…'}</p> : <>
      {loading && <p className="quiet" role="status">Atualizando registros do processamento…</p>}
      <p className="observation-note">Agendamentos de {formatDate(data.from)} até {formatDate(data.to)} (limite final exclusivo). Consultado em {formatDate(data.computed_at)}. Horários no seu fuso local. Retenção prevista: {data.retention_days} dias.</p>
      {data.items.length === 0 ? <p className="empty-series">Nenhum registro encontrado nesta janela e seleção. Uma lista vazia não comprova cobertura do processamento.</p> : <div className="table-wrap"><table><caption className="sr-only">Falhas operacionais do processamento do Vigil</caption><thead><tr><th scope="col">Monitor</th><th scope="col">Situação</th><th scope="col">Agendamento</th><th scope="col">Encerramento</th><th scope="col">Execuções do processamento</th></tr></thead><tbody>{data.items.map(job => <tr key={job.job_id}>
        <td data-label="Monitor"><strong>{monitors.find(monitor => monitor.id === job.monitor_id)?.name ?? 'Monitor indisponível'}</strong><small>Configuração {job.config_version}</small></td>
        <td data-label="Situação">{job.status === 'exhausted' ? 'Execuções esgotadas' : 'Prazo encerrado'}<small>{jobReason(job.error_code)}</small></td>
        <td data-label="Agendamento"><time dateTime={job.scheduled_at}>{formatDate(job.scheduled_at)}</time></td>
        <td data-label="Encerramento"><time dateTime={job.finished_at}>{formatDate(job.finished_at)}</time></td>
        <td data-label="Execuções">{job.execution_count}</td>
      </tr>)}</tbody></table></div>}
      <div className="pagination"><span>{data.total === 0 ? '0 registros' : offset >= data.total ? 'Atualizando página…' : `${offset + 1}–${Math.min(offset + 20, data.total)} de ${data.total}`}</span><div className="button-group"><button disabled={unavailable || offset === 0} onClick={() => setOffset(value => Math.max(0, value - 20))}>Anterior</button><button disabled={unavailable || offset + 20 >= data.total} onClick={() => setOffset(value => value + 20)}>Próxima</button></div></div>
      <button className="link" disabled={unavailable} onClick={() => setRetry(value => value + 1)}>Recarregar lista</button>
    </>}
  </div>;
}
