-- =====================================================================
--  Juritel — être prévenu des demandes d'accès sans service d'e-mail
-- ---------------------------------------------------------------------
--  Cette fonction renvoie UNIQUEMENT le nombre de demandes en attente.
--  Aucune adresse, aucun nom : elle peut donc être appelée avec la clé
--  publique de l'application, sans secret à confier à GitHub.
--  L'action « Demandes d'accès » du dépôt l'interroge chaque heure et
--  ouvre un signalement (issue) quand le compte n'est pas nul ; GitHub
--  vous envoie alors sa notification habituelle par e-mail.
--
--  À exécuter une fois dans Supabase : SQL Editor > New query > Run.
-- =====================================================================

create or replace function public.demandes_en_attente()
returns integer
language sql
security definer
set search_path = public
as $$
  select count(*)::int from public.demandes;
$$;

-- la fonction ne doit rien exposer d'autre que ce compte
revoke all on function public.demandes_en_attente() from public;
grant execute on function public.demandes_en_attente() to anon, authenticated;

-- Vérification : doit renvoyer un nombre (0 s'il n'y a aucune demande).
-- select public.demandes_en_attente();
