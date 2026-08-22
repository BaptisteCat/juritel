-- =====================================================================
--  Juritel — favoris par utilisateur + agrégation des votes
--  À exécuter une fois dans Supabase › SQL Editor.
--  Ne contient aucune donnée : uniquement le schéma et les règles d'accès.
-- =====================================================================


-- ---------------------------------------------------------------------
--  1. FAVORIS
--     Table à part de la base commune : chaque membre ne voit et ne
--     modifie que ses propres lignes. Rien ici ne touche « base ».
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

-- seul un membre admis peut poser un favori, et seulement pour lui-même
drop policy if exists "favoris ajout" on public.favoris;
create policy "favoris ajout"
  on public.favoris for insert
  with check (est_admis() and email = lower(auth.jwt() ->> 'email'));

-- nécessaire à l'upsert du client (insert ... on conflict do update)
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
--  2. RÉSUMÉ DES VOTES
--     Le client rapatriait toute la table — les votes de tous les membres
--     — pour n'en tirer que des compteurs : un volume qui croissait comme
--     le carré du nombre d'utilisateurs. L'agrégation passe au serveur ;
--     le résultat est borné par le nombre de contacts notés.
--
--     « maj » est renvoyée en texte : la fonction reste valable que la
--     colonne soit de type timestamptz ou text, le client la parse.
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

-- le client ne lit plus que SES votes : cet index rend la requête immédiate
create index if not exists votes_email_idx on public.votes (email);


-- ---------------------------------------------------------------------
--  Contrôle rapide
-- ---------------------------------------------------------------------
-- select * from public.votes_resume() limit 5;
-- select * from public.favoris;
