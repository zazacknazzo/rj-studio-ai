# Intake humano — Salon Knowledge do RJ Studio

Estado: coleta em `draft`; nenhum fato aprovado ou publicado por este documento.
Base inspecionada: Ticket 10 `7e9c64081ac5e1d15652a213f972cbc8ec1aaadb`.

Este documento contém **26 fichas propostas para confirmação**, não 26 fatos
conhecidos. Os campos de conteúdo e fonte estão em branco. Perguntas, IDs e
termos de busca são sugestões de coleta, não afirmações sobre o salão.
Não foram usados valores de fixtures, pesquisa externa, credenciais ou dados de
Customers. O YAML de produção continua com `version: 1` e `facts: []`.

## Como preencher e aprovar

1. Preencha cada `statement` com o texto exato que autoriza enviar ao Customer,
   em português, e cada `source` com uma referência humana verificável: responsável,
   documento/registro e data. Não cole conversas de Customers ou dados privados.
2. Informe a data real da revisão em `reviewed_at` (`AAAA-MM-DD`). Deixe pendente
   enquanto não houve revisão humana. A data de criação desta ficha não é revisão.
3. **PO** significa você, product owner e aprovador final. **Especialista** significa
   Joelma e/ou Rogério; eles validam conteúdo técnico antes da sua aprovação final.
   Indicação de responsável nesta ficha não significa validação já realizada.
4. Para desconhecido, responda “não confirmado”; para inaplicável, “não aplicável”.
   Nenhuma dessas respostas autoriza inferir que serviço, desconto ou política
   existe ou não existe. Retire fichas inaplicáveis do lote de publicação.
5. Duplique fichas por serviço, profissional, preço, promoção ou regra real.
   Substitua IDs com `a-confirmar` por IDs específicos antes da primeira publicação.
   Depois mantenha IDs estáveis. Se duas fichas descrevem o mesmo serviço, consolide
   os dados e flags em um fact ou divida informações sem contradição.
6. Todas as fichas ficam `draft` aqui. Registre sua decisão humana por ID em um
   bloco de aprovação ao final. A transferência para o YAML e eventual mudança
   para `approved` serão uma etapa posterior, revisada; não ocorrem nesta tarefa.

## Contrato atual, conferido no código

Fonte padrão: `knowledge/rj_studio.yaml`; configuração: `SALON_KNOWLEDGE_PATH`.
Raiz YAML: apenas `version: 1` e `facts: [...]`. Cada fact usa **`id`**, não
`fact_id`; “fact_id proposto” abaixo é o nome de apresentação desse mesmo `id`.
Campos extras e chaves/IDs duplicados são rejeitados.

| Campo YAML | Obrigatoriedade e regra atual |
| --- | --- |
| `id` | Obrigatório; mínimo 3 caracteres; regex `^[a-z0-9][a-z0-9-]*$`; único no documento. |
| `category` | Obrigatório: `identity`, `location`, `channel`, `hours`, `service`, `price`, `professional`, `policy`, `handoff_condition`. |
| `topic` | Obrigatório; string com mínimo de 1 caractere; termos explícitos de seleção. |
| `status` | Obrigatório: `draft`, `pending` ou `approved`. Somente `approved` entra no conjunto selecionável. |
| `fact_type` | Obrigatório: `operational_commercial` ou `technical`; independente da categoria. |
| `statement` | Obrigatório; string com mínimo de 1 caractere. É a afirmação completa renderizada sem alteração. |
| `source` | Obrigatório inclusive em draft; string com mínimo de 1 caractere. O loader não verifica autenticidade da fonte. |
| `reviewed_at` | Obrigatório inclusive em draft; data. Registrar uma revisão humana real. Não há expiração automática por data. |
| `approved_by` | Opcional/default `null`; obrigatório e não nulo para `approved`; deve ser `null`/omitido para `draft` e `pending`. O código não autentica quem escreveu o nome. |
| `validated_by` | Default `[]`; somente nomes exatos `Joelma` e `Rogério`. Deve ficar vazio para `operational_commercial`. Para `technical` aprovado precisa de pelo menos um desses nomes. Não preencher antes de validação real. |
| `requires_human_consultation` | Default `false`; somente facts `service` podem usar `true`. Confirmar explicitamente antes de publicar um serviço; o default não prova que avaliação é dispensável. |
| `mandatory_policy_ids` | Default `[]`; somente facts `service` podem ter referências. Cada ID precisa existir e ser categoria `policy`, mesmo no draft. Serviço aprovado só pode referenciar políticas aprovadas. |

