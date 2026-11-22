# Primeiro teste real — procedimento proposto, NÃO EXECUTADO

G0 não autoriza conta, ativação, webhook real nem envio. Os dois gates estão
**NO-GO** no [parecer de readiness](telnyx-g0-readiness.md). Este documento prepara
uma execução futura; não fornece comandos que conectem conta ou enviem mensagem.
Pedir auditoria do código/evidências/checklist antes de qualquer conexão real.

## Registro de autorização futuro

Após resolver os bloqueadores pertinentes, registrar em local restrito: auditor,
decisor, operador titular/suplente, SHA/release/configuração verificados, ambiente,
janela de início/fim, número secundário e participante por referências opacas,
finalidade/consentimento vigente, máximo de **uma resposta**, orçamento aprovado,
condições de parada e validade da autorização. Falta de limite financeiro ou
validade mantém NO-GO. Aprovação de ingresso e de saída são registros diferentes.
Não registrar tokens/chaves/telefones/PII no GitHub ou neste arquivo.

## Etapa 1 — ingresso real isolado (gate próprio)

1. Auditor aprova R01–R15 aplicáveis e o escopo exclusivamente receive-only;
   decisor concede autorização explícita de conexão para janela limitada.
   Não copiar o `active`/opt-in SQL do harness para ambiente operacional.
2. SRE atesta release com ingress separado, sem processamento/generator/sender,
   sem credencial de outbound, deny de egress externo ao DB e sem rotas/CLIs
   alternativas. Evidenciar negação após reboot, restore e rollback no destino.
   Secrets de ingress e administração vêm do mecanismo seguro aprovado.
3. Confirmar TLS/proxy, assinatura com chave da conta por proveniência confiável,
   relógio, limitação streaming/duplicatas de headers, persistência antes do ACK,
   ausência de payload/Authorization em logs/APM e gate ACK conservador de 2 s.
   Resolver a divergência 204/2xx versus200 no caminho configurado.
4. Só após a autorização configurar webhook/routing no número secundário,
   preservar Business App e manter automação/egress desabilitados. Registrar
   comprovação do binding sem dados da conta no repositório público.
5. Participante previamente autorizado envia texto de teste sem PII; operador
   verifica uma admissão durável e ACK, zero chamadas de LLM, zero outbox/envio.
   Repetição do mesmo envelope não pode criar Message adicional. Testar rejeição
   de assinatura inválida e fluxo humano para unsupported em ensaio aprovado.
6. Encerrar a janela e desconectar o endpoint conforme autorização, conservar
   evidência mínima com retenção aprovada. Medir ingresso no destino; não inferir
   resultado de envio, custo de LLM ou elegibilidade a partir desse sucesso.

Pausar ingresso se assinatura/binding/clock/DB/proxy/retention/operador falhar,
ocorrer retry/failover sem tratamento ou surgir qualquer trabalho de saída.
Contenção e exclusão posterior seguem os runbooks aprovados; não descartar
evidências críticas ou responder2xx apenas para esconder formatos rejeitados.

## Etapa 2 — uma única resposta real (novo gate, atualmente bloqueado)

1. Auditor verifica solução operacional AUD-01/AR-02: raízes independentes e
   autenticadas, authority/witness atuais, ledger cobrindo todo possível HTTP,
   fences em boot/restore/reboot/rollback, IAM/release/revoke e reconciliação.
   Executar fault injection e negativos no destino sem destinatários comerciais.
   Snapshot antigo, autoridade indisponível/contraditória, proof vencida, store
   legado, comando manual ou caminho alternativo nunca podem conceder envio.
2. Revalidar R01–R20 de saída: identidade atual de conta/org/profile/WABA/número/
   destinatário, elegibilidade real de Coexistence, estado atual active, opt-in
   vigente e workflow de revogação utilizável. Reconnect, echo ou backup não
   substituem prova. Consentimento revogado antes do marker deve negar saída.
3. Operador testa pausa antes/durante processamento, mudança de canal, perda de
   autoridade e kill switch externo; confirmar zero novas submissões após a
   barreira. Marker já commitado pode estar em voo: não prometer recall.
   Em in-flight/unknown, interromper e reconciliar sem repetir.
4. Participante autorizado inicia Message livre de PII. Confirmar janela atual
   menor que 24 h; sem janela não enviar e não trocar por template. Somente fatos
   reais aprovados e resposta final revisada pelo humano podem ser selecionados.
   O G0 usa LLMDecision/Salon Knowledge sintéticos: não há aceite conversacional
   nem configuração de modelo real implícitos neste procedimento.
5. Humano aprova **o request exato** (destino, canal, conteúdo, SHA, chave estável
   por entrega e escopo) por mecanismo operacional autenticado/auditado. Não
   alterar DB, flags ou gates para permitir o teste. Exigir permit externo de
   uso único e limite externo de uma resposta; reduzir concorrência sozinho
   não protege contra bypass/restart. Esse mecanismo ainda precisa existir.
6. Só com gate explícito GO de saída e liberação atual, executar uma submissão
   pelo caminho aprovado. Registrar receipt/marker/aceitação e status mínimos
   sem corpo/segredos/PII públicos; verificar acceptance separadamente de
   sent/delivered/read. Inconclusivo, timeout,409/422 ou conflito: parar, preservar
   unknown e chave original, não reenviar nem gerar outra chave.
7. Revogar autorização/egress ao atingir uma tentativa potencial, término da
   janela, orçamento ou primeiro incidente. Confirmar kill switch e leitura do
   estado atual, registrar resultado e solicitar auditoria pós-teste. Falha
   de status não autoriza uma segunda resposta. Produção/merge seguem proibidos.

## Critérios de parada e rollback

Parar imediatamente em destinatário errado/duplicata, consentimento ausente ou
revogado, mudança de binding/active, perda de operador, authority/witness/ledger
ou clock, auth/DB inválidos, retry tempestivo sem tratamento, unknown/conflito,
logs com dados indevidos ou qualquer limite excedido.

Rollback de código mantém DB/ledger/fences/identidades compatíveis. Nunca restaurar
SQLite antigo para repetir envio ou limpar unknown/pause/lifecycle/consentimento.
Restore começa com egress negado externamente e depende de reconciliação e nova
autorização atual; fonte restaurada não aprova a si mesma. Nada disso foi executado
em conta/infraestrutura real neste G0.
