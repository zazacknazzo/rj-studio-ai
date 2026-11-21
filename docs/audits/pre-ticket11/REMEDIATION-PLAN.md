# Plano de correção por dependência

Proposta revisável; **nenhuma correção ou implementação foi iniciada**. Papéis abaixo são donos propostos, não designação nominal. A auditoria não altera issue #11, roadmap, código de produção ou inteligênciaV1.

## Antes de retomar Ticket 11 offline

1. **Coordenação (AUD-03).** Responsável do projeto confirma um escritor Git, fetch/SHA/status/handoff e branch própria do Ticket 11. Adotar o procedimento já exercitado nesta auditoria; propor protocolo permanente em tarefa documental autorizada. Critério: outra conta consegue reconstruir estado e comandos sem sobrescrever progresso.
2. **Toolchain (AUD-02).** Mantenedor usa runner isolado e diretório temporário privado0700 com `--basetemp`; planeja pip/pytest corrigidos e registra resolução. O ensaio privado desta auditoria passou, mas os advisories permanecem. Critério: não executar a toolchain vulnerável em host compartilhado sem mitigação e obter revisão/execução limpa da atualização antes de CI/release.
3. **Contrato de recovery (AUD-01).** Incluir explicitamente no desenho do sender: restore não concede autorização operacional; nenhuma key nova/retentativa por ausência de marker em cópia antiga. Planejar testes dos snapshots reproduzidos e gate de quarentena. Critério: spec do Ticket 11 não promete segurança de restore que dependa só do arquivo restaurado. Isso é requisito corretivo antes do aceite do componente, não permissão para implementar T12/13.

Essas condições se aplicam antes de trabalho dependente e impedem aprovação automática. Nenhum defeito P1/P2 do caminho offline exige mudar a inteligência ou reescrever a fundação antes de escrever serialização/testes mockados. Se o escopo de Ticket 11 passar a incluir runtime/restore operacional, AUD-01 passa a bloqueá-lo até mitigação implementada e auditada.

## Grafo de dependências e aceite

| Ordem / entrega proposta | Dependências e trabalho | Responsável / ticket | Evidência de aceite | Gate |
| --- | --- | --- | --- | --- |
| A. Handoff e ambiente | AUD-02/03; exclusividade, temp privado, toolchain e manifestos | Engenharia/CI, antes T11 | Retomada em clone limpo, checks e ausência de segredo/conta real | Desenvolvimento/CI seguro |
| B. Contrato exato do sender | Fontes oficiais atuais, DTO/key/fingerprint e contrato restoreAUD-01; serialização determinística, organização/método/path/query/body | Sender, T11 offline | Spec aprovada, bytes estáveis em restart/mesma key e conflitos negados | Antes do aceite de qualquer transporte |
| C. Sender só com transporte mockado | B; zero retry interno/redirect inesperado; resposta validada, timeout/response lost→unknown, acceptance com ID/escopo | Sender, T11 | Uma chamada por autorização; testes SQLite+runner+HTTPinterceptado; 409/10036,422/10027,429/5xx,malformed/timeouts sem retry cego | AceiteT11 e auditoria independente, sem runtime |
| D. Restore em quarentena | AUD-01; inventário de snapshots/fences; procedimento/epoch externo ao snapshot ou proteção operacional equivalente | Recovery/composição/operação, T12–13 sob autorização | Restore antes de claim/marker/pause/disconnect não chama sender até reconciliação e revalidação positiva | Antes de qualquer saída operacional |
| E. Rota e observabilidade | C + CX-24/29/30; raw headers, streaming, unknown durável, commit→ACK dentro do orçamento | Ingress/composição, T12 somente com nova autorização | Testes ASGI duplicata real/chunked/lock/commit/latência/replay e sem ACK indevido | Antes de expor rota |
| F. Ativação e consentimento | D/E + CX-11/33/36; binding/sync elegíveis, revogação/opt-out e templates reais; autorização administrativa utilizável | Operação/composição, T12–13 | Workflow autenticado, E2E sintético completo e verificação positiva de conta/identidade | Antes de ativar canal |
| G. Retenção/privacidade/reconciliação | CX-01/07/08/32; erasure/WAL/backups/dedupe/unknown; operador móvel/TLS/rotação e resolução de conflito | Operação/segurança/privacidade, T13 | Política com dono nominal, scripts/testes de retenção/restore e simulação de operador | Antes de piloto |
| H. CI/docs e produto | AUD-04/06 + CX-19/21/26; fixture histórica, pipeline reproduzível, runbook corrente e revisão de naturalidade separada | Engenharia/release/produto, #8/#12/T13 | CI/execução independente, secret review e avaliação humana; sem mudançasLLM incidentais | Antes de piloto/release |
| I. Piloto restrito | C–H + CX-10/18/20; número secundário elegível, consentimento, orçamento/rollback | Product owner/operação, #6/T13 | Autorização específica; E2E/echo/status/restart/takeover; p95≤ 8 s e custo≤ US$ 10/1000replies ou decisão formal revisada | Piloto, nunca inferido de pytest |
| J. Estratégia SaaS/router | AUD-05, CX-23/27/28; ratificaçãoV2.5 e isolamento, evals de multimodelo | Produto/arquitetura, #13 | Specs futuras e gates próprios | ForaT11; antes de SaaS/roteamento real |

Nenhuma linha autoriza implementar tickets não liberados. T12/13 são sequência proposta, não tarefa iniciada. Produção exige resolver todos os bloqueadores aplicáveis ou exceção formal do responsável com evidência e mitigação; esta auditoria não aceita exceções.

## Como verificar as correções depois

- Reproduzir os cenários documentados antes da mudança para demonstrar o problema; transformar a expectativa insegura de AUD-01 em negativa após a proteção escolhida.
- Executar testes de comportamento na fronteira dependente, incluindo código real de SQLite/runner e transporte interceptado; não apenas asserts sobre campos internos ou mocks de autorização.
- Reexecutar a suíte integral/checks após mudanças funcionais autorizadas. Exigir SHA do código, ambiente, skips e limitações, sem converter reexecução em prova de produção.
- Atualizar evidência de issue #11 somente após revisão dos achados pelo responsável; preservar CX-31 resolvido offline e histórico dos demais. Nenhuma checkbox foi modificada aqui.