O schema não contém campos `duration`, `payment_methods`, `discount`, `expires_at`,
`appointment` ou `availability`. Duração é descrita no `statement` do serviço;
pagamento, descontos/promos, orçamento e agendamento usam `policy` nas fichas.
Preços de serviços usam `price`. Uma orientação técnica usa categoria existente
(por exemplo `policy`) com `fact_type: technical`; não existe categoria `technical`.

Para cada serviço, preencher adicionalmente, sem aceitar defaults por omissão:

- `requires_human_consultation`: **a confirmar — true ou false**;
- `mandatory_policy_ids`: **a confirmar — IDs de políticas reais, ou lista vazia confirmada**.

As fichas abaixo são Markdown de intake, **não YAML pronto para carregar**.
`statement`, `source` e `reviewed_at` incompletos não passam pelo loader nem mesmo
como draft; não os substitua por dados inventados para satisfazer validação.

## Fichas pendentes

Metadados iniciais de **cada** ficha: `status: draft`, `approved_by: null`,
`validated_by: []`, `reviewed_at: pendente de revisão humana`.
“Responsável” é informação operacional do intake, não um novo campo YAML.
Especialidades técnicas, duração ou descrição que contenham afirmação técnica
precisam ser separadas/reclassificadas como `technical` e validadas por especialista.

### 01. `identidade-institucional`

- **fact_id proposto (`id`):** `identidade-institucional`
- **category:** `identity` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** nome salão identidade; confirmar os termos relevantes.
- **Conteúdo solicitado:** Nome público e descrição institucional que podem ser usados no atendimento.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

### 02. `localizacao-publica`

- **fact_id proposto (`id`):** `localizacao-publica`
- **category:** `location` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** endereço localização chegar; confirmar os termos relevantes.
- **Conteúdo solicitado:** Endereço público completo e orientações de acesso confirmadas, se aplicáveis.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

### 03. `contato-publico`

- **fact_id proposto (`id`):** `contato-publico`
- **category:** `channel` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** contato telefone whatsapp; confirmar os termos relevantes.
- **Conteúdo solicitado:** Canal público oficial de atendimento; somente contato institucional autorizado.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

### 04. `horarios-atendimento`

- **fact_id proposto (`id`):** `horarios-atendimento`
- **category:** `hours` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** horário funcionamento atendimento; confirmar os termos relevantes.
- **Conteúdo solicitado:** Dias, horários, fuso e distinção entre atendimento pelo WhatsApp e funcionamento presencial.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

### 05. `horarios-excecoes`

- **fact_id proposto (`id`):** `horarios-excecoes`
- **category:** `hours` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** feriado funcionamento horário; confirmar os termos relevantes.
- **Conteúdo solicitado:** Exceções confirmadas, datas de validade e quem confirma alterações; se desconhecido, registrar isso na ficha.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

### 06. `servico-a-confirmar`

- **fact_id proposto (`id`):** `servico-a-confirmar`
- **category:** `service` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** a definir por serviço; confirmar os termos relevantes.
- **Conteúdo solicitado:** Nome de um serviço efetivamente oferecido, descrição e limites comerciais. Replicar por serviço confirmado.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

### 07. `preco-servico-a-confirmar`

