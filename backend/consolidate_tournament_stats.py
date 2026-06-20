# In consolidate_tournament_stats.py
import os
import json
from collections import defaultdict
from markupsafe import Markup

def consolidate_tournament_stats(event_id):
    data_dir = "data"
    prefix = f"event_{event_id}_match_"
    output_path = os.path.join(data_dir, f"event_{event_id}_player_totals.json")
    highlights_path = os.path.join(data_dir, f"event_{event_id}_highlights.json")

    player_totals = defaultdict(lambda: {
        "name": "", "points": 0, "bagsin": 0, "bagson": 0, "bagsoff": 0,
        "4baggers": 0, "rounds": 0, 
        "rounds_won": 0, "rounds_lost": 0, "rounds_tied": 0,
        "opp_points": 0,
        "sum_positive_round_net_points": 0 # Initialize new metric
    })

    highest_ppr = {"player": "", "ppr": 0, "match": ""}
    highest_dpr = {"player": "", "dpr": -9999, "match": ""} # Net points per round in a game

    match_files = [f for f in os.listdir(data_dir) if prefix in f and f.endswith("_stats.json")]
    print(f"📦 Found {len(match_files)} stats files to process for event {event_id} totals.")

    for file in match_files:
        path = os.path.join(data_dir, file)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                details = data.get("event_match_details", [])
                inning_history = data.get("event_match_inning_history", [])

                # Aggregate base stats from game details (per player per game)
                for p_detail in details:
                    pid = str(p_detail["playerid"])
                    # Set name once, robustly
                    if not player_totals[pid]["name"]:
                        first_name = p_detail.get('playerfirstname', 'N/A')
                        last_name_full = p_detail.get('playerlastname', '')
                        last_initial = last_name_full[0] if last_name_full else ''
                        player_totals[pid]["name"] = f"{first_name} {last_initial}."

                    player_totals[pid]["points"] += p_detail.get("totalpts", 0) # Player's gross points
                    player_totals[pid]["bagsin"] += p_detail.get("totalbagsin", 0)
                    player_totals[pid]["bagson"] += p_detail.get("totalbagson", 0)
                    player_totals[pid]["bagsoff"] += p_detail.get("totalbagsoff", 0)
                    player_totals[pid]["rounds"] += p_detail.get("rounds", 0) # Total rounds player threw in
                    player_totals[pid]["4baggers"] += p_detail.get("totalfourbaggers", 0)
                    player_totals[pid]["opp_points"] += p_detail.get("opponentpts", 0) # Opponent's gross points

                    ppr_game = p_detail.get("ptsperrnd", 0)
                    dpr_game = p_detail.get("diffperrnd", 0)
                    current_player_name_for_highlight = player_totals[pid]["name"]
                    if ppr_game > highest_ppr["ppr"]:
                        highest_ppr = {"player": current_player_name_for_highlight, "ppr": ppr_game, "match": file.replace(f"event_{event_id}_match_","").replace("_stats.json","")}
                    if dpr_game > highest_dpr["dpr"]:
                        highest_dpr = {"player": current_player_name_for_highlight, "dpr": dpr_game, "match": file.replace(f"event_{event_id}_match_","").replace("_stats.json","")}

                # Process inning_history for round outcomes and sum_positive_round_net_points
                inning_map = defaultdict(list)
                for inning_entry in inning_history:
                    inning_map[inning_entry["inningno"]].append(inning_entry)

                for inning_no, player_inning_pair in inning_map.items():
                    if len(player_inning_pair) != 2: continue

                    p1_inning_data = player_inning_pair[0]
                    p2_inning_data = player_inning_pair[1]
                    
                    pid1 = str(p1_inning_data["playerid"])
                    pid2 = str(p2_inning_data["playerid"])

                    # 'totalpoints' in inning_history is the gross points scored by that player in that specific inning
                    p1_gross_pts_this_round = p1_inning_data.get("totalpoints", 0)
                    p2_gross_pts_this_round = p2_inning_data.get("totalpoints", 0)

                    if p1_gross_pts_this_round > p2_gross_pts_this_round:
                        player_totals[pid1]["rounds_won"] += 1
                        player_totals[pid2]["rounds_lost"] += 1
                        player_totals[pid1]["sum_positive_round_net_points"] += (p1_gross_pts_this_round - p2_gross_pts_this_round)
                    elif p2_gross_pts_this_round > p1_gross_pts_this_round:
                        player_totals[pid2]["rounds_won"] += 1
                        player_totals[pid1]["rounds_lost"] += 1
                        player_totals[pid2]["sum_positive_round_net_points"] += (p2_gross_pts_this_round - p1_gross_pts_this_round)
                    else: # Tie
                        player_totals[pid1]["rounds_tied"] += 1
                        player_totals[pid2]["rounds_tied"] += 1
        except Exception as e:
            print(f"⚠️ Error reading or processing file {file}: {e}")

