# Achados priorizados — baseline pré-Ticket 11

Código: `07c1b7dc150d7eb1776b97d891cd29347adffd37`. Classificação usa impacto **na superfície existente** e gate dependente; funcionalidade futura ausente não vira defeito crítico fictício. Não houve correção automática, fechamento de risco ou aceitação de exceção.

**P0: nenhum confirmado. P1: nenhum confirmado. P2: três itens**, dois com saldo aberto e um mitigado para esta execução. Nenhum dos P2 demonstra envio externo duplicado ou exploração remota. Não foram descartados por causa dos 1.983 testes aprovados.

| ID | Prioridade / natureza | Estado e gate |
| --- | --- | --- |
| AUD-01 | P2, risco operacional confirmado por reprodução local | Aberto: restore antigo perde fences; corrigir/mitigar antes de habilitar saída ou aceitar integração operacional |
| AUD-02 | P2, advisories de toolchain constatados; exploração não demonstrada | Aberto: antes de CI/host compartilhado, isolamento temporário privado ou ferramenta corrigida; pip do ambiente também precisa atualização |
| AUD-03 = DOC-02 | P2, lacuna de governança na baseline | Mitigado nesta auditoria por branch/handoff/escritor Git único; protocolo permanente pendente antes de duas contas alternarem desenvolvimento |
| AUD-04 | P3, inconsistências de documentação corrente | Aberto: runbook/índices/estado de autorização devem ser reconciliados em tarefa documental própria |
| AUD-05 = DOC-01/07 | P3, direção/planejamento contraditórios | Decisão de produto pendente; não autoriza tenancy nem alteração do roadmap nesta auditoria |
| AUD-06 | P3, lacuna de reprodução histórica/CI | Aberto: fixture v8 local e resolução de dependências não portáveis; antes do aceite reprodutível CX-19 |
| AR-01 | P3, risco residual de chamada LLM após pausa | Reproduzido: uma chamada, zero reply; avaliar política de custo/privacidade antes do piloto |
| AR-02 | P3, fronteira interna genérica mais permissiva | Reproduzido sem bypass Telnyx externo; manutenção contratual |
| AR-03 | P3, dívida técnica de invariantes SQL | Sem defeito reproduzido; revisão por matriz de gates nas futuras mudanças |

## AUD-01 — snapshot antigo permite nova autorização local

- **Local:** `src/rj_studio_ai/persistence.py:246`, `:921`, `:1120`; `src/rj_studio_ai/telnyx_submission.py:60`.
- **Descrição:** initialize valida/migra o arquivo e reaplica os efeitos presentes nele. Não consegue distinguir snapshot consistente de estado obsoleto. Marker, accepted, disconnect, consentimento e clock posteriores ao snapshot podem desaparecer juntos.
- **Invariante:** restore não deve reviver trabalho potencialmente submetido/bloqueado sem verificação e reconciliação explícitas. A durabilidade de um commit não prova frescor de uma cópia restaurada.
- **Reprodução:** (1) snapshot em pending antes do claim, ou em sending antes do marker; (2) na linha atual authorize+accepted, ou ACCOUNT_OFFBOARDED e cancelled; (3) abrir cópia anterior, initialize, migrations_are_current; (4) claim/authorize voltam a passar, conservando a chave. Três cenários reproduzidos com SQLite real e fixtures sintéticas, sem HTTP. Script integral em [SQLITE-CONCURRENCY-REVIEW.md](SQLITE-CONCURRENCY-REVIEW.md).
- **Impacto:** futuros workers sobre restore antigo podem repetir tentativa ou enviar depois de bloqueio. Mesma chave pode ajudar externamente, mas retenção máxima, bytes/organização e expiry impedem tratá-la como proteção suficiente. Duplicação externa **não foi observada**.
- **Evidência:** sete probes do revisorB, três dedicados a restore; revisão direta do auditor principal e reexecução dos três cenários. Os testes de backup existentes preservam bloqueio já contido na cópia, não impedem rollback para antes dele.
- **Correção recomendada:** restore em quarentena sem saída; inventário/reconciliação de work potencialmente divergente; revalidação positiva de binding/consentimento e política verificável de epoch/fence fora do snapshot, ou procedimento operacional equivalente. Não trocar chave ou apagar unknown para “resolver”. Definir contrato antes do aceite do sender, e implementar somente em tarefa autorizada.
- **Regressão proposta:** snapshots antes de claim/marker/pausa/disconnect e depois de acceptance, restart e key expiry; nenhum sender invocado até liberação autenticada e evidência positiva. Testar perda de WAL/restore conforme procedimento operacional escolhido.
- **Gate/dono:** recovery/composição/operação; contrato T11, habilitação T12–13. Bloqueia saída operacional/piloto; não impede escrever testes/serialização com transporte inteiramente mockado. Vincular CX-15/33/35 sem criar risco duplicado.