- **fact_id proposto (`id`):** `preco-servico-a-confirmar`
- **category:** `price` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** a definir por serviço e preço; confirmar os termos relevantes.
- **Conteúdo solicitado:** Preço, moeda, unidade, inclusões, exclusões e condições; ou regra explícita de preço sob avaliação, se confirmada.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

### 08. `regra-orcamento-servico-a-confirmar`

- **fact_id proposto (`id`):** `regra-orcamento-servico-a-confirmar`
- **category:** `policy` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** a definir por serviço e orçamento; confirmar os termos relevantes.
- **Conteúdo solicitado:** Como o orçamento é obtido, fatores autorizados que alteram o valor e quem pode confirmá-lo.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

### 09. `profissional-a-confirmar`

- **fact_id proposto (`id`):** `profissional-a-confirmar`
- **category:** `professional` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** a definir por profissional e especialidade; confirmar os termos relevantes.
- **Conteúdo solicitado:** Nome profissional autorizado para divulgação, serviços e especialidades confirmados. Replicar por profissional.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

### 10. `duracao-servico-a-confirmar`

- **fact_id proposto (`id`):** `duracao-servico-a-confirmar`
- **category:** `service` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** a definir por serviço e duração; confirmar os termos relevantes.
- **Conteúdo solicitado:** Duração estimada conhecida, unidade, variação e ressalvas. Não preencher estimativa sem fonte humana.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO; consultar especialista se necessário.
- **reviewed_at:** ____________________

### 11. `formas-pagamento`

- **fact_id proposto (`id`):** `formas-pagamento`
- **category:** `policy` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** pagamento formas pagar; confirmar os termos relevantes.
- **Conteúdo solicitado:** Meios de pagamento realmente aceitos e restrições aplicáveis.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

### 12. `condicoes-parcelamento`

- **fact_id proposto (`id`):** `condicoes-parcelamento`
- **category:** `policy` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** parcelamento parcelas pagamento; confirmar os termos relevantes.
- **Conteúdo solicitado:** Existência ou ausência confirmada de parcelamento; limites, taxas e condições, quando houver.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

### 13. `politica-descontos`

- **fact_id proposto (`id`):** `politica-descontos`
- **category:** `policy` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** desconto descontos negociar; confirmar os termos relevantes.
- **Conteúdo solicitado:** Existência ou ausência confirmada de desconto; autorização, elegibilidade e limites. Não autoriza negociação automática.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

### 14. `promocao-a-confirmar`

- **fact_id proposto (`id`):** `promocao-a-confirmar`
- **category:** `policy` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** promoção promoções oferta; confirmar os termos relevantes.
- **Conteúdo solicitado:** Promoção confirmada ou ausência confirmada; vigência, público, serviços, valores e condições completas.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

### 15. `politica-atrasos`

- **fact_id proposto (`id`):** `politica-atrasos`
- **category:** `policy` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** atraso tolerância chegada; confirmar os termos relevantes.
- **Conteúdo solicitado:** Regra real para atraso, tolerância e encaminhamento, se existente.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

### 16. `politica-sinal-reembolso`

- **fact_id proposto (`id`):** `politica-sinal-reembolso`
- **category:** `policy` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** sinal adiantamento reembolso devolução; confirmar os termos relevantes.
- **Conteúdo solicitado:** Existência ou ausência confirmada de sinal, cobrança antecipada, reembolso e condições.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

### 17. `politica-agendamento`

- **fact_id proposto (`id`):** `politica-agendamento`
- **category:** `policy` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** agendar agendamento reservar; confirmar os termos relevantes.
- **Conteúdo solicitado:** Como solicitar atendimento e quem confirma a reserva. Não registrar disponibilidade atual nem prometer criação automática.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

### 18. `politica-alteracao`

- **fact_id proposto (`id`):** `politica-alteracao`
- **category:** `policy` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** alterar remarcar reagendar; confirmar os termos relevantes.
- **Conteúdo solicitado:** Processo, antecedência e condições reais para alteração/remarcação; responsável pela confirmação humana.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

### 19. `politica-cancelamento`

