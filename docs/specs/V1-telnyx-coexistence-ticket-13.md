# Telnyx Coexistence Ticket 13 — operational readiness OFFLINE

Status: escopo autorizado pelo pedido explícito do Ticket13 e pelo
[parecer T12](https://github.com/zazacknazzo/rj-studio-ai/issues/11#issuecomment-7069497120).
Baseline f1496be42732b7e57d317444d7ed0020997f0327; branch única
`codex/telnyx-coexistence-13-readiness`. Esta especificação precede a implementação.
Não autoriza piloto, produção, HTTP Telnyx, conta, credenciais comerciais, ativação,
egress operacional, rota no main, merge, Baileys, inteligência/LLM ou SaaS.

## Escopo e provas

CP0 spec/ADR/handoff; CP1 inventário completo de gates; CP2 laboratório de recovery;
CP3 segurança/consentimento; CP4 retenção/backups; CP5 CI/métricas/testes;
CP6 runbooks/plano de piloto; CP7 quatro revisões independentes, correções e integral;
CP8 relatório A–P/issue11. Em cada checkpoint: testes aplicáveis, handoff, commit
coerente, push normal e consulta da SHA remota. Sem force push, reset ou descarte de WIP.
Um escritor humano confirmado; revisores apenas leem o repo e produzem probes fora dele.

## AUD-01: contrato executável de laboratório

Implementar sessão offline sem capacidade de envio, sempre sobre store explicitamente
quarantinado. Nenhum release do laboratório altera o store ou concede permissão HTTP.
A autoridade externa é um contrato injetável; a implementação simulada fica nos testes,
com SQLite real separado do snapshot da aplicação. Um witness também independente
retém o maior contador observado. Nenhum adapter comercial/endpoint/CLI de release.

Cada boot/restore começa fechado. Begin eleva epoch/revision de maneira serializada,
vincula recurso, boot nonce e fingerprint consistente do snapshot. Invalidar sessões
anteriores e qualquer liberação. Ler autoridade e witness sem cache em cada decisão.
O witness cerca TODAS as revisões: release, revogação, inventário, evidência e roles,
não apenas epochs. Revision regressiva ou mesma revisão com conteúdo diferente falha
fechada. Indisponibilidade, commit parcial ou resposta fora do escopo fecham a sessão.
Crash/restart exige novo begin e nova revalidação, nunca reusa permit em SQLite.

Contrato de inventário externo write-ahead: antes de possível submissão, reservar
identidade lógica estável + submission key original + digest exato do request.
Registro deve ser durável antes de marker/transporte, com falso positivo conservador
se houver crash. A prova de completude é obrigação da futura composição externa:
lista vazia local não prova ausência de submissões. Inventariar união local/externa,
inclusive entregas ausentes do snapshot e chave divergente para mesma identidade.
Não reenviar itens anteriores ao recovery. Unknown/accepted/conflict ficam bloqueados
por identidade e chave; reconciliação autenticada registra prova, sem retry automático
ou nova chave, mesmo após 24h. Prova not_submitted também não transforma trabalho antigo
em fila: cancelamento/decisão explícita e novo inbound posterior pertencem a outro gate.

Release autenticado, CAS de revisão e trilha append-only exigem recuperação e aprovação
por pessoas distintas, binding/organização/profile/número atuais, sync/Coexistence
positivos, consentimento/finalidade/janela atuais e inventário reconciliado completo.
Evidências têm escopo de epoch/recurso e prazo; fixture opaca não prova fato real.
Revogação e perda/rotação de credenciais invalidam permissões. App não é operador.
O laboratório só declara `simulation_ready`; `operational_egress` permanece false.

Testar snapshots antes de claim/marker/disconnect/pause/consent revogado e depois
de acceptance; restore repetido, autoridade antiga inclusive mesmo epoch,
witness indisponível, respostas repetidas, inventário órfão, chave divergente,
reconciliação unknown, papéis, expiração, revogação, concorrência e crash entre commits.
Rollback simultâneo de todas as raízes externas não é detectável offline. Autoridade
linearizável, witness independente, completude do ledger e integração no deploy real
exigem evidência posterior. AUD-01 permanece ABERTO; não propor encerramento operacional.

## Segurança, consentimento e eventos

Documentar segregação, aprovação/revogação/rotação de acesso, associação de credencial
a organização/profile/número, audit/redação, TLS/proxy/headers, replay, limites,
configuração e dependências fail-closed. Nenhum secret/PII real.
Especificar captura de consentimento por finalidade/escopo/proveniência/prazo,
opt-out e trilha; serializar revogação versus autorização no SQLite real. Conversa ativa
e echo não provam permissão nem janela API. Templates precisam aprovação atual real;
sender V1 continua somente texto free-form E.164 e não adiciona suporte a template.

CX29: mídia/localização/futuro/batch inválido permanecem 422 com observação agregada
durável e sem payload privado. Falha ao persistir permanece503. Definir alertas, fila
humana segura e esgotamento de retries/failover; jamais 2xx para ocultar rejeição.

## Dados, CI e operação futura

Matriz de TODAS as tabelas/categorias: finalidade/dados/prazo proposto/necessidade,
minimização/expurgo/idempotência/reuso/backups/aceite. Não expurgar fences/dedupe por
conveniência. Não ativar purge novo ou declarar conformidade LGPD integral.
Testes de retenção/replay/backup existentes e novos devem preservar integridade/unknown.

CI sem segredos ou fixture privada: resolução explícita versionada, pytest integral,
concorrência/restore/migrations, Ruff/format, compileall, pip check/audit, Gitleaks,
diff e guard de rede com probes IPv4/IPv6/DNS/filhos. Separar instalação/audit online
público dos testes sem rede; provar isolamento kernel na CI Linux quando disponível.
Skip histórico v8 deve permanecer identificado se o artefato original não é recuperável;
teste sintético de compatibilidade tem provenance própria e não substitui história.

Métricas finitas sem PII; ACK local <1.5s e contrato externo conservador2s,
p50/p95/p99,204/422/503,dedupe,signature,quarantine,lifecycle,unknown,conflict,
unsupported,SQLite,backlog e intervenção. Carga offline inclui lock/deadline/retry.
Não extrapolar latência in-process para TLS/proxy/rede, SLA comercial ou p95E2E.

Runbooks com dono/pré-condições/evidência/proibições e plano de piloto apenas futuro.
Preservar todos CX01–37/AUD; nenhum checkbox fecha sem decisão do orquestrador.
Ao terminar: parar desenvolvimento e solicitar auditoria final do orquestrador.
