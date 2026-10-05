# Marca Vigil

Olho geométrico de observação, em verde profundo do produto (`#145c43`). O símbolo
permanece estático e não representa o estado ou a saúde de um monitor.

- `vigil-eye.svg`: símbolo vetorial, fundo transparente.
- `vigil-logo.svg`: símbolo + nome em Public Sans Bold, com letras convertidas em
  contornos; funciona sem instalar fontes ou fazer requisições externas.
- `vigil-logo.png`: versão de 1024px da logo, com fundo transparente.
- `../favicon.svg`: versão em negativo sobre verde, ajustada para 16/32px.
- `../favicon.ico`: fallback com representações de 16 e 32px.
- `../apple-touch-icon.png`: versão de 180px para favoritos na tela inicial.

Na aplicação, `src/Brand.tsx` combina o símbolo decorativo com o nome textual
acessível. Login, dashboard, abertura de sessão e status pública compartilham a
mesma marca; os links conservam seus destinos. Não usar a pupila como indicador
de atividade nem animá-la conforme saúde.

Símbolo desenhado para este projeto. Lettering derivado da Public Sans 700 já
instalada no frontend; licença dos autores em `PUBLIC-SANS-LICENSE.txt`. PNGs e
ICO são renderizações dos SVGs, não imagens geradas por IA. Nenhuma dependência
nova é necessária para servir os assets.
