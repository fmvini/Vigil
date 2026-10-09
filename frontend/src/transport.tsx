import { createContext, useContext, type ReactNode } from 'react';
import { api, type ApiClient } from './api';

const Transport = createContext({ client: api, demo: false });
export function TransportProvider({ client, children }: { client: ApiClient; children: ReactNode }) {
  return <Transport.Provider value={{ client, demo: true }}>{children}</Transport.Provider>;
}
export function useTransport() { return useContext(Transport); }
export function useApi() { return useTransport().client; }
