import { POLICY_VERSION } from '../src/legalContent.ts';

export const legalVersions = { terms_version: POLICY_VERSION, privacy_version: POLICY_VERSION };
export async function acceptLegal(page) {
  await page.getByRole('checkbox', { name: /Política de Privacidade/ }).check();
  await page.getByRole('checkbox', { name: /Termos de Uso/ }).check();
}
