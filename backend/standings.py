# standings.py
import json
from collections import defaultdict

def get_team_display_name_from_match_entry(match_entry):
    players = match_entry.get("player_info", [])
    names = [
        f"{p.get('firstname', '') if p.get('firstname') else ''} {p.get('lastname', '') if p.get('lastname') else ''}".strip()
        for p in players
    ]
    names = [name for name in names if name]
    return " & ".join(names) if names else f"Team {match_entry.get('bracketteamid', 'N/A')}"

def compute_standings(matches_input):
    print("\n--- Starting compute_standings ---")
    team_data = {} 
    teams_of_interest = ['1', '2', '3', '6'] # For focused debugging

    # 1. Initialize team_data
    for m_entry in matches_input:
        team_id = str(m_entry.get("bracketteamid")) if m_entry.get("bracketteamid") is not None else None
        if team_id and team_id not in team_data:
            team_data[team_id] = {
                "name": get_team_display_name_from_match_entry(m_entry), "losses": 0, "wins": 0,
                "eliminated_in_L_match_id": 0, "rank_category": 99, "rank_value": 0
            }
    bye_team_ids = set()
    for m_entry in matches_input:
        team_id = str(m_entry.get("bracketteamid")) if m_entry.get("bracketteamid") is not None else None
        if team_id and team_id not in bye_team_ids:
            player_info_list = m_entry.get("player_info", [])
            is_potential_bye = False
            if player_info_list: 
                is_potential_bye = all("bye" in p.get("firstname", "").lower() or "bye" in p.get("lastname", "").lower() for p in player_info_list)
            elif not player_info_list and team_id in team_data and "bye" in team_data[team_id]["name"].lower(): 
                is_potential_bye = True
            if is_potential_bye: bye_team_ids.add(team_id)
    for tid in bye_team_ids:
        if tid in team_data: del team_data[tid]
    print(f"DEBUG: Active (non-bye) teams initialized: {list(team_data.keys())}")

    # 2. Group matches and process outcomes
    grouped_matches = defaultdict(list)
    for m_entry in matches_input:
        bm_id = m_entry.get("bracketmatchid")
        if bm_id is not None: grouped_matches[str(bm_id)].append(m_entry)

    print("DEBUG: Processing match outcomes (Step 2)...")
    # Sort matches by match_id_int to process in a somewhat logical order, though not strictly necessary
    # if loss counting is self-contained per match.
    sorted_match_ids = sorted(grouped_matches.keys(), key=lambda x: int(x))

    for match_id_str in sorted_match_ids:
        pair_entries = grouped_matches[match_id_str]
        match_id_int = int(match_id_str) 

        if len(pair_entries) != 2: continue
        
        pos0 = pair_entries[0].get("bracketpos", "")
        pos1 = pair_entries[1].get("bracketpos", "")
        entry_T, entry_B = None, None

        # Ensure one is T and the other is B
        if ("T" in pos0 and "B" in pos1): entry_T, entry_B = pair_entries[0], pair_entries[1]
        elif ("B" in pos0 and "T" in pos1): entry_T, entry_B = pair_entries[1], pair_entries[0]
        else: continue # Skip if T/B cannot be clearly identified
            
        if entry_T.get("matchStatusID") != 5: continue

        team_T_id_str = str(entry_T.get("bracketteamid")) if entry_T.get("bracketteamid") is not None else None
        team_B_id_str = str(entry_B.get("bracketteamid")) if entry_B.get("bracketteamid") is not None else None

        # Skip if byes or teams not in our active list
        if not team_T_id_str or not team_B_id_str or team_T_id_str in bye_team_ids or team_B_id_str in bye_team_ids: continue
        if team_T_id_str not in team_data or team_B_id_str not in team_data: continue
        
        # Scores are taken from entry_T's perspective.
        # scorehome in entry_T refers to team_T_id_str's score.
        # scoreaway in entry_T refers to team_B_id_str's score.
        scores_arr = entry_T.get("scores") 
        if not scores_arr or not isinstance(scores_arr, list) or not scores_arr[0] or not isinstance(scores_arr[0], dict): continue
        
        score_T_actual_str = scores_arr[0].get("scorehome") 
        score_B_relative_to_T_str = scores_arr[0].get("scoreaway") 

        if score_T_actual_str is None or score_B_relative_to_T_str is None: continue
        try:
            score_T_actual = int(score_T_actual_str)
            score_B_relative_to_T = int(score_B_relative_to_T_str)
        except ValueError: continue
        
        current_winner_id, current_loser_id = None, None
        if score_T_actual > score_B_relative_to_T:
            current_winner_id, current_loser_id = team_T_id_str, team_B_id_str
        elif score_B_relative_to_T > score_T_actual:
            current_winner_id, current_loser_id = team_B_id_str, team_T_id_str
        else: continue # Skip ties

        if current_winner_id in teams_of_interest or current_loser_id in teams_of_interest:
             print(f"  MATCH_OUTCOME: Match {match_id_int} (Side: {entry_T.get('bracketside', '').upper()}) "
                   f"T_Team({entry_T.get('bracketpos')}): {team_T_id_str} (Reported Score: {score_T_actual}), "
                   f"B_Team({entry_B.get('bracketpos')}): {team_B_id_str} (Reported Score: {score_B_relative_to_T}) -> "
                   f"Winner: {current_winner_id}, Loser: {current_loser_id}")

        # Increment wins and losses based on THIS match's outcome ONLY
        if current_winner_id in team_data: 
            team_data[current_winner_id]["wins"] += 1
        if current_loser_id in team_data:
            team_data[current_loser_id]["losses"] += 1
            
            if current_loser_id in teams_of_interest:
                 print(f"    LOSS_UPDATE: Team {current_loser_id} after Match {match_id_int}. Losses now: {team_data[current_loser_id]['losses']}.")

            if team_data[current_loser_id]["losses"] == 2:
                is_L_bracket_match_of_2nd_loss = entry_T.get("bracketside", "").upper() == "L"
                if is_L_bracket_match_of_2nd_loss:
                    team_data[current_loser_id]["eliminated_in_L_match_id"] = match_id_int
                
                if current_loser_id in teams_of_interest:
                    print(f"  DEBUG_ELIM_POINT: Team {current_loser_id} reached 2nd loss in Match {match_id_int}. "
                          f"Bracket side of this match: {entry_T.get('bracketside', '').upper()}. "
                          f"elim_L_match_id for Team {current_loser_id} NOW: {team_data[current_loser_id]['eliminated_in_L_match_id']}")
    
    # --- Step 3, 4, 5, 6 remain identical to your last provided debug version ---
    # Make sure to copy them exactly as they were, including their debug prints.
    # For brevity, they are not repeated here but are assumed to be the same.
    # Step 3: Identify Champion and Runner-Up
    print("DEBUG: Identifying Champion/Runner-up (Step 3)...")
    final_match_id_event = 14 
    if str(final_match_id_event) in grouped_matches and len(grouped_matches[str(final_match_id_event)]) == 2:
        f_entry1, f_entry2 = grouped_matches[str(final_match_id_event)]
        f_team1_id = str(f_entry1.get("bracketteamid")) if f_entry1.get("bracketteamid") is not None else None
        f_team2_id = str(f_entry2.get("bracketteamid")) if f_entry2.get("bracketteamid") is not None else None
        if f_team1_id and f_team1_id not in bye_team_ids and f_team2_id and f_team2_id not in bye_team_ids and f_team1_id in team_data and f_team2_id in team_data:
            f_scores_arr = f_entry1.get("scores")
            if f_scores_arr and f_scores_arr[0]:
                f_sh_str, f_sa_str = f_scores_arr[0].get("scorehome"), f_scores_arr[0].get("scoreaway")
                if f_sh_str is not None and f_sa_str is not None:
                    try:
                        f_score_home, f_score_away = int(f_sh_str), int(f_sa_str)
                        final_winner_id, final_loser_id = (f_team1_id, f_team2_id) if f_score_home > f_score_away else (f_team2_id, f_team1_id)
                        if final_winner_id in team_data: team_data[final_winner_id]["rank_category"] = 0 
                        if final_loser_id in team_data: team_data[final_loser_id]["rank_category"] = 1
                        print(f"  DEBUG_FINAL: Champ={final_winner_id} (cat 0), Runner-up={final_loser_id} (cat 1)")
                    except ValueError: pass
    
    # Step 4: Assign rank categories
    print("\nDEBUG: Assigning rank_categories for 2-loss teams (Step 4)...")
    for team_id_str_key in list(team_data.keys()):
        data = team_data[team_id_str_key]
        if team_id_str_key in teams_of_interest:
            print(f"  Processing Team {team_id_str_key} for rank_cat: initial_cat={data['rank_category']}, losses={data['losses']}, elim_L_match={data.get('eliminated_in_L_match_id', 'N/A')}")
        if data["rank_category"] == 99 and data["losses"] >= 2: # Only if not already Champ/Runner-up
            elim_match_id_val = data["eliminated_in_L_match_id"]
            original_category_before_change = data["rank_category"]
            new_category_assigned = -1
            if elim_match_id_val == 13: data["rank_category"] = 2; new_category_assigned = 2
            elif elim_match_id_val == 12: data["rank_category"] = 3; new_category_assigned = 3
            elif elim_match_id_val == 10 or elim_match_id_val == 9: data["rank_category"] = 4; new_category_assigned = 4
            elif elim_match_id_val > 0 : 
                current_max_match_id = 0; str_keys = [k for k in grouped_matches.keys() if k.isdigit()]
                if str_keys: current_max_match_id = int(max(str_keys, key=int))
                data["rank_category"] = 10 + (current_max_match_id - elim_match_id_val); new_category_assigned = data["rank_category"]
            else: # This case is now hit if elim_L_match_id is 0
                data["rank_category"] = 50 ; new_category_assigned = 50 
            if team_id_str_key in teams_of_interest:
                 print(f"    Team {team_id_str_key} (elim_L_match={elim_match_id_val}) had cat {original_category_before_change}, NOW ASSIGNED category {new_category_assigned}")
    
    # Step 5 & 6: Sorting and Grouping
    print("\nDEBUG: Final team_data before sorting (selected teams):")
    for tid_debug in teams_of_interest + ['4','5']:
        if tid_debug in team_data: print(f"  Team {tid_debug}: {team_data[tid_debug]}")
        else: print(f"  Team {tid_debug}: Not in final team_data")

    teams_to_rank_list = []
    for team_id, data in team_data.items():
        if team_id in bye_team_ids: continue
        if data["rank_category"] == 99 and (data["wins"] > 0 or data["losses"] > 0) : data["rank_category"] = 100 
        if data["rank_category"] != 99 or data["wins"] > 0 or data["losses"] > 0 :
            teams_to_rank_list.append({"id": team_id, "data": data})
    teams_to_rank_list.sort(key=lambda x: (x["data"]["rank_category"], x["data"].get("rank_value", 0), -x["data"]["wins"]))
    
    print("\nDEBUG: Sorted teams_to_rank_list (showing rank_category for key teams):")
    for item in teams_to_rank_list:
        if item["id"] in teams_of_interest + ['4','5']:
            print(f"  Sorted: Team {item['id']}, Category: {item['data']['rank_category']}")

    final_standings_grouped = []
    if not teams_to_rank_list: return []
    current_rank_group = [teams_to_rank_list[0]["id"]]
    for i in range(1, len(teams_to_rank_list)):
        if teams_to_rank_list[i]["data"]["rank_category"] == teams_to_rank_list[i-1]["data"]["rank_category"] and \
           teams_to_rank_list[i]["data"].get("rank_value", 0) == teams_to_rank_list[i-1]["data"].get("rank_value", 0):
            current_rank_group.append(teams_to_rank_list[i]["id"])
        else:
            final_standings_grouped.append(current_rank_group)
            current_rank_group = [teams_to_rank_list[i]["id"]]
    if current_rank_group: final_standings_grouped.append(current_rank_group)
    
    print(f"--- compute_standings returning: {final_standings_grouped} ---")
    return final_standings_grouped