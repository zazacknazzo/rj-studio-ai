# Intake humano — Salon Knowledge do RJ Studio

Estado: **22 facts `approved` publicados no YAML de runtime e 8 facts `draft` preservados no intake**.
Base inicial: `f8e7ff695b0947c82486afe54aae14acd118713f`.
Conteúdo aprovado pelo product owner: commit `0b017cdb0d8fbd5c03e25854cab318a7b6fded8d`.
Dados institucionais/comerciais: responsável do RJ Studio via WhatsApp em
**02/10/2026**, conforme transcrição fornecida pelo responsável do produto.
Correções posteriores são identificadas na fonte de cada ficha; sua data não foi informada.

O WhatsApp abaixo é o contato institucional explicitamente fornecido. Não há
dados de Customers, fixtures, pesquisa externa ou credenciais. O YAML de runtime
usa `version: 1` e contém exclusivamente os 22 facts comerciais/institucionais aprovados.

## Estado de confiança e revisão

- `approved` no intake: os 22 dados institucionais/comerciais antes `pending`
  foram aprovados explicitamente pelo product owner em 02/10/2026. A aprovação
  corresponde aos textos/fontes do commit indicado; o conjunto está publicado no YAML.
- `draft` técnico: duração/resultado informados ainda exigem validação técnica.
- `draft` provisório: propostas/inferências que não vieram da responsável do salão.
- Os 22 facts aprovados recebem `approved_by: rj-studio-product-owner`
  e `reviewed_at: 2026-10-02`, conforme aprovação humana atual.
- Os oito drafts continuam sem `approved_by`, com revisão/validação ainda pendentes.
  Todas as fichas mantêm `validated_by: []`; nenhuma validação técnica foi inferida.
- Responsável operacional pela aprovação: product owner; fatos técnicos precisam
  de Joelma e/ou Rogério, sem atribuir validação já realizada a qualquer pessoa.

Os textos de `statement` preservam a versão aprovada ou o draft identificado, com valores,
qualificadores e condições da fonte. Não deduzir inclusões, disponibilidade,
especialidades, duração adicional ou política a partir da existência de um preço.

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
`appointment` ou `availability`. Duração é descrita no `statement` de um fact técnico de serviço;
pagamento, descontos/promos, orçamento e agendamento usam `policy` nas fichas.
Preços de serviços usam `price`. Uma orientação técnica usa categoria existente
(por exemplo `policy`) com `fact_type: technical`; não existe categoria `technical`.

Para cada serviço, preencher adicionalmente, sem aceitar defaults por omissão:

- `requires_human_consultation`: **a confirmar — true ou false**;
- `mandatory_policy_ids`: **a confirmar — IDs de políticas reais, ou lista vazia confirmada**.

As fichas abaixo são Markdown de intake, **não YAML pronto para carregar**.
A data da fonte não comprova revisão/publicação. Os 22 facts aprovados têm a
data da aprovação atual; os oito drafts ainda não têm revisão humana registrada
em `reviewed_at`. A lacuna impede carregar esses drafts pelo loader mesmo como
draft. Não inventar uma data para satisfazer validação.

## Facts comerciais/institucionais publicados e drafts preservados

IDs propostos são estáveis após publicação. `topic` é metadata de busca proposta,
sem aprovação implícita de serviço, efeito ou regra. Cada preço inclui o nome do
serviço e suas condições; faixas relacionadas ficam juntas.

### 01. `identidade-institucional`

- **id:** `identidade-institucional`
- **category:** `identity` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** nome salão studio identidade beleza
- **statement aprovado:** O nome do salão é RJ Studio de Beleza.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 02. `tempo-mesmo-endereco`

- **id:** `tempo-mesmo-endereco`
- **category:** `identity` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** história tempo anos endereço studio
- **statement aprovado:** Em 02/10/2026, foi informado que o RJ Studio de Beleza está há 22 anos no mesmo endereço.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 03. `localizacao-publica`

- **id:** `localizacao-publica`
- **category:** `location` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** endereço localização onde fica avenida doutor zuquim santana
- **statement aprovado:** O RJ Studio de Beleza fica na Avenida Dr. Zuquim, 1854, Santana.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 04. `horarios-atendimento`

