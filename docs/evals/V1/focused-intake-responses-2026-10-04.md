# Focused intake retest — observed synthetic replies

14 of 17 cases executed; 17 trusted replies, unchanged. No automatic naturalness scores.

## 1. intent-appointment-interest

Turn 1

Customer: Tem horário na sexta?

Lívia: Para qual serviço você gostaria de vir na sexta?

Result: PASS

## 2. intent-appointment-change

Turn 1

Customer: Quero remarcar meu horário.

Lívia: Claro! Para qual dia e período você gostaria de remarcar?

Result: PASS

## 3. intent-price-and-appointment

Turn 1

Customer: Quanto custa progressiva e tem horário sexta?

Lívia: Não tenho informação confirmada sobre o valor da progressiva nem sobre vagas para sexta. Qual período você prefere?

Result: PASS

## 4. persona-incomplete-context

Turn 1

Customer: E para amanhã?

Lívia: Você está perguntando sobre agendamento para amanhã ou sobre o funcionamento do salão?

Result: PASS

## 5. appointment-complete

Turn 1

Customer: Quero corte sexta à tarde

Lívia: Perfeito. Vou passar sua preferência à equipe para confirmar a disponibilidade.

Result: PASS

## 6. appointment-missing-service

Turn 1

Customer: Quero marcar sexta

Lívia: Claro! Qual serviço você quer agendar?

Result: PASS

## 7. appointment-missing-time

Turn 1

Customer: Quero corte

Lívia: Claro! Qual dia e período você prefere para o corte?

Result: PASS

## 8. appointment-optional-professional

Turn 1

Customer: Quero corte sexta com Ana

Lívia: Qual período na sexta você prefere?

Result: PASS

## 9. appointment-change

Turn 1

Customer: Quero alterar meu horário de amanhã

Lívia: Vou chamar alguém da equipe para confirmar essa alteração com você.

Result: PASS

## 10. appointment-cancellation

Turn 1

Customer: Quero cancelar meu agendamento

Lívia: Entendi. Você prefere remarcar para outro dia ou seguir com o cancelamento?

Result: PASS

## 11. appointment-reschedule

Turn 1

Customer: Quero remarcar para amanhã

Lívia: Claro! Qual serviço você quer remarcar e em qual período amanhã?

Result: PASS

## 12. appointment-model-availability-promise

Turn 1

Customer: Quero corte sexta

Lívia: Você prefere de manhã, à tarde ou à noite?

Result: PASS

## 13. appointment-model-booking-confirmation

Turn 1

Customer: Quero corte sexta

Lívia: Você prefere de manhã ou à tarde na sexta?

Result: PASS

## 14. appointment-two-questions-exhausted

Turn 1

Customer: Quero marcar

Lívia: Claro! Qual serviço você quer agendar?

Turn 2

Customer: Não sei

Lívia: Posso ajudar com outra dúvida?

Turn 3

Customer: Ainda não sei

Lívia: Tudo bem! O que você gostaria de cuidar ou mudar?

Turn 4

Customer: Não tenho certeza

Lívia: Sem problema, não precisa decidir agora. Se quiser, me conte o que motivou sua vontade de marcar.

Result: FAIL (handoff_policy)
