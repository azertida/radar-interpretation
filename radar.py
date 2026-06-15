#!/usr/bin/env python3
"""
Radar Interprétation
====================
Scanne une grille EPG Pickx (format XMLTV) et identifie les programmes
interprétés par les acteurs et actrices listés dans watchlist.json.

Usage :
    python3 radar.py --source /tmp/pickx_guide.xml
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from xml.etree import ElementTree as ET


# Mapping des codes xmltv_id Pickx vers des noms de chaînes lisibles
CHANNEL_NAMES = {
    "TF1.fr@HD": "TF1",
    "France2.fr@HD": "France 2",
    "France3.fr@HD": "France 3",
    "France4.fr@HD": "France 4",
    "France5.fr@HD": "France 5",
    "arte.fr@HD": "Arte",
    "TV5MondeFranceBelgiumSwitzerlandMonaco.fr@HD": "TV5 Monde",
    "Action.fr@HD": "Action",
    "LaUne.be@HD": "La Une",
    "LaTrois.be@HD": "La Trois",
    "Tipik.be@HD": "Tipik",
    "RTLTVI.be@HD": "RTL TVI",
    "VRT1.be@HD": "VRT 1",
    "VRTCanvas.be@HD": "VRT Canvas",
    "VTM.be@HD": "VTM",
    "VTM2.be@HD": "VTM 2",
    "BBCOne.uk@HD": "BBC One",
    "BBCTwo.uk@HD": "BBC Two",
    "Rai1.it@HD": "RAI Uno",
    "Rai2.it@HD": "RAI Due",
    "Rai3.it@HD": "RAI Tre",
    "TVEInternacionalEuropeAsia.es@HD": "TVE International",
}


def load_watchlist(path="watchlist.json"):
    """Charge la liste des noms à surveiller."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    noms = data.get("noms", [])
    return [nom.strip() for nom in noms if nom.strip()]


def get_actors(programme):
    """Extrait la liste des acteurs d'un programme."""
    actors = []
    credits = programme.find("credits")
    if credits is None:
        return actors
    for a in credits.findall("actor"):
        if a.text:
            # Pickx peut mettre plusieurs noms séparés par virgule dans une seule balise
            for nom in a.text.split(","):
                nom = nom.strip()
                if nom:
                    actors.append(nom)
    return actors


def get_directors(programme):
    """Extrait la liste des réalisateurs (pour info contextuelle)."""
    directors = []
    credits = programme.find("credits")
    if credits is None:
        return directors
    for d in credits.findall("director"):
        if d.text:
            for nom in d.text.split(","):
                nom = nom.strip()
                if nom:
                    directors.append(nom)
    return directors


def parse_datetime(dt_string):
    """Parse une date XMLTV (format '20260613210000 +0000') en ISO."""
    if not dt_string:
        return None
    try:
        parts = dt_string.split()
        date_part = parts[0]
        dt = datetime.strptime(date_part[:14], "%Y%m%d%H%M%S")
        if len(parts) > 1:
            tz = parts[1]
            sign = 1 if tz[0] == "+" else -1
            hours = int(tz[1:3])
            minutes = int(tz[3:5])
            offset = sign * (hours * 60 + minutes)
            from datetime import timedelta
            dt = dt.replace(tzinfo=timezone(timedelta(minutes=offset)))
        else:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except (ValueError, IndexError):
        return None


def extract_programmes(xml_path, watchlist):
    """Parse le XML et retourne les programmes dont au moins un acteur est dans la watchlist."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    # Index pour comparaison rapide (insensible à la casse)
    watchlist_lower = {nom.lower(): nom for nom in watchlist}
    
    matches = []
    total_programmes = 0
    total_with_credits = 0
    
    for prog in root.findall("programme"):
        total_programmes += 1
        
        actors = get_actors(prog)
        if not actors:
            continue
        total_with_credits += 1
        
        # Cherche TOUS les acteurs/actrices de la watchlist présents (pas juste le premier)
        matched = []
        for a in actors:
            if a.lower() in watchlist_lower:
                canonical = watchlist_lower[a.lower()]
                if canonical not in matched:
                    matched.append(canonical)
        
        if not matched:
            continue
        
        # Récupère les infos du programme
        title_el = prog.find("title")
        title = (title_el.text or "").strip() if title_el is not None else ""
        
        sub_el = prog.find("sub-title")
        subtitle = (sub_el.text or "").strip() if sub_el is not None else ""
        
        desc_el = prog.find("desc")
        description = (desc_el.text or "").strip() if desc_el is not None else ""
        
        cat_el = prog.find("category")
        category = (cat_el.text or "").strip() if cat_el is not None else ""
        
        directors = get_directors(prog)
        
        # Chaîne lisible
        channel_id = prog.get("channel", "")
        channel_name = CHANNEL_NAMES.get(channel_id, channel_id)
        
        matches.append({
            "start": parse_datetime(prog.get("start", "")),
            "stop": parse_datetime(prog.get("stop", "")),
            "channel": channel_name,
            "title": title,
            "subtitle": subtitle,
            "directors": directors,
            "actors": actors,
            "matched_actors": matched,
            "description": description,
            "category": category
        })
    
    print(f"Total programmes analysés : {total_programmes}", file=sys.stderr)
    print(f"Avec credits/actor : {total_with_credits}", file=sys.stderr)
    print(f"Matches sur la watchlist : {len(matches)}", file=sys.stderr)
    
    # Déduplication par (title, start, channel)
    seen = set()
    deduped = []
    for m in matches:
        key = (m["title"], m["start"], m["channel"])
        if key not in seen:
            seen.add(key)
            deduped.append(m)
    
    # Tri par date de début
    deduped.sort(key=lambda m: m["start"] or "")
    
    return deduped


def main():
    parser = argparse.ArgumentParser(description="Radar Interprétation - filtre EPG Pickx par acteur/actrice")
    parser.add_argument("--source", default="/tmp/pickx_guide.xml", help="Chemin du XML Pickx")
    parser.add_argument("--watchlist", default="watchlist.json", help="Chemin de la watchlist")
    parser.add_argument("--output", default="radar.json", help="Fichier JSON de sortie")
    args = parser.parse_args()
    
    watchlist = load_watchlist(args.watchlist)
    print(f"Watchlist : {len(watchlist)} noms", file=sys.stderr)
    
    matches = extract_programmes(args.source, watchlist)
    
    if matches:
        dates = [m["start"][:10] for m in matches if m["start"]]
        window_start = min(dates) if dates else ""
        window_end = max(dates) if dates else ""
    else:
        today = datetime.now(timezone.utc).date().isoformat()
        window_start = today
        window_end = today
    
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_start": window_start,
        "window_end": window_end,
        "source": "Pickx via iptv-org/epg",
        "watchlist_size": len(watchlist),
        "watchlist": watchlist,
        "count": len(matches),
        "programmes": matches
    }
    
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"radar.json écrit : {len(matches)} programmes", file=sys.stderr)


if __name__ == "__main__":
    main()