- **id:** `horarios-atendimento`
- **category:** `hours` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** horário funcionamento abre fecha terça quarta quinta sexta sábado
- **statement aprovado:** O funcionamento informado é de terça a sábado, das 9h às 18h30.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 05. `contato-publico`

- **id:** `contato-publico`
- **category:** `channel` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** whatsapp telefone contato número falar salão
- **statement aprovado:** O WhatsApp principal do RJ Studio de Beleza é (11) 98289-6366.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 06. `precos-cortes`

- **id:** `precos-cortes`
- **category:** `price` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** corte feminino mulher masculino homem cortar
- **statement aprovado:** Corte feminino: R$ 100,00. Corte masculino: R$ 60,00.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 07. `precos-escova`

- **id:** `precos-escova`
- **category:** `price` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** escova cabelo curto médio longo extra
- **statement aprovado:** Escova: cabelo curto, R$ 50,00; curto a médio, R$ 60,00; longo, R$ 70,00; longo a extra longo, R$ 80,00; extra longo, R$ 90,00.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 08. `precos-progressiva`

- **id:** `precos-progressiva`
- **category:** `price` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** progressiva escova alisar alisamento cabelo liso
- **statement aprovado:** Escova progressiva: curto, R$ 180,00; médio, R$ 200,00; longo, R$ 250,00; extra longo, R$ 270,00.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 09. `precos-coloracao`

- **id:** `precos-coloracao`
- **category:** `price` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** coloração coloracao raiz completa aplicação aplicar
- **statement aprovado:** Coloração de raiz: R$ 140,00. Coloração completa: R$ 170,00. Aplicação de coloração: R$ 90,00.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 10. `preco-gloss-express`

- **id:** `preco-gloss-express`
- **category:** `price` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** gloss express
- **statement aprovado:** Gloss Express: R$ 170,00.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 11. `preco-botox-capilar`

- **id:** `preco-botox-capilar`
- **category:** `price` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** botox capilar
- **statement aprovado:** Botox capilar: R$ 180,00.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 12. `preco-tonalizacao`

- **id:** `preco-tonalizacao`
- **category:** `price` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** tonalização tonalizar
- **statement aprovado:** Tonalização: R$ 150,00.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 13. `preco-reconstrucao-capilar`

- **id:** `preco-reconstrucao-capilar`
- **category:** `price` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** reconstrução capilar
- **statement aprovado:** Reconstrução capilar: R$ 220,00.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 14. `preco-cauterizacao`

- **id:** `preco-cauterizacao`
- **category:** `price` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** cauterização
- **statement aprovado:** Cauterização: R$ 180,00.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 15. `preco-limpeza-cor`

- **id:** `preco-limpeza-cor`
- **category:** `price` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** limpeza cor
- **statement aprovado:** Limpeza de cor: a partir de R$ 300,00.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 16. `preco-mechas-reflexo`

- **id:** `preco-mechas-reflexo`
- **category:** `price` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** mechas reflexo luzes orçamento
- **statement aprovado:** Mechas ou reflexo custam a partir de R$ 500,00. O valor varia conforme comprimento, quantidade de cabelo, quantidade de mechas, cor e modelo de mechas.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 17. `precos-mega-hair`

- **id:** `precos-mega-hair`
- **category:** `price` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** mega hair megahair alongamento ponto americano fita adesiva queratina
- **statement aprovado:** Mega hair: ponto americano, a partir de R$ 400,00; fita adesiva, a partir de R$ 500,00; queratina, a partir de R$ 500,00. O valor varia conforme a quantidade.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026. Confirmação posterior pelo responsável do produto: o termo original corresponde a QUERATINA; data dessa confirmação não informada.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 18. `precos-unhas`

- **id:** `precos-unhas`
- **category:** `price` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** unhas manicure pedicure gel esmaltação blindagem
- **statement aprovado:** Manicure: R$ 42,00. Pedicure: R$ 48,00. Unha de gel: R$ 150,00. Esmaltação em gel: R$ 70,00. Blindagem: R$ 100,00.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 19. `precos-sobrancelhas`