## AUD-02 — toolchain instalada tem advisories e pytest exclui versão corrigida

- **Local:** `pyproject.toml:31` (`pytest>=8.3,<9`); pip25.0.1 pertence ao venv do ambiente, não ao runtime declarado.
- **Descrição/invariante:** ambiente de teste precisa evitar ferramentas com vulnerabilidades aplicáveis sem mitigação. `pip-audit2.10.1` completou e reportou 14 entradas brutas, sete IDs únicos: seis de pip25.0.1 e um de pytest8.4.2. O pin<9 exclui pytest 9.0.3, versão corrigida indicada para CVE-2025-71176.
- **Reprodução/evidência:** criar venv e instalar `.[dev]` conforme baseline; executar pip-audit com cache gravável. JSON, hash, versões, aliases e escopo estão em [TEST-EVIDENCE.md](TEST-EVIDENCE.md) e [SECURITY-PRIVACY-REVIEW.md](SECURITY-PRIVACY-REVIEW.md). Não houve exploit. Python3.12 implementa PEP706, mitigando um dos caminhos de pip, sem eliminar os demais advisories.
- **Impacto:** risco local/instalação/CI; pytest usa `/tmp/pytest-of-*` em UNIX com possibilidade de abuso por usuário local segundo advisory. Não é falha remota do webhook. Nenhum advisory foi retornado para as bibliotecas runtime resolvidas nesta consulta; app local não auditável no índice foi explicitamente pulada.
- **Correção recomendada:** validar atualização de pip do ambiente e pytest corrigido em tarefa própria; até lá, runner isolado e parent temporário privado0700 com `--basetemp`, índice confiável e resolução registrada. Um ensaio de autorização concorrente passou com temp privado; a mitigação não corrige o pacote nem substitui atualização.
- **Regressão proposta:** reinstalar toolchain corrigida em ambiente limpo, reexecutar suíte/checks/advisories e demonstrar isolamento/permissões temporárias do CI. Nenhuma atualização foi feita nesta auditoria.
- **Gate/dono:** mantenedor de dependências/CI antes de host compartilhado e aceite reprodutível. A limitação não exige mudar algoritmo do sender para começar desenho/testes offline em ambiente isolado. Relacionado CX-19/21.

## AUD-03 / DOC-02 — protocolo entre contas não existia na baseline

- **Local:** `AGENTS.md:32–47`; ausência de `docs/handoffs/TICKET-10.md` em `07c1b7d`; decisão posterior de continuidade na issue #11, seçãoK/comentário final.
- **Descrição/invariante:** uma segunda conta deve conhecer estado real, último push, testes e exclusividade antes de escrever. Disciplina Git genérica não implementa checkpoints/handoff nem lock humano.
- **Reprodução/evidência:** `git ls-tree -r 07c1b7d docs/handoffs` não encontra protocolo; AGENTS contém apenas regras genéricas. Não houve perda de trabalho observada, e não se inferiu acesso a worktrees em outra máquina.
- **Impacto:** colisão de trabalho, suposições de teste incorretas ou continuidade sobre SHA antiga quando duas contas escreverem sem coordenação. Não é defeito de autenticação ou envio.
- **Mitigação nesta auditoria:** branch exclusiva criada a partir da SHA exata, um escritor Git, revisores com documentos separados, handoff versionado, push normal com SHA remota verificada. Isso atende a continuidade desta tarefa; não altera AGENTS nem define lock distribuído.
- **Correção recomendada/regressão:** tarefa documental própria para protocolo permanente; ensaio em segunda conta com fetch/status/SHA/handoff, retomada sem sobrescrita, conflito recusado e sem force push.
- **Gate/dono:** responsável do projeto/engenharia antes de uma segunda conta assumir branch de desenvolvimento. P2 **mitigado nesta execução**, ainda não implementado como norma geral. Não bloqueia sender mockado por escritor exclusivo.

## AUD-04 — instruções correntes misturam estados históricos