# In consolidate_tournament_stats.py
# ... (other parts of the function are as you provided in the 9.5KB version) ...

    # Calculate final derived stats
    for pid, stats in player_totals.items():
        rounds = stats["rounds"]
        total_bags_placed = stats["bagsin"] + stats["bagson"] + stats["bagsoff"]
        player_total_bags_thrown = rounds * 4 
        
        tournament_net_points_overall = stats["points"] - stats["opp_points"]
        cornhole_pct = round(100 * stats["bagsin"] / player_total_bags_thrown, 1) if player_total_bags_thrown else 0
        
        opp_ppr_val = stats["opp_points"] / rounds if rounds else 0
        point_diff_per_round = (stats["points"] - stats["opp_points"]) / rounds if rounds else 0
        total_rounds_outcomes = stats["rounds_won"] + stats["rounds_lost"] + stats["rounds_tied"]

        # Calculate Scored Pts / Rnd (sum_positive_round_net_points per round)
        scored_pts_per_round_val = round(stats["sum_positive_round_net_points"] / rounds, 2) if rounds else 0.0 # Ensure this is calculated

        stats.update({
            # "sum_positive_round_net_points" is already accumulated from inning_history processing
            "scored_pts_per_round": scored_pts_per_round_val, # ADD/ENSURE THIS LINE IS PRESENT
            "tournament_net_points_overall": tournament_net_points_overall, 
            "player_total_bags_thrown": player_total_bags_thrown, 
            "cornhole_pct": cornhole_pct, 
            "ppr": round(stats["points"] / rounds, 2) if rounds else 0, # Standard Gross PPR
            "4bagger_pct": round(100 * stats["4baggers"] / rounds, 1) if rounds else 0,
            "rounds_won_pct": round(100 * stats["rounds_won"] / total_rounds_outcomes, 1) if total_rounds_outcomes else 0,
            "rounds_lost_pct": round(100 * stats["rounds_lost"] / total_rounds_outcomes, 1) if total_rounds_outcomes else 0,
            "rounds_tied_pct": round(100 * stats["rounds_tied"] / total_rounds_outcomes, 1) if total_rounds_outcomes else 0,
            "bagsin_pct": round(100 * stats["bagsin"] / total_bags_placed, 1) if total_bags_placed else 0,
            "bagson_pct": round(100 * stats["bagson"] / total_bags_placed, 1) if total_bags_placed else 0,
            "bagsoff_pct": round(100 * stats["bagsoff"] / total_bags_placed, 1) if total_bags_placed else 0,
            "opp_ppr": round(opp_ppr_val, 2),
            "point_diff": round(point_diff_per_round, 2) # This is Net Pts PER ROUND (overall)
        })
    # ... (rest of the function: saving JSON files, etc.)
    with open(output_path, "w", encoding="utf-8") as out:
        json.dump(player_totals, out, indent=2)
    print(f"✅ Saved consolidated stats to {output_path}")

    with open(highlights_path, "w", encoding="utf-8") as out:
        json.dump({"highest_ppr": highest_ppr, "highest_dpr": highest_dpr}, out, indent=2)
    print(f"✅ Saved highlights to {highlights_path}")


def render_highlights_section(event_id): # This function stays in consolidate_tournament_stats.py
    path = f"data/event_{event_id}_highlights.json"
    if not os.path.exists(path):
        return "<p>No highlights data available.</p>"
    try:
        with open(path, "r", encoding="utf-8") as f:
            highlights = json.load(f)
    except Exception as e:
        return f"<p>Error loading highlights: {str(e)}</p>"

    if not highlights or "highest_ppr" not in highlights or "highest_dpr" not in highlights:
        return "<p>Highlights data is incomplete.</p>"

    highest_ppr_player = highlights.get('highest_ppr', {}).get('player', 'N/A')
    highest_ppr_val = highlights.get('highest_ppr', {}).get('ppr', 'N/A')
    highest_ppr_match = highlights.get('highest_ppr', {}).get('match', 'N/A')
    highest_dpr_player = highlights.get('highest_dpr', {}).get('player', 'N/A')
    highest_dpr_val = highlights.get('highest_dpr', {}).get('dpr', 'N/A')
    highest_dpr_match = highlights.get('highest_dpr', {}).get('match', 'N/A')

    return Markup(f"""
    <div style='margin-top: 16px; background: #2b2b2b; border: 1px solid #444; padding: 15px; border-radius: 8px; color: #e0e0e0; font-size: 0.95em;'>
        <div style='font-weight: bold; font-size: 1.1em; color: #58c6ff; margin-bottom: 12px; border-bottom: 1px solid #444; padding-bottom: 8px;'>📈 Highlights</div>
        <div style='margin-bottom: 8px;'>
            <strong>Highest PPR Game:</strong> 
            <span style='color: #lime; font-weight:bold;'>{highest_ppr_val}</span> by 
            <span style='color: #fafafa;'>{highest_ppr_player}</span> 
            (Match: {highest_ppr_match})
        </div>
        <div>
            <strong>Highest DPR Game (Net Pts/Round in a game):</strong> 
            <span style='color: #lime; font-weight:bold;'>{highest_dpr_val}</span> by 
            <span style='color: #fafafa;'>{highest_dpr_player}</span> 
            (Match: {highest_dpr_match})
        </div>
    </div>
    """)