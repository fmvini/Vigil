import { useEffect, useId, useRef, useState } from 'react';
import { Brand } from './Brand';
import { ThemeControl } from './ThemeControl';
import { api, ApiError, errorMessage } from './api';
import { Alert } from './Forms';
import { currentFreshness, freshnessLabels, healthLabels } from './domain';
import type { Check, MetricPeriod, Metrics, Monitor, Page, PublicIncident, PublicStatus as PublicStatusDTO } from './types';

export function useResource<T>(path: string, revision = 0, load?: (path: string, signal: AbortSignal) => Promise<T>, paused = false) {
  const [state, setState] = useState<{ path: string; data: T | null; error: unknown; loading: boolean }>({ path, data: null, error: null, loading: true });
  const latest = useRef({ revision, load });
  latest.current = { revision, load };
  const reader = useRef<{ revision: number; refresh: () => void } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let running = false;
    let pending = false;
    const refresh = async () => {
      if (paused || controller.signal.aborted) return;
      if (running) { pending = true; return; }
      running = true;
      setState(previous => ({ path, data: previous.path === path ? previous.data : null, error: null, loading: true }));
      try {
        const data = await (latest.current.load ? latest.current.load(path, controller.signal) : api.request<T>(path, 'GET', undefined, controller.signal));
        if (!controller.signal.aborted) setState({ path, data, error: null, loading: pending });
      } catch (error) {
        if (!controller.signal.aborted) setState({ path, data: null, error, loading: pending });
      } finally {
        running = false;
        if (pending && !controller.signal.aborted) { pending = false; void refresh(); }
      }
    };
    reader.current = { revision: latest.current.revision, refresh };
    if (paused) setState(previous => ({ path, data: previous.path === path ? previous.data : null, error: null, loading: false }));
    else void refresh();
    return () => { controller.abort(); reader.current = null; };
  }, [path, paused]);
  useEffect(() => {
    if (reader.current && reader.current.revision !== revision) {
      reader.current.revision = revision; reader.current.refresh();
    }
  }, [path, revision, paused]);
  return state.path === path ? state : { path, data: null, error: null, loading: true };
}

export function formatMetric(value: number | null | undefined, unit = '') {
  return value == null ? 'Sem dados' : `${value.toLocaleString('pt-BR', { maximumFractionDigits: unit === '%' ? 2 : 1 })}${unit === '%' ? '%' : unit ? ` ${unit}` : ''}`;
}
export function formatDate(value: string) {
  return new Date(value).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}
const endReasons: Record<string, string> = { recovered: 'Recuperado', configuration_changed: 'Configuração alterada', archived: 'Arquivado' };
const errorCodes: Record<string, string> = { timeout: 'Timeout', dns_error: 'Erro de DNS', connection_error: 'Erro de conexão', tls_error: 'Erro de TLS', unexpected_status: 'Status HTTP inesperado', retry_recovered: 'Recuperado após retry', high_latency: 'Latência elevada', failure_pending: 'Falha abaixo do limite offline' };
export function reason(value: string | null) { return value ? errorCodes[value] ?? value : 'Nenhuma'; }

function PeriodSelect({ value, onChange }: { value: MetricPeriod; onChange: (period: MetricPeriod) => void }) {
  const id = useId();
  return <label className="compact-label" htmlFor={id}>Período<select id={id} value={value} onChange={e => onChange(e.target.value as MetricPeriod)}><option value="24h">Últimas 24 horas</option><option value="7d">Últimos 7 dias</option><option value="30d">Últimos 30 dias</option></select></label>;
}