- **Locais:** `docs/automation-operations.md:87` e `:111` ainda dizem lifecycle/status futuros; contradizem `:129–145` e T08/09. `docs/specs/README.md:9` diz V1 Draft versus spec aprovada; `:30–37` mistura autorizações históricas. `docs/decisions/README.md:22–27` omite ADR0014/0015. `docs/PRODUCT.md:30–35` omite OpenAI. SpecT10:24–25 atribui byte-identical à query, enquanto fonte atual exige mesmos parâmetros/valores e body byte-for-byte.
- **Invariante/impacto:** documentação de estado corrente deve orientar gates corretos; stale runbook pode confundir operação e auditoria. Nenhum bypass de gate de código foi reproduzido por essas frases. Reuso de “Ticket 11/12” entre séries inteligência/Telnyx amplia ambiguidade.
- **Reprodução/evidência:** comparar trechos e código/fonte oficial, conforme DOC-03–10 em [DOCUMENTATION-AUDIT.md](DOCUMENTATION-AUDIT.md). Scanner de destinos relativos não encontrou arquivo ausente, sem provar anchors/URLs universais.
- **Correção/regressão proposta:** alinhar descrições atuais e identificar trechos históricos, prefixar série, atualizar índice de ADR; revisão cruzada por mapa runtime/offline. Gate: antes de usar runbook no piloto, dívida documental para desenvolvimento offline. Não alterar política ou roadmap incidentalmente.

## AUD-05 — V7 normativa versus estratégia V2.5 e datas vencidas

- **Locais:** `AGENTS.md:22–23`, `docs/ROADMAP.md:5,17,25`, `docs/PRODUCT.md:9–11`, `docs/CONTEXT.md:119`; issues10/13.
- **Invariante/reprodução:** fontes de direção precisam indicar qual decisão vale. Docs preservam SaaS V7 e prazoV6 de02/10/2026, enquanto issue #13 propõe comercializar apósV2 com fundaçãoV2.5; issue #10 remete à nova direção como histórica. Ratificação/spec ainda são exigidas.
- **Impacto/evidência:** conflito de planejamento confirmado, sem autorização para tenancy na V1. Nenhuma falha de isolamento foi explorada, pois produto continua single-business.
- **Correção/regressão/gate:** decisão do product owner e revisão documental coordenada, sem datas artificiais; antes de planejar/comercializar SaaS, verificar todas as fontes e testes de isolamento da futura spec. CX-27 continua gate distinto. Não bloqueia sender offline.

## AUD-06 — reprodução histórica/CI ainda incompleta

- **Local:** `tests/test_commercial_steering.py:423–432`; `.github/` ausente; `pyproject.toml:10–32` usa faixas abertas sem lock versionado da resolução auditada.
- **Invariante/reprodução:** clone limpo deve reproduzir evidência exigida. Teste v8 procura fixture ignorada em work; suíte independente efetivamente pula um caso. API GitHub retorna statuses=[] e runs de PR=[] para a SHA, o que não prova execuçãoCI.
- **Impacto/evidência:** compatibilidade daquela evidência histórica fica sem validação portátil, e outra resolução pode divergir. Não é justificativa para chamar a suíte inteira não executada: 1.983 casos passaram.
- **Correção/regressão proposta:** fixturev8 sanitizada com provenance ou teste equivalente aprovado, CI offline e snapshot/lock reproduzível da toolchain; ensaio em clone limpo sem fixture pessoal. GateCX-19 antes de aceite de release, sem impacto demonstrado no algoritmo do sender.

## Observações AR e riscos já registrados

AR-01/02/03 têm local, cenário, impacto, recomendação, teste e gate no [relatório arquitetural](ARCHITECTURE-REVIEW.md). São mantidos como P3, sem promoção artificial: custo de LLM após pausa; subclasses no store interno genérico; concentração de SQL. O caminho estrito Telnyx não demonstrou bypass.

CX-35 é um bloqueador conhecido do **aceite do sender**, não novo defeito de T10: organização/método/path/query/bodyHTTP ainda não vinculados, e SDK futuro pode repetir sem autorização. CX-24/29/30 são gates da futura rota; CX-36 é gate operacional de consentimento/templates. A lista completa e os dez riscos principais estão em [RISK-REGISTER.md](RISK-REGISTER.md). Ausência de implementação autorizada futura foi classificada como lacuna/gate, sem inventar código pronto nem novo P1.
