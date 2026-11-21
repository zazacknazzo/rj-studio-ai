# Ticket 11 — sender Telnyx WhatsApp, validação offline

Data: 21/11/2026, America/Sao_Paulo. Escopo autorizado exclusivamente offline.
**Candidato funcional final:** `a049753205001d81a9ac0f11253eab5760a2f017`.
Checkpoint final de código/testes: `789c2c89328b0472506c3d34593dfe741c052883`
(altera somente expectativa de head histórico após o candidato funcional).
O SHA da entrega documental posterior deve ser obtido de origin e consta na entrega/issue;
não se tenta prever o hash do próprio commit neste arquivo.

## A. Resultado técnico e dois pareceres

Sender textual free-form implementado como componente dormente com transporte
explicitamente interceptado. Runner e executor restringem este sender a claims Telnyx;
preparam o request antes da autorização SQLite, vinculam seu MAC à chave durável na
mesma transação dos marcadores e executam uma única troca após commit. A resposta exige
identidade e schema conhecidos válidos. Incerteza remota fica unknown sem reenvio.

**Elegibilidade OFFLINE:** candidato elegível à aprovação após auditoria direta;
duas execuções integrais finais verdes e revisões independentes concluídas.
As três perspectivas independentes verificaram as correções; o aceite cabe à auditoria
direta do orquestrador. Não é uma aprovação concedida pelo implementador.

**Uso OPERACIONAL/PRODUÇÃO: NO-GO.** AUD01 permanece aberto. Não há quarentena externa,
recovery operacional, composição HTTP/credenciais, ativação ou saída Telnyx no runtime.
Tickets12–13, piloto, envio real e merge não foram autorizados nem implementados.

## B–D. Baseline, branch, diff e arquivos

- Repositório: `zazacknazzo/rj-studio-ai`.
- Baseline exata T10: `07c1b7dc150d7eb1776b97d891cd29347adffd37`.
- Branch publicada exclusivamente: `codex/telnyx-coexistence-11-sender`.
- Auditoria prévia lida pelo GitHub em `502bca89e64b45e981ad9c5f2eeb189aad3dd9e6`;
  nenhuma importação/merge dessa branch documental.
