# Guia de Instalação — Painel DP (sem precisar de TI)

Este guia assume que você nunca fez nada parecido antes. São ~20 minutos,
só clicando — nenhum comando de terminal é necessário.

Vamos usar dois serviços gratuitos:

- **Supabase** — guarda o login dos analistas, os clientes cadastrados e as
  tabelas de INSS/IRRF.
- **Streamlit Community Cloud** — coloca o painel no ar, com um link que
  qualquer analista acessa pelo navegador.

---

## Parte 1 — Criar o banco de dados (Supabase)

1. Acesse **supabase.com** e clique em "Start your project". Crie uma conta
   (dá pra usar login do GitHub ou e-mail/senha).
2. Clique em **New project**. Dê um nome (ex.: `painel-dp-sinergy`), crie uma
   senha de banco de dados (guarde essa senha em lugar seguro) e escolha a
   região mais próxima (South America - São Paulo, se disponível).
3. Espere ~2 minutos o projeto ser criado.
4. No menu à esquerda, clique em **SQL Editor** → **New query**.
5. Abra o arquivo `db/schema.sql` (está junto com este guia), copie todo o
   conteúdo, cole no editor do Supabase e clique em **Run**. Isso cria todas
   as tabelas, já com as tabelas de INSS/IRRF de abril/2026 pré-carregadas.
6. Vá em **Authentication → Users → Add user**. Crie o seu próprio usuário
   (seu e-mail + uma senha). Esse é o primeiro login do painel.
7. Copie o **UID** desse usuário que aparece na lista.
8. Volte no **SQL Editor**, rode este comando (troque `<SEU-UUID>` pelo UID
   copiado e ajuste seu nome):
   ```sql
   update perfis set is_admin = true, nome_completo = 'Ariana Santana'
   where id = '<SEU-UUID>';
   ```
   Isso te torna administradora do painel (pode cadastrar clientes, liberar
   acesso de outros analistas e editar as tabelas fiscais).
9. Ainda no Supabase, vá em **Project Settings → API**. Anote dois valores:
   - **Project URL**
   - **anon public key**
   Vai precisar deles na Parte 2.

Para cadastrar os outros analistas depois, repita o passo 6 (Add user) para
cada um — o painel já libera o acesso deles automaticamente, só falta você
entrar na aba "Administração" e marcar quais clientes cada um pode ver.

---

## Parte 2 — Colocar o painel no ar (Streamlit Community Cloud)

1. Acesse **github.com** e crie uma conta gratuita, se ainda não tiver.
2. Clique em **New repository**. Dê um nome (ex.: `painel-dp`), marque como
   **Private** (recomendado, já que tem lógica de cálculo fiscal) e clique em
   **Create repository**.
3. Na página do repositório vazio, clique em **uploading an existing file** e
   arraste TODOS os arquivos e pastas desta entrega (`app.py`, a pasta
   `core/`, a pasta `pages/`, a pasta `db/`, `requirements.txt`, a pasta
   `.streamlit/` — menos o `secrets.toml.example`, esse não precisa subir).
   Clique em **Commit changes**.
4. Acesse **share.streamlit.io** e faça login com sua conta do GitHub.
5. Clique em **Create app** → **From an existing repo**. Escolha o
   repositório que você acabou de criar, o branch `main` e o arquivo
   principal `app.py`.
6. Antes de clicar em "Deploy", clique em **Advanced settings → Secrets** e
   cole:
   ```toml
   SUPABASE_URL = "cole aqui a Project URL do Supabase"
   SUPABASE_ANON_KEY = "cole aqui a anon public key do Supabase"
   ```
7. Clique em **Deploy**. Em 1-2 minutos o painel estará no ar, com um link
   tipo `https://painel-dp-sinergy.streamlit.app` que você pode compartilhar
   com os analistas.

Pronto — a partir daqui, sempre que quiser atualizar o painel (por exemplo,
quando eu mandar uma versão nova do código), é só subir os arquivos novos no
mesmo repositório do GitHub (mesmo processo do passo 3) que o Streamlit
Cloud atualiza sozinho.

---

## Uso do dia a dia

- **Analistas**: acessam o link do painel, fazem login com o e-mail/senha
  que você criou pra eles, escolhem o cliente, sobem o arquivo mensal e
  baixam a conferência.
- **Você (administradora)**: além disso, acessa a aba "Administração" para
  cadastrar novos clientes, liberar quais analistas veem quais clientes, e
  atualizar as tabelas de INSS/IRRF quando a lei mudar.

## Limitações da v1 (para você saber o que esperar)

- O login não fica salvo entre sessões do navegador — se fechar a aba,
  precisa logar de novo (dá pra evoluir isso depois).
- Novos analistas são criados direto no Supabase (Authentication → Add
  user) — ainda não tem uma tela de "criar analista" dentro do próprio
  painel, mas o cadastro de acesso aos clientes já é feito por lá.
- Hoje só o processo de **Férias** está implementado. A estrutura já foi
  pensada pra receber Rescisão, Folha mensal, Benefícios e Encargos/eSocial
  como novas páginas, sem precisar redesenhar login nem cadastro de clientes.
