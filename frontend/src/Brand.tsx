const content = <>
  <svg className="brand-eye" viewBox="0 0 64 64" width="36" height="36" fill="none" aria-hidden="true">
    <path d="M5 32C12 20 21 14 32 14s20 6 27 18c-7 12-16 18-27 18S12 44 5 32Z" stroke="currentColor" strokeWidth="5" strokeLinejoin="round" />
    <circle cx="32" cy="32" r="8" fill="currentColor" />
  </svg>
  <span>vigil</span>
</>;

export function Brand({ href }: { href?: string }) {
  return href ? <a className="brand" href={href}>{content}</a> : <span className="brand">{content}</span>;
}