- Main conferida: `af1c9eb862a4180ca6b9e537349e4f8abaa2bb29`; T10 permanece na baseline.
- [Comparação completa contra T10](https://github.com/zazacknazzo/rj-studio-ai/compare/07c1b7dc150d7eb1776b97d891cd29347adffd37...codex/telnyx-coexistence-11-sender).
- Diff final: **34 arquivos, +3346/−9 linhas**, 0 atrás da baseline; inventário ao final.

## E. Contrato HTTP oficial verificado

Consultas públicas realizadas em21/11/2026, sem API de conta, credenciais comerciais
ou chamadas ao host api.telnyx.com. A ferramenta web não conseguiu abrir a página geral
de idempotência; seu Markdown oficial foi lido diretamente com TLS/proxy gerenciados.

| Fonte | Evidência e limite |
| --- | --- |
| [Endpoint WhatsApp](https://developers.telnyx.com/api-reference/whatsapp-messaging/send-a-whatsapp-message) | POST `https://api.telnyx.com/v2/messages/whatsapp`; declara Idempotency-Key opcional. Obrigatório localmente. |
| [OpenAPI oficial](https://raw.githubusercontent.com/team-telnyx/openapi/master/openapi/spec3.json) | Operation SendWhatsappMessage referencia `messaging_WhatsappMessage` e resposta200 `WhatsappResponse`; não confundir com schema SMS. |
| [Idempotência](https://developers.telnyx.com/docs/development/api-fundamentals/idempotency) | Organização+método+path+chave; query mesmos parâmetros/valores; body byte-identical. Headers comuns não compõem escopo externo. |
| [SDK Python](https://github.com/team-telnyx/telnyx-python/blob/master/README.md) | Padrão2retries em conexão/408/409/429/5xx e timeout1min; timeouts também repetidos. SDK não usado. |

Hashes SHA256 dos documentos efetivamente consultados:

- OpenAPI: `fc59cb60a25c5091e73889842c808f1db7b4c0bb36bbb0228ee9ed2f629eca18`.
- Idempotency Markdown: `ffb46a8a2039abc459544860a2ebf5d15917b8f4c1b83947291df26cca4c8e0d`.
- SDK README: `09fd32891da69befceb88f21dc4ab4878b5fe02e78fb3adbba1f079fb56c3743`.

O formato é `from`, `to`, `type=WHATSAPP`, `messaging_profile_id` UUID e
`whatsapp_message={type:text,text:{body,preview_url:false}}`. Sem template/fallback.
A organização vem do binding autorizado, não de um campo inventado no body. A futura
composição de credenciais precisará comprovar a organização real da conta; aqui não
há credencial nem verificação comercial. A OpenAPI atual aceita BSUID no request,
mas o subconjunto V1 deliberadamente exige E.164 e preserva CX37.

A resposta oficial usa `data.id` string (não declara formato UUID), `from` objeto,
`to` array e `body`. O schema omite listas required de identidade; a política local
exige identidade completa, um destinatário e texto correspondente. Conhecidos opcionais
presentes também devem respeitar tipos/enums/formato: from.status/line_type,
carrier, encoding, received_at RFC3339, wait_seconds number|null e campos textuais.
Modalidades conhecidas conflitantes são rejeitadas; adições desconhecidas são ignoradas.
Apenas200 tem contrato de sucesso publicado neste endpoint;201/202/204 não são aceitos
por inferência. Nenhum status no HTTP promove sent/delivered/read.
Consulta GitHub do candidato a049753 retornou statuses=[] e workflow_runs de PR=[];
isto não é prova universal de ausência de CI, nem evidência de CI executada.

409/10036 significa processamento em andamento;422/10027 significa query/body divergente
sob a chave. Só sucessos2xx podem ser replayados por **até24h**; não há prova de retenção
mínima integral. Expiração pode executar novamente. Documentação recomendar replay
não concede autorização interna para reenviar unknown. Timeouts são orçamentos locais,
não promessa de SLA remoto.

## F. Request determinístico e identidade durável — CX35

`TelnyxRequestSigner` recebe organização/profile e uma chave de integridade local
injetada, independente de credenciais Telnyx. Exige chave bytes>=32 e identificador
opaco. O request imutável usa POST/HTTPS/host/path fixos, query vazia, JSON UTF8 com
chaves ordenadas/separadores compactos, Unicode sem normalização e preview_url=false.
O header Idempotency-Key é a UUIDv4 já persistida por entrega no T10.

A entrada HMAC-SHA256 versionada inclui organização/profile, método/scheme/host/path,
query canônica, content-type, chave durável, modalidade/tipo, remetente/destinatário e
bytes exatos do body. O store compara o Message durável, bytes canônicos e escopo com
channel_lifecycle sob o writer; compara ou insere o MAC antes dos marcadores. O sender
verifica novamente o MAC antes do transporte. Mutação material, host não permitido,
chave/payload diferente ou troca de chave de integridade recusa a identidade anterior.

Migration0022 adiciona `telnyx_http_requests(submission_key,version,integrity_key_id,
request_mac)`, sem reconstruir tabelas ou backfill inventado de HTTP histórico. Não
copia body, telefone ou credenciais. Triggers negam alteração/DELETE/REPLACE e reuso
posterior da chave em nova outbox. Recibos sobrevivem a purge terminal e reuso de ID
numérico; a nova entrega recebe outra UUID. Essa retenção integra CX01 e não é solução
LGPD. O fingerprint de intenção herdado do T10 não foi removido nem descrito como anônimo.

A chave HMAC deve ser estável e protegida fora do SQLite em futura composição aprovada.
Perda/rotação bloqueia vínculo anterior e exige investigação, nunca troca da chave de
submissão. MAC reduz guessing por observador apenas do banco; não prova autorização
operacional, organização real de uma credencial futura ou frescor de snapshot antigo.

## G. Matriz de respostas e resultados

Todos os resultados abaixo foram simulados por callables interceptados. Há zero
cliente HTTP/default, SDK, token, redirect handler ou loop de retry neste sender.
O exchange recebe explicitamente retries=0, follow_redirects=false, connect/read
budgets positivos e finitos cuja soma corresponde ao orçamento. Callables são uma
fronteira interna confiável; esse contrato não impede código arbitrário malicioso.

| Evidência | Resultado durável / efeito |
| --- | --- |
|200 completo, identidade/escopo/texto e opcionais válidos | ProviderAcceptance com Message ID; estado accepted, sujeito a ledger T08 |
|200 sem ID/identidade/body, JSON inválido/duplicado/NaN, schema conhecido malformado, status desconhecido, tamanho>1MiB | unknown, telnyx_response_invalid |
|200 identidade/número/org/profile/texto divergente ou origin humano | unknown; sem aceitação inferida |
|201/202/204 ou outros HTTP sem contrato | unknown; nenhuma aceitação por classe2xx |
|409 +10036 | unknown, telnyx_in_progress |
|422 +10027 | unknown, telnyx_key_conflict; sem gerar nova chave |
|Outros409/422,408,413,429,5xx/503 e redirect | unknown, telnyx_http_unknown (ou response_invalid se corpo não puder ser classificado) |
|Timeout conexão/leitura, conexão interrompida, resposta perdida, qualquer exceção no exchange | unknown, telnyx_transport_unknown; uma chamada, sem retry |
|Falha na preparação antes de autorização/exchange | prova local NOT_SUBMITTED da tentativa; retry limitado existente, mesma UUID |
|Falha local depois do marker | unknown ou lease expirado→unknown; nenhuma prova retroativa de não submissão |
|Crash depois do marker, antes/depois de possível envio | lease expira para unknown; restart não reenfileira |
|Callback antecipado | receipt T08 retido; reconciliação atômica na acceptance, sem aceitação pelo callback isolado |
|Callback posterior | ledger avança sent/delivered/read ou conserva conflito; HTTP não substitui ledger |
|Callback com escopo incompatível | finalização rejeita/rollback; receipt/marker preservados, lease→unknown |
|Falha de commit da acceptance | não reexecuta exchange; marker permanece, lease→unknown |

O método genérico send falha fechado; a integração usa prepare→store authorization→
send_prepared. Esse último é um seam de baixo nível cujo chamador precisa de autorização
já commitada; não é API pública, capability contra código hostil ou ativação. O runner
real exerce a sequência uma única vez. Message.echo jamais fornece aceitação da IA.

## H. SQLite, concorrência, gates e recovery

Sequência exercitada: claim durável, owner/lease, preparação/verificação, reavaliação
atômica completa, commit de binding+marcadores lógico/tentativa, exchange interceptado,
validação e finalize durável. Outro BEGIN IMMEDIATE consegue escrever durante exchange
ou callback: nenhuma transação SQLite permanece em I/O. Um runner/worker concorrente
não obtém segunda autorização; sondagem independente também usou oito workers.

Owner/lease, pause/revision, handoff/episódio, ordering barrier, conflito de delivery,
channel active positivamente verificado, organização/profile/número comercial,
Customer E.164, consentimento e janela<24h continuam reavaliados. Não existe bypass de
verification_required. Reconexão continua sem ativar. Meta/Twilio mantêm semântica e
contratos; construtores com sender concreto inferem provider=telnyx ou rejeitam provider
incompatível antes do claim, preservando outros outboxes sem tentativas.

Pausa/disconnect que ganha antes do marker impede exchange. Se ocorrer depois do marker,
o efeito já autorizado pode iniciar/completar; testes registram essa janela CX06,
sem prometer recall. Falhas de commit/DDL revertem vínculo/markers ou acceptance conforme
a fronteira. Migrações0020→0021→0022 preservam evidência histórica; nenhuma prova de
request externo é fabricada para tentativas anteriores.

**AUD01 OPEN:** três pontos antigos (antes claim, marker e disconnect) e uma sondagem
pós-expiração com evidência de política renovada reproduzem autorização local insegura
em snapshot obsoleto. São quatro testes passing porque demonstram a lacuna conhecida,
explicitamente nomeados known_gap; não são proteção aprovada. Snapshot depois de
acceptance conserva não reenvio, mas não resolve o rollback anterior.

Contrato obrigatório especificado: restore entra em quarentena **fora do arquivo
restaurado**, sem composição de saída. Futuro trabalho autorizado deve inventariar
possível submissão, reconciliar fontes externas/status, revalidar canal/sync/binding,
consentimento/janela atuais e exigir liberação autenticada com epoch externo ou controle
equivalente demonstrável. Ausência de evidência mantém quarentena/unknown. Não criar
chave nova, promover unknown ou confiar em integridade/migrations/MAC para frescor.
Nenhum mecanismo operacional dessa sequência foi implementado; é gate antes de egress.

## I. Testes integrais, checks e toolchain

Ambiente isolado `/tmp/ticket11`, pai0700, venv próprio; Python3.12.14, SQLite3.53.1,
pip26.3, pytest9.2.0, Ruff0.17.6, pip-audit2.10.1 e Gitleaks8.30.1. Alteração de
constraint somente dev: pytest>=9.0.3,<10; dependências de runtime declaradas intactas.
A restrição anterior<9 impedia a versão corrigida. Manifesto observado em
[ticket11-toolchain.txt](ticket11-toolchain.txt), não apresentado como lock.

Instalação: python3 -m venv em pai privado; pip install --index-url https://pypi.org/simple
--upgrade 'pip>=26', depois -e '.[dev]' pip-audit. Ambiente allowlist manteve apenas
PATH/HOME/TMPDIR e proxy/CA gerenciados, PIP_CONFIG_FILE=/dev/null; sem credenciais
comerciais. Primeira tentativa sem proxy falhou network unreachable; corrigida conforme
guidance cloud-environment-runtime preservando TLS. Não foi tratado como falha de código.

Testes executam ambiente novo reduzido sem proxies/tokens comerciais, com
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 e guard sitecustomize que bloqueia connect/connect_ex/
sendto em AF_INET/AF_INET6, herdado por filhos Python. Pai temporário0700 e --basetemp
privado. Guard é verificável e portátil em
[scripts/check_telnyx_offline.py](../../scripts/check_telnyx_offline.py); não é sandbox
por kernel para executáveis arbitrários. Documentação pública, PyPI/advisories e GitHub
ocorrem separadamente dos testes. Não se carregou .env comercial.

| Verificação executada | Resultado |
| --- | --- |
|Pytest integral implementador, código a049753 + validação789c2c8 |2130passed/1skip,393.78s,exit0 |
|Pytest integral Spec independente, mesmo candidato789c2c8 |2130passed/1skip,399.84s,exit0 |
|Ruff check / format--check |PASS,315arquivos |
|Compileall src/tests/scripts | PASS |
|Pip check | PASS, nenhuma dependência quebrada |
|Git diff--check | PASS nos checkpoints |
|Pip-audit atualizado |82dependências no JSON,0pacotes com advisories; app local não indexada explicitamente pulada |
|Gitleaks commits novos |Recorte funcional/CP5:0detecções; entrega documental acrescenta1falso positivo do hash público do schema, triado sem ignores |
|Gitleaks árvore final |3detecções brutas: duas baseline (prosa de eval e constante sintética) e o SHA256 público do schema oficial neste relatório; todos falsos positivos triados, nenhum ignore |
|Retomada clone limpo |3passed/0skip9.14s; SHA/origin/branch/status confirmados |

[Resumo executado/JUnit e hashes](ticket11-test-evidence.json) preserva os totais e
hashes dos logs reais; os comandos portáteis permitem reexecução em outro ambiente.

[Pip-audit JSON real](ticket11-pip-audit.json) preserva skip explícito da aplicação local
não encontrada no PyPI. Zero advisory retornado não é prova universal de segurança ou
validação do deploy futuro. Gitleaks árvore exit1 por três falsos positivos triados;
não se afirma zero detecção bruta. Binário8.30.1 conferido contra checksum oficial.

### Falhas e execuções anteriores, sem ocultação

- CP1 request+migrações históricas:40passed9.62s; CP2 request/sender76passed3.23s;
  CP3 integração/submissão/delivery101passed34.52s.
- CP4 inicial2failed/26passed11.81s; segunda2failed/26passed12.01s; terceira1failed/
  27passed; ajustes de fixtures/expectativas (colunas handoff, ValueError de escopo,
  OperationalError encapsulada por SQLAlchemy). Final28passed11.41s.
- Correções de review:116passed11.08s; depois145passed29.63s incluindo regressões;
  head migrations19passed9.44s; runner portátil40passed12.79s; provider scope+legacy
  56passed20.08s. Recortes se sobrepõem, não somar como cobertura independente.
- Integral local antiga interrompida por SIGINT após2failed/868passed/1skip279.43s;
  falhas reais: expected head0021 e mensagem de downgrade. Substituta interrompida
  após1failed/426passed/1skip123.81s ainda com a mensagem antiga coletada; nova parcial
  425passed/1skip109.71s foi interrompida para incluir a correção de provider da Spec.
- Spec inicial interrompida2failed/942passed/1skip287.89s; -x próprio1failed/33passed
  34.24s; substituta1failed/426passed/1skip119.01s; outra parcial647passed/1skip175.24s
  interrompida para a correção de provider. Nenhuma parcial é descrita como suíte verde.
- Integrais completos anteriores no candidato a049753: implementador1failed/2129passed/
  1skip422.95s; Spec1failed/2129passed/1skip402.26s. Única falha: outro expected head0021
  em test_telnyx_messages.py. Alterado somente o ramo de head atual para0022, mantendo
  rollback/journal/effects/FKs. Global search de todos os testes deixa apenas0021
  intencionais históricos. Par focado2passed3.63s local e2passed3.55s independente.
- Skip histórico: test_historical_v8_record_remains_loadable, fixture ignorada
  work/evals/openai-agentic-surface-smoke-2026-10-04-01/phase-A.json ausente. Não foi
  inventado artefato para esconder o skip. CX19/AUD06 permanecem.

## J. Standards Review independente

[Relatório integral](ticket11-standards-review.md), leitura direta do diff/código, próprios
comandos e três probes reproduzíveis. Original229passed84.22s +3probes11.14s. A perspectiva
inicial não encontrou o P2 de schema, reconhecido no relatório; não se converte esse PASS
parcial em prova de ausência. Após correções:117passed18.10s +3probes11.47s e último
provider guard2passed8.05s. Revisor não editou código/testes/commits. Parecer offline PASS
para auditoria; operacional NO-GO.

## K. Spec Review e revisão adversarial independentes

[Spec](ticket11-spec-review.md): fontes oficiais, código real e execução integral própria.
Confirmou e demonstrou profile inválido/schema UUID, opcionais malformados aceitos e
provider=None consumindo tentativas Meta. Correções realizadas com regressões e seus
próprios probes de fechamento. Resultado integral final2130passed/1skip399.84s,exit0.

[Adversarial](ticket11-adversarial-review.md): probes próprios em SQLite, oito workers,
erros/restart/no resend e schema. Antes6failed/8passed20.77s; depois, mesmos14probes
14passed15.48s. Timeout extremo P3 também confirmado/corrigido:3probes passed0.35s.
Nenhum P1/P2 novo confirmado pendente nessas perspectivas após as correções. Não é prova
formal de todos os interleavings nem teste de transporte/conta comercial.

## L. Issue11 e ressalvas revalidadas

A entrega acompanha atualização do [registro central](https://github.com/zazacknazzo/rj-studio-ai/issues/11)
com SHA remota final/evidências após o push documental. Nenhum checkbox/risco é encerrado
por esta entrega; conferir a seção e o comentário de entrega mais recentes no issue.

| Risco | Evidência offline / saldo e gate |
| --- | --- |
|CX01 | Recibo HTTP privado também é retido sem expiry; retenção/erasure/backups antes de piloto, operação/T13. |
|CX06 | Marker→HTTP conserva janela residual; pause tardio não recolhe chamada, T11–13/aceite operacional. |
|CX11/CX33 | Canal positivamente verificado e org/profile obrigatórios; nenhum reconnect ativa; ativação/sync reais T12–13. |
|CX15/CX35 | Bytes+escopo+UUID vinculados durablemente e transporte único simulado; unknown não reenvia, inclusive expiry. Orquestrador/aceite externo ainda requeridos. |
|CX16/CX36 | Janela e consentimento rechecados; captura/revogação operacional e proveniência real não existem, gate de piloto/T12–13. |
|CX17 | Sender offline existe; composição/runtime/rota/credenciais e conta reais continuam ausentes, T12–13. |
|CX19/CX21 | Suítes/revisores/checks próprios, skip explícito, push normal; sem inferir CI/merge/release. |
|CX24/CX29/CX30 | Ingress HTTP raw/streaming, formatos não suportados e deadline real2s fora de escopo, T12–13. |
|CX32 | Callback conflitante/unknown preservado, sem reconciliação humana ou liberação de ordering, T12–13. |
|CX37 | BSUID outbound bloqueado sem inferir telefone; subconjunto E.164 mantido. |
|AUD01 | Aberto: contrato+quatro sondagens de gap; proteção operacional pendente fora do snapshot. |
|AUD02 | Atualização real/venv isolado e auditoria sem advisory retornado; decisão formal/CI permanece com mantenedor/orquestrador. |
|AUD03 | Protocolo permanente e ensaio clone implementados; exclusividade humana necessária, duas contas reais simultâneas não comprovadas. |

Nenhum risco novo distinto do registro existente foi necessário: achados corrigidos
foram defeitos no candidato do sender/configuração, não novas exceções aceitas.

## M. Isolamento e limites de evidência

**Executado:** SQLite real em arquivos temporários sintéticos, pytest/checks/sondagens,
Git remoto/clone/push e consultas públicas de documentação/advisories.
**Inspecionado:** contratos oficiais e ADRs/specs06–10, auditoria pré11 e issue11,
paths de runner/executor/store/migrations/ledger e diffs de escopo.
**Simulado:** todos os HTTP/request/response/timeouts/crashes de sender; canal/consent
positivos são fixtures explícitas, não verificação de conta comercial.
**Não comprovado:** conta/org real de API key futura, sync/onboarding/Coexistence+55,
latência/custos/entrega real, coordenação efetiva de duas contas humanas, CI/release,
isolamento por kernel ou mitigação operacional de restore.
**Não executado:** HTTP Telnyx real, token comercial, ativação/onboarding, envio real,
rota pública, worker Telnyx runtime, merge/main, Baileys e Tickets12–13.

Diff não altera factories/config/main, adapters Meta/Twilio nem persona/grounding/
lógica comercial da Lívia. Teste PROFILE agora UUID sintética apenas; testes históricos
mudaram somente expected head para0022. Neste clone não existe worktree Baileys de
outra máquina; nada nele foi acessado e nenhum arquivo Baileys aparece no diff. Não
se reproduz afirmação de verificação por hashes de máquinas não disponíveis.

## N. Continuidade e checkpoints publicados

AGENTS contém protocolo permanente; [template](../handoffs/TEMPLATE.md) e
[handoff atual](../handoffs/TICKET-11.md) registram estado/testes/falhas/próxima ação.
Uma única conta é escritora Git; revisores escrevem somente relatórios separados.
Nenhum force push, reset destrutivo, rebase publicado ou merge foi usado.

| Marco | SHA remota efetivamente confirmada |
| --- | --- |
|CP0 spec/ADR/continuidade antes do código |cbf31a0c948a3c9c6801412739c5b724920a1964 |
|Toolchain separada AUD02 |066861f347411491f34def3e81f7c0e6484d38cf |
|CP1 request/identidade |a9fbe86cbbd95000491695864eb0911950a53c32 |
|CP2 transporte/resposta |43574436e6bd99d53d2b90598001480aa70c8b59 |
|CP3 runner/SQLite |a7825b94d9cc0a757f37e5cd5243c1ec9c843714 |
|CP4 adversariais/recovery |2751652a3df39e0bf3f0d5c7588172b510eab0db |
|CP5 correções/reviews, WIP explícito |4ec507a3c057b5c7bdc96bf3a0768265b62c552d |
|CP5 correção adicional provider |a049753205001d81a9ac0f11253eab5760a2f017 |
|CP5 correção de expectativa histórica, sem mudança funcional |789c2c89328b0472506c3d34593dfe741c052883 |
|CP5 suíte/reviews concluídos |7823243293f888321723dc6bcbb9f0fcbcc361b1 |
|CP6 relatório/evidências/entrega |HEAD remoto confirmado após commit; informado na entrega/issue |

Ensaio reproduzível: clone novo da branch, fetch, origin/status/branch, HEAD local e
remoto iguais a049753, baseline ancestral confirmada, leitura AGENTS+handoff e execução
do script portátil no próprio clone (PYTHONPATH aponta para o clone). Testes:
runner_commits_exact_binding... e duas parametrizações concrete_sender_default_provider...
**3passed/0skip9.14s**. Status final limpo e remoto conservado. Não se sobrescreveu trabalho
publicado. Esse ensaio simula retomada sem conversa; não comprova autenticação de segunda
conta. Controle humano exclusivo de escrita continua obrigatório; Markdown não é lock.

## O. Estado dos achados e próxima decisão

AUD01: contrato especificado e testes de falha conhecida implementados; quarentena,
reconciliação e fence externos ainda ausentes; **bloqueia envio operacional**.
AUD02: toolchain efetivamente atualizada e auditada em ambiente isolado, não apenas
proposta; validação integral final concluída; formalização/CI ainda gate do mantenedor.
AUD03: protocolo/checkpoints/ensaio implementados; limitação de exclusividade humana
mantida. Nenhum checkbox foi fechado ou exceção aceita.

Desenvolvimento encerrado após esta entrega. Solicita-se auditoria direta do orquestrador.
Qualquer T12–13, remediação operacional ou ativação exige autorização nova.

## Arquivos alterados contra Ticket10

- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/architecture/ticket11-adversarial-review.md`
- `docs/architecture/ticket11-pip-audit.json`
- `docs/architecture/ticket11-spec-review.md`
- `docs/architecture/ticket11-standards-review.md`
- `docs/architecture/ticket11-test-evidence.json`
- `docs/architecture/ticket11-toolchain.txt`
- `docs/architecture/v1-ticket11-validation.md`
- `docs/automation-operations.md`
- `docs/decisions/0019-deterministic-offline-telnyx-sender.md`
- `docs/decisions/README.md`
- `docs/handoffs/TEMPLATE.md`
- `docs/handoffs/TICKET-11.md`
- `docs/specs/README.md`
- `docs/specs/V1-telnyx-coexistence-ticket-11.md`
- `pyproject.toml`
- `scripts/check_telnyx_offline.py`
- `src/rj_studio_ai/delivery.py`
- `src/rj_studio_ai/migrations/__init__.py`
- `src/rj_studio_ai/migrations/versions/0022_telnyx_http_identity.py`
- `src/rj_studio_ai/persistence.py`
- `src/rj_studio_ai/providers/telnyx_sender.py`
- `src/rj_studio_ai/telnyx_request.py`
- `tests/test_agentic_intake_migration.py`
- `tests/test_migrations.py`
- `tests/test_openai_metadata_migration.py`
- `tests/test_telnyx_authentication.py`
- `tests/test_telnyx_http_migration.py`
- `tests/test_telnyx_messages.py`
- `tests/test_telnyx_request.py`
- `tests/test_telnyx_sender.py`
- `tests/test_telnyx_sender_adversarial.py`
- `tests/test_telnyx_sender_integration.py`
