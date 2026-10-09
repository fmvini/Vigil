import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Brand } from './Brand';
import { ThemeControl } from './ThemeControl';
import { LEGAL_CONTACT, policies, POLICY_VERSION } from './legalContent';
import { COOKIE_PREFERENCE_KEY, createCookiePreference, parseCookiePreference, readCookiePreference, type CookieChoice } from './cookiePreference';

export type PolicyKey = keyof typeof policies;
const policyLinks = [
  ['privacy', 'Privacidade'], ['terms', 'Termos de Uso'], ['cookies', 'Cookies'],
] as const;

export function PolicyPage({ policy }: { policy: PolicyKey }) {
  const content = policies[policy];
  useEffect(() => { const previous = document.title; document.title = `${content.title} | Vigil`; return () => { document.title = previous; }; }, [content.title]);
  return <div className="legal-page">
    <a className="skip-link" href="#policy-main">Pular para o conteúdo</a>
    <header className="legal-header"><Brand href="/" /><ThemeControl /></header>
    <main id="policy-main" tabIndex={-1}>
      <h1>{content.title}</h1>
      <p className="quiet">Versão de <time dateTime={POLICY_VERSION}>{POLICY_VERSION.split('-').reverse().join('/')}</time></p>
      <nav className="policy-nav" aria-label="Políticas do Vigil">{policyLinks.map(([key, title]) => <a key={key} href={`/${key}`} aria-current={key === policy ? 'page' : undefined}>{title}</a>)}</nav>
      <nav className="policy-index" aria-label="Nesta política"><h2>Nesta página</h2><ul>{content.sections.map(section => <li key={section.id}><a href={`#${section.id}`}>{section.title}</a></li>)}</ul></nav>
      <article className="policy-content" aria-label={content.title}>{content.sections.map(section => <section key={section.id} id={section.id} aria-labelledby={`title-${section.id}`}>
        <h2 id={`title-${section.id}`}>{section.title}</h2>
        {section.paragraphs.map((paragraph, i) => <p key={i}>{paragraph}</p>)}
        {section.bullets && <ul>{section.bullets.map((bullet, i) => <li key={i}>{bullet}</li>)}</ul>}
      </section>)}
        <section aria-labelledby="legal-contact-title"><h2 id="legal-contact-title">Contato</h2><p>{LEGAL_CONTACT.name}</p>{LEGAL_CONTACT.email ? <p><a href={`mailto:${LEGAL_CONTACT.email}`}>{LEGAL_CONTACT.email}</a></p> : <p className="quiet">O canal de contato ainda não foi informado.</p>}</section>
      </article>
      <a className="legal-return" href="/">Voltar ao Vigil</a>
    </main>
  </div>;
}

export function NotFound({ demo = false }: { demo?: boolean }) {
  useEffect(() => { const previous = document.title; document.title = '404 · Página não encontrada | Vigil'; return () => { document.title = previous; }; }, []);
  return <div className="legal-page not-found-page">
    <a className="skip-link" href="#not-found-main">Pular para o conteúdo</a>
    <header className="legal-header"><Brand href={demo ? '/demo' : '/'} /><ThemeControl /></header>
    <main id="not-found-main" tabIndex={-1}>
      <h1>404 · Página não encontrada</h1>
      <p>{demo ? 'Este endereço não existe na demonstração. Os exemplos continuam disponíveis.' : 'Este endereço não existe ou a página foi removida. Você pode voltar ao início para continuar.'}</p>
      <a className="legal-return" href={demo ? '/demo' : '/'}>{demo ? 'Voltar à demonstração' : 'Voltar ao início'}</a>
    </main>
  </div>;
}

export function LegalShell({ children }: { children: ReactNode }) {
  const [preference, setPreference] = useState(readCookiePreference);
  const [reopened, setReopened] = useState(false);
  const [temporary, setTemporary] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const visible = reopened || !preference;
  useEffect(() => {
    const change = (event: StorageEvent) => {
      if (event.key !== COOKIE_PREFERENCE_KEY && event.key !== null) return;
      try { if (event.storageArea && event.storageArea !== window.localStorage) return; } catch { return; }
      setPreference(parseCookiePreference(event.newValue)); setReopened(false); setTemporary(false);
    };
    window.addEventListener('storage', change);
    return () => window.removeEventListener('storage', change);
  }, []);
  useEffect(() => {
    if (!preference) return;
    // Browser timeouts are signed 32-bit; a long preference needs several waits.
    const delay = Math.min(Date.parse(preference.expires_at) - Date.now(), 2_147_483_647);
    const timer = window.setTimeout(() => setPreference(current => parseCookiePreference(JSON.stringify(current))), Math.max(0, delay));
    return () => window.clearTimeout(timer);
  }, [preference]);
  useEffect(() => { if (reopened) heading.current?.focus(); }, [reopened]);
  function choose(choice: CookieChoice) {
    const value = createCookiePreference(choice);
    let saved = true;
    try { window.localStorage.setItem(COOKIE_PREFERENCE_KEY, JSON.stringify(value)); } catch { saved = false; }
    setPreference(value); setTemporary(!saved); setReopened(false);
    trigger.current?.focus({ preventScroll: true });
  }
  return <div className="legal-shell">
    <div className="legal-surface">{children}</div>
    <footer className="legal-footer">
      <nav aria-label="Informações legais">{policyLinks.map(([key, title]) => <a key={key} href={`/${key}`} target="_blank" rel="noopener noreferrer">{title}<span className="sr-only"> (abre em nova aba)</span></a>)}<button ref={trigger} className="link" type="button" aria-expanded={visible} aria-controls={visible ? 'cookie-preferences' : undefined} onClick={() => setReopened(true)}>Preferências de cookies</button></nav>
      {temporary && <p role="status" className="quiet">Não foi possível salvar neste navegador. Sua escolha será mantida enquanto esta página estiver aberta.</p>}
    </footer>
    {visible && <section id="cookie-preferences" className="cookie-banner" aria-labelledby="cookie-title" aria-describedby="cookie-description">
      <div className="cookie-copy"><h2 id="cookie-title" ref={heading} tabIndex={-1}>Cookies e preferências</h2><p id="cookie-description">Usamos somente cookies de sessão necessários ao acesso e armazenamento de preferências neste navegador. Não usamos analytics nem cookies de marketing. Você pode continuar sem aceitar; os cookies de sessão necessários permanecem para entrar na conta.</p><a href="/cookies" target="_blank" rel="noopener noreferrer">Ler a Política de Cookies<span className="sr-only"> (abre em nova aba)</span></a></div>
      <div className="cookie-actions"><button type="button" onClick={() => choose('accepted')}>Aceitar cookies</button><button type="button" onClick={() => choose('refused')}>Continuar sem aceitar</button></div>
    </section>}
  </div>;
}
