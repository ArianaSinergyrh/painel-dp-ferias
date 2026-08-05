-- Migração: hierarquia de papéis (Analista / Coordenador / Gerente / Diretor)
-- Rode isso no SQL Editor do Supabase DEPOIS do schema.sql original.
--
-- Regras de visão:
--   Analista    -> só os clientes liberados diretamente para ele (acesso_empresas)
--   Coordenador -> os dele + os dos analistas que estão abaixo dele (supervisor_id)
--   Gerente     -> os dele + toda a equipe abaixo (coordenadores e analistas ligados a eles)
--   Diretor     -> todos os clientes, de todas as equipes, sem exceção

alter table perfis add column if not exists cargo text not null default 'analista'
    check (cargo in ('analista', 'coordenador', 'gerente', 'diretor'));

alter table perfis add column if not exists supervisor_id uuid references perfis(id) on delete set null;
alter table perfis add column if not exists email text;

-- preenche o e-mail de quem já existe (necessário para o botão "enviar redefinição de senha")
update perfis set email = u.email from auth.users u where perfis.id = u.id and perfis.email is null;

-- quem já era administrador (is_admin = true) vira Diretor automaticamente
update perfis set cargo = 'diretor' where is_admin = true and cargo = 'analista';

-- a partir de agora, todo cadastro novo já grava o e-mail junto (recria a function do schema.sql)
create or replace function public.handle_new_user()
returns trigger as $$
begin
    insert into public.perfis (id, nome_completo, email, is_admin)
    values (new.id, coalesce(new.raw_user_meta_data->>'nome_completo', new.email), new.email, false);
    return new;
end;
$$ language plpgsql security definer;

-- retorna o próprio usuário + todos os que estão abaixo dele na hierarquia
-- (segue supervisor_id recursivamente: se A supervisiona B e B supervisiona C, subordinados_de(A) = {A, B, C})
create or replace function subordinados_de(usuario uuid)
returns table(id uuid)
language sql
stable
security definer
as $$
    with recursive arvore as (
        select p.id from perfis p where p.id = usuario
        union all
        select p.id from perfis p join arvore a on p.supervisor_id = a.id
    )
    select id from arvore;
$$;

-- perfis: permitir que cada um veja seu próprio registro, gerente/diretor veem todos (para montar a equipe)
drop policy if exists "perfis: leitura propria ou admin" on perfis;
create policy "perfis_select" on perfis
    for select using (
        id = auth.uid()
        or exists (select 1 from perfis p where p.id = auth.uid() and p.cargo in ('gerente', 'diretor'))
    );

create policy "perfis_update_gestor" on perfis
    for update using (
        exists (select 1 from perfis p where p.id = auth.uid() and p.cargo in ('gerente', 'diretor'))
    );

-- processamentos: leitura segue a mesma regra de hierarquia (self + subordinados, ou tudo se diretor)
drop policy if exists "processamentos: leitura por acesso" on processamentos;
create policy "processamentos_select_hierarquia" on processamentos
    for select using (
        exists (select 1 from perfis p where p.id = auth.uid() and p.cargo = 'diretor')
        or empresa_id in (
            select empresa_id from acesso_empresas
            where usuario_id in (select id from subordinados_de(auth.uid()))
        )
    );

-- empresas: diretor/gerente/coordenador podem cadastrar e editar clientes
drop policy if exists "empresas: escrita admin" on empresas;
drop policy if exists "empresas: update admin" on empresas;
create policy "empresas_insert_gestor" on empresas
    for insert with check (
        exists (select 1 from perfis p where p.id = auth.uid() and p.cargo in ('gerente', 'diretor'))
    );
create policy "empresas_update_gestor" on empresas
    for update using (
        exists (select 1 from perfis p where p.id = auth.uid() and p.cargo in ('gerente', 'diretor'))
    );

-- acesso_empresas: gerente/diretor liberam clientes para qualquer um da equipe
drop policy if exists "acesso: escrita admin" on acesso_empresas;
drop policy if exists "acesso: update admin" on acesso_empresas;
create policy "acesso_insert_gestor" on acesso_empresas
    for insert with check (
        exists (select 1 from perfis p where p.id = auth.uid() and p.cargo in ('gerente', 'diretor'))
    );
create policy "acesso_update_gestor" on acesso_empresas
    for update using (
        exists (select 1 from perfis p where p.id = auth.uid() and p.cargo in ('gerente', 'diretor'))
    );

-- parâmetros fiscais: só gerente/diretor mexem nas tabelas de INSS/IRRF
drop policy if exists "parametros_faixas: escrita admin" on parametros_faixas;
drop policy if exists "parametros_faixas: update admin" on parametros_faixas;
create policy "faixas_insert_gestor" on parametros_faixas
    for insert with check (
        exists (select 1 from perfis p where p.id = auth.uid() and p.cargo in ('gerente', 'diretor'))
    );
create policy "faixas_update_gestor" on parametros_faixas
    for update using (
        exists (select 1 from perfis p where p.id = auth.uid() and p.cargo in ('gerente', 'diretor'))
    );

drop policy if exists "parametros_gerais: escrita admin" on parametros_gerais;
drop policy if exists "parametros_gerais: upsert admin" on parametros_gerais;
create policy "gerais_insert_gestor" on parametros_gerais
    for insert with check (
        exists (select 1 from perfis p where p.id = auth.uid() and p.cargo in ('gerente', 'diretor'))
    );
create policy "gerais_update_gestor" on parametros_gerais
    for update using (
        exists (select 1 from perfis p where p.id = auth.uid() and p.cargo in ('gerente', 'diretor'))
    );
