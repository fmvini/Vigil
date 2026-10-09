export const POLICY_VERSION = '2026-10-09';

export const LEGAL_CONTACT: { name: string; email: string | null } = {
  name: 'Responsável pelo Vigil — identificação pendente',
  email: null,
};

export interface PolicySection {
  id: string;
  title: string;
  paragraphs: string[];
  bullets?: string[];
}

export interface PolicyDocument {
  title: string;
  sections: PolicySection[];
}

export const policies: Record<'privacy' | 'terms' | 'cookies', PolicyDocument> = {
  privacy: {
    title: 'Política de Privacidade',
    sections: [
      {
        id: 'sobre', title: 'Sobre esta política',
        paragraphs: [
          'Esta política explica como o Vigil trata os dados necessários para criar contas, administrar projetos e monitorar serviços HTTP. Ela se aplica ao site, à API e às verificações executadas para os monitores cadastrados.',
          'A confirmação desta política no cadastro e no login registra sua ciência das práticas descritas. Ela não autoriza publicidade, rastreamento ou tratamento de dados para finalidades adicionais.',
        ],
      },
      {
        id: 'dados', title: 'Dados que utilizamos',
        paragraphs: ['Utilizamos os dados fornecidos por você e os registros gerados pelo funcionamento do serviço:'],
        bullets: [
          'Conta: e-mail, identificador e datas de criação/atualização. A senha é recebida para autenticação e armazenada como hash, não em texto legível.',
          'Projetos e monitores: nomes, descrições, URLs de endpoints, configurações de verificações, opções de publicação e registros de pausa ou arquivamento.',
          'Monitoramento: horários, códigos HTTP, latência, tentativas, estado observado, incidentes e falhas de processamento. O executor não lê nem armazena o corpo das respostas dos endpoints.',
          'Sessões: identificadores de autenticação, proteção CSRF, expiração e revogação. O registro de sessão armazena um hash do token de autenticação.',
          'Aceites: conta associada, versões dos termos e da política, data e operação de cadastro ou login. Esse registro não inclui IP nem identificação do navegador.',
          'Preferências no navegador: tema e escolha no aviso de cookies. Provedores de infraestrutura podem processar dados de conexão e registros técnicos para disponibilizar e proteger seus serviços.',
        ],
      },
      {
        id: 'finalidades', title: 'Finalidades e fundamentos do tratamento',
        paragraphs: [
          'Os dados de conta, sessão e monitoramento são utilizados para prestar o serviço solicitado, autenticar usuários, separar os dados de cada conta e apresentar resultados. O tratamento necessário a essas funções está ligado à execução do serviço contratado.',
          'Registros de aceites e informações necessárias ao cumprimento de obrigações ou ao exercício regular de direitos podem ser conservados para essas finalidades. Medidas de segurança e prevenção de abuso devem se limitar ao necessário, respeitando os direitos dos titulares.',
          'Esta versão não inclui analytics, anúncios ou cookies de marketing. Uma nova finalidade que dependa de consentimento deverá ser apresentada de forma específica antes de sua ativação.',
        ],
      },
      {
        id: 'publicacao', title: 'O que pode ficar público',
        paragraphs: [
          'Projetos e monitores são privados por padrão. Ao publicar uma página de status e marcar monitores como públicos, você torna acessíveis os nomes publicados, saúde observada, qualidade e horários das leituras, além do resumo de incidentes públicos.',
          'A página pública não divulga o e-mail da conta, URLs dos endpoints, descrições privadas, configurações ou detalhes técnicos das tentativas. Ainda assim, escolha nomes que não revelem dados pessoais ou informações confidenciais.',
          'A demonstração utiliza exemplos fictícios em memória. Editar ou simular resultados na demonstração não envia esses dados ao banco nem executa requisições aos endpoints. Recarregar restaura os exemplos.',
        ],
      },
      {
        id: 'infraestrutura', title: 'Infraestrutura e compartilhamento',
        paragraphs: [
          'Na instância online, o Render hospeda o site e a API; o Neon fornece o banco de dados; o GitHub Actions executa as verificações; e o Cloudflare agenda os disparos do executor. Esses fornecedores participam do funcionamento técnico conforme suas funções. O agendador Cloudflare não recebe credenciais do banco nem URLs dos monitores.',
          'As verificações encaminham uma requisição HTTP ao endpoint que você cadastrou. O operador desse endpoint pode registrar o acesso do executor conforme suas próprias práticas.',
          'O uso de infraestrutura de terceiros pode envolver processamento fora do Brasil, conforme a localização dos serviços. Informações necessárias também podem ser fornecidas em atendimento a obrigações legais ou determinações de autoridades competentes. O Vigil não utiliza os dados da conta para venda ou publicidade nesta versão.',
        ],
      },
      {
        id: 'retencao', title: 'Armazenamento e conservação',
        paragraphs: [
          'A rotina de retenção elimina histórico de verificações e jobs encerrados antigos após o limite operacional de 30 dias e incidentes encerrados após 90 dias. Incidentes abertos continuam armazenados; suas referências a verificações antigas podem ser removidas durante a limpeza. A limpeza depende da execução da rotina e esses limites não garantem eliminação imediata de todas as cópias.',
          'A sessão de autenticação tem duração máxima de sete dias e pode terminar antes por inatividade, revogação ou saída da conta. Registros de sessões encerradas são tratados pela rotina de retenção.',
          'Arquivar um projeto ou monitor interrompe sua utilização ativa, mas não equivale a excluir a conta nem a eliminar todo o histórico. Contas, configurações e registros de aceites não possuem exclusão automática por prazo nesta versão. Solicitações de eliminação devem considerar a finalidade restante, obrigações aplicáveis e referências que precisam ser preservadas; o responsável deve definir e informar os prazos de conservação antes da publicação definitiva desta política.',
        ],
      },
      {
        id: 'seguranca', title: 'Segurança e cuidados com endpoints',
        paragraphs: [
          'A instância online utiliza HTTPS, cookies de sessão com proteção HttpOnly, Secure e SameSite, proteção CSRF e controles de acesso por conta. Nenhuma medida elimina todos os riscos; proteja sua senha e encerre a sessão em dispositivos compartilhados.',
          'Não cadastre senhas, tokens, dados pessoais sensíveis ou outros segredos em URLs, nomes ou descrições. Monitore somente serviços para os quais você tem autorização.',
        ],
      },
      {
        id: 'direitos', title: 'Seus direitos e contato',
        paragraphs: [
          'Você pode solicitar confirmação e acesso aos dados, correção, informações sobre compartilhamento e, nas situações aplicáveis, portabilidade, anonimização, bloqueio, eliminação e revogação de consentimento. Pode também questionar tratamentos em desacordo com a legislação e apresentar pedido à autoridade de proteção de dados. Solicitações podem exigir verificação de identidade para proteger a conta.',
          'A identificação do responsável e o canal de atendimento de privacidade ainda não foram informados para esta versão. Esses dados precisam ser preenchidos antes de sua publicação definitiva. Não envie senhas ou dados pessoais em comentários públicos do repositório.',
        ],
      },
      {
        id: 'alteracoes', title: 'Atualizações',
        paragraphs: ['A versão aparece nesta página e é registrada no cadastro e no login. Mudanças nas práticas de tratamento devem ser refletidas nesta política e identificadas em uma nova versão. A ciência desta política não substitui consentimentos específicos quando eles forem necessários.'],
      },
    ],
  },
  terms: {
    title: 'Termos de Uso',
    sections: [
      {
        id: 'servico', title: 'O serviço Vigil',
        paragraphs: [
          'O Vigil permite organizar projetos, configurar monitores de endpoints HTTP e consultar resultados, métricas e incidentes. Para criar uma conta ou entrar, você deve aceitar estes termos e confirmar a leitura da Política de Privacidade. Se não concordar, não conclua o cadastro ou login; as políticas e a demonstração permanecem disponíveis sem conta.',
          'A demonstração usa dados fictícios. As alterações realizadas nela ficam em memória no navegador e não representam verificações de serviços reais.',
        ],
      },
      {
        id: 'conta', title: 'Sua conta e suas responsabilidades',
        paragraphs: [
          'Forneça um e-mail que você esteja autorizado a utilizar, mantenha suas credenciais protegidas e utilize o serviço de acordo com a legislação. Quem representa uma organização deve ter autorização para cadastrar os serviços dela.',
          'Você responde pelas URLs e informações que cadastra e pela decisão de tornar nomes e status públicos. Não inclua segredos, tokens, dados pessoais sensíveis ou conteúdo confidencial nesses campos.',
        ],
      },
      {
        id: 'uso', title: 'Uso permitido',
        paragraphs: ['Cadastre somente endpoints para os quais tenha autorização de monitoramento e respeite a capacidade e as regras do serviço de destino. É proibido:'],
        bullets: [
          'Usar o Vigil para invasão, exploração de vulnerabilidades, varredura não autorizada, sobrecarga ou ataques.',
          'Tentar contornar limites, controles de rede, proteção de contas ou isolamento dos dados.',
          'Inserir conteúdo ilícito, violar direitos de terceiros ou compartilhar credenciais de outras pessoas sem autorização.',
        ],
      },
      {
        id: 'limites', title: 'Leituras, frequência e limitações',
        paragraphs: [
          'Os resultados descrevem o que foi observado em cada verificação. Ausência de dados, pausa ou leituras antigas não confirmam disponibilidade; uma leitura bem-sucedida também não garante funcionamento contínuo.',
          'O perfil gratuito tem verificações agendadas e depende de infraestrutura externa. Podem ocorrer atrasos de horas, interrupções ou rodadas não executadas. O intervalo configurado não é uma promessa de prazo nem um SLA. Atualizar a página consulta os resultados salvos e não dispara uma verificação.',
          'O Vigil não substitui monitoramento crítico, controles próprios de segurança, backups ou procedimentos de resposta a incidentes. Avalie essas limitações antes de depender do serviço para suas operações.',
        ],
      },
      {
        id: 'dados', title: 'Dados, publicação e encerramento',
        paragraphs: [
          'O tratamento de dados segue a Política de Privacidade. A publicação de uma página de status é opcional; revise o que ficará público antes de ativá-la.',
          'Você pode pausar ou arquivar monitores e arquivar projetos pela interface. Arquivamento não equivale a eliminação da conta ou de todo o histórico. A interface ainda não oferece exclusão de conta; pedidos devem ser tratados pelo canal de atendimento do responsável, cuja identificação está pendente nesta versão.',
          'O responsável pode restringir utilização abusiva ou incompatível com estes termos, observadas a legislação aplicável e as circunstâncias. Os termos não afastam direitos legais do usuário nem responsabilidades que não possam ser limitadas por contrato.',
        ],
      },
      {
        id: 'versao', title: 'Versão e atendimento',
        paragraphs: [
          'Registramos a versão aceita, a data e a operação de cadastro ou login junto à conta. Alterações nestes termos devem ser informadas por uma nova versão, cuja aceitação será exigida em novo cadastro ou login.',
          'A identificação do responsável e o contato de atendimento precisam ser preenchidos antes da publicação definitiva destes termos. Estes documentos não estabelecem renúncia genérica a direitos nem autorização para tratamento adicional de dados.',
        ],
      },
    ],
  },
  cookies: {
    title: 'Política de Cookies',
    sections: [
      {
        id: 'tecnologias', title: 'Cookies e armazenamento local',
        paragraphs: [
          'Cookies são pequenos registros enviados pelo servidor e guardados pelo navegador. O armazenamento local (localStorage) é outra tecnologia do navegador, utilizada pelo Vigil para lembrar escolhas de interface. Esta política descreve ambos.',
          'Nesta versão, o Vigil não inclui cookies de publicidade, analytics ou rastreamento de comportamento. O aviso não ativa ferramentas de terceiros nem muda a finalidade dos cookies necessários à autenticação.',
        ],
      },
      {
        id: 'sessao', title: 'Cookie necessário de sessão',
        paragraphs: [
          'Na instância online, o cookie __Host-vigil_session mantém a autenticação. Ele é restrito à origem do site, possui proteção HttpOnly e Secure, usa SameSite=Lax e pode durar até sete dias. A sessão pode terminar antes por inatividade ou revogação; sair da conta remove o cookie.',
          'No ambiente local de desenvolvimento, o nome é vigil_session e a configuração é adaptada ao HTTP local. Não criamos uma sessão autenticada para visitar as políticas, a página 404 ou a demonstração.',
          'Você pode continuar sem aceitar o aviso. O cookie estritamente necessário ainda será usado se decidir entrar na conta. Bloqueá-lo nas configurações do navegador impede a manutenção do login.',
        ],
      },
      {
        id: 'preferencias', title: 'Preferências guardadas no navegador',
        paragraphs: [
          'A chave vigil.theme lembra o tema escolhido (Claro, Escuro ou Sistema) até você alterá-lo ou limpar os dados do site. A preferência do aviso de cookies guarda a decisão, a versão e o horário no próprio navegador, por até 180 dias.',
          'Essas preferências não são enviadas à API como dados de monitoramento. Se o navegador impedir seu armazenamento, a escolha permanece apenas na página atual e pode ser solicitada novamente ao recarregar.',
        ],
      },
      {
        id: 'escolha', title: 'Aceitar, recusar e revisar sua escolha',
        paragraphs: [
          'No aviso, “Aceitar cookies” registra sua concordância com as práticas descritas. “Continuar sem aceitar” registra a recusa; ambas as opções mantêm somente as tecnologias necessárias e as preferências explicitamente escolhidas, pois não existem categorias opcionais nesta versão.',
          'O controle “Preferências de cookies” no rodapé permite reabrir o aviso e mudar a decisão. Uma nova versão desta política, uma escolha expirada ou a limpeza do armazenamento pode fazer o aviso aparecer novamente.',
          'Nenhuma escolha no aviso substitui a aceitação dos Termos de Uso e a ciência da Política de Privacidade exigidas para cadastro ou login. Se cookies opcionais forem adicionados no futuro, deverão ter informação e escolha específicas antes da ativação.',
        ],
      },
      {
        id: 'terceiros', title: 'Infraestrutura, links e contato',
        paragraphs: [
          'Render, Neon, GitHub e Cloudflare participam da infraestrutura conforme descrito na Política de Privacidade. Links externos e endpoints de terceiros têm práticas próprias. O Vigil não controla cookies de outros sites que você visite.',
          'A identificação do responsável e o canal para dúvidas de privacidade e cookies ainda precisam ser preenchidos antes da publicação definitiva desta política.',
        ],
      },
    ],
  },
};
