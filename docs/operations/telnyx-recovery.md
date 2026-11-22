# Recovery e antirollback — laboratório e gate externo

Status22/11/2026: implementação OFFLINE, AUD-01 ABERTO. Não é runbook executável de
release. Não há endpoint/CLI/credencial de produção nem adapter de autoridade real.
Código: offline_recovery.py; stand-ins SQLite somente tests/offline_recovery_fixture.py.

## Raízes e protocolo demonstrado

| Raiz | Papel | Backup/credencial | Falha segura |
| --- | --- | --- | --- |
| SQLite da aplicação | Snapshot de Messages/markers/lifecycle/consent | Pode estar antigo; nunca autoridade | Abre somente leitura para fingerprint; store quarantinado |
| FreshnessAuthority injetável | Epoch/revisionCAS, inventário, provas, acesso e audit | Fora do snapshot; app não é recoverer/approver | Sem resposta atual não há simulation_ready |
| FreshnessWitness injetável | Maior epoch/revision/digest e server-time observados | Administração e restauração independentes | Rollback/equivocação/skew/indisponibilidade fecham sessão |
| Identidade e provas atuais | Credencial→recurso/role e verificação externa | Rotação/revogação independentes | Refs locais não são provas operacionais |

1. Constructor exige store explicitamente quarantinado; toda sessão nova começa fechada.
2. Begin lê resposta autenticada e ligada a desafio imprevisível; witness verifica escopo,
   revisão e digest. Snapshot consistente via transação somente leitura é fingerprintado.
3. Autoridade eleva epoch e revision, revoga releases anteriores e importa inventário
   local sem remover entradas externas. Identidade lógica usa provider/channel/inbound ID,
   independente do ID SQLite e da submission key. Colisão de chave/bytes é rejeitada.
4. Cada mutação da autoridade, inclusive roles/provas/revogação/negações auditadas, cerca
   revision+digest no witness ANTES do commit da autoridade. Falha depois desse fence
   deixa witness adiante e bloqueia a linha anterior: exige remediação independente.
   O fixture simula esse protocolo com DOIS arquivos SQLite separados, não um serviço.
5. Inventário conserva chave e MAC/request digest conhecidos. Importação incerta vira
   unknown; conflito não perde seu bloqueio. Não se afirma completude pela lista local:
   inventory_complete precisa prova externa que cubra todos os caminhos de submissão.
6. Reconciler autenticado usa prova externa scoped da mesma epoch, accepted ou
   not_submitted. Não aceita retryable, prova inventada ou troca de chave. Toda entrega
   pré-recovery permanece em blocked_intents mesmo reconciliada. Não reabre fila antiga.
7. Provas de binding/org/profile/número, sync, consent/finalidade e janela atuais são
   epoch-bound e expiram. Aprovação por pessoa distinta do recoverer usa CAS e audit.
8. Diagnóstico lê de novo authority+witness e snapshot, sem cache de permit. Expiração,
   revogação, boot novo, resposta repetida, erro, clock regressivo ou mudança do snapshot
   fecham a sessão. Reserva externa revalida proofs/TTL/inventory dentro da mutaçãoCAS.
9. Write-ahead de possível submissão é durável antes de qualquer troca simulada;
   crash preserva unknown externo mesmo se nenhuma linha local o conhece.
   Nenhum transporte é recebido ou invocado por esta API.
10. `simulation_ready=true` é só resultado de ensaio. `operational_egress=false` sempre;
    authorize_delivery_submission do store quarantinado continua negando.

O fixture usa tokens aleatórios sintéticos, hashes de credenciais, roles separados,
escopo fixo e audit append-only sem tokens/conteúdo. Não demonstra autenticação TLS,
assinatura de respostas externas, IAM empresarial, WORM ou durabilidade sob perda de host.
O contrato EXIGE adapter autenticado com desafio/escopo; dataclass AuthorityReply,
isoladamente, não autentica rede. O código não contém um adapter operacional.

## Cenários executáveis e limite

tests/test_offline_recovery.py exercita snapshots antes de geração, claim, marker,
pause real, lifecycle disconnect real, revogação real do consent e após acceptance;
reinícios/repeated restore, inventário externo órfão, unknown/accepted/not_submitted,
proofs ausentes/expiradas, privilégios, audit, colisões, rollback de autoridade antes de
boot e dentro da epoch depois de revogação não observada pelo app, mesma revisão
contraditória, indisponibilidade e commit parcial witness→authority.
Probes independentes acrescentam corrida TTL/reserva e revoke/reserve.
Números/tempos e falhas anteriores ficam no relatório de validação, não inferidos aqui.

O snapshot é intencionalmente conservador: qualquer alteração local após begin exige
nova recuperação. O laboratório não é projetado para tráfego contínuo nem avalia
segurança/performance de uma futura integração ao writer/transport.
O store genérico legado ainda demonstra a lacuna original fora da composição fechada.

## Evidência externa obrigatória antes de propor fechamento AUD-01

| Requisito externo | Dono | Evidência de aceite necessária |
| --- | --- | --- |
| Authority linearizável e não restaurável junto do app | SRE+Segurança | Provisão, IAM segregado, CAS/multiwriter, failover, rollback tentado |
| Witness realmente independente, raízes/backup separados | Segurança | Restore da authority sem regressão do witness; corrupção/perda/clock; alertas |
| Cada mutação ancorada antes de efetivar/reconhecer | Recovery+SRE | Crash/fault injection entre commits; release antigo jamais aceito |
| Ledger completo antes de todo possível HTTP | Engenharia | Inspeção de TODOS os caminhos/SDKs; marker externo pré-I/O; sem bypass |
| Credential real vinculada org/profile/número/WABA | Responsável da conta | Consulta autenticada autorizada e prova saneada; sem inferir do payload |
| Sync/coexistence/elegibilidade atuais | Integração | Estado positivo real e expiração; reconnect sozinho não basta |
| Consentimento/finalidade/janela reais | Privacidade+Operações | Proveniência verificável e revogação concorrente/restart |
| Release/revoke/IAM/audit reais | Segurança+Operações | Dois operadores designados, revogação imediata, acesso app insuficiente |
| Integração final de writer/transport/fences | Engenharia | Teste no ambiente de destino, restore/unknown/TTL/race sem replay |
| Backup/WAL/perda de host e retomada | DBA+SRE | Restore íntegro quarantinado e inventário reconciliado com fontes externas |

Rollback conjunto de authority+witness+identidade/tempo e todas as raízes de confiança
não pode ser detectado por software que recebeu somente o estado antigo. Exige uma raiz
não revertida, armazenamento/serviço independente com controles verificáveis ou suspensão
operacional. Não ocultar essa impossibilidade com HMAC, schema, número maior no snapshot
ou mais tabelas locais. Nenhuma dessas propriedades operacionais foi provada neste ticket.

