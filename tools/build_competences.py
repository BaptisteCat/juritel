#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Régénère competences.json (commune -> juridictions compétentes).

Sources :
  - cour d'appel, tribunal judiciaire, tribunal de proximité, conseil de
    prud'hommes : jeu officiel du ministère de la Justice sur data.gouv.fr
    (« Liste des juridictions compétentes pour les communes de France ») ;
  - tribunaux de commerce : référentiel Infogreffe de 2021, CONSERVÉ tel quel —
    l'API Infogreffe est fermée depuis, rien ne permet de le rafraîchir ;
  - tribunaux administratifs et cours administratives d'appel : tables du code
    de justice administrative (R221-3 et R221-7), conservées telles quelles.

Le fichier existant sert donc de base pour ce qui ne peut pas être régénéré.

Usage :  python tools/build_competences.py [chemin/competences.json]
"""
import csv
import io
import json
import sys
import urllib.request
from datetime import date

DATASET = ("https://www.data.gouv.fr/api/1/datasets/"
           "liste-des-juridictions-competentes-pour-les-communes-de-france/")


def lire(url, binaire=False):
    with urllib.request.urlopen(url, timeout=120) as r:
        d = r.read()
    return d if binaire else json.loads(d.decode("utf-8"))


def csv_le_plus_recent():
    d = lire(DATASET)
    csvs = [r for r in d.get("resources", []) if (r.get("format") or "").lower() == "csv"]
    if not csvs:
        raise SystemExit("Aucune ressource CSV dans le jeu de données")
    csvs.sort(key=lambda r: r.get("last_modified") or "", reverse=True)
    return csvs[0]


def decode(raw):
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def colonne(entetes, *mots):
    """Retrouve une colonne par mots-clés : les intitulés varient d'une année à l'autre."""
    for i, h in enumerate(entetes):
        bas = h.lower()
        if all(m in bas for m in mots):
            return i
    return None


def main():
    dest = sys.argv[1] if len(sys.argv) > 1 else "competences.json"
    try:
        ancien = json.load(open(dest, encoding="utf-8"))
    except Exception:
        ancien = {}

    res = csv_le_plus_recent()
    print(f"  source : {res.get('title')} ({res.get('last_modified', '')[:10]})")
    lignes = decode(lire(res["url"], binaire=True)).splitlines()
    sep = ";" if lignes[0].count(";") >= lignes[0].count(",") else ","
    lect = csv.reader(io.StringIO("\n".join(lignes)), delimiter=sep)
    entetes = next(lect)
    iCom = colonne(entetes, "commune") or 0
    iCA = colonne(entetes, "cour", "appel", "compétente") or colonne(entetes, "cour", "appel", "competente")
    iTJ = colonne(entetes, "judiciaire", "compétent") or colonne(entetes, "judiciaire", "competent")
    iTPRX = colonne(entetes, "proximité", "compétent") or colonne(entetes, "proximite", "competent")
    iCPH = colonne(entetes, "prud", "compétent") or colonne(entetes, "prud", "competent")
    if None in (iCA, iTJ, iCPH):
        raise SystemExit(f"Colonnes inattendues : {entetes}")

    noms = {"ca": [], "tj": [], "tprx": [], "cph": []}
    index = {k: {} for k in noms}

    def idx(cle, nom):
        nom = (nom or "").strip()
        if not nom:
            return -1
        if nom not in index[cle]:
            index[cle][nom] = len(noms[cle])
            noms[cle].append(nom)
        return index[cle][nom]

    # tribunaux de commerce : on garde l'ancienne affectation, commune par commune
    tco_noms = list(ancien.get("tco", []))
    tco_anc = {insee: v[4] for insee, v in (ancien.get("c") or {}).items() if len(v) > 4}

    communes, sans_tco = {}, 0
    for row in lect:
        if len(row) <= max(i for i in (iCom, iCA, iTJ, iCPH) if i is not None):
            continue
        insee = (row[iCom] or "").strip()
        if not insee:
            continue
        tco = tco_anc.get(insee, -1)
        if tco == -1:
            sans_tco += 1
        communes[insee] = [
            idx("ca", row[iCA]),
            idx("tj", row[iTJ]),
            idx("tprx", row[iTPRX]) if iTPRX is not None else -1,
            idx("cph", row[iCPH]),
            tco,
        ]

    out = {
        "v": 2,
        "source": "data.gouv.fr (ministère de la Justice, Infogreffe 2021, CJA)",
        "genere": date.today().isoformat(),
        "sourceDate": (res.get("last_modified") or "")[:10],
        "ca": noms["ca"], "tj": noms["tj"], "tprx": noms["tprx"], "cph": noms["cph"],
        # non régénérables : repris du fichier précédent
        "tco": tco_noms,
        "ta": ancien.get("ta", []), "caa": ancien.get("caa", []), "tadep": ancien.get("tadep", {}),
        "c": communes,
    }
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"competences.json : {len(communes)} communes, "
          f"{len(noms['ca'])} CA / {len(noms['tj'])} TJ / {len(noms['tprx'])} TPRX / {len(noms['cph'])} CPH"
          f" ; {sans_tco} communes sans tribunal de commerce repris -> {dest}")


if __name__ == "__main__":
    main()
