# Autoridade WAHA Cloudflare exige testemunha administrativamente independente

Status: desenho aceito no escopo B3 solicitado em22/11/2026; operação ainda NO-GO.
Complementa ADR0021/0022. Usar dois Workers/Durable Objects SQLite com raízes e
administração distintas: autoridade e inventário na conta principal; testemunha
monotônica em outra conta/administrador, sem suas credenciais de deploy no Mac.

Durable Objects oferecem transações e consistência forte, mas seu PITR permite
restaurar o próprio objeto. Dois objetos sob uma administração comum não demonstram
independência. R2 bucket locks removíveis pelo administrador não substituem essa
separação. O usuário confirmou ter somente uma conta Cloudflare; portanto não há
evidência operacional para fechar AUD-01/AR-02. Uma segunda conta administrada
separadamente, ou testemunha equivalente com raiz não revertida, é requisito externo.

Cada mutação é CAS, verifica o estado atual da testemunha e a avança antes de
persistir/reconhecer a autoridade. Respostas Ed25519 ligam nonce/tempo/escopo/conta;
runtime e operador têm segredos distintos. Boot troca epoch, pausa e remove grants.
Âncora externa precede cada novo MAC do journal local; falha entre raízes exige
reconciliação, sem apagar registros ou adivinhar que não houve submissão.

Identidade lógica é HMAC de provider/canal/ID canônico do inbound/tipo de resposta;
não depende do ID numérico SQLite. Bytes exatos, destinatário e chave são ligados
ao inventário. Consumo durável marca unknown antes de qualquer POST; ticket efêmero
é consumido uma única vez. Só Provider Acceptance real valida accepted. Unknown,
restart ou restore nunca recriam ticket nem habilitam retry. Reconciliação registra
prova de acceptance e conserva impossibilidade de reenviar a intenção anterior.

Store B1 permanece fechado. A factory B3 explícita compõe journal ancorado, store
estrito, sender e executor canônicos; não delega autorização ao store permissivo.
Configuração operacional ausente/mesma conta/assinatura inválida/autoridade indisponível
impedem o caminho. O grant atual é somente uma intenção/destinatário, por até uma
hora, conforme autorização humana para primeira resposta. Não é piloto/produção.

Manter Worker sem conteúdo de Messages e sem credencial WAHA; somente hashes,
epochs, revisions e resultados. WAHA/API/dashboard continuam locais. Não criar
tunnel público para WhatsApp. SQLite DO no Free e ausência de alarmes/WebSockets
persistentes minimizam custo; limites/custo reais dependem de uso e plano.

Referências primárias: [Storage/PITR](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/),
[permissões](https://developers.cloudflare.com/workers/authorization/),
[R2 locks](https://developers.cloudflare.com/r2/buckets/bucket-locks/),
[preços](https://developers.cloudflare.com/durable-objects/platform/pricing/).