- **id:** `precos-sobrancelhas`
- **category:** `price` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** sobrancelha sobrancelhas design desenho henna fio despigmentação
- **statement aprovado:** Design de sobrancelha: R$ 50,00. Design de sobrancelha com henna: R$ 80,00. Sobrancelha fio a fio: R$ 400,00. Despigmentação de sobrancelhas: R$ 250,00 por sessão.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026. Confirmação posterior pelo responsável do produto: o termo original corresponde a HENNA; data dessa confirmação não informada.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 20. `precos-penteados`

- **id:** `precos-penteados`
- **category:** `price` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** penteado penteados social noiva
- **statement aprovado:** Penteado social: R$ 200,00. Penteado de noiva: R$ 350,00.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 21. `precos-maquiagem`

- **id:** `precos-maquiagem`
- **category:** `price` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** maquiagem maquiar social noiva
- **statement aprovado:** Maquiagem social: R$ 200,00. Maquiagem de noiva: R$ 350,00.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 22. `precos-depilacao`

- **id:** `precos-depilacao`
- **category:** `price` · **fact_type:** `operational_commercial` · **status:** `approved`
- **topic:** depilação depilar virilha simples íntima buço axila meia perna completa
- **statement aprovado:** Depilação: virilha simples, R$ 70,00; virilha íntima, R$ 90,00; buço, R$ 35,00; axila, R$ 40,00; meia perna, R$ 50,00; perna completa, R$ 80,00.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** `2026-10-02`
- **approved_by:** `rj-studio-product-owner`
- **Responsável pela validação:** product owner.

### 23. `tecnica-botox-capilar`

- **id:** `tecnica-botox-capilar`
- **category:** `service` · **fact_type:** `technical` · **status:** `draft`
- **topic:** botox capilar execução tempo duração resultado hábitos
- **statement a revisar:** Informação técnica a validar: o tempo de execução informado para botox capilar é de aproximadamente 2 horas; o resultado informado pode durar até 60 dias. A duração varia conforme hábitos do cabelo e grau de exigência da cliente.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026.
- **validated_by:** `[]`
- **reviewed_at:** pendente de revisão humana registrada.
- **Responsável pela validação:** Joelma e/ou Rogério, seguida de aprovação final do product owner.

### 24. `tecnica-progressiva`

- **id:** `tecnica-progressiva`
- **category:** `service` · **fact_type:** `technical` · **status:** `draft`
- **topic:** progressiva escova execução tempo duração resultado hábitos
- **statement a revisar:** Informação técnica a validar: o tempo de execução informado para escova progressiva é de aproximadamente 2 horas; a duração pretendida informada é de até 90 dias. A duração varia conforme hábitos do cabelo e grau de exigência da cliente.
- **source:** Informação fornecida pela responsável do RJ Studio via WhatsApp em 02/10/2026. Confirmação posterior pelo responsável do produto: a duração pretendida na mensagem original foi até 90 dias; data dessa confirmação não informada.
- **validated_by:** `[]`
- **reviewed_at:** pendente de revisão humana registrada.
- **Responsável pela validação:** Joelma e/ou Rogério, seguida de aprovação final do product owner.

### 25. `horarios-segunda-domingo-provisorio`

- **id:** `horarios-segunda-domingo-provisorio`
- **category:** `hours` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic:** segunda domingo funcionamento
- **statement a revisar:** PROVISÓRIO: considerar que não há funcionamento regular na segunda-feira e no domingo, por inferência do horário informado de terça a sábado. Isso não constitui confirmação de fechamento.
- **source:** Proposta provisória fornecida pelo responsável do produto neste intake. Não veio diretamente da responsável do salão; depende de confirmação humana.
- **validated_by:** `[]`
- **reviewed_at:** pendente de revisão humana registrada.
- **Responsável pela validação:** product owner; regras provisórias também exigem confirmação da responsável do salão.

### 26. `horarios-excecoes`

