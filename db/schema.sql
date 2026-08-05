-- Painel DP — schema do Supabase (rodar no SQL Editor do projeto Supabase)
-- Desenhado para crescer: toda tabela relevante tem `tipo_processo` para que
-- rescisão, folha mensal, benefícios, encargos/e-Social entrem depois sem
-- precisar mudar a estrutura, só adicionar linhas/páginas novas.

-- ==================== PERFIS (1 linha por analista, ligada ao Auth) ====================
create table if not exists perfis (
    id uuid primary key references auth.users(id) on delete cascade,
    nome_completo text,
    is_admin boolean not null default false,
    criado_em timestamptz not null default now()
);

-- cria o perfil automaticamente sempre que um usuário novo é criado no Supabase Auth
create or replace function public.handle_new_user()
returns trigger as $$
begin
    insert into public.perfis (id, nome_completo, is_admin)
    values (new.id, coalesce(new.raw_user_meta_data->>'nome_completo', new.email), false);
    return new;
end;
$$ language plpgsql security definer;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute procedure public.handle_new_user();

-- ==================== EMPRESAS (clientes atendidos) ====================
create table if not exists empresas (
    id serial primary key,
    nome text not null,
    cnpj text,
    ativo boolean not null default true,
    criado_em timestamptz not null default now()
);

-- ==================== ACESSO: quais analistas veem quais clientes ====================
create table if not exists acesso_empresas (
    usuario_id uuid references perfis(id) on delete cascade,
    empresa_id int references empresas(id) on delete cascade,
    primary key (usuario_id, empresa_id)
);

-- ==================== PARÂMETROS FISCAIS (por processo) ====================
create table if not exists parametros_faixas (
    id serial primary key,
    tipo_processo text not null default 'ferias',
    tabela text not null check (tabela in ('INSS', 'IRRF')),
    faixa_ordem int not null,
    valor_ate numeric,              -- null = faixa aberta (sem limite superior)
    aliquota numeric not null,
    parcela_deduzir numeric not null default 0,
    vigencia_inicio date not null default current_date,
    ativo boolean not null default true
);

create table if not exists parametros_gerais (
    chave text not null,
    tipo_processo text not null default 'ferias',
    valor numeric not null,
    descricao text,
    primary key (chave, tipo_processo)
);

-- ==================== HISTÓRICO DE PROCESSAMENTOS ====================
create table if not exists processamentos (
    id serial primary key,
    tipo_processo text not null default 'ferias',
    empresa_id int references empresas(id),
    usuario_id uuid references perfis(id),
    criado_em timestamptz not null default now(),
    nome_arquivo text,
    total_funcionarios int,
    total_ok int,
    total_verificar int,
    total_sem_dados int
);

-- ==================== VALORES INICIAIS (tabela vigente usada no exemplo de Abril/2026) ====================
insert into parametros_faixas (tipo_processo, tabela, faixa_ordem, valor_ate, aliquota, parcela_deduzir) values
    ('ferias', 'INSS', 1, 1621.01, 0.075, 0),
    ('ferias', 'INSS', 2, 2901.84, 0.09, 24.32),
    ('ferias', 'INSS', 3, 4354.27, 0.12, 111.40),
    ('ferias', 'INSS', 4, 8475.55, 0.14, 198.49),
    ('ferias', 'IRRF', 1, 2428.80, 0.0, 0),
    ('ferias', 'IRRF', 2, 2826.65, 0.075, 182.16),
    ('ferias', 'IRRF', 3, 3751.05, 0.15, 394.16),
    ('ferias', 'IRRF', 4, 4664.68, 0.225, 675.49),
    ('ferias', 'IRRF', 5, null, 0.275, 908.73)
on conflict do nothing;

insert into parametros_gerais (chave, tipo_processo, valor, descricao) values
    ('dep_deducao', 'ferias', 189.59, 'Dedução por dependente (IRRF)'),
    ('ded_simplificada', 'ferias', 607.20, 'Dedução simplificada mensal (IRRF)'),
    ('redutor_limite', 'ferias', 7350.00, 'Limite de rendimento p/ redutor adicional'),
    ('redutor_a', 'ferias', 978.62, 'Constante A do redutor adicional'),
    ('redutor_b', 'ferias', 0.133145, 'Constante B do redutor adicional'),
    ('tolerancia', 'ferias', 0.05, 'Tolerância de diferença aceitável (R$)')
on conflict do nothing;

-- ==================== ROW LEVEL SECURITY ====================
alter table perfis enable row level security;
alter table empresas enable row level security;
alter table acesso_empresas enable row level security;
alter table parametros_faixas enable row level security;
alter table parametros_gerais enable row level security;
alter table processamentos enable row level security;

-- perfis: cada um lê o próprio; admin lê todos
create policy "perfis: leitura propria ou admin" on perfis
    for select using (id = auth.uid() or exists (select 1 from perfis p where p.id = auth.uid() and p.is_admin));

-- empresas: quem tem acesso liberado, ou admin, ou vê todas (leitura simplificada p/ v1)
create policy "empresas: leitura autenticada" on empresas
    for select using (auth.role() = 'authenticated');
create policy "empresas: escrita admin" on empresas
    for insert with check (exists (select 1 from perfis p where p.id = auth.uid() and p.is_admin));
create policy "empresas: update admin" on empresas
    for update using (exists (select 1 from perfis p where p.id = auth.uid() and p.is_admin));

-- acesso_empresas: leitura autenticada (o app já filtra pelo usuário certo); escrita só admin
create policy "acesso: leitura autenticada" on acesso_empresas
    for select using (auth.role() = 'authenticated');
create policy "acesso: escrita admin" on acesso_empresas
    for insert with check (exists (select 1 from perfis p where p.id = auth.uid() and p.is_admin));
create policy "acesso: update admin" on acesso_empresas
    for update using (exists (select 1 from perfis p where p.id = auth.uid() and p.is_admin));

-- parametros: leitura para todo autenticado, escrita só admin
create policy "parametros_faixas: leitura autenticada" on parametros_faixas
    for select using (auth.role() = 'authenticated');
create policy "parametros_faixas: escrita admin" on parametros_faixas
    for insert with check (exists (select 1 from perfis p where p.id = auth.uid() and p.is_admin));
create policy "parametros_faixas: update admin" on parametros_faixas
    for update using (exists (select 1 from perfis p where p.id = auth.uid() and p.is_admin));

create policy "parametros_gerais: leitura autenticada" on parametros_gerais
    for select using (auth.role() = 'authenticated');
create policy "parametros_gerais: escrita admin" on parametros_gerais
    for insert with check (exists (select 1 from perfis p where p.id = auth.uid() and p.is_admin));
create policy "parametros_gerais: upsert admin" on parametros_gerais
    for update using (exists (select 1 from perfis p where p.id = auth.uid() and p.is_admin));

-- processamentos: cada analista vê os seus clientes; admin vê tudo
create policy "processamentos: leitura por acesso" on processamentos
    for select using (
        exists (select 1 from perfis p where p.id = auth.uid() and p.is_admin)
        or empresa_id in (select empresa_id from acesso_empresas where usuario_id = auth.uid())
    );
create policy "processamentos: insercao autenticada" on processamentos
    for insert with check (auth.role() = 'authenticated');

-- ==================== PRIMEIRO ADMIN ====================
-- Depois de criar seu próprio usuário em Authentication > Add user, rode:
--   update perfis set is_admin = true, nome_completo = 'Ariana Santana' where id = '<seu-uuid-de-usuario>';
-- (o uuid aparece na lista de usuários do Supabase Auth)
