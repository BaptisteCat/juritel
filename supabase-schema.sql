-- =====================================================================
--  Juritel — votes, propositions et favoris
--  À exécuter en une fois dans Supabase › SQL Editor.
--
--  Sondage du 22/08/2026 : « base », « acces », « demandes », est_admis()
--  et est_proprietaire() existent déjà ; « votes », « propositions » et
--  « favoris » sont ABSENTES. Tant qu'elles le restent, les votes et les
--  favoris ne vivent que dans le navigateur de chacun.
--
--  Ce fichier est idempotent : le rejouer ne casse rien.
--  Il ne contient aucune donnée, uniquement schéma et règles d'accès.
-- =====================================================================


-- ---------------------------------------------------------------------
--  1. VOTES — un membre, un vote par numéro
--     La clé primaire (email, contact) fait respecter cette règle par la
--     base elle-même : les compteurs SONT donc des personnes, ce dont le
--     classement des numéros se sert.
-- ---------------------------------------------------------------------
create table if not exists public.votes (
  email   text        not null default lower(auth.jwt() ->> 'email'),
  contact text        not null,
  valeur  smallint    not null,          -- +1 : ça répond / -1 : ça ne répond pas
  maj     timestamptz not null default now(),
  primary key (email, contact)
);

alter table public.votes enable row level security;

-- tout membre admis lit l'ensemble des votes : c'est ce qui rend le signal
-- collectif. Le client, lui, ne lit plus que les siens (voir votes_resume).
drop policy if exists "votes lecture" on public.votes;
create policy "votes lecture"
  on public.votes for select
  using (est_admis());

drop policy if exists "votes ajout" on public.votes;
create policy "votes ajout"
  on public.votes for insert
  with check (est_admis() and email = lower(auth.jwt() ->> 'email'));

-- nécessaire à l'upsert du client (insert ... on conflict do update)
drop policy if exists "votes maj" on public.votes;
create policy "votes maj"
  on public.votes for update
  using      (email = lower(auth.jwt() ->> 'email'))
  with check (email = lower(auth.jwt() ->> 'email'));

-- le client supprime par « contact » seul : c'est CETTE règle qui empêche
-- d'effacer le vote d'autrui.
drop policy if exists "votes retrait" on public.votes;
create policy "votes retrait"
  on public.votes for delete
  using (email = lower(auth.jwt() ->> 'email'));

grant select, insert, update, delete on public.votes to authenticated;

-- le client ne lit plus que SES votes : cet index rend la requête immédiate
create index if not exists votes_email_idx on public.votes (email);


-- ---------------------------------------------------------------------
--  2. RÉSUMÉ DES VOTES — agrégation côté serveur
--     Le client rapatriait la table entière, tous les votes de tous les
--     membres, pour n'en tirer que des compteurs : un volume qui croissait
--     comme le carré du nombre d'utilisateurs. Le résumé, lui, est borné
--     par le nombre de contacts notés.
--
--     « maj » est renvoyée en texte : la fonction reste valable que la
--     colonne soit timestamptz ou text, le client la parse.
-- ---------------------------------------------------------------------
create or replace function public.votes_resume()
returns table (contact text, ok integer, ko integer, dernier_ok text)
language sql
security definer
stable
set search_path = public
as $$
  select v.contact::text,
         count(*) filter (where v.valeur > 0)::int,
         count(*) filter (where v.valeur < 0)::int,
         max(v.maj::text) filter (where v.valeur > 0)
  from public.votes v
  where est_admis()          -- security definer, mais l'appelant reste jugé
  group by v.contact
$$;

revoke all     on function public.votes_resume() from public, anon;
grant  execute on function public.votes_resume() to authenticated;


-- ---------------------------------------------------------------------
--  3. PROPOSITIONS — la quarantaine
--     Un membre ne touche jamais la base principale : ses ajouts atterrissent
--     ici, et le propriétaire seul décide de les intégrer ou de les refuser.
-- ---------------------------------------------------------------------
create table if not exists public.propositions (
  id      bigint generated always as identity primary key,
  email   text        not null default lower(auth.jwt() ->> 'email'),
  cree    timestamptz not null default now(),
  donnees jsonb       not null,
  etat    text        not null default 'attente'
          check (etat in ('attente','integree','refusee'))
);

alter table public.propositions enable row level security;

-- chacun voit ce qu'il a proposé ; le propriétaire voit tout
drop policy if exists "propositions lecture" on public.propositions;
create policy "propositions lecture"
  on public.propositions for select
  using (est_proprietaire() or email = lower(auth.jwt() ->> 'email'));

drop policy if exists "propositions depot" on public.propositions;
create policy "propositions depot"
  on public.propositions for insert
  with check (est_admis() and email = lower(auth.jwt() ->> 'email'));

-- seul le propriétaire statue
drop policy if exists "propositions arbitrage" on public.propositions;
create policy "propositions arbitrage"
  on public.propositions for update
  using (est_proprietaire()) with check (est_proprietaire());

drop policy if exists "propositions suppression" on public.propositions;
create policy "propositions suppression"
  on public.propositions for delete
  using (est_proprietaire());

grant select, insert, update, delete on public.propositions to authenticated;

create index if not exists propositions_etat_idx on public.propositions (etat, cree);


-- ---------------------------------------------------------------------
--  4. FAVORIS — propres à chaque compte
--     Table à part de la base commune : personne ne voit ni ne modifie les
--     favoris d'un autre.
-- ---------------------------------------------------------------------
create table if not exists public.favoris (
  email       text        not null default lower(auth.jwt() ->> 'email'),
  juridiction text        not null,
  cree        timestamptz not null default now(),
  primary key (email, juridiction)
);

alter table public.favoris enable row level security;

drop policy if exists "favoris lecture" on public.favoris;
create policy "favoris lecture"
  on public.favoris for select
  using (email = lower(auth.jwt() ->> 'email'));

drop policy if exists "favoris ajout" on public.favoris;
create policy "favoris ajout"
  on public.favoris for insert
  with check (est_admis() and email = lower(auth.jwt() ->> 'email'));

-- nécessaire à l'upsert du client
drop policy if exists "favoris maj" on public.favoris;
create policy "favoris maj"
  on public.favoris for update
  using      (email = lower(auth.jwt() ->> 'email'))
  with check (email = lower(auth.jwt() ->> 'email'));

drop policy if exists "favoris retrait" on public.favoris;
create policy "favoris retrait"
  on public.favoris for delete
  using (email = lower(auth.jwt() ->> 'email'));

grant select, insert, update, delete on public.favoris to authenticated;


-- ---------------------------------------------------------------------
--  Contrôle — à passer une fois connecté dans l'application
-- ---------------------------------------------------------------------
-- select count(*) from public.votes;
-- select * from public.votes_resume() limit 5;
-- select * from public.favoris;
-- select id, email, cree, etat from public.propositions order by cree desc;