export function MetricsPanel({ path, revision = 0 }: { path: string; revision?: number }) {
  const [period, setPeriod] = useState<MetricPeriod>('24h');
  const [retry, setRetry] = useState(0);
  const { data, error, loading } = useResource<Metrics>(`${path}?period=${period}`, revision + retry);
  return <section className="observation-section" aria-label="Métricas de disponibilidade">
    <div className="section-heading"><div><h2>Disponibilidade por amostras</h2><p>Ciclos avaliados na janela selecionada, sem estimar lacunas entre checks.</p></div><PeriodSelect value={period} onChange={setPeriod} /></div>
    {error ? <><Alert message={errorMessage(error)} /><button onClick={() => setRetry(r => r + 1)}>Recarregar métricas</button></> : !data ? <p role="status" className="loading">Carregando métricas…</p> : <>
      {loading && <p className="quiet" role="status">Atualizando métricas…</p>}
      <dl className="metric-values"><div><dt>Uptime por amostras</dt><dd>{formatMetric(data.uptime_percent, '%')}</dd><small>{data.sample_count} ciclos avaliados</small></div><div><dt>Latência média</dt><dd>{formatMetric(data.average_latency_ms, 'ms')}</dd><small>{data.latency_sample_count} amostras de sucesso</small></div><div><dt>Latência p95</dt><dd>{formatMetric(data.p95_latency_ms, 'ms')}</dd><small>Percentil dos dados elegíveis</small></div></dl>
      <p className="observation-note">{formatDate(data.from)} até {formatDate(data.to)} · calculado em {formatDate(data.computed_at)}.{!data.data_complete && ' Qualidade parcial: há monitores sem uma leitura atual válida.'}</p>
      <dl className="job-counts"><div><dt>Sucessos</dt><dd>{data.success_count}</dd></div><div><dt>Falhas</dt><dd>{data.failure_count}</dd></div><div><dt>Excluídos</dt><dd>{data.excluded_count}</dd></div><div><dt>Cancelados</dt><dd>{data.cancelled_count}</dd></div><div><dt>Pendentes</dt><dd>{data.pending_count}</dd></div><div><dt>Slots omitidos</dt><dd>{data.skipped_slots}</dd></div></dl>
      <p className="observation-note">Excluídos e lacunas operacionais não são falhas do endpoint. Estes contadores não comprovam cobertura contínua.</p>
      {data.series.length === 0 ? <p className="empty-series">Ainda não há ciclos avaliados neste período.</p> : <details className="series"><summary>Ver série temporal ({data.series.length} intervalos de {data.bucket_seconds === 3600 ? '1 hora' : '1 dia'})</summary><div className="table-wrap"><table><caption className="sr-only">Série temporal de disponibilidade</caption><thead><tr><th scope="col">Início do intervalo</th><th scope="col">Ciclos</th><th scope="col">Uptime</th><th scope="col">Média</th><th scope="col">p95</th></tr></thead><tbody>{data.series.map(bucket => <tr key={bucket.bucket_start}><td data-label="Intervalo">{formatDate(bucket.bucket_start)}</td><td data-label="Ciclos">{bucket.sample_count}<small>{bucket.success_count} sucessos · {bucket.failure_count} falhas</small></td><td data-label="Uptime">{formatMetric(bucket.uptime_percent, '%')}</td><td data-label="Média">{formatMetric(bucket.average_latency_ms, 'ms')}</td><td data-label="p95">{formatMetric(bucket.p95_latency_ms, 'ms')}</td></tr>)}</tbody></table></div><p className="observation-note">Intervalos ausentes são lacunas, não períodos com 100% de disponibilidade.</p></details>}
    </>}
  </section>;
}

function Pagination({ offset, total, onChange, loading }: { offset: number; total: number; onChange: (offset: number) => void; loading: boolean }) {
  useEffect(() => {
    if (!loading && offset > 0 && offset >= total) onChange(total === 0 ? 0 : Math.floor((total - 1) / 20) * 20);
  }, [loading, offset, total, onChange]);
  return <div className="pagination"><span>{total === 0 ? '0 registros' : offset >= total ? 'Atualizando página…' : `${offset + 1}–${Math.min(offset + 20, total)} de ${total}`}</span><div className="button-group"><button disabled={loading || offset === 0} onClick={() => onChange(Math.max(0, offset - 20))}>Anterior</button><button disabled={loading || offset + 20 >= total} onClick={() => onChange(offset + 20)}>Próxima</button></div></div>;
}

