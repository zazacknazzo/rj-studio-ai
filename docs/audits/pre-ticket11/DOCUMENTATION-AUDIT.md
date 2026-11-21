# Auditoria documental e governança — revisão C

Baseline: `07c1b7dc150d7eb1776b97d891cd29347adffd37`. Leitura independente realizada em 20/11/2026 (America/Sao_Paulo). Nenhum documento de produto, spec, ADR ou issue foi modificado para corrigir as divergências abaixo.

## O que as evidências sustentam

README:12 e a factory/configuração apresentam somente Twilio/Meta. `main.py:250–273` expõe rotas Meta/Twilio/WhatsApp, não Telnyx. Os capítulos finais de ARCHITECTURE.md:351–406 registram explicitamente status, lifecycle e elegibilidade Telnyx **offline**. Não encontrei alegação nesses capítulos de sender Telnyx, piloto ou ativação concluídos.

A frase “V1 through Ticket11” em ARCHITECTURE.md:4 e PRODUCT.md:30 refere-se à antiga série **inteligência V1** (appointment-interest), não ao futuro sender da série **Telnyx Coexistence**. É ambígua para leitores novos, mas não constitui evidência de Ticket11 Telnyx implementado. O sender ausente concorda com a specT10/ADR0018.

Li diretamente AGENTS.md, README.md, PRODUCT/ROADMAP/ARCHITECTURE/CONTEXT, automation-operations, índices de specs/ADRs, specs06–10 e ADRs0014–0018; consultei código e testes correspondentes. Também consultei diretamente as issues [#6](https://github.com/zazacknazzo/rj-studio-ai/issues/6), [#8](https://github.com/zazacknazzo/rj-studio-ai/issues/8), [#9](https://github.com/zazacknazzo/rj-studio-ai/issues/9), [#10](https://github.com/zazacknazzo/rj-studio-ai/issues/10), [#12](https://github.com/zazacknazzo/rj-studio-ai/issues/12) e [#13](https://github.com/zazacknazzo/rj-studio-ai/issues/13). A análise integral da issue11 e de cada CX fica em RISK-REGISTER.md, sem fechamento de riscos nesta auditoria.

## Inconsistências e classificação

| ID local | Arquivo/linha ou fonte | Evidência e implicação | Tipo / prioridade | Categoria exigida / ação recomendada |
| --- | --- | --- | --- | --- |
| DOC-01 | `AGENTS.md:22–23`, `docs/ROADMAP.md:17`, `docs/PRODUCT.md:9–11`, `docs/CONTEXT.md:119`; issue13 | Documentos normativos mantêm SaaS somente V7; issue13 propõe início após V2 com gateV2.5. Issue10 já se declara histórico e remete à nova direção. Issue13 ainda exige ratificação/spec antes de mudar arquitetura. | Inconsistência de direção, P3 para esta auditoria | **Decisão de produto pendente**. Ratificar e reconciliar em branch autorizada; não antecipar tenants na V1. |
| DOC-02 | `AGENTS.md:33–48`; inexistência de `docs/handoffs/TICKET-10.md` na baseline | Disciplina Git genérica não define lease humano, checkpoint por fase, handoff durável ou comparação de SHA entre contas. Aprovação T10 na issue11 pede fazê-lo a partir do T11; não foi implementado retroativamente. | Lacuna de governança, P2 **antes de duas contas escreverem a mesma branch**; não defeito de envio | **Impede desenvolvimento concorrente sem protocolo**. Auditoria adota branch exclusiva, um escritor de Git e handoff; adoção permanente no desenvolvimento requer tarefa autorizada. |
| DOC-03 | `docs/automation-operations.md:85–87` e `:110–111` | Afirma que lifecycle ainda não é gate e status/lifecycle aguardam T08/09; contradiz `:129–145`, parserT08/09 e gates reais. | Inconsistência documental confirmada, P3 | **Dívida de documentação**. Atualizar apenas trechos de estado corrente em futura correção documental, preservando histórico. Não bloqueia sender offline. |
| DOC-04 | `docs/specs/README.md:9` versus `docs/specs/V1.md:8` e `docs/ROADMAP.md:11` | Índice V1 diz Draft; spec diz approved e roadmap approved. Índice:13 exige status sincronizado. | Inconsistência confirmada, P3 | **Dívida de documentação**. Sincronizar ciclo de vida sem fingir aceite de gates operacionais. |
| DOC-05 | `docs/specs/README.md:30–37` | Entradas antigas ainda dizem T04/05–13 não autorizados ou T07 aguardando auditoria; entradas seguintes registram T07–10. As specs preservam autorização histórica por ticket. | Ambiguidade de escopo temporal, P3 | **Dívida de documentação**. Identificar textos como autorização histórica e apontar registro atual; não interpretar ausência de atualização como revogação do pedido atual. |
| DOC-06 | `docs/decisions/README.md:22–27` | Índice salta ADR0013 para0016; ADR0014/0015 existem e são relevantes para auth/ingress. | Descobribilidade incompleta, P3 | **Dívida de documentação**. Incluir links em correção documental própria. |
| DOC-07 | `docs/ROADMAP.md:5,25`; issue10 | Deadline20dias/V6 em02/10/2026 já passou; issue10 reconhece vencimento e requer replanejar após piloto. | Planejamento desatualizado, P3 | **Decisão de produto pendente**. Não criar datas retroativas ou prometer V6 entregue. |
| DOC-08 | `docs/specs/V1-telnyx-coexistence-ticket-10.md:24–25` | Descreve query/body byte-identical como regra externa. FonteTelnyx atual diz query com mesmos parâmetros/valores e body byte-for-byte. Exigência local mais forte pode ser válida; atribuição externa literal é imprecisa. | Inconsistência de contrato documental, P3 | **Dívida de documentação**. Separar regra externa de serialização determinística local no Ticket11. Nenhum bypass de idempotência causado na baseline. |
| DOC-09 | `docs/PRODUCT.md:30–35` versus runtime/configuração OpenAI | Lista “Claude or deterministic” como produto atual, mas ARCHITECTURE e configuração também permitem OpenAI. Há documentação específica de promoção OpenAI. | Descrição resumida incompleta, P3 | **Dívida de documentação**. Atualizar descrição sem selecionar modelo novo ou reabrir inteligência. |
| DOC-10 | “Ticket11/12” em PRODUCT/ARCHITECTURE/ROADMAP versus série Telnyx | Duas numerações reutilizadas; T11 inteligência existe, T11 Telnyx não. | Ambiguidade, P3 | **Dívida de documentação**. Prefixar a série em futuras referências de estado. |
| DOC-11 | Issue11 CX-37 e specT10 destinatário | Bloqueio local BSUID é real. OpenAPI atual já documenta envio Telnyx BSUID em `to`; não cabe afirmar que nenhuma fonte oficial fornece campo de destino. | Atualização de evidência, não defeito | **Decisão de produto pendente** para ampliar suporte. Preservar negativa até implementação/revisão explícitas. Não fechar CX-37 só porque a documentação existe. |

DOC-02 é uma lacuna cujo gate é **coordenação entre escritores**, não uma falha P2 do contrato do sender. O protocolo adotado nesta auditoria e o handoff reduzem o risco desta execução; AGENTS.md permanece intocado, conforme autorização restrita.

## Continuidade entre duas contas

Na SHA de origem não há diretório `docs/handoffs` rastreado, `TICKET-10.md` ou instruções específicas “duas contas/checkpoint/handoff” em AGENTS.md. A decisão aparece na issue11, não em um protocolo completo implementado no repositório. O estado não deve ser descrito como suporte multi-conta pronto.

Procedimento concreto desta auditoria: uma branch isolada, somente o auditor principal faz commits/push, revisores escrevem documentos distintos, handoff registra origem/última SHA remota/fases/comandos/achados/próxima ação, push normal sem force e leitura remota antes de continuar. A próxima conta precisa comparar sua SHA local com a remota e obter exclusividade de escrita; um arquivo de handoff não é um lock distribuído nem autenticação de operador.

## Requisitos, implementação e gates

| Documento / família | Comparação com evidência direta | Resultado |
| --- | --- | --- |
| SpecsT06/ADR0014 | Ed25519 bruto, scope, replay, segredo e factory negativa constam do código/testes | Conforme offline; corpo em streaming/raw ASGI e chave real explicitamente futuros |
| SpecsT07/ADR0015 | IDs separados, source Meta, BSUID namespaced, echo/edit/revoke e ACK transacional | Conforme subconjunto; unsupported permanece CX-29, não suportado silenciosamente |
| SpecsT08/ADR0016 | Ledger scoped e conflito sucesso/falha, sem inferir retry/acceptance | Conforme desenho; workflow de resolver conflito não existe e não é prometido |
| SpecsT09/ADR0017 | Reconnect não ativa; sem API/command de rebinding/ativação | Conforme desenho conservador; sync/elegibilidade positiva é gate externo |
| SpecsT10/ADR0018 | Consentimento e janela separados, UUID/fingerprint, marker, unknown | Conforme política offline; request externo não vinculado ainda é CX-35 |
| README / health-ready | Configuração/runtime somente Meta/Twilio, single-process WAL/FULL | Não prova contaTelnyx nem readiness de envio; não usar ready local como gate externo |
| Specs V1/evals | Evidências históricas de modelos/human review, sem autorização de modificar persona | Sem rodada live nesta auditoria; qualidade CX-26 permanece issue12 e gate do piloto |
| Issue6 | P95E2E<=8s e custo<=US$10/1000 replies completas, consentimento/restart/operação | Aberta. Testes offline e aceite estático não fecham piloto |
| Issue8 | Consolidação/release sem merge automático; proíbe segredos/PII/sessões | Aberta. Nenhum merge/autorização de release foi inferido |
| Issue9 | Gates reais Meta/Twilio pendentes | Coerente com README/ROADMAP; evidênciaBaileys não fecha adapters oficiais |
| Issues10/13 | Issue10 adiciona aviso de histórico e propostaSaaSV2.5 | A transição existe em issue, ainda não reconciliada com docs normativas |
| Issue12 | Agentic existe; naturalidade/factualidade flexível exigem reabertura autorizada | Não presumir “só frases fixas”; nenhuma alteração de prompt/modelo nesta auditoria |

Não identifiquei dependência circular técnica entre os componentes offlineT01–10 nesta perspectiva. Há dependências deliberadas de release: sender11 antes de composição12, composição/consentimento/operação antes de aceite13, e aceite humano/operacional antes de piloto. Reconnect, ready local e suitePASS não substituem esses gates.

## Verificação de links

Executei scanner somente de existência dos destinos de links Markdown relativos dos **136 arquivos `.md` rastreados na baseline**: **zero destinos relativos inexistentes**. O scanner removeu fragmentos e ignorou esquemas externos/mailto/data. Não validou anchors, links HTML/referências indiretas ou todos os URLs públicos; portanto não é uma declaração de “todos os links válidos”. As fontes externas da matriz foram consultadas separadamente. Alguns URLs deram erro na ferramenta web, mas GETHTTPS público entregou o conteúdo (documentado na matriz), sem login.

Comando usado: Python `git ls-files '*.md'`, regex para `](destino)`, resolução relativa ao arquivo e `Path.exists()`. Nenhuma escrita ocorreu nessa verificação.

## Falta de evidência e ações por dependência

1. Antes de outra conta assumir a branch: checkpoint/handoff publicado, SHA remota confirmada e exclusividade explícita de escritor.
2. Antes do aceite do sender: preservar classificação unknown, especificar request/response exatos e retries do transporte; atualizar imprecisão de query como regra externa versus política local.
3. Antes da rota/piloto: runbook corrente sem afirmações contraditórias, cabeçalhos brutos/limite em streaming/deadline2s, unsupported durável e identidade operacional utilizável.
4. Antes do piloto: proprietários nominais dos gates, evidência consentimento/opt-out, retenção/backup, naturalidade issue12 e métricas issue6.
5. Antes do primeiro SaaS externo: ratificação/specV2.5; não modificar silenciosamente o roadmap durante esta auditoria.

Não atribuo owner nominal quando a issue só identifica “Ticket/engenharia/operação”. Essa ausência precisa ser resolvida pelo responsável do projeto; a auditoria não designa pessoas nem encerra checkboxes.
