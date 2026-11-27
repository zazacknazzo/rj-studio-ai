# Atendimento a qualquer mensagem individual

Pedido de 27/11/2026. Branch codex/waha-open-inbound, base 00aca10.
A especificação está em docs/specs/WAHA-OPEN-INBOUND.md.

WAHA_AUDIENCE=all_direct autoriza a admissão de novos Customers por webhook
assinado da conta verificada. Respostas exigem a mensagem de origem persistida
e a autorização de envio de uma tentativa. O pipeline de inteligência existente
mantém KB aprovada, contexto por Conversation, grounding e handoff.
O valor padrão allowlist preserva o comportamento do teste anterior.

A audiência integra o escopo do journal e o estado autenticado do ledger.
O operador deve preparar um novo escopo ao mudar audiência. Editar somente
uma variável num ledger anterior falha na verificação de escopo.
JIDs de telefone e LID são aceitos para chats individuais. A identidade de cada
Conversation segue o endereço fornecido pelo provedor. Identidades diferentes
não recebem união inferida de históricos.

## Preparação local de 27/11

Novo checkout operacional relativo à raiz desta missão em work/livia-open,
projeto Compose rj-livia-open. Configuração privada com all_direct.
O backend contém o código 9aeb48e, imagem rj-livia-open-backend também marcada
rj-livia-private-test-backend, compatível com o modo allowlist anterior.
As sessões, ledger, SQLite e configuração permanecem no armazenamento local.

Antes de criar o novo escopo foram conferidos o journal, o selo SQLite, a ausência
de mensagens, tentativas, intenções e revogações no escopo anterior e o consumo.
Uma inicialização de inspeção acrescentou checkpoint/boot ao journal antigo
sem avanço simultâneo do ledger. Com o processo antigo parado e lock exclusivo,
os dois registros foram conferidos por HMAC e reancorados pela autoridade,
conservando pausa, inventário e sequência. O escopo anterior está alinhado.

No novo escopo foram carregadas as reservas anteriores, totalizando uma chamada,
18.664 tokens e 54.340 microusd reservados. O checkpoint privado da transição
conserva referências autenticadas da origem. Os registros anteriores permanecem
preservados. A configuração aceita qualquer contato direto, porém mantém o
limite global cumulativo de 20 chamadas, 500.000 tokens e a reserva de custo
de US$1 calculada pelas taxas versionadas do projeto. Esses limites são globais.

O usuário autorizou expressamente uma hora de operação para qualquer contato
direto e aceitou o risco de rollback conjunto em 27/11. O deadline do novo
escopo é 1795816375665, equivalente a 27/11/2026 18h52min55s de Brasília.
Start/resume conservam prazo e budgets. AUD-01/AR-02 continuam abertos.

## Validação

- 86 testes focados passaram, abrangendo novos remetentes, LID, isolamento do
  histórico, self/eco/grupos, replay, contato revogado, desconhecido global e
  ausência de envio sem resposta persistida.
- Suíte isolada local registrou 2380 PASS. O teste adicional que exige ausência
  de envio espontâneo foi incluído no lote focado final.
- Ruff, formatação, pip check e diff check passaram.
- CI do código 9aeb48e foi disparado no run 46066675125. Consultar seu resultado
  no GitHub antes de atribuir conclusão.
- Recebimento no aparelho e múltiplos turnos continuam exigindo evidência real.

## Operação e pausa

Use scripts/livia-test status, pause, resume, start e stop no checkout operacional.
Os comandos revalidam identidade da conta da IA e o prazo antes de ativar.
All_direct conserva HMAC, bloqueio de grupos/broadcast/status/self, mídia,
opt-out, handoff, pausa, budgets, prazo, idempotência e unknown sem retry.
A ausência de sessão WORKING impede ativação. QR deve ser lido pelo proprietário
no aparelho da conta da IA. Preserve os perfis antes de qualquer recuperação.

## Conexão nesta execução

O perfil compartilhado do teste anterior permaneceu em STARTING, com a página
presa em carregamento e sem QR. Hash do Client.js conferiu com o patch publicado.
A criação de um perfil de browser novo permitiu chegar a SCAN_QR_CODE.
A referência ao perfil anterior foi preservada em
work/livia-open/.local/b1/sessions-preserved-before-repair.
O novo diretório de sessões pertence somente ao projeto rj-livia-open.
O espelho SQLite de metadados foi copiado por backup consistente, e a sessão
default foi criada com webhook interno/HMAC verificados na configuração atual.

O backend segue pausado enquanto o usuário lê o QR no aparelho da IA.
A página privada outputs/Parear Lívia.html consulta o PNG temporário gerado
por work/pareamento.py, executado no checkout work/livia-open.
O auxiliar remove o PNG ao terminar ou detectar WORKING. Os arquivos privados
permanecem fora do Git. Revalide a identidade exata antes de executar resume.