export function IncidentList({ path, monitorId, revision = 0 }: { path: string; monitorId?: string; revision?: number }) {
  const [state, setState] = useState('all'); const [period, setPeriod] = useState('30d');
  const [offset, setOffset] = useState(0); const [retry, setRetry] = useState(0); const id = useId();
  const query = new URLSearchParams({ state, period, limit: '20', offset: String(offset) });
  if (monitorId) query.set('monitor_id', monitorId);
  const { data, error, loading } = useResource<Page<PublicIncident>>(`${path}?${query}`, revision + retry);
  return <section className="observation-section" aria-label="Incidentes">
    <div className="section-heading"><div><h2>Incidentes</h2><p>Indisponibilidade confirmada e motivos de encerramento.</p></div><div className="filter-group"><label className="compact-label" htmlFor={`${id}-state`}>Situação<select id={`${id}-state`} value={state} onChange={e => { setState(e.target.value); setOffset(0); }}><option value="all">Todos</option><option value="open">Abertos</option><option value="closed">Encerrados</option></select></label><label className="compact-label" htmlFor={`${id}-period`}>Janela de incidentes<select id={`${id}-period`} value={period} onChange={e => { setPeriod(e.target.value); setOffset(0); }}><option value="30d">Últimos 30 dias</option><option value="90d">Últimos 90 dias</option></select></label></div></div>
    {error ? <><Alert message={errorMessage(error)} /><button onClick={() => setRetry(r => r + 1)}>Recarregar incidentes</button></> : !data ? <p role="status" className="loading">Carregando incidentes…</p> : <>
      {data.items.length === 0 ? <p className="empty-series">Nenhum incidente registrado nesta janela e situação. A ausência de incidentes não comprova disponibilidade.</p> : <div className="table-wrap"><table><caption className="sr-only">Incidentes registrados</caption><thead><tr><th scope="col">Monitor</th><th scope="col">Início observado</th><th scope="col">Detecção</th><th scope="col">Encerramento</th></tr></thead><tbody>{data.items.map(incident => <tr key={incident.id}><td data-label="Monitor"><strong>{incident.monitor_name}</strong><small>{incident.ended_at ? 'Encerrado' : 'Aberto'}</small></td><td data-label="Início">{formatDate(incident.started_at)}</td><td data-label="Detecção">{formatDate(incident.detected_at)}</td><td data-label="Encerramento">{incident.ended_at ? <>{formatDate(incident.ended_at)}<small>{endReasons[incident.end_reason ?? ''] ?? 'Encerramento administrativo'}</small></> : <span className="health offline">Em aberto</span>}</td></tr>)}</tbody></table></div>}
      <Pagination offset={offset} total={data.total} onChange={setOffset} loading={loading} />
    </>}
  </section>;
}

export function MonitorDetail({ monitor, revision, onBack }: { monitor: Monitor; revision: number; onBack: () => void }) {
  const [period, setPeriod] = useState<MetricPeriod>('24h'); const [offset, setOffset] = useState(0); const [retry, setRetry] = useState(0);
  const { data, error, loading } = useResource<Page<Check>>(`/monitors/${monitor.id}/checks?period=${period}&limit=20&offset=${offset}`, revision + retry);
  const freshness = currentFreshness(monitor);
  return <section className="monitor-detail" aria-label={`Detalhes de ${monitor.name}`}><button className="link back-link" onClick={onBack}>Voltar aos monitores</button><h2>{monitor.name}</h2><p className="endpoint-url">{monitor.url}</p><div className="detail-status"><span className={`badge ${freshness}`}>{freshnessLabels[freshness]}</span><span>Última saúde: {monitor.health_status ? healthLabels[monitor.health_status] : 'Não avaliada'}{freshness !== 'fresh' && monitor.health_status ? ' (histórica)' : ''}</span></div>
    <MetricsPanel path={`/monitors/${monitor.id}/metrics`} revision={revision} />
    <section className="observation-section" aria-label="Histórico de verificações"><div className="section-heading"><div><h2>Histórico de verificações</h2><p>Um registro por ciclo avaliado; retries são tentativas do mesmo ciclo.</p></div><PeriodSelect value={period} onChange={value => { setPeriod(value); setOffset(0); }} /></div>
      {error ? <><Alert message={errorMessage(error)} /><button onClick={() => setRetry(r => r + 1)}>Recarregar histórico</button></> : !data ? <p role="status">Carregando verificações…</p> : <>
        {data.items.length === 0 ? <p className="empty-series">Nenhuma verificação registrada neste período.</p> : <div className="check-history">{data.items.map(check => <article key={check.id} className="check-entry"><div className="check-heading"><time dateTime={check.scheduled_at}>{formatDate(check.scheduled_at)}</time><span className={`health ${check.outcome === 'success' ? 'online' : 'offline'}`}>{check.outcome === 'success' ? 'Sucesso' : 'Falha'}</span></div><dl className="check-values"><div><dt>Resposta</dt><dd>{check.http_status === null ? 'Sem resposta HTTP' : `HTTP ${check.http_status}`}</dd></div><div><dt>Latência</dt><dd>{formatMetric(check.latency_ms, 'ms')}</dd></div><div><dt>Saúde após ciclo</dt><dd>{healthLabels[check.health_after]}</dd></div><div><dt>Tentativas</dt><dd>{check.attempt_count}</dd></div></dl><details><summary>Detalhes do ciclo</summary><p className="observation-note">Conclusão: {formatDate(check.completed_at)} · duração: {formatMetric(check.cycle_duration_ms, 'ms')} · atraso na fila: {formatMetric(check.queue_delay_ms, 'ms')} · configuração: {check.config_version}</p><p className="observation-note">Erro: {reason(check.error_code)} · degradação: {reason(check.degradation_reason)}</p><ol className="attempts">{check.attempts.map((attempt, index) => <li key={index}>{attempt.http_status === null ? reason(attempt.error_code) : `HTTP ${attempt.http_status}`} · latência {formatMetric(attempt.latency_ms, 'ms')} · duração {formatMetric(attempt.duration_ms, 'ms')}</li>)}</ol></details></article>)}</div>}
        <Pagination offset={offset} total={data.total} onChange={setOffset} loading={loading} />
      </>}
    </section><IncidentList path={`/projects/${monitor.project_id}/incidents`} monitorId={monitor.id} revision={revision} />
  </section>;
}

