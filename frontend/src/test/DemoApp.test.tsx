import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from '../App';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); window.history.replaceState({}, '', '/'); });
function isolated() {
  const fetch = vi.fn(() => { throw new Error('REAL_API_FORBIDDEN'); });
  const source = vi.fn(() => { throw new Error('REAL_SSE_FORBIDDEN'); });
  vi.stubGlobal('fetch', fetch); vi.stubGlobal('EventSource', source);
  vi.stubGlobal('scrollTo', vi.fn());
  return { fetch, source };
}
it('abre demo antes da autenticação e preserva estado na status pública e no retorno', async () => {
  const { fetch, source } = isolated(); const cookies = document.cookie;
  window.history.replaceState({}, '', '/demo'); render(<App />);
  await screen.findByRole('heading', { name: 'Loja Horizonte' });
  fireEvent.click(screen.getByRole('button', { name: 'Novo' }));
  fireEvent.change(screen.getByLabelText('Nome do projeto'), { target: { value: 'Projeto do visitante' } });
  fireEvent.click(screen.getByLabelText('Publicar página de status'));
  fireEvent.click(screen.getByRole('button', { name: 'Salvar projeto' }));
  await screen.findByRole('heading', { name: 'Projeto do visitante' });
  fireEvent.click(screen.getByRole('link', { name: 'Abrir página pública' }));
  await screen.findByText('Nenhum monitor foi publicado neste projeto.');
  expect(window.location.pathname).toMatch(/^\/demo\/status\//);
  fireEvent.click(screen.getByRole('link', { name: 'Pular para o conteúdo' }));
  expect(screen.queryByText('Página de demonstração não encontrada')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('link', { name: /vigil/i }));
  await screen.findByRole('button', { name: 'Projeto do visitante' });
  fireEvent.click(screen.getByRole('button', { name: 'Restaurar demonstração' }));
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Projeto do visitante' })).not.toBeInTheDocument());
  expect(fetch).not.toHaveBeenCalled(); expect(source).not.toHaveBeenCalled(); expect(document.cookie).toBe(cookies);
});
it.each(['/demo/status/vigil-demo', '/demo/status/desconhecida', '/demo/unknown'])('resolve %s sem fallback de rede', async path => {
  const { fetch, source } = isolated();
  window.history.replaceState({}, '', path); render(<App />);
  if (path.endsWith('vigil-demo')) await screen.findByRole('heading', { name: 'Loja Horizonte' });
  else await screen.findByRole('heading', { name: path.endsWith('unknown') ? '404 · Página não encontrada' : 'Página não publicada' });
  expect(fetch).not.toHaveBeenCalled(); expect(source).not.toHaveBeenCalled();
});
