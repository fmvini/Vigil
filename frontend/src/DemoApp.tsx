import { useEffect, useRef, useState, type MouseEvent } from 'react';
import { Dashboard } from './App';
import { PublicStatus } from './Observations';
import { DemoClient } from './demo';
import { TransportProvider, useApi } from './transport';
import { errorMessage } from './api';
import { Alert } from './Forms';
import type { Monitor } from './types';
import { NotFound } from './Legal';

const displayIdentity = { user: { id: 'demo-visitor', email: 'Visitante da demonstração' }, csrf_token: '' };
export function DemoApp() {
  const [client] = useState(() => new DemoClient());
  const [route, setRoute] = useState(window.location.pathname);
  const [revision, setRevision] = useState(0);
  const [notice, setNotice] = useState('');
  const banner = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const update = () => banner.current?.parentElement?.style.setProperty('--demo-banner-offset', `${(banner.current?.getBoundingClientRect().height ?? 0) + 16}px`);
    update();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update);
    if (banner.current) observer?.observe(banner.current);
    window.addEventListener('resize', update);
    return () => { observer?.disconnect(); window.removeEventListener('resize', update); };
  }, []);
  useEffect(() => { const change = () => setRoute(window.location.pathname); window.addEventListener('popstate', change); return () => window.removeEventListener('popstate', change); }, []);
  function navigate(path: string) { window.history.pushState({}, '', path); setRoute(new URL(path, window.location.origin).pathname); window.scrollTo(0, 0); }
  function internal(event: MouseEvent<HTMLDivElement>) {
    const link = (event.target as Element).closest('a');
    if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || link.target === '_blank') return;
    const url = new URL(link.href, window.location.origin);
    if (url.origin === window.location.origin && /^\/demo(?:\/|$)/.test(url.pathname)) {
      if (url.pathname === window.location.pathname && url.hash) return;
      event.preventDefault(); navigate(url.pathname + url.search + url.hash);
    }
  }
  const status = route.match(/^\/demo\/status\/([^/]+)\/?$/);
  let slug = status?.[1] ?? '';
  try { slug = decodeURIComponent(slug); } catch { slug = ''; }
  return <TransportProvider client={client}><div className="demo-shell" onClick={internal}>
    <div ref={banner} className="demo-banner" role="region" aria-label="Modo demonstração">
      <div><strong>Demonstração · dados fictícios</strong><p>Explore e edite livremente. Alterações vivem nesta aba; recarregar ou compartilhar o link restaura os exemplos.</p></div>
      <div className="button-group"><button onClick={() => { client.reset(); setRevision(n => n + 1); navigate('/demo'); setNotice('Demonstração restaurada com os exemplos iniciais.'); }}>Restaurar demonstração</button><a href="/">Sair da demonstração</a></div>
      {notice && <p className="demo-notice" role="status">{notice}</p>}
    </div>
    <div key={revision}>{route === '/demo' || route === '/demo/' ? <Dashboard session={displayIdentity} onLogout={() => window.location.assign('/')} />
      : status && slug ? <PublicStatus key={slug} slug={slug} />
      : <NotFound demo />}</div>
  </div></TransportProvider>;
}

export function DemoSimulation({ monitors, onSaved, disabled }: { monitors: Monitor[]; onSaved: (monitor: Monitor) => void; disabled: boolean }) {
  const api = useApi();
  const [id, setId] = useState('');
  const [scenario, setScenario] = useState('success');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const selected = monitors.find(m => m.id === id) ?? monitors[0];
  async function simulate() {
    if (!selected) return; setBusy(true); setError(''); setNotice('');
    try { const updated = await api.request<Monitor>(`/demo/monitors/${selected.id}/simulate`, 'POST', { scenario }); onSaved(updated); setNotice(`Verificação fictícia de ${updated.name} adicionada. Nenhum endpoint foi acessado.`); }
    catch (error) { setError(errorMessage(error)); } finally { setBusy(false); }
  }
  return <section className="demo-simulation" aria-labelledby="demo-simulation-title"><h2 id="demo-simulation-title">Simule uma verificação</h2><p>Escolha um resultado fictício para ver métricas, histórico e incidentes reagirem. Falhas consecutivas seguem o limiar configurado.</p>
    <div className="demo-simulation-controls"><label htmlFor="demo-monitor">Monitor da simulação<select id="demo-monitor" value={selected?.id ?? ''} onChange={e => { setId(e.target.value); setNotice(''); }} disabled={disabled || busy || !selected}>{!selected && <option value="">Crie um monitor para simular</option>}{monitors.map(m => <option key={m.id} value={m.id}>{m.name}{m.paused_at ? ' (pausado)' : ''}</option>)}</select></label>
      <label htmlFor="demo-result">Resultado fictício<select id="demo-result" value={scenario} onChange={e => setScenario(e.target.value)} disabled={disabled || busy}><option value="success">Resposta esperada</option><option value="slow">Latência no limiar</option><option value="retry">Sucesso após tentativa extra</option><option value="failure">Falha HTTP</option></select></label>
      <button className="primary" disabled={disabled || busy || !selected || Boolean(selected.paused_at)} onClick={simulate}>{busy ? 'Simulando…' : 'Simular verificação'}</button>
    </div>{selected?.paused_at && <p className="quiet">Retome este monitor para permitir a simulação.</p>}{error && <Alert message={error} />}{notice && <p className="success" role="status">{notice}</p>}
  </section>;
}
