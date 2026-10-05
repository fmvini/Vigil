import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { AuthForm } from '../Forms';
import { json } from './fixtures';

afterEach(() => vi.unstubAllGlobals());
it('login mostra invalid_credentials em português sem distinguir usuário de senha ou ecoar dados', async () => {
  const onSession = vi.fn();
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ error: { code: 'invalid_credentials', message: 'Invalid email or password', details: { email: 'private@example.com', token: 'PRIVATE_TOKEN' } } }, 401)));
  render(<AuthForm notice="" onSession={onSession} />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('E-mail'), 'tester@example.com');
  await user.type(screen.getByLabelText('Senha'), 'incorrect');
  await user.click(screen.getByRole('button', { name: 'Entrar' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('E-mail ou senha inválidos. Confira os dados e tente novamente.');
  expect(screen.getByRole('alert')).not.toHaveTextContent(/Invalid email|private@example.com|PRIVATE_TOKEN|incorrect/);
  expect(screen.getByRole('button', { name: 'Entrar' })).toBeEnabled();
  expect(onSession).not.toHaveBeenCalled();
});
