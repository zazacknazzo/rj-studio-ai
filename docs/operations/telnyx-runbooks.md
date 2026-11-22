# Runbooks de operação futura e rollback

22/11/2026. PLANEJAMENTO/ENSAIO OFFLINE. Não executar procedimentos comerciais neste
ticket. Não há UI móvel/descoberta de IDs, fila operacional ou release operacional
implantados. Papéis são propostos; nomes, plantão/acesso e simulação humana aprovados
são pré-condição de piloto (CX07/08/29). Auditar no ambiente correspondente antes de GO.

Toda intervenção registra case opaco, ator, instante confiável, revision/epoch antes e
depois, razão categórica e prova mínima em repositório restrito. Não anexar corpos,
telefones, tokens, QR, banco ou comprovante privado na issue/repo público.
Autoridade da conta/Segurança/DBA operam domínios independentes; app não tem esse poder.

| Procedimento | Responsável | Pré-condições | Ações/evidências exigidas | Ações proibidas |
| --- | --- | --- | --- | --- |
| Inicialização segura | SRE+Segurança | Autorização daquele ambiente; config validada; acesso restrito | Iniciar semprequarantinado, conferir versão/schema/FK/clock, authority/witness e inventário; readiness distingue ingresso/saída; semworker até gates positivos | Inferir envio dehealth/HMAC/active; ligarTelnyx porenv/flag |
| Canal desconectado/offboarded | Operações+responsável conta | Evento autenticado ou confirmação independente | Ver bloqueio/revision, suspender saídas, manter callbacks/ingressseguros, levantar in-flight/unknown; abrir caso de conta | Apagar lifecycle/effects ou reenviar pendências |
| Reconexão/sync pendente | Responsável conta+SRE | Reautorização específica; número secundário elegível | Obter binding/sync/Coexistence positivos de fonte autenticada; novoepoch; revalidar consent/janela e futuro release auditado | Tratar ACCOUNT_RECONNECTED/sync_pending/echo comoactive |
| Operador assumir atendimento | Operador designado | Seleção privada inequívoca de Conversation/opaqueID; autenticação pessoal | Ler estado, pausar ANTES de responder, GET após POST/replay e confirmar revision/paused ATUAIS (receipt pode ser histórico); mostrarhandoff_active,unresolved_delivery,in_flight_possible; só então BusinessApp; registrarcase | Esperar echo para pausar; expor clientes para descobrirID; prometer recall |
| Pausar/retomar automação | Operador+supervisor | Permissão/allowlist e revision atual; interface segura aprovada | Pause idempotente operationID; conferir estado. Resume só intenção futura, canal/consent/janela atuais, semunknown/conflict; novo inbound source>cutoff | Limpar receipt/cutoff, reabrir trabalho antigo, tratar resume como reconciliação |
| Outbound unknown | Operações+recovery | Quarentena da Conversation e inventário preservado | Levantar key/escopo/bytes/markers/tempos do ledger, verificar provider autorizado; registrar accepted ou prova de não submissão por processo aprovado; bloquear oldwork | Converter emretryable automaticamente; nova key; retry após24h ou apagarunknown |
| Status conflitante | Operações+integração | status_conflict preservado | Correlacionar provider+ID+channel+Customer/account/profile em ambiente restrito; guardar eventos contraditórios; decisão autenticada e revisada | Escolher “último timestamp” e sobrescreverterminal, apagarflag |
| Falha/lock/disco SQLite | DBA+SRE | Alerta ou503/commitincerto | Suspender processamento, observar lock/disco/fsync/integridade e backlog;503 permite replayidêntico; backup/restore sóquarentena | ACKantescommit; retry deHTTPambíguo; cópiaDBvivo semWAL |
| Webhook indisponível | SRE+integração | Alarmes/deadline/failover observado | Verificardisponibilidade semsecrets, acompanhar tentativas do provider, aplicar contingência aprovada com a mesma dedupe/fence; compararcontagens/casos | 2xxfalso, processarsemassinatura, endpointalternativo semmesmosgates |
| Restore/quarentena | DBA+recoverer+approver distintos | Autorização específica de restore e raizindependente disponível | Restaurar consistentemente semegress; novoepoch, inventário externo inclusiveórfãos, reconciliarunknown, obterprovasatuais; testesantirollback; auditdeaprovador distinto | Restaurar authority/witness junto, resetrevision, releasebaseadoemSQLite, workersantecipados |
| Retentativas/failover provedor | Integração+SRE | Contrato real deURL/tentativas conhecido e métricas | Mesmoevent/Message/key/escopo, commitantesACK, replaysdedupados; contar422/503; investigar esgotamento e abrircasohumano | NovoIDparaocultarretry; doubleprocessing entreURLs; retry outbound cego |
| Rotação/perda de segredos | Segurança+responsável conta | Incidentecase, inventário e novo material por canalconfiável | Suspender saída/revogarantiga, comprovarcredential→org/profile/número, publicarpublickeypordeployaprovado, testeassinaturareal só sobautorização, auditar acessos | Chaveemrepo/chat/log; dupla key sem prazo; inferirbinding debody |
| Desativação emergencial | Incidentcommander+SRE/Segurança | Qualquer gatilho deparada; autoridade revogável | Revogarpermits/access emraizexterna, parar workers, manterobservação/ingressseguro quandoaprovado, inventariarin-flight/unknown e avisaroperador | DeletarDB/filas como kill; presumirqueHTTPjámarcadofoicancelado |
| Rollback de versão | Release+DBA+Segurança | Autorização, compatibilidade schema e backupverificados | Primeirodesativarsaída; rollbackdecodecompatível preservandoDB/ledger/fences, reexecutar testes; schema0023não tem downgradeoperacional autorizado | gitreset/forcepush/mainmerge; trocarDBporbackupantigopara“compatibilizar”; repetirenvios |
| Encerramento seguro de piloto | Productowner+Operações+SRE | Piloto FUTURO explicitamenteautorizado; horário/limites atingidos | Revogarpermissões, pararworkers, reconciliarouholdtodosunknown, conferircontagens/custos, registrarretention/backup e decisãodeencerramento | Deixarautorizaçãotemporáriasemexpirar; promoverprodução porausênciadefalha |
| Unsupported/intervençãohumana | Operações+integração+privacidade | Alerta422/retries oucaseautenticado | Nãoexecutargerador; procurarfonteautorizada semcopiarpayload, pausarantesdehumano, abrirreferênciamínima/emfilaaprovada; esgotamentosemresoluçãoparaoperador | 2xxparasumirretries, baixar mídiaautomaticamente, inventar texto/Customer, registrarcoordenadas/contato emlogs |

