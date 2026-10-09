import { scheduledCadence, useRuntimeConfig } from './runtimeConfig';
import { useTransport } from './transport';

// Deployment timing describes the executor's schedule, never a measured result.
export function CheckTiming() {
  const runtime = useRuntimeConfig();
  const { demo } = useTransport();
  if (demo) return <aside className="check-timing" aria-label="Execução das verificações"><p>As leituras desta demonstração são fictícias. Use <strong>Simular verificação</strong> no painel para acrescentar resultados em memória; nenhum endpoint é acessado.</p></aside>;
  return <aside className="check-timing" aria-label="Execução das verificações">
    {runtime.loading ? <p className="quiet">Consultando a agenda de verificações…</p>
      : runtime.failed ? <><p>Não foi possível consultar a agenda de verificações.</p><button className="link" onClick={runtime.retry}>Consultar agenda novamente</button></>
      : runtime.data?.scheduled_checks_interval_seconds != null ? <>
        <p><strong>Verificações agendadas</strong> · agenda configurada a cada {scheduledCadence(runtime.data.scheduled_checks_interval_seconds)}.</p>
        <p>A execução pode atrasar por horas. Esse intervalo não garante o prazo da primeira medição nem das seguintes.</p>
      </> : null}
    <p className="quiet">A página consulta os dados a cada 30 segundos. Atualizar consulta os resultados salvos; não inicia uma verificação do endpoint. Sem dados, a saúde ainda não foi avaliada.</p>
  </aside>;
}