- **fact_id proposto (`id`):** `politica-cancelamento`
- **category:** `policy` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** cancelar cancelamento; confirmar os termos relevantes.
- **Conteúdo solicitado:** Processo, antecedência, cobranças ou isenções confirmadas e responsável pela confirmação humana.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

### 20. `avaliacao-servico-a-confirmar`

- **fact_id proposto (`id`):** `avaliacao-servico-a-confirmar`
- **category:** `service` · **fact_type:** `technical` · **status:** `draft`
- **topic proposto:** a definir pelo serviço que exige avaliação; confirmar os termos relevantes.
- **Conteúdo solicitado:** Serviço que exige avaliação individual, motivo seguro para informar e limites do atendimento automático. Confirmar a flag de consulta humana.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** Especialista + PO.
- **reviewed_at:** ____________________

### 21. `orientacao-preparo-a-confirmar`

- **fact_id proposto (`id`):** `orientacao-preparo-a-confirmar`
- **category:** `policy` · **fact_type:** `technical` · **status:** `draft`
- **topic proposto:** a definir por serviço e preparo; confirmar os termos relevantes.
- **Conteúdo solicitado:** Orientação de preparo que o especialista autoriza informar de forma geral; condições e limites de aplicação.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** Especialista + PO.
- **reviewed_at:** ____________________

### 22. `orientacao-cuidados-a-confirmar`

- **fact_id proposto (`id`):** `orientacao-cuidados-a-confirmar`
- **category:** `policy` · **fact_type:** `technical` · **status:** `draft`
- **topic proposto:** a definir por serviço e cuidados; confirmar os termos relevantes.
- **Conteúdo solicitado:** Cuidados gerais seguros aprovados, condições e situações em que é necessária avaliação individual.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** Especialista + PO.
- **reviewed_at:** ____________________

### 23. `limites-resultados-a-confirmar`

- **fact_id proposto (`id`):** `limites-resultados-a-confirmar`
- **category:** `policy` · **fact_type:** `technical` · **status:** `draft`
- **topic proposto:** a definir por serviço e resultado; confirmar os termos relevantes.
- **Conteúdo solicitado:** O que pode ser afirmado sobre resultados e quais limites precisam acompanhar a informação, sem garantia inventada.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** Especialista + PO.
- **reviewed_at:** ____________________

### 24. `handoff-tecnico-a-confirmar`

- **fact_id proposto (`id`):** `handoff-tecnico-a-confirmar`
- **category:** `handoff_condition` · **fact_type:** `technical` · **status:** `draft`
- **topic proposto:** a definir por gatilho técnico específico; confirmar os termos relevantes.
- **Conteúdo solicitado:** Situação técnica específica que exige profissional humano; texto seguro, sem diagnóstico nem recomendação personalizada inventada.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** Especialista + PO.
- **reviewed_at:** ____________________

### 25. `handoff-operacional-a-confirmar`

- **fact_id proposto (`id`):** `handoff-operacional-a-confirmar`
- **category:** `handoff_condition` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** a definir por gatilho operacional específico; confirmar os termos relevantes.
- **Conteúdo solicitado:** Situação operacional/comercial específica que exige humano, com gatilho inequívoco e responsabilidade confirmada.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

### 26. `handoff-excecao-a-confirmar`

- **fact_id proposto (`id`):** `handoff-excecao-a-confirmar`
- **category:** `handoff_condition` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic proposto:** a definir por exceção específica; confirmar os termos relevantes.
- **Conteúdo solicitado:** Outra exceção concreta aprovada pelo responsável que exige humano; não usar uma condição genérica selecionada em toda conversa.
- **statement a aprovar:** ____________________
- **source humana:** ____________________
- **Responsável pela validação:** PO.
- **reviewed_at:** ____________________

## Uso pelo Reply AST e limites de publicação

