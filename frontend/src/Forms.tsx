import { useState, type FormEvent } from 'react';
import { useApi, useTransport } from './transport';
import { isDemoUrl } from './demo';
import { Brand } from './Brand';
import { ThemeControl } from './ThemeControl';
import { errorMessage } from './api';
import { defaultConfig, validateMonitor } from './domain';
import { intervalHelp, useRuntimeConfig, type RuntimeConfig } from './runtimeConfig';
import type { Monitor, MonitorConfig, Project, Session, User } from './types';
import { POLICY_VERSION } from './legalContent';

export function Alert({ message }: { message: string }) {
  return <div className="alert" role="alert">{message}</div>;
}

export function AuthForm({ onSession, notice }: { onSession: (session: Session) => void; notice: string }) {
  const api = useApi();
  const [register, setRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [busy, setBusy] = useState(false);
  const [privacyAccepted, setPrivacyAccepted] = useState(false);
  const [termsAccepted, setTermsAccepted] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setSuccess('');
    if (!privacyAccepted || !termsAccepted) { setError('Leia e aceite separadamente a Política de Privacidade e os Termos de Uso para continuar.'); return; }
    if (busy) return;
    setBusy(true);
    const credentials = { email: email.trim(), password, terms_version: POLICY_VERSION, privacy_version: POLICY_VERSION };
    try {
      if (register) {
        await api.request<User>('/auth/register', 'POST', credentials);
        setPrivacyAccepted(false); setTermsAccepted(false);
        setRegister(false); setPassword(''); setSuccess('Conta criada. Entre com seu e-mail e senha.');
      } else {
        const session = await api.request<Session>('/auth/login', 'POST', credentials);
        api.setCsrfToken(session.csrf_token); onSession(session);
      }
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  return <main className="auth-page">
    <div className="auth-story"><div className="auth-header"><Brand href="#auth-form" /><ThemeControl /></div>
      <div><h1>Seus serviços, <br />sob observação.</h1><p>Organize endpoints em projetos e configure como cada serviço será monitorado.</p>
        <div className="auth-note">Uma leitura honesta do estado dos seus serviços. Dados ausentes ou antigos nunca significam que está tudo bem.</div>
      </div><span className="quiet">Monitoramento HTTP</span>
    </div>
    <div className="auth-content"><section className="auth-form" id="auth-form" aria-labelledby="auth-title">
      <h2 id="auth-title">{register ? 'Crie sua conta' : 'Entre no Vigil'}</h2>
      <p>{register ? 'Comece organizando seu primeiro projeto.' : 'Acesse seus projetos e monitores.'}</p>
      {notice && <Alert message={notice} />}{error && <Alert message={error} />}
      {success && <p className="success" role="status">{success}</p>}
      <form onSubmit={submit}>
        <label htmlFor="email">E-mail</label><input id="email" type="email" autoComplete="email" required maxLength={254} value={email} onChange={e => setEmail(e.target.value)} disabled={busy} />
        <label htmlFor="password">Senha</label><input id="password" type="password" autoComplete={register ? 'new-password' : 'current-password'} required minLength={register ? 10 : 1} maxLength={128} value={password} onChange={e => setPassword(e.target.value)} disabled={busy} aria-describedby={register ? 'password-help' : undefined} />
        {register && <small id="password-help">Use de 10 a 128 caracteres.</small>}
        <fieldset className="auth-consents" disabled={busy} aria-describedby="consent-help"><legend>Aceites obrigatórios</legend>
          <label className="check-label" htmlFor="privacy-accepted"><input id="privacy-accepted" type="checkbox" required checked={privacyAccepted} onChange={e => setPrivacyAccepted(e.target.checked)} /><span>Li e aceito a <a href="/privacy" target="_blank" rel="noopener noreferrer">Política de Privacidade</a>.</span></label>
          <label className="check-label" htmlFor="terms-accepted"><input id="terms-accepted" type="checkbox" required checked={termsAccepted} onChange={e => setTermsAccepted(e.target.checked)} /><span>Li e aceito os <a href="/terms" target="_blank" rel="noopener noreferrer">Termos de Uso</a>.</span></label>
          <small id="consent-help">Os links abrem em nova aba e preservam este formulário.</small>
        </fieldset>
        <button className="primary full" disabled={busy}>{busy ? 'Aguarde…' : register ? 'Criar conta' : 'Entrar'}</button>
      </form>
      <button className="link auth-switch" disabled={busy} onClick={() => { setRegister(!register); setError(''); setSuccess(''); setPassword(''); setPrivacyAccepted(false); setTermsAccepted(false); }}>{register ? 'Já tenho uma conta' : 'Criar uma conta'}</button>
      <div className="demo-entry"><a className="demo-cta" href="/demo">Visualizar demonstração</a><p className="quiet">Explore todas as funcionalidades com dados fictícios, sem criar uma conta.</p></div>
    </section></div>
  </main>;
}

interface EditorProps<T> { value?: T; onCancel: () => void; onSaved: (value: T) => void; onBusyChange: (busy: boolean) => void }

export function ProjectForm({ value, onCancel, onSaved, onBusyChange }: EditorProps<Project>) {
  const api = useApi();
  const [name, setName] = useState(value?.name ?? '');
  const [description, setDescription] = useState(value?.description ?? '');
  const [isPublic, setIsPublic] = useState(value?.public_status_enabled ?? false);
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault(); setError('');
    if (!name.trim()) { setError('Informe o nome do projeto.'); return; }
    setBusy(true); onBusyChange(true);
    try { onSaved(await api.request<Project>(value ? `/projects/${value.id}` : '/projects', value ? 'PATCH' : 'POST', { name: name.trim(), description: description.trim() || null, public_status_enabled: isPublic })); }
    catch (err) { setError(errorMessage(err)); } finally { setBusy(false); onBusyChange(false); }
  }
  return <section className="editor" aria-labelledby="project-form-title">
    <h2 id="project-form-title">{value ? 'Editar projeto' : 'Novo projeto'}</h2>
    <p>Agrupe os endpoints de uma aplicação ou ambiente.</p>{error && <Alert message={error} />}
    <form onSubmit={submit}><fieldset disabled={busy}>
      <label htmlFor="project-name">Nome do projeto</label><input id="project-name" autoFocus required maxLength={100} value={name} onChange={e => setName(e.target.value)} />
      <label htmlFor="project-description">Descrição <span className="quiet">(opcional)</span></label><textarea id="project-description" maxLength={500} rows={3} value={description} onChange={e => setDescription(e.target.value)} />
      <label className="check-label" htmlFor="project-public"><input id="project-public" type="checkbox" checked={isPublic} onChange={e => setIsPublic(e.target.checked)} />Publicar página de status</label><small>Permite acesso sem login ao nome do projeto e aos monitores marcados como públicos. URLs, configurações e descrição permanecem privadas.</small>
      <div className="form-actions"><button className="primary">{busy ? 'Salvando…' : 'Salvar projeto'}</button><button type="button" onClick={onCancel}>Cancelar</button></div>
    </fieldset></form>
  </section>;
}

const numericFields = [
  ['interval_seconds', 'Intervalo (segundos)', 60, 3600, 'Tempo entre ciclos.'],
  ['timeout_ms', 'Timeout (ms)', 1000, 15000, 'Tempo máximo por tentativa.'],
  ['expected_status', 'Status HTTP esperado', 200, 599, 'A resposta deve ter este status exato.'],
  ['failure_threshold', 'Falhas para ficar offline', 1, 10, 'Número de ciclos consecutivos com falha.'],
  ['retry_count', 'Tentativas extras', 0, 2, 'Retries por ciclo, após uma falha transitória.'],
] as const;

type MonitorEditorProps = EditorProps<Monitor> & { projectId: string };

export function MonitorForm(props: MonitorEditorProps) {
  const runtime = useRuntimeConfig();
  if (runtime.data && !runtime.loading && !runtime.failed) return <ConfiguredMonitorForm {...props} runtime={runtime.data} />;
  return <section className="editor" aria-labelledby="monitor-form-title">
    <h2 id="monitor-form-title">{props.value ? 'Editar monitor' : 'Novo monitor'}</h2>
    {runtime.failed ? <><Alert message="Não foi possível confirmar o intervalo permitido para este ambiente. Tente carregar a configuração novamente antes de salvar." /><button type="button" onClick={runtime.retry}>Carregar configuração novamente</button></> : <p role="status">Consultando o intervalo permitido para este ambiente…</p>}
    <div className="form-actions"><button type="button" onClick={props.onCancel}>Cancelar</button></div>
  </section>;
}

function ConfiguredMonitorForm({ value, projectId, onSaved, onCancel, onBusyChange, runtime }: MonitorEditorProps & { runtime: RuntimeConfig }) {
  const api = useApi();
  const { demo } = useTransport();
  const [config, setConfig] = useState<MonitorConfig>(() => value ? {
    name: value.name, url: value.url, interval_seconds: value.interval_seconds, timeout_ms: value.timeout_ms,
    expected_status: value.expected_status, failure_threshold: value.failure_threshold, retry_count: value.retry_count, latency_threshold_ms: value.latency_threshold_ms, is_public: value.is_public,
  } : { ...defaultConfig, interval_seconds: runtime.minimum_interval_seconds });
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const intervalInvalid = !Number.isSafeInteger(config.interval_seconds) || config.interval_seconds < runtime.minimum_interval_seconds || config.interval_seconds > 3600;
  const update = (key: keyof MonitorConfig, value: string | number | boolean | null) => setConfig(c => ({ ...c, [key]: value }));
  async function submit(e: FormEvent) {
    e.preventDefault(); setError('');
    const payload = { ...config, name: config.name.trim(), url: config.url.trim() };
    const validation = demo && !isDemoUrl(payload.url) ? 'Na demonstração, use uma URL fictícia terminada em .invalid.' : !payload.name ? 'Informe o nome do monitor.' : validateMonitor(payload, runtime.minimum_interval_seconds);
    if (validation) { setError(validation); return; }
    setBusy(true); onBusyChange(true);
    try { onSaved(await api.request<Monitor>(value ? `/monitors/${value.id}` : `/projects/${projectId}/monitors`, value ? 'PATCH' : 'POST', payload)); }
    catch (err) { setError(errorMessage(err)); } finally { setBusy(false); onBusyChange(false); }
  }
  return <section className="editor" aria-labelledby="monitor-form-title">
    <h2 id="monitor-form-title">{value ? 'Editar monitor' : 'Novo monitor'}</h2>
    <p>O método é GET. Alterar as regras de check reinicia a leitura de saúde.</p>{error && <Alert message={error} />}
    <form onSubmit={submit}><fieldset disabled={busy}>
      <div className="form-grid"><div><label htmlFor="monitor-name">Nome do monitor</label><input id="monitor-name" required autoFocus maxLength={100} value={config.name} onChange={e => update('name', e.target.value)} /></div>
      <div><label htmlFor="monitor-url">URL do endpoint</label><input id="monitor-url" type="url" required maxLength={2048} placeholder={demo ? "https://api.exemplo.invalid/health" : "https://api.seuservico.com/health"} value={config.url} onChange={e => update('url', e.target.value)} aria-describedby="url-help" /><small id="url-help">{demo ? 'Use um domínio fictício .invalid. Nenhuma URL será acessada.' : 'Endpoint público, sem credenciais ou secrets. Redirects não são seguidos.'}</small></div></div>
      <h3>Regras de verificação</h3><div className="form-grid rules">
        {numericFields.map(([key, label, min, max, help]) => <div key={key}><label htmlFor={key}>{label}</label><input id={key} type="number" min={key === 'interval_seconds' ? runtime.minimum_interval_seconds : min} max={max} step={1} required value={Number.isNaN(config[key]) ? '' : config[key]} onChange={e => update(key, e.target.valueAsNumber)} aria-invalid={key === 'interval_seconds' && intervalInvalid ? true : undefined} aria-describedby={`${key}-help`} /><small id={`${key}-help`}>{key === 'interval_seconds' ? <>{intervalHelp(runtime)}{intervalInvalid && ` Ajuste o intervalo para um valor inteiro de ${runtime.minimum_interval_seconds} a 3600 segundos antes de salvar.`}</> : help}</small></div>)}
        <div><label htmlFor="latency_threshold_ms">Limiar de latência (ms)</label><input id="latency_threshold_ms" type="number" min={100} max={15000} step={1} value={config.latency_threshold_ms ?? ''} onChange={e => update('latency_threshold_ms', e.target.value === '' ? null : e.target.valueAsNumber)} aria-describedby="latency-help" /><small id="latency-help">Opcional. Em branco desativa a degradação por latência.</small></div>
      </div><label className="check-label" htmlFor="monitor-public"><input id="monitor-public" type="checkbox" checked={config.is_public} onChange={e => update('is_public', e.target.checked)} />Exibir na página pública</label><small>Publica somente nome, saúde e qualidade dos dados quando a página de status do projeto estiver ativada.</small><div className="form-actions"><button className="primary" disabled={intervalInvalid}>{busy ? 'Salvando…' : 'Salvar monitor'}</button><button type="button" onClick={onCancel}>Cancelar</button></div>
    </fieldset></form>
  </section>;
}
