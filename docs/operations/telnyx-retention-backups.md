# Retenção, LGPD e backups — matriz completa T13

22/11/2026. Inventário obtido de sqlite_master/PRAGMA table_info num SQLite sintético
migrado até0023, sem conteúdo comercial. Todas as24tabelas da aplicação são listadas,
além das fontes externas simuladas, backups e evidências. Nenhum prazo novo/expurgo
automático foi ativado. Prazos abaixo são PROPOSTAS para decisão de privacidade,
jurídico/produto e operação antes do piloto; não declaração de conformidade LGPD.

A necessidade é a finalidade indicada, limitada por hold de unknown/conflito/replay.
“Sem expurgo automático” é estado atual + gate aberto, não permissão de retenção eterna.
Revisar necessidade a cada90d; se não houver limite demonstravelmente seguro, bloquear
o piloto até aprovar tombstone/namespace/controle anti-reuso e expurgo verificáveis.
A retenção de Messages já existente não cobre todas as categorias nem secure erase.

| Tabela/categoria | Finalidade/necessidade | Dados envolvidos | Prazo proposto/hold | Minimização e expurgo | Idempotência/reuso de identificadores | Backup/restore | Critério de aceite |
| --- | --- | --- | --- | --- | --- | --- | --- |
| conversations | Vínculo Customer/Conversation | provider/endereço,IDs/tempos | 90d após encerramento, proposto | Minimizar endereço; apagar só sem trabalho/fences dependentes | IDs locais podem ser reutilizados; não usar como idempotency | Backup≤30d proposto; restore semprequarentena | Replay não recria Conversation autorizável |
| messages | Contexto e histórico mínimo | texto/endereço/IDs/in_reply_to | 90d após última atividade, proposto | Purge atual só trabalho terminal elegível; pedido erasure revisado | Corpo pode sair; conservar recibo/fence; risco IDnumérico reusado | WAL/freepages/backups também contêm texto; expiração/cripto a provar | Purge+replay+restart não readmite inbound |
| message_processing | Claim/gate da geração | inboundID,state,owner,lease,revision | Com Message enquanto não terminal;90d terminal proposto | Não remover claim aberto ou revision antes de encerrar | Apagar sem receipt pode regenerar; preservar tombstone antes | Não restaurar processing antigo como autorização | Unknown/lease/restart sem geração dupla |
| generation_metrics | Uso/custo/latência | provider/model/tokens/custo/IDinbound | 30d individual;90d agregado proposto | Remover ligação Customer após agregação; sem prompt/resposta | Não é fonte de dedupe; cascade atual acompanha Message | Somente agregados em relatório público | Agregado coerente, sem texto/endereço |
| appointment_intakes | Preferências transitórias para handoff | serviço/dia/período/profissional/tokens | 30d após atendimento/encerramento, proposto | Revisão com privacidade; não transformar em perfil permanente | Estado/tokens não podem reativar após delete/restore | Incluído em backup restrito≤30d | Sem appointment inventado ou revival de episódio |
| conversation_handoffs | Estado humano e proteção da automação | active/owner/reason/tempos | Enquanto identidade puder reaparecer; revisão90d | Remover só com tombstone/gate de Customer/conversa | Delete sem gate poderia habilitar geração/envio | Snapshot antigo não revoga handoff atual externo | Restore antes de handoff permanecequarantinado |
| conversation_operation_ids | Seleção administrativa opaca | conversationID/opaqueID | Vida da Conversation + tombstone até encerrar dedupe | Não publicar índice de clientes; invalidar vínculo ao remover | Nunca reutilizar opaqueID para outro Customer | Backup restrito; old ID não autentica | Reuso/lookup indevido negados |
| conversation_automation_controls | Pause/revision/cutoff | channelID,paused,revision/resumed_at | Sem expurgo automático; revisão90d/tombstone projetado | Não apagar pausa para atender retenção; pseudonimizar só com desenho | Perda reabre gates; revision não pode regredir | Authority externa e quarentena prevalecem | Purge/restart/replay conserva bloqueio |
| automation_operation_receipts | Replay/audit administrativo | operationID,actor,revision,result sem corpo | 180d audit proposto; dedupe até tombstone seguro | Resultado mínimo; revisão de acesso/necessidade | Apagar permite replay de operationID antigo; barrar namespace expirado | Audit externo retém decisões de restore | Replay não aplica operação novamente |
| operational_events | Journal de fatos operacionais | event/message/customer/channelIDs,kind/reason/tempos | Sem expurgo automático; revisão180d/tombstones | Não há corpo; IDs continuam dados pessoais/pseudônimos | Necessário replay/ordering/pausa/lifecycle; não eliminar arbitrariamente | Backup e restauração com epoch/reconciliação | Evento antigo não ganha efeito novo após expurgo |
| operational_event_aliases | Correlacionar referências externas | namespace/messageID/eventID | Mesmo horizonte de journal/dedupe | Não usar alias para fundir clientes; minimização após spec | Excluir pode perder correlação; risco reuso namespace | Conservar junto ao journal ou tombstone equivalente | Replay com alias não gera nova Message |
| human_pause_effects | Deduplicar efeito de intervenção | event/conversation/provider/channel/customer/messageIDs,revision | Sem expurgo automático; revisão180d | Tombstone de identidade antes de remover dados identificáveis | Perder permite repausa/risco lógico em replay | Restore antigo não autoriza resume | Echo duplicado após resume não reaplica efeito |
| inbound_event_receipts | Dedupe/source após purge de texto | IDs/endereços/aliases/source/first_receipt | Sem expurgo automático; revisão180d | Sem body/hashbody; tokenização requer desenho anti-reuso | Apagar reabre geração por inbound antigo; janela provider insuficiente | Retém além de conteúdo; restore quarantinado | Replay com novoenvelope não readmite Message purgada |
| outbound_deliveries | Estado/ordering/idempotência de entrega | IDs/endereço,state,key,fingerprint,markers/conflict | Não terminal/unknown/conflito: hold; terminal90d proposto | Purge atual apenas elegíveis; não apagar unknown/conflito | IDnumérico reutilizável; key não reutilizável e MAC externo retido | Backups anteriores a accepted exigem inventário externo | Oldkey não ganha retry ou outra key |
| delivery_attempts | Prova potencial de submissão e non-submission | owner,attempt,status,providerID,markers/retryevidence | Enquanto delivery retido; holdunknown; terminal180d proposta de política | Cascade terminal atual existe: não afirmar retenção180d implementada | Marker crítico; terminal pode sair só mantendo HTTPidentity/dedupe/ledger | Inventário externo precisa cobrir tentativas perdidas no snapshot | Unknown nunca some para virar retry |
| delivery_status_events | Correlação scoped e contradições | provider/event/message/channel/customer/account/profileIDs,status/time | Sem expurgo automático; revisão180d/holdconflict | Sem texto; reduzir IDs só com tombstone/correlação comprovada | Apagar evento pode perder conflito/terminalidade | Restauração não constitui reconciliação de provider | Status cedo/replay/contraditório preservado |
| pending_delivery_statuses | Callbacks legados aguardando associação | provider/messageID,status/error/tempos | Até reconciliar ou hold; revisão30d | Sem descartar status órfão por idade sem investigar | IDdeprovider reutilizado exige escopo; canal legado limitado | Snapshot pode perder pending; inventário operacional necessário | Órfão não vira delivered de outra entrega |
| channel_lifecycle | Binding/estado/epochlocal do canal | WABA/channel/org/profileIDs,state/revision/evidence | Binding ativo +180d audit proposto; bloqueio sem expurgo | Desativar não apagar; refs mínimas de verificação | Delete/reinsert não pode ativar; reuso de número precisa novo binding | Estado ativo restaurado não prova atualidade | Disconnect/reconnect/rebinding sem revival |
| channel_lifecycle_effects | Deduplicar efeitos de lifecycle | event_record_id | Mesmo horizonte journal/lifecycle | Conservar fence/tombstone antes de expurgar | Apagar pode reaplicar ou perder bloqueio | Backup inclui efeito; autoridade externa é gate | Replay/restart preserva estado bloqueado |
| telnyx_http_requests | Identidade exata privada por key | submissionkey,versão,keyID,requestMAC | Sem expurgo automático; revisão180d/holdunknown | MAC sem corpo; não é anonimização; rotação não perde verificação | Guards impedem keyreuse após purge; apagar enfraquece segurança | Chave de integridade foraDB; restore não prova frescor | Key/bytes/escopo imutáveis após purge/restart |
| telnyx_consent | Permissão temporal por canal/Customer | endereço,evidenceRef,grant/expiry/revoke | Vigência; prova/revogações180d propostos sob avaliação jurídica | Sem comprovante privado noDB; audit de mudanças futuro é lacuna | Revogação não pode sumir em purge/upsert/restore | Fonte atual independente prevalece; snapshot não renova grant | Revogação concorrente bloqueia autorização posterior |
| telnyx_policy_clock | High-water temporal | singleton/checked_at | Vida da identidade/canal; sem expurgo | Sem PII direta; não resetar para reabrir janela | Reset permite reavaliar tempo antigo; não é dedupe | Clock externo/witness deve bloquear rollback | Regressão não reabre24h |
| telnyx_ingress_rejections | Observabilidade limitada de rejeições | reasonfixa,count,first/lastlocal | 30d buckets/agregados proposto; contadoratual sempurge | Sem payload/IDs/hashbody; reset só via política e audit | Não é recibo/dedupe; retries incrementam, não mensagens únicas | Backup não serve para recuperar mídia privada | 422durável; counterfailure503; cardinalidade finita |
| alembic_version | Histórico/schema | revision | Vida doDB | Não contém Customer; sem expurgo isolado | Schema válido não prova frescor | Guardar versão junto do manifest de backup | Upgrade linear/integridade/FK |
| Authority/Witness/Audit externos (simulados) | Frescor/roles/inventário/decisão independente | epoch/revision/digest,keys,intenthash,refs/actor | Hold de safety contínuo; audit180d proposto | Minimizar refs; tombstones somente com revisão do threatmodel | Perder maior revision/keys revive release; não apagar porTTLde24h | Domínios de backup distintos; rollback conjunto é gate impossível local | Rollback da authority sem rollback do witness é detectado |
| Backups/WAL/SHM/freepages | Recuperação consistente e forense mínima | Todos os dados presentes na época | Backups rotativos≤30d proposto; incidenthold revisado | Criptografia/ACL/expiração/chaves; cópiaSQLiteAPI+manifest; sem cópiaDBvivo solta | Backup antigo perde dedupe/revoke; entrar semprequarentena | Erasure precisa agenda de expiração ou cryptoerasure verificável | Restore íntegro+quarentena+reconciliação; powerloss real pendente |
| Evidências de auditoria/CI | Provar mudanças/testes sem dados reais | SHAs,versões,resultados saneados/atores de teste | 180d proposto; decisõesduráveis revisadas anualmente | Não publicar DB/JUnitcomPII/logsbrutos; fixtures sintéticas | Hash de relatório não é fencing; não usar como permissão | ArtifactsCI atuais14d; relatório/audit180d propostos; repo público só técnicos/sintéticos | Reprodução em clone limpo sem segredos/história pessoal |

