import { useEffect, useRef, useState } from 'react';
import { ApiError, errorMessage } from './api';
import { useApi, useTransport } from './transport';
import { DemoApp, DemoSimulation } from './DemoApp';
import { Alert, AuthForm, MonitorForm, ProjectForm } from './Forms';
import { currentFreshness, freshnessLabels, healthLabels, summarize } from './domain';
import type { Freshness, Monitor, Project, Session } from './types';
import { IncidentList, MetricsPanel, MonitorDetail, PublicLink, PublicStatus, useResource } from './Observations';
import { useLiveUpdates } from './live';
import { ProcessingFailures } from './ProcessingFailures';
import { Brand } from './Brand';
import { ThemeControl } from './ThemeControl';
import { CheckTiming } from './CheckTiming';
import { LegalShell, NotFound, PolicyPage } from './Legal';

type Editor = { type: 'project'; value?: Project } | { type: 'monitor'; value?: Monitor } | null;
type Archive = { type: 'project'; value: Project } | { type: 'monitor'; value: Monitor } | null;

export default function App() {
  return <LegalShell><AppRoute /></LegalShell>;
}

function AppRoute() {
  const policy = window.location.pathname.match(/^\/(privacy|terms|cookies)\/?$/)?.[1];
  if (policy) return <PolicyPage policy={policy as 'privacy' | 'terms' | 'cookies'} />;
  if (/^\/demo(?:\/|$)/.test(window.location.pathname)) return <DemoApp />;
  const match = window.location.pathname.match(/^\/status\/([^/]+)\/?$/);
  if (match) {
    let slug = match[1];
    try { slug = decodeURIComponent(slug); } catch { /* Invalid slug returns the API's 404. */ }
    return <PublicStatus slug={slug} />;
  }
  return window.location.pathname === '/' ? <AuthenticatedApp /> : <NotFound />;
}

function AuthenticatedApp() {
  const api = useApi();
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    api.request<Session>('/auth/me', 'GET', undefined, controller.signal)
      .then(value => { if (!controller.signal.aborted) { api.setCsrfToken(value.csrf_token); setSession(value); } })
      .catch(err => { if (!controller.signal.aborted) { if (err instanceof ApiError && err.status === 401) api.setCsrfToken(null); else setError(errorMessage(err)); } })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [attempt]);
  useEffect(() => {
    api.onUnauthorized = () => { api.setCsrfToken(null); setSession(null); setNotice('Sua sessão expirou. Entre novamente para continuar.'); };
    return () => { api.onUnauthorized = undefined; };
  }, []);
  if (loading) return <main className="boot"><div className="boot-header"><Brand /><ThemeControl /></div><p role="status">Verificando sua sessão…</p><a className="demo-cta" href="/demo">Visualizar demonstração</a></main>;
  if (error) return <main className="boot"><div className="boot-header"><Brand /><ThemeControl /></div><h1>Não foi possível abrir sua sessão</h1><Alert message={error} /><button className="primary" onClick={() => setAttempt(a => a + 1)}>Tentar novamente</button><a className="demo-cta" href="/demo">Visualizar demonstração</a></main>;
  if (!session) return <AuthForm notice={notice} onSession={value => { setSession(value); setNotice(''); }} />;
  return <Dashboard session={session} onLogout={() => { api.setCsrfToken(null); setSession(null); setNotice(''); }} />;
}

