# WAHA privado reutiliza o core e mantém egress fechado

Status: aceito no escopo B1 aprovado em 22/11/2026; não libera AUD-01/AR-02.

WAHA precisa ser um canal, sem outro mecanismo de inteligência ou memória.
Criamos factory ASGI explícita, separada de main, com adapter WEBJS/HMAC, store
canônico e ProcessingRunner/MessageResponder/OpenAI/context/Knowledge existentes.
Uma opção de seleção usa histórico já persistido na relevância de Knowledge.
Os providers existentes conservam o comportamento padrão.

Uma cadeia MAC local e um head em outra pasta protegem transações/reservas de B1
contra adulteração, rollback unilateral e commits interrompidos. Não satisfazem
independência administrativa/antirollback externo. Consequentemente o store WAHA
nega autorização e HTTP de saída em código, sem flag de escape ou handle legado.
Nenhum executor de outbound é iniciado. O transporte é testável com fakes, mas
não é integrado a envio real antes da autoridade/recovery auditados.

Isso permite observar OpenAI real e receber ingresso privado após QR, mantendo
explícito o impedimento de conversa bidirecional. Não se transforma outbox pending
em acceptance fake para demonstrar memória real. Evidência de fixture, OpenAI e
WhatsApp é reportada separadamente. Boot pausa, revogação não é desfeita por resume,
unknown não é reenviado e credenciais/QR ficam somente na configuração/interface
local. Logs WAHA são desativados porque a versão imprime credenciais na inicialização.
