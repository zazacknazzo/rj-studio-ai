# Plano de piloto real — NÃO EXECUTAR

22/11/2026. A existência deste plano não autoriza conta, HTTP Telnyx, ativação, envio,
piloto, produção ou merge. Ticket13 termina com auditoria final do orquestrador.
Os nomes/conta/número não são conhecidos ou aprovados; nenhuma credencial é criada.
Toda execução abaixo depende de autorização explícita FUTURA, com escopo separado.

## Autorizações em duas etapas

1. Primeiro: auditoriaT13 e autorização específica de validação da infraestrutura,
   authority/witness/backup/IAM/ingress. Evidência independente no ambiente de destino;
   AUD01 não fecha por laboratório/quarentena. Sem autorização, nenhuma conta é acessada.
2. Depois: productowner/orquestrador aprovam piloto delimitado após resolver todos
   bloqueadores aplicáveis (ou exceção formal específica com dono/mitigação/prazo).
   Não há exceção aceita aqui. NaturalidadeCX26 exige trabalho próprio sem alterarLLM
   incidentalmenteT13. Produção exige decisão posterior própria.

Registro restrito de autorização deve identificar: organização/WABA/profile/número
secundário e dono, credencial vinculada, participantes/opt-in, finalidade, operadores/
plantão, janela de tempo, número máximo de mensagens, orçamento total, versão/SHA,
origem do tráfego, métricas/pontos de medição, gatilhos deparada e aprovador.
Tokens/PII nunca constam da issue/repo público. Aprovação não pode ser por silêncio.

## Checklist de elegibilidade e preparação

| Gate futuro | Evidência necessária | Dono / impossível demonstrar somenteoffline |
| --- | --- | --- |
| Conta/número autorizados | Titular confirma número secundário+55 e controle da conta; principal preservado | Responsávelda conta; autorização e elegibilidadeindividual reais |
| Elegibilidade Telnyx/Meta | Confirmação pelo caminho correto de onboarding, região/conta/portfolio/número | Integração+conta; documentação geral não certifica estenúmero |
| Coexistence | BusinessApp mantido registrado, app suportado, administrador deportfolio; opçãoCoexistence noEmbeddedSignup | Conta; não usar signupstandard/AddNumber que migra caminho |
| Sync/binding atuais | is_on_biz_app verdadeiro e estado elegível/active corroborados; syncprogress/autenticidade/cutoff | Integração; eventos internos dehistórico/sync podem não chegar ao cliente |
| Infra antirollback | Authority/witness/ledger completos, credenciaissegregadas, restore/rollback/falha/crash testados | SRE+Segurança; AUD01 precisa teste real de cada raiz e composiçãofinal |
| Assinatura real | Publickey com proveniência, runtime/libsodium, clock/NTP; rawbytes/TLS/proxy/headers validados | Segurança+SRE; teste real somente quandoautorizado |
| Consentimento | Prova de cada voluntário, finalidade/escopo/validade, workflowrevoke auditável | Privacidade+Operações; nenhum cliente presumidamenteconsentido |
| Janela/template | Voluntário inicia conversa elegível; free-form sójanela atual; template real só com suporte/aprovação próprios | Operações; V1 não temsenderdetemplate, não iniciarfora dajanela |
| Operador/fila/alerts | Pessoasdesignadas, caminho privado para selecionarConversation e pausar nocelular, fallbackunsupported resolvido | Operações; ensaiohumano e fila real ainda gatesCX08/29 |
| Release/CI | Checks finalSHA, secretreview, rollout/rollback compatíveis e autorizaçãoauditada | Release+orquestrador; CInão autorizaenvio |
| Custo/latência | Tarifas/Telnyx+Meta atuais e orçamento, custoLLM e E2Edefinidos | Produto+Financeiro; preços/uso reais não medidosT13 |

Fontes públicas conferidas22/11:
[Coexistence Telnyx](https://developers.telnyx.com/docs/messaging/whatsapp/coexistence),
[webhooks Coexistence](https://developers.telnyx.com/docs/messaging/whatsapp/coexistence/webhooks),
[WhatsApp Business Policy](https://whatsappbusiness.com/policy/).
Não seguir passos de onboarding neste ticket. Compartilhar histórico é escolha futura
de privacidade; não importar seis meses por conveniência e não confundir história com
consentimento. Sync/reconnect não tornam trabalho antigo reenviável.

## Exposição proposta, sujeita a aprovação explícita

Número secundário exclusivo do ensaio; até5voluntários com opt-in verificável,
até20respostas controladas, até60min e teto total propostoUS$5 para a sessão.
São LIMITES propostos, não estimativa de tarifa ou autorização financeira atual.
Sem campanhas/followups, mídia/location, BSUIDoutbound, templates ou clientes externos
não incluídos. Cada pessoa pode revogar/encerrar a qualquer momento.

Sequência futura: verificar todosgates; registrar autorização temporária e versão;
voluntário envia primeiro; observar receive→journal→reply→acceptance/status com IDs
saneados; ensaiarpausa ANTES dohumano, resume com novo inbound eclockconfiável;
replay/restart/desconexão/rotaindisponível apenas conforme plano de falhas aprovado;
simularopt-out e revogação; conferir custos/backlog e encerrar com permissõesrevogadas.
Restore destrutivo ou falha física em canal real exigem autorização própria adicional,
não são deduzidos do plano de mensagens controladas.

## Parada e rollback

Interromper novas saídas imediatamente por: qualquer envio duplicado/fora do escopo,
consentimento faltante/revogado, unknown/conflict sem operador, perda de auth/fence/
clock/SQLite, assinatura inválida inesperada, mudança de binding/lifecycle, riscoPII,
não suportado sem tratamento humano seguro, perda de operador, teto de mensagens/
tempo/custo, latênciaACK fora decontrato ou decisão do participante/productowner.
Preservar emvoo/unknown; revogar na raiz e pararworkers. Não apagarfilas/keys.
Rollback de código mantém DB/ledger/fences compatíveis e quarentena; nunca restaurar
snapshot antigo para repetir envios. Fechar casos humanos e registrar exposição real.

## Aceitação final do piloto futuro

Todos os participantes/recebimentos/saídas correlacionados sem duplicação/consent
indevido; pausas/opt-out/revogações e retorno futuro verificados; ingress/callbacks/
retries/unknown observáveis; zeroP1/P2 novo pendente no escopo; custos dentro doteto.
Targets históricosCX20/#6: p95E2E≤8s e custoLLM≤US$10/1000replies completas,
sem alteração tácita; pontos e tamanho deamostra ratificados antes da execução.
Amostra de20mensagens é um smoke restrito, insuficiente para SLA/escala/comercial.
Productowner/orquestrador dão parecer separado sobre maisensaios, encerramento ou
gateposterior. Nenhum sucesso promove produção automaticamente.