- **id:** `horarios-excecoes`
- **category:** `hours` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic:** feriados feriado funcionamento
- **statement a revisar:** PROVISÓRIO: confirmar o funcionamento em feriados com a equipe; não prometer abertura nem fechamento.
- **source:** Proposta provisória fornecida pelo responsável do produto neste intake. Não veio diretamente da responsável do salão; depende de confirmação humana.
- **validated_by:** `[]`
- **reviewed_at:** pendente de revisão humana registrada.
- **Responsável pela validação:** product owner; regras provisórias também exigem confirmação da responsável do salão.

### 27. `classificacao-comprimento-provisoria`

- **id:** `classificacao-comprimento-provisoria`
- **category:** `policy` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic:** comprimento curto médio longo extra cabelo avaliação
- **statement a revisar:** PROVISÓRIO: a IA não deve definir sozinha se um cabelo é curto, médio, longo ou extra longo, nem criar faixas em centímetros. Quando a classificação afetar o preço, solicitar avaliação/foto ou confirmação da equipe.
- **source:** Proposta provisória fornecida pelo responsável do produto neste intake. Não veio diretamente da responsável do salão; depende de confirmação humana.
- **validated_by:** `[]`
- **reviewed_at:** pendente de revisão humana registrada.
- **Responsável pela validação:** product owner; regras provisórias também exigem confirmação da responsável do salão.

### 28. `avaliacao-mechas-provisoria`

- **id:** `avaliacao-mechas-provisoria`
- **category:** `policy` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic:** mechas reflexo luzes avaliação orçamento
- **statement a revisar:** PROVISÓRIO: exigir avaliação antes de confirmar o preço final de mechas/reflexo. Preservar o preço informado a partir de R$ 500,00.
- **source:** Proposta provisória fornecida pelo responsável do produto neste intake. Não veio diretamente da responsável do salão; depende de confirmação humana.
- **validated_by:** `[]`
- **reviewed_at:** pendente de revisão humana registrada.
- **Responsável pela validação:** product owner; regras provisórias também exigem confirmação da responsável do salão.

### 29. `avaliacao-mega-hair-provisoria`

- **id:** `avaliacao-mega-hair-provisoria`
- **category:** `policy` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic:** mega hair megahair quantidade avaliação orçamento
- **statement a revisar:** PROVISÓRIO: exigir avaliação antes de confirmar o preço final de mega hair. Preservar os valores a partir de; não calcular a quantidade automaticamente.
- **source:** Proposta provisória fornecida pelo responsável do produto neste intake. Não veio diretamente da responsável do salão; depende de confirmação humana.
- **validated_by:** `[]`
- **reviewed_at:** pendente de revisão humana registrada.
- **Responsável pela validação:** product owner; regras provisórias também exigem confirmação da responsável do salão.

### 30. `aplicacao-coloracao-limites-provisorios`

- **id:** `aplicacao-coloracao-limites-provisorios`
- **category:** `policy` · **fact_type:** `operational_commercial` · **status:** `draft`
- **topic:** aplicação coloração produto incluso incluído fornecido cliente
- **statement a revisar:** PROVISÓRIO: para aplicação de coloração, o preço informado é R$ 90,00; não inferir se o produto está incluído ou se a cliente fornece a coloração.
- **source:** Proposta provisória fornecida pelo responsável do produto neste intake. Não veio diretamente da responsável do salão; depende de confirmação humana. O preço citado foi fornecido pela responsável do RJ Studio via WhatsApp em 02/10/2026; a regra sobre não inferir inclusões é provisória.
- **validated_by:** `[]`
- **reviewed_at:** pendente de revisão humana registrada.
- **Responsável pela validação:** product owner; regras provisórias também exigem confirmação da responsável do salão.

## Dados ainda não fornecidos — manter em aberto

Estas fichas de coleta **não entram nos 30 facts preenchidos acima**. Continuam
como campos vazios de intake, sem afirmar presença/ausência de política ou serviço.
Seu estado inicial continua `draft`; não têm fonte, data de revisão ou aprovador.

