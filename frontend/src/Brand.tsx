const content = <>
  <img className="brand-eye" src="/brand/vigil-eye.svg" width="36" height="36" alt="" aria-hidden="true" />
  <span>vigil</span>
</>;

export function Brand({ href }: { href?: string }) {
  return href ? <a className="brand" href={href}>{content}</a> : <span className="brand">{content}</span>;
}