export function Dashboard({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const api = useApi();
  const { demo } = useTransport();
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState('');
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [mutationError, setMutationError] = useState('');
  const [editor, setEditor] = useState<Editor>(null);
  const [archive, setArchive] = useState<Archive>(null);
  const [busy, setBusy] = useState('');
  const [editorBusy, setEditorBusy] = useState(false);
  const [reloadProjects, setReloadProjects] = useState(0);
  const [reloadMonitors, setReloadMonitors] = useState(0);
  const [notice, setNotice] = useState('');
  const [search, setSearch] = useState('');
  const [quality, setQuality] = useState<Freshness | 'all'>('all');
  const searchInput = useRef<HTMLInputElement>(null);
  const [now, setNow] = useState(Date.now());
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [observationRevision, setObservationRevision] = useState(0);
  const [detailId, setDetailId] = useState('');
  const refreshBlocked = Boolean(editor || archive || editorBusy || busy);
  const projectSnapshot = useResource<Project[]>('/projects', reloadProjects, (path, signal) => api.list<Project>(path, signal), refreshBlocked);
  const monitorSnapshot = useResource<Monitor[]>(`/projects/${projectId}/monitors`, reloadMonitors, (path, signal) => api.list<Monitor>(path, signal), refreshBlocked || !projectId);
  const projectLoading = projectSnapshot.loading;
  const projectError = projectSnapshot.error ? errorMessage(projectSnapshot.error) : '';
  const monitorLoading = Boolean(projectId) && monitorSnapshot.loading;
  const monitorError = monitorSnapshot.error ? errorMessage(monitorSnapshot.error) : '';
  const project = projects.find(p => p.id === projectId);
  const projectMonitors = monitors.filter(m => m.project_id === projectId);
  const detail = projectMonitors.find(m => m.id === detailId);
  const connected = useLiveUpdates(projectId, () => {
    setReloadProjects(n => n + 1); setReloadMonitors(n => n + 1); setObservationRevision(n => n + 1);
  }, () => setReloadProjects(n => n + 1), refreshBlocked);
  useEffect(() => {
    if (projectSnapshot.data) {
      const items = projectSnapshot.data;
      setProjects(items); setProjectId(id => items.some(p => p.id === id) ? id : items[0]?.id ?? '');
    }
  }, [projectSnapshot.data]);
  useEffect(() => {
    if (monitorSnapshot.data) { setMonitors(monitorSnapshot.data); setUpdatedAt(Date.now()); setNow(Date.now()); }
  }, [monitorSnapshot.data]);
  useEffect(() => { setMonitors([]); setUpdatedAt(null); setSearch(''); setQuality('all'); }, [projectId]);
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 15000); return () => window.clearInterval(timer); }, []);
  const summary = summarize(projectMonitors, now);
  const visible = projectMonitors.filter(m => (quality === 'all' || currentFreshness(m, now) === quality) && `${m.name} ${m.url}`.toLocaleLowerCase('pt-BR').includes(search.toLocaleLowerCase('pt-BR')));
  const hasFilters = search !== '' || quality !== 'all';
  function clearFilters() { setSearch(''); setQuality('all'); searchInput.current?.focus(); }
  function select(id: string) {
    setProjectId(id); setEditor(null); setArchive(null); setSearch(''); setQuality('all'); setMutationError(''); setNotice(''); setDetailId('');
  }
  function openEditor(value: NonNullable<Editor>) { setEditor(value); setArchive(null); setMutationError(''); setNotice(''); }
  async function pause(monitor: Monitor) {
    setBusy(monitor.id); setMutationError(''); setNotice('');
    const action = currentFreshness(monitor, now) === 'paused' ? 'resume' : 'pause';
    try {
      const updated = await api.request<Monitor>(`/monitors/${monitor.id}/${action}`, 'POST');
      setMonitors(items => items.map(m => m.id === updated.id ? updated : m));
      setObservationRevision(n => n + 1);
      setNotice(`${monitor.name}: ${action === 'pause' ? 'monitor pausado' : 'monitor retomado'}.`);
    } catch (err) { setMutationError(errorMessage(err)); } finally { setBusy(''); }
  }
  async function confirmArchive() {
    if (!archive) return;
    setBusy(archive.value.id); setMutationError('');
    try {
      await api.request(`/${archive.type === 'project' ? 'projects' : 'monitors'}/${archive.value.id}`, 'DELETE');
      if (archive.type === 'project') { setProjects(items => items.filter(p => p.id !== archive.value.id)); select(projects.find(p => p.id !== archive.value.id)?.id ?? ''); }
      else setMonitors(items => items.filter(m => m.id !== archive.value.id));
      setObservationRevision(n => n + 1);
      setNotice(`${archive.value.name} foi arquivado.`); setArchive(null);
    } catch (err) { setMutationError(errorMessage(err)); } finally { setBusy(''); }
  }
  async function logout() {
    if (demo) { onLogout(); return; }
    setBusy('logout'); setMutationError('');
    try { await api.request('/auth/logout', 'POST'); onLogout(); }
    catch (err) { if (err instanceof ApiError && err.status === 401) onLogout(); else setMutationError(errorMessage(err)); }
    finally { setBusy(''); }
  }
  const actionsDisabled = Boolean(busy || editorBusy || editor || archive || projectLoading);
  return <div className="app-shell">
    <a className="skip-link" href="#main">Pular para o conteúdo</a>
    <aside className="sidebar">
      <Brand href="#main" />
      <div className="sidebar-heading"><h2>Projetos</h2><button className="link" onClick={() => openEditor({ type: 'project' })} disabled={actionsDisabled}>Novo</button></div>
      {projectLoading ? <p role="status" className="quiet">Carregando projetos…</p> : projectError ? <><Alert message={projectError} /><button onClick={() => setReloadProjects(n => n + 1)}>Tentar novamente</button></> : <nav aria-label="Projetos"><ul className="project-list">{projects.map(p => <li key={p.id}><button disabled={Boolean(busy || editorBusy)} aria-current={p.id === projectId ? 'page' : undefined} onClick={() => select(p.id)}>{p.name}</button></li>)}</ul>{projects.length === 0 && <p className="quiet">Seus projetos aparecerão aqui.</p>}</nav>}
      <div className="account"><span title={session.user.email}>{session.user.email}</span><button className="link" onClick={logout} disabled={Boolean(busy || editorBusy)}>{busy === 'logout' ? 'Saindo…' : demo ? 'Sair da demonstração' : 'Sair da conta'}</button></div>
    </aside>
    <main id="main" className="workspace" tabIndex={-1}>
      <div className="workspace-top"><div className="workspace-preferences"><span>Visão geral</span><ThemeControl /></div><div className="sync-status">
        <span role="status">{demo ? 'Dados fictícios em memória' : connected ? 'Atualizações conectadas' : 'Sincronização a cada 30 s'}</span>
        {refreshBlocked ? <span className="quiet">A consulta automática aguarda a ação em andamento.</span> : !demo && !connected && <span className="quiet">Consulta automática a cada 30 s.{project && ' Use Atualizar para consultar agora.'}</span>}
        {project && <span className="quiet">{updatedAt === null ? 'Nenhuma consulta dos monitores concluída.' : <>Última consulta dos monitores às <time dateTime={new Date(updatedAt).toISOString()}>{new Date(updatedAt).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time></>}</span>}
      </div></div>
      <header className="page-heading"><div><h1>{project?.name ?? 'Seus projetos'}</h1><p>{project?.description || (project ? 'Gerencie os endpoints e acompanhe a qualidade das leituras.' : 'Crie um projeto para organizar seus endpoints.')}</p></div>
        {project && <div className="button-group"><button onClick={() => openEditor({ type: 'project', value: project })} disabled={actionsDisabled}>Editar projeto</button><button className="danger-text" onClick={() => { setArchive({ type: 'project', value: project }); setNotice(''); }} disabled={actionsDisabled}>Arquivar projeto</button></div>}
      </header>
      {mutationError && <Alert message={mutationError} />}{notice && <p className="success" role="status">{notice}</p>}
      {archive && <section className="archive-confirm" aria-labelledby="archive-title"><h2 id="archive-title">Arquivar {archive.value.name}?</h2><p>{archive.type === 'project' ? 'O projeto e seus monitores deixarão as listagens ativas. O histórico será preservado.' : 'O monitor deixará a listagem ativa e não executará novos checks. O histórico será preservado.'} Este incremento não permite restaurar itens arquivados.</p><div className="form-actions"><button className="danger" onClick={confirmArchive} disabled={Boolean(busy)}>{busy ? 'Arquivando…' : 'Confirmar arquivamento'}</button><button onClick={() => { setArchive(null); setMutationError(''); }} disabled={Boolean(busy)}>Cancelar</button></div></section>}
      {editor?.type === 'project' && <ProjectForm key={editor.value?.id ?? 'new-project'} value={editor.value} onBusyChange={setEditorBusy} onCancel={() => setEditor(null)} onSaved={saved => { setProjects(items => items.some(p => p.id === saved.id) ? items.map(p => p.id === saved.id ? saved : p) : [...items, saved]); setProjectId(saved.id); setEditor(null); setObservationRevision(n => n + 1); setNotice('Projeto salvo.'); }} />}
      {editor?.type === 'monitor' && project && <MonitorForm key={editor.value?.id ?? 'new-monitor'} value={editor.value} projectId={project.id} onBusyChange={setEditorBusy} onCancel={() => setEditor(null)} onSaved={saved => { setMonitors(items => items.some(m => m.id === saved.id) ? items.map(m => m.id === saved.id ? saved : m) : [...items, saved]); setEditor(null); setObservationRevision(n => n + 1); setNotice('Monitor salvo.'); }} />}
      {!project && !projectLoading && !projectError && editor?.type !== 'project' && <section className="empty"><h2>Comece com um projeto</h2><p>Um projeto reúne os monitores de uma aplicação. Depois, adicione os endpoints que deseja acompanhar.</p><button className="primary" onClick={() => openEditor({ type: 'project' })}>Criar primeiro projeto</button></section>}
      {project && <>
        <PublicLink key={`public-${project.id}`} slug={project.public_slug} enabled={project.public_status_enabled} />
        <CheckTiming />
        {demo && <DemoSimulation key={project.id} monitors={projectMonitors} disabled={actionsDisabled || monitorLoading} onSaved={updated => { setMonitors(items => items.map(m => m.id === updated.id ? updated : m)); setReloadProjects(n => n + 1); setObservationRevision(n => n + 1); }} />}
        <section className="overview" aria-label="Resumo do projeto"><div><span className="quiet">Saúde observada</span><strong>{monitorLoading || monitorError ? 'Indisponível' : summary.health ? healthLabels[summary.health] : 'Ainda sem leitura'}</strong><p>{monitorError ? 'Não foi possível consultar os monitores.' : monitorLoading ? 'Consultando os monitores…' : summary.partial ? 'Resumo parcial. Há monitores sem dados atuais.' : summary.health ? 'Considera apenas monitores com dados atualizados.' : 'Nenhum monitor com medição atual elegível.'}</p></div>
          {!monitorLoading && !monitorError && <dl className="quality-counts">{(['no_data', 'stale', 'paused', 'fresh'] as const).map(state => <div key={state}><dt>{freshnessLabels[state]}</dt><dd>{summary.counts[state]}</dd></div>)}</dl>}
        </section>
        {detail ? <MonitorDetail key={detail.id} monitor={detail} revision={observationRevision} onBack={() => setDetailId('')} /> : <>
        <MetricsPanel key={`metrics-${project.id}`} path={`/projects/${project.id}/metrics`} revision={observationRevision} />
        <section className="monitor-section" aria-labelledby="monitors-title"><div className="section-heading"><div><h2 id="monitors-title">Monitores {!monitorLoading && !monitorError && <span className="count">{projectMonitors.length}</span>}</h2><p>Saúde e qualidade dos dados são estados independentes.</p></div><div className="button-group"><button disabled={monitorLoading || actionsDisabled} onClick={() => { setReloadMonitors(n => n + 1); setObservationRevision(n => n + 1); }}>Atualizar</button><button className="primary" disabled={actionsDisabled || monitorLoading || Boolean(monitorError)} onClick={() => openEditor({ type: 'monitor' })}>Novo monitor</button></div></div>
          {monitorLoading ? <div className="loading" role="status">Carregando monitores…<div className="skeleton" /><div className="skeleton" /></div> : monitorError ? <><Alert message={monitorError} /><button onClick={() => setReloadMonitors(n => n + 1)}>Tentar novamente</button></> : <>
            <div className="list-toolbar" role="group" aria-label="Filtros de monitores">
              <label className="search-label" htmlFor="monitor-search">Buscar monitores<input ref={searchInput} id="monitor-search" type="search" placeholder="Nome ou URL" value={search} onChange={e => setSearch(e.target.value)} aria-controls="monitor-results" /></label>
              <label className="quality-filter" htmlFor="monitor-quality">Qualidade dos dados<select id="monitor-quality" value={quality} onChange={e => setQuality(e.target.value as Freshness | 'all')} aria-controls="monitor-results"><option value="all">Todos</option><option value="fresh">Atualizados</option><option value="stale">Desatualizados</option><option value="no_data">Sem dados</option><option value="paused">Pausados</option></select></label>
              <div className="filter-summary"><span className="quiet">{visible.length} de {projectMonitors.length} {projectMonitors.length === 1 ? 'monitor' : 'monitores'}</span>{hasFilters && <button type="button" className="link" onClick={clearFilters}>Limpar filtros</button>}</div>
            </div>
            <div id="monitor-results">{projectMonitors.length === 0 ? <div className="empty compact"><h3>Nenhum endpoint configurado</h3><p>Adicione seu primeiro monitor. Ele aparecerá como “Sem dados” até receber uma medição real.</p></div> : visible.length === 0 ? <p className="empty compact" role="status">Nenhum monitor corresponde aos filtros. Limpe os filtros para ver todos os monitores.</p> : <div className="table-wrap"><table><caption className="sr-only">Monitores do projeto {project.name}</caption><thead><tr><th scope="col">Endpoint</th><th scope="col">Dados</th><th scope="col">Última saúde</th><th scope="col">Último check</th><th scope="col">Ações</th></tr></thead><tbody>{visible.map(m => <MonitorRow key={m.id} monitor={m} now={now} disabled={actionsDisabled} busy={busy === m.id} onDetail={() => setDetailId(m.id)} onPause={() => pause(m)} onEdit={() => openEditor({ type: 'monitor', value: m })} onArchive={() => { setArchive({ type: 'monitor', value: m }); setNotice(''); }} />)}</tbody></table></div>}</div>
          </>}
        </section>
        <IncidentList key={`incidents-${project.id}`} path={`/projects/${project.id}/incidents`} revision={observationRevision} />
        </>}
        <ProcessingFailures key={`processing-${project.id}`} projectId={project.id} monitors={projectMonitors} revision={observationRevision} blocked={refreshBlocked} />
        <p className="pipeline-note">Métricas e histórico representam apenas ciclos persistidos. Sem medições, os valores permanecem sem dados; lacunas não significam disponibilidade.</p>
      </>}
    </main>
  </div>;
}

