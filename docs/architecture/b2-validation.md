# B2 — evidência WAHA e limites operacionais

Checkpoint de 22/11/2026: P0/P1 executados no ambiente real; P2 aguarda mensagem
nova do participante; P3–P5 não concluídos. Egress NO-GO, AUD-01/AR-02 abertos.
Código publicado em `0f77e05e5c3e121f6c05772724216c019e65f9f1`;
[CI completo aprovado](https://github.com/zazacknazzo/rj-studio-ai/actions/runs/45047050391).

## Diagnóstico observado

Baseline remota conferida por ls-remote e fetch:
`3aa8721cfe4449597b42423d8479ecf51d18180c`. B2 isolada, exclusividade confirmada.
Colima estava parado; foi iniciado com configuração existente. Iniciamos apenas
containers WAHA/backend já existentes; sessão preservada estava STOPPED e voltou
a WORKING por `POST /api/sessions/default/start`. Não houve novo QR nem logout.

Com WORKING e secundário correto, `identities_for` original falhou no backend em
2,077s e 2,679s como OutboundOutcomeUnknown, sem conflitos, sem validar sessão.
GET direto com timeout20 retornou HTTP200, numberExists true, chatId @lid para
secundário/participante. Uma consulta levou 6,89s; participante 0,830s. Pela rede
Docker também retornou200 em 0,605s/0,279s. DNS interno resolveu normalmente.
RemoteProtocolError inicial durante boot e HTTP422 durante STOPPED/STARTING não
foram confundidos com esse timeout de contatos em WORKING.

Código embarcado em `/app/dist/core/engines/webjs/session.webjs.core.ts`, método
checkNumberStatus: getNumberId retorna numberExists/chatId. WEBJS não devolve pn
nesse método; LID é aceito somente como resposta da consulta explícita. Referência:
[API oficial de contatos](https://waha.devlike.pro/docs/how-to/contacts/).

## Correção

- Contatos têm prazo20; falhas distinguem timeout, transporte, HTTP e identidade.
  Não são resultados ambíguos de envio. POST de envio conserva unknown sem retry.
- Resume aceita até75s: três contatos20s + duas leituras de sessão5s + margem.
- Revalidação começa pausada e remove aliases anteriores; exige todos os contatos,
  ausência de conflito, WORKING e mesmo secundário antes/depois das consultas.
- Revisão de controles do journal impede sobrescrever pausa/revogação ocorrida
  durante a consulta, sem segurar lock durante a rede nem bloquear ACK por20s.
- Launcher usa o src do checkout atual mesmo quando o venv editável é compartilhado.
- Sem alteração de Knowledge, preços, modelo, persona ou composição de egress.

Backend B2 real respondeu `paused:false`, `scope:inference_only`; status posterior:
WORKING, secondary_matches true, connected_secondary true, processing true,
knowledge_facts22, egress false, nenhuma chamada OpenAI reservada naquele momento.

## Bloqueio preciso de saída

ADR0021/0022 e testes G0/T13 continuam válidos. `.local/b1/backend`, control e
witness pertencem ao mesmo host/administrador e podem voltar juntos a snapshot
antigo. MAC não distingue esse conjunto antigo de estado atual. Quarentena atual
nega envio até nesse caso; ela não é evidência de uma autorização positiva segura.

| Alternativa | Resultado para este ambiente |
| --- | --- |
| Timeout maior, outra pasta local, outro container ou flag | Não resolve frescor independente, nem autorização durável |
| Apenas ID aleatório local ou tentativa de reenvio idempotente | Snapshot pode apagar identidade/consentimento; WAHA sendText não tem garantia verificada de deduplicação por chave |
| Autoridade externa monotônica + ledger/witness independentes + gateway de envio exclusivo | Caminho necessário; serviço, endpoint autenticado e credenciais com IAM separado não estão configurados |

Dependência operacional: serviço externo ao domínio de restore deste Mac, com
epoch por boot, CAS/revisão monotônica, desafio/escopo autenticados, witness
independente e credenciais app/operador separadas. Antes de todo HTTP, registrar
identidade lógica durável, destinatário, request digest e possibilidade de submissão.
Em restore/restart, inventariar pendências externas e locais, manter unknown
bloqueado, reconciliar com evidência do provedor e liberar por papel separado.
Revalidar consentimento, pausa, handoff, binding e kill switch no caminho exclusivo
de transporte. Fault injection deve cobrir falha entre cada commit e chamada HTTP.

Não existem esses serviços/credenciais na composição inspecionada. Implementar
outro SQLite local e declará-lo independente violaria o aceite da missão. Nenhum
bypass ou executor de saída foi acrescentado. Autorização específica só deve ser
pedida depois de provisionar e auditar esses controles; ainda não há autorização.

## Verificação executada

Red da regressão: 1FAILED reproduzindo OutboundOutcomeUnknown antes da correção.
Focal inicial:53PASS. Focal adversarial corrigido:82PASS. Lote anterior teve11
falhas de driver corrigidas. Focal final:83PASS/0SKIP/27,49s. Integral do CI na SHA
acima:2348PASS/0SKIP/289,23s, Linux/Python3.12, interfaces de rede isoladas pelo
kernel. Ruff/format/compileall/pipcheck/diff, auditoria de dependências e Gitleaks
passaram no CI. Varredura local de valores privados conhecidos: zero ocorrências.
Integral local preliminar interrompida em973PASS para recolher o snapshot final;
não é contada como suite completa nem atribuída ao snapshot final.

[Revisões separadas](b2-review.md): Standards0 achados; Spec0 defeitos novos e3
grupos de aceite pendentes na revisão. O grupo de regressão posteriormente foi
satisfeito pelo CI; ingresso real e egress permanecem pendentes.

Rebuild da imagem final com volumes existentes comprovou boot pausado e novo resume
com paused:false. SHA256 dos quatro módulos embarcados confere com o checkout.
Sessão tem um webhook para backend, evento message inscrito e HMAC esperado.
Primeira mensagem real foi solicitada ao participante; zero ingressos/zero chamadas
OpenAI foram observados no banco até este checkpoint. Não inferir uso real de
Knowledge ou memória a partir de testes sintéticos ou22 fatos apenas carregados.

Credenciais já compartilhadas são consideradas expostas. Não foram exibidas ou
alteradas. Rotacionar OpenAI/API/dashboard/webhook/operador em manutenção coordenada;
WAHA_JOURNAL_KEY requer migração/encerramento seguro, nunca troca isolada ou limpeza.