## CX29: decisão por formato e fila operacional proposta

| Entrada | Comportamento existente offline | Procedimento seguro futuro / saldo |
| --- | --- | --- |
| Mídia/anexo/áudio/vídeo | Inboundnão suportado→422+agregado; echo humano de mídia ainda pausa | Humano no BusinessApp após pausa; sem downloadautomático/URLs privadas; suporte novo exige spec |
| Localização/contacts/interactive | 422, sem inbound inventado ougeração | Operador avalia finalidade/acessonecessário; não guardar coordenadas/endereço emcounter |
| Evento/body/status/lifecycle desconhecido | Rejeição conservadora; não ativar | Integração confere fonteoficial e testa antes de ampliar parser; alerta comrazãofinita |
| Arrays/batch inválido/siblingunsupported | Nenhum siblingcomita;422 (counterfailure503) | Repetir envelopeoriginal apenas porprovider; não fabricar lote válido parcial |
| 422repetido | Counter contaOBSERVAÇÕES, nãoMessagesúnicas | Alerta proposto≥3rejeições/min ouumaforma nova, triagem≤60s emsessãopiloto |
| Retries/failover esgotados | Não há fila/composiçãoexterna emT13 | Casehumano e comparação comfonteautorizada; impedirperdasilenciosa/temporal prolongada |
| Necessidade de humano | API depausa existe, workflowmóvelaindanão | Operadordesignado; fila comcaseIDopaco,motivo,prioridade,owner,age,estado e referênciarestrita; acesso/audit/minimização exigemimplementação e aprovação |

O agregado de rejeição NÃO identifica qual Customer ou conteúdo ficou sem tratamento.
Não é arquivo de recuperação. Fila mínima/encaminhamento e fonte autorizada para
identificar o caso são gates antes do piloto; se a identificação segura não existir,
não iniciar piloto. Alertas propostos não estão implantados por estes documentos.

## Ensaio local permitido

Somente fixtures/testes sem rede: scripts/check_telnyx_offline.py, venv próprio eDB
temporário, sem conta/segredo real. test_automation_operations verificaauth/revision/
pausa/resume; test_telnyx_operational_readiness verificaordemrevoke/marker;
test_offline_recovery verificaepoch/proofs/release/revoke e store semprequarantinado.
Simulação automatizada não é teste humano de celular nem drill de infraestrutura.