## Expurgo, direito de apagamento e verificações

Responsável de privacidade recebe pedido sem divulgar existência de Conversation a
terceiro, verifica identidade proporcionalmente e define base legal/necessidade/exceções
com jurídico. DBA inventaria tabela por tabela, estado pendente, logs/APM, réplicas,
WAL/freepages, evidências e backups. Revogar/pausar precede exclusão quando aplicável.
Executar somente ferramenta/política aprovada; reter informação mínima de safety quando
justificada e comunicada. Não usar “LGPD” para apagar unknown ou dedupe sem mitigação.

O purge atual pode apagar corpo/delivery terminal e suas attempts por cascade, mas
mantém receipts/journal/requestidentity que protegem replay/keyreuse. Isso não prova
apagamento físico: SQLite/WAL/freepages/snapshots precisam tratamento operacional.
VACUUM/checkpoint/secure_delete, cryptoerasure e descarte de backup exigem procedimento
testado sob carga e inventário de cópias; não serão executados em dados reaisT13.
Tombstones com HMAC podem minimizar exposição, mas chaves/reuso/rotação/expiração e
correlação ainda exigem spec/migration/testes próprios. Um hash sozinho continua
correlacionável e não autoriza afirmar anonimização.

## Backup e restore

- DBA/SRE: snapshot consistente por SQLite backup API ou ferramenta equivalente
  comprovada, manifest com versão/schema/hash/cutoff e dados criptografados sob ACL.
  Banco vivo não é copiado ignorando WAL. RPO/RTO propostos (nãoSLA):15min/60min,
  sujeitos a teste no ambiente real antes do piloto.
- Segredos de integridade, authority e witness não compartilham restore unit comDB.
  Backups de authority/witness exigem monotonicidade/raízes independentes comprovadas.
- Toda restauração, migração reversa ou rollback de versão começa sem workers/egress,
  com epoch novo independente e inventário completo de possíveis submissões.
- Integrity_check/FK/migrations aprovados são necessários, insuficientes para frescor.
  Reconciliação não troca keys/unknown; provas atuais de canal/consent são obrigatórias.
- Expiração dos backups≤30d e restauração de dados sujeitos a apagamento devem ser
  ensaiadas com fixtures e log saneado. Consentimento/apagamento pendente não revivem
  silenciosamente por uma cópia antiga. Evidência de deploy e análise jurídica pendentes.

Testes existentes reproduzíveis: test_telnyx_messages.py (purge/replay), 
test_telnyx_submission.py (unknown/terminal purge/newlogicalkey),
test_telnyx_sender_adversarial.py (MAC/keyreuse depois purge),
test_telnyx_submission_migration.py e test_migrations.py (histórico/restore/FK).
Os testes T13 recovery acrescentam snapshots anteriores aos fatos e inventário externo.
Não somar contagens sobrepostas; resultados atuais no relatório A–P. CX01 continua aberto.