export function PublicLink({ slug, enabled }: { slug: string; enabled: boolean }) {
  const [message, setMessage] = useState('');
  const path = `/status/${encodeURIComponent(slug)}`;
  async function copy() { try { await navigator.clipboard.writeText(new URL(path, window.location.origin).href); setMessage('Link público copiado.'); } catch { setMessage('Não foi possível copiar. Use o link da página para copiar o endereço.'); } }
  return <div className="public-link"><span>{enabled ? 'Página pública ativada' : 'Página pública desativada'}</span>{enabled && <><a href={path} target="_blank" rel="noopener noreferrer">Abrir página pública</a><button className="link" onClick={copy}>Copiar link público</button></>}{message && <span role="status">{message}</span>}</div>;
}

export function PublicStatus({ slug }: { slug: string }) {
  const [revision, setRevision] = useState(0);
  const { data, error, loading } = useResource<PublicStatusDTO>(`/public/status/${encodeURIComponent(slug)}`, revision);
  useEffect(() => { const timer = window.setInterval(() => setRevision(n => n + 1), 30000); return () => window.clearInterval(timer); }, []);
  useEffect(() => { const previous = document.title; if (data) document.title = `${data.name} · Status | Vigil`; return () => { document.title = previous; }; }, [data?.name]);
  return <div className="public-page"><a className="skip-link" href="#public-main">Pular para o conteúdo</a><header className="public-header"><Brand href="/" /><div className="public-preferences"><span>Página de status</span><ThemeControl /></div></header><main id="public-main" tabIndex={-1}>
    {error ? <section className="empty"><h1>{error instanceof ApiError && error.status === 404 ? 'Página não publicada' : 'Não foi possível consultar o status'}</h1><p>{error instanceof ApiError && error.status === 404 ? 'Esta página está desativada, foi arquivada ou o endereço não existe.' : errorMessage(error)}</p><button onClick={() => setRevision(r => r + 1)}>Tentar novamente</button></section> : !data ? <p role="status" className="loading">Consultando status publicado…</p> : <>
      <h1>{data.name}</h1><section className="overview" aria-label="Saúde publicada"><div><span className="quiet">Saúde observada</span><strong>{data.health_status ? healthLabels[data.health_status] : 'Ainda sem leitura'}</strong><p>{data.data_complete ? 'Resumo dos monitores públicos com leituras elegíveis.' : 'Resumo parcial. Há monitores públicos sem dados atuais.'}</p></div><dl className="quality-counts">{(['no_data', 'stale', 'paused', 'fresh'] as const).map(value => <div key={value}><dt>{freshnessLabels[value]}</dt><dd>{data.freshness_counts[value]}</dd></div>)}</dl></section>
      <div className="section-heading"><div><h2>Serviços</h2><p className="quiet">Consultado em {formatDate(data.computed_at)}. Atualização a cada 30 segundos.</p></div><button onClick={() => setRevision(r => r + 1)} disabled={loading}>{loading ? 'Atualizando…' : 'Atualizar status'}</button></div>
      {data.monitors.length === 0 ? <p className="empty-series">Nenhum monitor foi publicado neste projeto.</p> : <ul className="public-monitors">{data.monitors.map(m => <li key={m.id}><strong>{m.name}</strong><div><span className={`badge ${m.freshness}`}>{freshnessLabels[m.freshness]}</span><span className={m.health_status ? `health ${m.health_status}` : 'quiet'}>{m.health_status ? healthLabels[m.health_status] : 'Não avaliada'}{m.freshness !== 'fresh' && m.health_status ? ' (histórica)' : ''}</span></div><small>{m.last_checked_at ? `Última medição: ${formatDate(m.last_checked_at)}` : 'Nenhuma medição recebida.'}</small></li>)}</ul>}
      <IncidentList key={slug} path={`/public/status/${encodeURIComponent(slug)}/incidents`} revision={revision} />
      <p className="pipeline-note">Ausência de dados, pausa ou leituras antigas não confirmam disponibilidade atual. Incidentes encerrados administrativamente não significam recuperação.</p>
    </>}
  </main><footer>Publicado com Vigil</footer></div>;
}
