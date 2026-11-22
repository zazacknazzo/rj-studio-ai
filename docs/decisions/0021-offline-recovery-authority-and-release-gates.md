# Recovery offline exige raízes independentes e não libera egress

Status: aceito no escopo offline autorizado Ticket13, 22/11/2026.
Complementa ADR0018–0020 sem alterar os contratos Meta/Twilio ou o runtime principal.

O snapshot SQLite pode perder juntos markers, accepted, pauses, lifecycle e consent.
Schema válido, HMAC e channel active não comprovam frescor. Portanto, uma sessão de
recovery nasce fechada e não lê autoridade de uma tabela restaurável.

Usaremos um contrato injetável de autoridade monotônica com epoch por boot, revisão
CAS por mutação, inventário write-ahead e liberação auditada. Um witness independente
memoriza revisão E digest, detectando rollback inclusive dentro do mesmo epoch e
resposta antiga contraditória. Indisponibilidade ou falha entre commits fecha a sessão.
A futura implementação externa precisa autenticar respostas com desafio/escopo,
linearizar writers, impedir rollback e separar as credenciais app/operador.
Um fixture SQLite em outro arquivo testa o protocolo; não demonstra essas propriedades
na infraestrutura. Rollback conjunto de todas as raízes continua impossível de detectar
sem uma raiz não revertida: gate externo explícito, AUD-01 aberto.

Inventário une registros locais e externos com identidade lógica independente do ID
numérico local. Marcador potencial precede transporte e não some após restore. Unknown
não vira retryable, não ganha outra chave, não é apagado após expirar idempotência.
Reconciliação registra resultado/prova e conserva bloqueio de trabalho pré-recovery.
Evidência atual e liberação por papel distinto do recoverer pertencem ao epoch corrente.

O código T13 é laboratório offline: gera somente diagnóstico simulation_ready.
Store continua explicitamente quarantinado e não há rota/CLI/adapter operacional.
Não criar uma opção de configuração que transforme o laboratório em autorização real.
O store genérico legado continua compatível para testes históricos; NÃO é composição
operacional autorizada, e seu comportamento permissivo não foi corrigido pelo laboratório.

Retenção será especificada sem expurgo automático novo: apagar conteúdo e apagar
identidades/fences têm riscos diferentes. Tombstones minimizados só poderão substituir
dados com especificação/migration/testes e decisão de privacidade posteriores.
Prazos são propostas técnicas sujeitas a encarregado/jurídico, não promessa LGPD.
