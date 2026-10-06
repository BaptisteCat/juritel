#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Régénère officiel.json depuis l'annuaire de l'administration (DILA).

Source : api-lannuaire.service-public.fr, jeu « api-lannuaire-administration »
(ministère de la Justice). Licence ouverte.

Le fichier produit alimente, côté application : la recherche (section « Annuaire
officiel »), les fiches générées à la volée et le bloc « Annuaire officiel » des
fiches existantes. Le format ne doit donc pas changer sans adapter index.html.

Usage :  python tools/build_officiel.py [chemin/officiel.json]
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import date

API = ("https://api-lannuaire.service-public.fr/api/explore/v2.1"
       "/catalog/datasets/api-lannuaire-administration/records")
# pivot DILA -> type utilisé par l'application
PIVOTS = {
    "tgi": "tj", "cour_appel": "ca", "ti": "tprx", "prudhommes": "cph",
    "tribunal_commerce": "commerce", "ta": "ta", "caa": "caa",
}
# La source écrit les voies EN CAPITALES : on leur rend une casse lisible. Les accents perdus par
# la source ne peuvent pas être réinventés (« STEPHANE » reste « Stephane »).
VOIE_MINUSCULE = {
    "rue", "avenue", "av", "boulevard", "bd", "place", "impasse", "allee", "allees", "chemin",
    "quai", "cours", "route", "voie", "esplanade", "faubourg", "passage", "square", "villa",
    "de", "du", "des", "le", "la", "les", "et", "sur", "sous", "au", "aux", "en", "bis", "ter",
}


def casse_voie(txt):
    if not txt or txt != txt.upper():
        return txt  # déjà en casse mixte : on n'y touche pas
    mots = []
    for i, m in enumerate(txt.lower().split()):
        if m in VOIE_MINUSCULE and i > 0:
            mots.append(m)
        elif "'" in m:  # d'amerique -> d'Amerique
            a, b = m.split("'", 1)
            mots.append(a + "'" + (b[:1].upper() + b[1:] if b else ""))
        else:
            mots.append(m[:1].upper() + m[1:])
    return " ".join(mots)


def lire(url, essais=4):
    for i in range(essais):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # réseau capricieux : on retente, puis on abandonne
            if i == essais - 1:
                raise
            time.sleep(2 * (i + 1))


def champ(v):
    """Les champs composites arrivent en JSON sérialisé ou déjà décodés."""
    if v in (None, ""):
        return []
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return []
    return v if isinstance(v, list) else [v]


def adresse(rec):
    for a in champ(rec.get("adresse")):
        if a.get("type_adresse") in (None, "", "Adresse"):
            morceaux = [a.get("numero_voie"), a.get("complement1"), a.get("complement2")]
            voie = casse_voie(" ".join(x.strip() for x in morceaux if x and x.strip()))
            ville = " ".join(x for x in [a.get("code_postal"), a.get("nom_commune")] if x)
            if voie and ville:
                return f"{voie} – {ville}"
            return voie or ville or ""
    return ""


def horaires(rec):
    out = []
    for h in champ(rec.get("plage_ouverture")):
        jours = h.get("nom_jour_debut") or ""
        if h.get("nom_jour_fin") and h["nom_jour_fin"] != jours:
            jours = f"{jours} – {h['nom_jour_fin']}"
        plages = []
        for a, b in (("valeur_heure_debut_1", "valeur_heure_fin_1"),
                     ("valeur_heure_debut_2", "valeur_heure_fin_2")):
            d, f = (h.get(a) or "")[:5], (h.get(b) or "")[:5]
            if d and f and (d, f) != ("", ""):
                p = f"{d}–{f}"
                if p not in plages:
                    plages.append(p)
        out.append({"jours": jours, "plages": " et ".join(plages),
                    "note": (h.get("commentaire") or "").strip()})
    return out


def recolte(pivot):
    """Toutes les fiches d'un pivot, par pages de 100 (limite de l'API)."""
    out, offset = [], 0
    while True:
        q = urllib.parse.urlencode({
            "where": f'pivot like "{pivot}"',
            "limit": 100, "offset": offset, "order_by": "nom",
        })
        d = lire(f"{API}?{q}")
        lot = d.get("results", [])
        out += lot
        offset += len(lot)
        if len(lot) < 100 or offset >= d.get("total_count", 0) or offset >= 10000:
            break
    return out


def main():
    dest = sys.argv[1] if len(sys.argv) > 1 else "officiel.json"
    fiches, vus = [], set()
    for pivot, t in PIVOTS.items():
        lot = recolte(pivot)
        print(f"  {pivot:18s} {len(lot):4d} fiches", flush=True)
        for r in lot:
            ident = r.get("id")
            if not ident or ident in vus:
                continue
            vus.add(ident)
            tels = [x.get("valeur", "").strip() for x in champ(r.get("telephone")) if x.get("valeur")]
            mails = [m.strip() for m in str(r.get("adresse_courriel") or "").split(";") if m.strip()]
            sites = [x.get("valeur", "").strip() for x in champ(r.get("site_internet")) if x.get("valeur")]
            fiches.append({
                "t": t,
                "id": ident,
                "nom": (r.get("nom") or "").strip(),
                "adresse": adresse(r),
                "tels": tels,
                "mails": mails,
                "site": sites[0] if sites else "",
                "horaires": horaires(r),
                "url": r.get("url_service_public") or "",
                "maj": (r.get("date_modification") or "").split(" ")[0],
                "insee": r.get("code_insee_commune") or "",
            })
    fiches.sort(key=lambda f: (f["t"], f["nom"]))
    out = {
        "v": 1,
        "source": "Annuaire officiel de l’administration (DILA, api-lannuaire.service-public.fr)",
        "genere": date.today().isoformat(),
        "j": fiches,
    }
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"officiel.json : {len(fiches)} juridictions -> {dest}")


if __name__ == "__main__":
    main()