| ID proposto da ficha | Categoria/tipo propostos | Informação humana necessária |
| --- | --- | --- |
| `profissional-a-confirmar` | `professional` / operacional | Nomes autorizados, serviços e especialidades confirmadas; nenhum nome de validador implica que atende determinado serviço. |
| `formas-pagamento` | `policy` / operacional | Meios aceitos e restrições. |
| `condicoes-parcelamento` | `policy` / operacional | Existência de parcelamento, parcelas, taxas e limites. |
| `politica-descontos` | `policy` / operacional | Descontos autorizados, elegibilidade e limites, ou ausência explicitamente confirmada. |
| `promocao-a-confirmar` | `policy` / operacional | Promoções reais, vigência e condições, ou ausência confirmada. |
| `politica-atrasos` | `policy` / operacional | Tolerância e procedimento real. |
| `politica-sinal-reembolso` | `policy` / operacional | Sinal, reembolso e respectivas condições. |
| `politica-agendamento` | `policy` / operacional | Como solicitar e quem confirma o agendamento. |
| `politica-alteracao` | `policy` / operacional | Procedimento e condições de alteração/remarcação. |
| `politica-cancelamento` | `policy` / operacional | Procedimento e condições de cancelamento. |
| `avaliacao-servico-a-confirmar` | `service` / técnico | Serviços que realmente exigem avaliação; flag de consulta e IDs de políticas, após confirmação. |
| `orientacao-preparo-a-confirmar` | `policy` / técnico | Preparo seguro e limites, após validação técnica. |
| `orientacao-cuidados-a-confirmar` | `policy` / técnico | Cuidados seguros e limites, após validação técnica. |
| `handoff-tecnico-a-confirmar` | `handoff_condition` / técnico | Gatilhos técnicos específicos aprovados. |
| `handoff-operacional-a-confirmar` | `handoff_condition` / operacional | Gatilhos operacionais/comerciais específicos aprovados. |
| `handoff-excecao-a-confirmar` | `handoff_condition` / operacional | Outras exceções específicas confirmadas. |

## Ambiguidades e gaps ainda abertos

- Endereço: cidade, UF, CEP e orientações de acesso não foram informados; não
  completar por dedução. “Santana” e o número informado foram preservados.
- Horário: não inferir fuso, horário específico do WhatsApp, atendimento regular
  na segunda/domingo ou exceções de feriado.
- Os 22 anos são uma informação de 02/10/2026, sem data de início comprovada;
  não converter em ano de fundação nem atualizar automaticamente.
- Faixas de comprimento não têm definição objetiva confirmada. Não criar
  centímetros nem classificar o cabelo automaticamente.
- Aplicação de coloração: inclusões/produto fornecido continuam desconhecidos.
- Mechas/reflexo e mega hair preservam os fatores de variação informados. Avaliação
  obrigatória é proposta `draft`, não política comercial confirmada. Unidade de
  quantidade do mega hair não foi informada; não calcular fios/gramas.
- Despigmentação de sobrancelhas: R$ 250,00 **por sessão**; número de sessões e
  resultado não foram informados.
- Botox/progressiva: aproximadamente 2 horas e até 60/90 dias são informações
  técnicas `draft`. “Hábitos do cabelo” e “grau de exigência da cliente” exigem
  esclarecimento profissional antes de uso. Não tratar duração como garantia.
- Os oito drafts ainda não têm `reviewed_at` humano. O schema exige data inclusive
  em `draft`; este Markdown registra a lacuna. Os 22 facts aprovados têm a data
  da aprovação atual; isso não constitui validação dos drafts.
- Flags `requires_human_consultation` e `mandatory_policy_ids` dos facts técnicos
  de serviço não foram confirmadas. Omissão/default não é autorização de atendimento
  sem avaliação. Não criar vínculo obrigatório com políticas provisórias.
- Os preços estão corretamente em categoria `price`. O catálogo descritivo de
  `service` para respostas de informação de serviço ainda precisa ser composto e
  revisado a partir desses mesmos dados comerciais, sem criar descrição técnica.
  O renderer exige categoria `service` para esse Intent; preço isolado não a supre.