Uma parte `{"kind": "fact", "knowledge_ref": "id-do-fato"}` referencia o `id`.
O mesmo ID deve estar declarado em `LLMDecision.knowledge_refs` e pertencer ao
conjunto **aprovado e selecionado para aquela resposta**. O renderer insere o
`statement` integral; modelo e Customer não podem mudar seu valor, moeda,
condições ou negação. `reply_text` e `critical_claims` do modelo não autorizam fatos.

O modelo pode combinar partes fact e frases institucionais. Escreva statements
curtos e autossuficientes, com nome do serviço/profissional e condições no próprio
texto. A resposta final tem teto de 800 caracteres; o schema do fact não impõe
esse teto, mas o renderer rejeita statements/respostas que excedem seus limites.

A seleção atual compara termos de `topic` com a consulta (normalização sem
acentos, tokens de pelo menos 3 caracteres), ordena por ID e respeita orçamento.
Não há busca semântica, stemming ou garantia de escolher todas as fichas relevantes.
Use nomes específicos e variantes de pergunta confirmadas; evite palavra genérica
que selecione políticas de outro serviço. Políticas obrigatórias acompanham o
serviço selecionado ou todo o conjunto é omitido por falta de orçamento.

Um `handoff_condition` selecionado **sempre** propõe handoff. Seu statement não
é uma condição executável: “se valor exceder X” não cria comparação numérica.
Não publicar gatilhos amplos ou condicionais que exigem lógica inexistente.
Serviço com `requires_human_consultation: true` selecionado também exige handoff;
nesse caminho a aplicação pode enviar só a confirmação segura, não seus fatos.

Preços e regras devem carregar todas as condições na mesma statement quando
necessário: somente o vínculo em um fact `service` força `mandatory_policy_ids`.
Um fact `price` selecionado isoladamente não carrega automaticamente outra política.
O Intent de promoção/desconto exige fact renderizado de categoria `policy`.

Não cadastrar disponibilidade atual, agendamentos de Customers ou promessas de
criação/alteração/cancelamento automático. A ficha de agendamento descreve apenas
o procedimento humano aprovado. Serviços, profissionais e condições não
confirmados continuam indisponíveis para respostas factuais.

## Gaps que a revisão humana precisa fechar

- O YAML atual tem **zero facts**; ainda faltam conteúdo, fontes, revisão e aprovação.
- A granularidade final depende do catálogo humano; as 26 fichas são o lote inicial,
  não uma afirmação de que existem 26 fatos publicáveis.
- O schema valida estrutura e metadados, mas não comprova identidade do aprovador,
  origem, atualidade, coerência comercial ou validação técnica. Isso depende da revisão.
- Promoções/exceções não expiram automaticamente. Confirmar quem revisará/removerá
  conteúdo ao fim da vigência antes de publicá-lo; uma data no texto não desativa o fact.
- Valores, condições e limites técnicos precisam estar completos no texto aprovado;
  o renderer preserva também um erro humano que tenha sido aprovado.
- Handoff condicional, disponibilidade em tempo real e execução de agendamento não
  são implementados pela inclusão de YAML. Não foi identificado bug de schema que
  exija mudança de código para este intake.

## Registro de decisão humana — preencher depois

Para cada ficha preenchida, responder:

- ID:
- Texto integral final autorizado (`statement`):
- Fonte humana (`source`):
- Data real de revisão (`reviewed_at`):
- Se técnico: quem validou e qual registro comprova (`validated_by` somente após validar):
- Decisão do PO: aprovar para futura publicação / ajustar / não publicar:
- Nome do aprovador final, somente se aprovação concedida:
- Se serviço: flag de consulta e IDs de políticas confirmados:

Uma resposta em bloco pode aprovar vários IDs se identificar a revisão exata e
os respectivos textos/fontes. Campos em branco não contam como aprovação.
Aprovação final pelo PO não substitui a validação técnica exigida pelo schema.

Referências: [contrato Knowledge](salon-knowledge.md),
[trusted rendering](structured-decision.md),
[schema/repository](../src/rj_studio_ai/salon_knowledge.py).