function MonitorRow({ monitor: m, now, disabled, busy, onDetail, onPause, onEdit, onArchive }: { monitor: Monitor; now: number; disabled: boolean; busy: boolean; onDetail: () => void; onPause: () => void; onEdit: () => void; onArchive: () => void }) {
  const freshness = currentFreshness(m, now);
  return <tr><td data-label="Endpoint"><button className="link monitor-name" onClick={onDetail} disabled={disabled} aria-label={`Ver histórico de ${m.name}`}>{m.name}</button><span className="endpoint-url" title={m.url}>{m.url}</span><small>GET · a cada {m.interval_seconds}s</small></td>
    <td data-label="Dados"><span className={`badge ${freshness}`}>{freshnessLabels[freshness]}</span></td>
    <td data-label="Última saúde"><span className={m.health_status ? `health ${m.health_status}` : 'quiet'}>{m.health_status ? healthLabels[m.health_status] : 'Não avaliada'}</span>{freshness !== 'fresh' && m.health_status && <small>Leitura histórica</small>}</td>
    <td data-label="Último check">{m.last_checked_at ? <><time dateTime={m.last_checked_at}>{new Date(m.last_checked_at).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</time><small>{m.last_http_status === null ? 'Sem resposta HTTP' : `HTTP ${m.last_http_status}`}{m.last_latency_ms === null ? '' : ` · ${Math.round(m.last_latency_ms)} ms`}</small></> : <><span className="quiet">Nenhum check</span><small>{freshness === 'paused' ? 'Retome para permitir a primeira medição.' : 'Aguardando a primeira medição.'}</small></>}</td>
    <td data-label="Ações"><div className="row-actions"><button disabled={disabled} onClick={onPause} aria-label={`${freshness === 'paused' ? 'Retomar' : 'Pausar'} ${m.name}`}>{busy ? 'Aguarde…' : freshness === 'paused' ? 'Retomar' : 'Pausar'}</button><button disabled={disabled} onClick={onEdit} aria-label={`Editar ${m.name}`}>Editar</button><button className="danger-text" disabled={disabled} onClick={onArchive} aria-label={`Arquivar ${m.name}`}>Arquivar</button></div></td>
  </tr>;
}