- Topics usam o nome e variantes específicas. A seleção lexical atual é por
  qualquer termo em comum, sem ranking semântico: termos como cabelo, escova,
  social e noiva ainda podem selecionar mais de um grupo. Preço em pergunta genérica
  não identifica sozinho o serviço. Revisar seleção antes do piloto, sem alterar
  código nesta tarefa. Topics não tornam uma inferência em fato confiável.
- Um `handoff_condition` selecionado sempre aciona encaminhamento; não cadastrar
  condições numéricas/genéricas como se o texto executasse comparação.
- A proposta de solicitar foto é só um `draft` operacional. Não habilita análise
  de fotos nem implementa multimodal. Vigência/expiração de promoções também não
  é automatizada pelo schema.

## Reply AST e critérios para futuras publicações

Uma parte `{"kind": "fact", "knowledge_ref": "id-do-fato"}` usa o `id` da ficha.
O mesmo ID deve constar em `knowledge_refs` e pertencer ao conjunto aprovado e
selecionado. O renderer insere a `statement` inteira; modelo/Customer não alteram
valores, moeda, condições ou negação. `reply_text` e `critical_claims` do modelo
não autorizam fatos. Statements completos devem caber na resposta de 800 caracteres.

Somente facts `service` podem vincular `mandatory_policy_ids`; um `price` isolado
não carrega política automaticamente. Por isso, condições comerciais confirmadas
já acompanham seus preços. Regras provisórias permanecem separadas. Disponibilidade
atual, reserva, agenda e alterações automáticas não são criadas por este documento.

Próximos registros humanos dos drafts, por ID: texto final, fonte, data real de
revisão, confirmação de regras provisórias, validação técnica quando exigida e
decisão final do product owner. **Há 22 facts aprovados no runtime e oito drafts
preservados exclusivamente no intake.**

## Registro de aprovação humana — 02/10/2026

O product owner declarou neste chat: “Aprovo os 22 facts pending do intake do
RJ Studio no commit 0b017cdb. Os 8 facts draft devem continuar draft.”

A aprovação abrange exclusivamente as fichas 01–22 (IDs, statements e sources)
do commit `0b017cdb0d8fbd5c03e25854cab318a7b6fded8d`. Os respectivos metadados
de status, aprovador e revisão foram registrados; os textos e fontes não foram
alterados. Fichas 23–30 e as fichas de coleta vazias continuam sem aprovação.
Esse registro inicial não atribuiu validação técnica nem publicou o YAML; a
publicação posterior autorizada está registrada abaixo.

## Registro de publicação no YAML — 02/10/2026

Foram materializados em `knowledge/rj_studio.yaml` exclusivamente os 22 IDs das
fichas 01–22 acima, vinculados à aprovação do conteúdo de `0b017cdb`. Os IDs,
topics, statements e sources foram copiados sem alteração. Todos usam
`status: approved`, `fact_type: operational_commercial`, `reviewed_at: 2026-10-02`,
`approved_by: rj-studio-product-owner` e `validated_by: []`. O identificador do
aprovador representa o papel estável do responsável pelo produto; não atribui
nome completo nem uma validação técnica.

As oito fichas 23–30 permanecem **literalmente inalteradas**, como `draft`,
e não foram incluídas no YAML. As fichas de coleta vazias também permanecem fora.
Nenhum campo de consulta humana ou vínculo de política foi inferido. O arquivo
publicado não contém fatos técnicos, regras provisórias, serviços descritivos,
profissionais ou políticas adicionais.

Validação da publicação: `SalonKnowledgeRepository` carregou exatamente os
22 IDs aprovados, sem referência inválida, com igualdade de IDs/topics/textos/fontes
em relação ao commit aprovado. Foram preservados os 43 valores, os cinco
“a partir de” e o “por sessão”. Testes Knowledge/grounding: 68 passaram; suíte
completa: 440 passaram, com um aviso existente de depreciação do Starlette.
Ruff check/format, compileall, pip check e diff check passaram. Não houve mudança
de código, teste, migration, provider ou configuração local.

Referências: [contrato Knowledge](salon-knowledge.md),
[trusted rendering](structured-decision.md),
[schema/repository](../src/rj_studio_ai/salon_knowledge.py).
