# Graph Report - Screenshot Reader Project  (2026-09-20)

## Corpus Check
- Large corpus: 204 files · ~531,694 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder.

## Summary
- 1105 nodes · 2264 edges · 81 communities (55 shown, 26 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 91 edges (avg confidence: 0.87)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Migration & Duplicate-Check Runner
- Score-Bot API & Auth
- Web Viz Chart Interactivity
- Legacy ELO Ladder CLI
- Reference Database Manager
- Discord Bot Test Client
- Role Assignment & Config
- Legacy CLI Requirements Doc
- Campaign Domain Vocabulary
- Screenshot Season Processing
- Discord Answer Parsing
- Landing Page Floating Logos
- Backend Client (Campaign API)
- Claude Image Extraction Adapter
- Player Match Resolution Workflow
- Player Role Feature Planning
- Match Data Cleaning CLI
- Claude Vision Score Extraction
- Stats Reader Module Init
- Pending Battle Ambiguity Handling
- Ambiguity Q&A Rendering
- ELO Ladder Test Suite
- Match-Persisted Webhook
- Player Hash & Resolution
- Player Role CRUD Functions
- Team ELO Recompute
- Match Persistence Helpers
- Player ELO Recompute
- Player Subbing System
- Match Cancel & Rejection
- Role Review Dead-End Check
- Postgres Migration Runner
- SQLite Database Utilities
- Screenshot Folder Scanner
- Interactive Role Assignment
- Match Summary Rendering
- Role-Based Report Generation
- Role Report Generator (Draft)
- Sample Match Role Processing
- Read API & ELO Endpoints
- Postgres Test Fixtures
- Role Distribution Reports (Draft)
- Discord Admin Role Check
- Frontend Deploy Workflow
- Chart.js Leaderboard Charts
- Pending-Match Pause States
- Reference DB Fuzzy Matching
- Leaderboard Role Filtering
- ELO Rating Formulas
- Interactive Player Management (Draft)
- SQLite Schema Update (Draft)
- Player Stats Role Update (Draft)
- Frontend Data Fetch (CORS)
- Frontend PRD Phases
- Cavern Angels Squadron Emblem
- Tangerine Squadron / Faction
- Stats Reader Package Init
- Teams Endpoint
- Roadmap Phase 4 (Polish)
- Roadmap Phase 7 (Validation)
- Death Star Emblem
- Gray Squadron Emblem
- Hive Guard Squadron Emblem
- Idiot's Array Emblem
- Kintan Striders Emblem
- Black Sabacc Squadron Emblem
- Remnant Squadron Emblem
- Sabacc Patch Emblem
- Siren Squadron Emblem
- Randolorians Squadron Emblem
- TIE Fighter Render
- TRA Squadron Emblem
- X-wing Icon Emblem

## God Nodes (most connected - your core abstractions)
1. `apply_schema()` - 89 edges
2. `start_ingestion()` - 26 edges
3. `ReferenceDatabase` - 26 edges
4. `stats_db_processor.py` - 24 edges
5. `_get_system_id()` - 20 edges
6. `_confirm_roster_sizes()` - 19 edges
7. `render_question()` - 17 edges
8. `parse_answer()` - 17 edges
9. `edit_match_player()` - 16 edges
10. `_make_ref_team()` - 16 edges

## Surprising Connections (you probably didn't know these)
- `Standard Workflow` --semantically_similar_to--> `Phase 1 (MVP)`  [INFERRED] [semantically similar]
  utilities/README.md → web_visualizations/README.md
- `Frontend Viz Phase 1 (MVP)` --semantically_similar_to--> `Roadmap Phase 1: Ingestion Workflow`  [INFERRED] [semantically similar]
  PRD_frontend.md → ROADMAP.md
- `Environment Notes for Picking This Up Cold` --semantically_similar_to--> `Testing Quickstart Six-Step Checklist`  [INFERRED] [semantically similar]
  ROADMAP.md → TESTING_QUICKSTART.md
- `create_match()` --uses--> `DuplicateMatchError`  [INFERRED]
  api/main.py → ingestion/workflow.py
- `test_post_matches_cancel_unknown_id_returns_404()` --calls--> `apply_schema()`  [EXTRACTED]
  tests/api/test_matches.py → db/migrate_runner.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Two-Layer Duplicate Ingestion Guard** — roadmap_duplicate_ingestion_guard, roadmap_stats_hash, roadmap_image_hash, ingestion_workflow [EXTRACTED 1.00]
- **Two-Tier Captain/Admin Trust Model** — context_captain, context_admin, docs_adr_0008_captain_admin_trust_levels, teams_onboarding [EXTRACTED 1.00]
- **Campaign Project Push/Pull Integration Boundary** — docs_campaign_integration_matches_latest_endpoint, ingestion_webhook, roadmap_phase5_read_api_webhook, docs_adr_0001_two_bot_split [INFERRED 0.90]
- **Pickup/Ranked ELO Calculation Pipeline** — stats_reader_stats_db_processor, stats_reader_fix_pickup_team_ids, stats_reader_elo_ladder, stats_reader_elo_ladder_readme_pickup_player_elo_ladder [INFERRED 0.85]
- **Web Visualization Data Loading Flow** — web_visualizations_script_fetchdata, web_visualizations_readme_stats_reports_dir, web_visualizations_readme_elo_reports_pickup_dir, web_visualizations_team, web_visualizations_pickup [INFERRED 0.75]
- **Pytest Automated Test Suite** — tests_readme_pytest, tests_test_score_extractor, tests_test_stats_reader, stats_reader_test_elo_ladder [EXTRACTED 1.00]

## Communities (81 total, 26 thin omitted)

### Community 0 - "Migration & Duplicate-Check Runner"
Cohesion: 0.07
Nodes (86): apply_schema(), Applies plain-SQL migration files under db/migrations/ to a Postgres connection., Apply any not-yet-applied migration file, in filename order., _build_match_summary(), cancel_ingestion(), _check_duplicate(), check_duplicate_image(), DuplicateMatchError (+78 more)

### Community 1 - "Score-Bot API & Auth"
Cohesion: 0.05
Nodes (75): api, require_campaign_api_key(), get_pg_conn(), answer_match(), AnswerRequest, cancel_match_route(), create_match(), _duplicate_match_exception() (+67 more)

### Community 2 - "Web Viz Chart Interactivity"
Cohesion: 0.06
Nodes (57): ES Modules Debug Page, createAdditionalLeaderboards(), createAIKillsLeaderboard(), createDamageLeaderboard(), createLeaderboardTable(), createLeastDeathsLeaderboard(), createNetKillsLeaderboard(), filterAllLeaderboards() (+49 more)

### Community 3 - "Legacy ELO Ladder CLI"
Cohesion: 0.05
Nodes (43): shutil, calculate_expected_outcome(), calculate_new_rating(), generate_combined_ladder(), generate_elo_ladder(), generate_player_elo_ladder(), main(), Calculate the expected outcome (probability of winning) for team A Args:… (+35 more)

### Community 4 - "Reference Database Manager"
Cohesion: 0.06
Nodes (29): interactive_menu(), interactive_player_management(), interactive_player_search(), interactive_team_management(), main(), populate_players_from_json(), Manages a reference database of canonical player and team information, Interactive console interface for reference database management (+21 more)

### Community 5 - "Discord Bot Test Client"
Cohesion: 0.10
Nodes (31): asyncio, bot, campaign_headers(), client(), fixture, X-API-Key header for the campaign-facing read endpoints (ROADMAP Phase 5) -…, _client(), _run() (+23 more)

### Community 6 - "Role Assignment & Config"
Cohesion: 0.09
Nodes (29): Script to assign roles to players in the reference database., ADR-0002: Discord-Mediated Ambiguity Resolution, ADR-0005: Backend-Owned Ingestion Workflow, dotenv, generate_player_roles_json(), Script to generate a consolidated player roles JSON file., Generate a JSON file mapping player names/hashes to their primary roles, Script to generate reports with role support. (+21 more)

### Community 7 - "Legacy CLI Requirements Doc"
Cohesion: 0.07
Nodes (36): argparse, datetime, Data Cleaning Requirements (FR004-005), Project Requirements Document (Legacy CLI), ELO Calculation & Ladder Generation Requirements (FR024-028), FR023: Prepare Player Stats for Player ELO, Reference Data Management Requirements (FR006-014), Reporting Requirements (FR029-030) (+28 more)

### Community 8 - "Campaign Domain Vocabulary"
Cohesion: 0.07
Nodes (39): Admin (domain term), Campaign (domain term), Captain (domain term), Faction (domain term), Match (domain term), System (domain term), Team (domain term), Turn (domain term) (+31 more)

### Community 9 - "Screenshot Season Processing"
Cohesion: 0.07
Nodes (34): parametrize, extract_date_from_filename(), extract_scores_from_multiple_images(), find_screenshots_dir(), process_all_seasons(), process_season_folder(), Process all images in a season folder Args: season_folder (str): Path to the…, Process multiple game score screen images and extract structured data. Args:… (+26 more)

### Community 10 - "Discord Answer Parsing"
Cohesion: 0.10
Nodes (35): parse_answer(), parse_edit_updates(), Turn a plain-text reply into the answer payload submit_answer() expects.…, Turn ['score=1700', 'kills=5'] into {'score': 1700, 'kills': 5}., render_question(), Discord renders consecutive 'N. text' lines as a native ordered list and…, test_parse_answer_missing_field_numeric_coerces_int(), test_parse_answer_missing_field_numeric_rejects_non_numeric() (+27 more)

### Community 11 - "Landing Page Floating Logos"
Cohesion: 0.09
Nodes (17): faction_win_rates.json, Landing Page (index.html), FloatingLogo, FloatingLogosBackground, Pilot Stats Page (pickup.html), Pilot ELO Ladder Tabs (General/Flex/Support/Farmer), Pilot Role Filter, chartjs-adapter-date-fns (+9 more)

### Community 12 - "Backend Client (Campaign API)"
Cohesion: 0.12
Nodes (29): attach_player_to_roster(), create_match(), create_player(), create_team(), edit_match_player(), edit_match_winner(), find_players(), Thin async HTTP wrapper over the backend API (ROADMAP Phases 1-3). Each… (+21 more)

### Community 13 - "Claude Image Extraction Adapter"
Cohesion: 0.15
Nodes (26): extract_from_image_bytes(), Adapter between raw uploaded image bytes and score_extractor's vision call,…, tempfile, _confirm_roster_sizes(), _get_system_id(), _make_ref_player(), _make_ref_team(), _persist_unambiguous_match() (+18 more)

### Community 14 - "Player Match Resolution Workflow"
Cohesion: 0.13
Nodes (21): collections, difflib, _advance(), _apply_field_overrides(), _find_player_candidates(), _find_ref_player(), _get_ref_player_by_id(), _load_pending_match() (+13 more)

### Community 15 - "Player Role Feature Planning"
Cohesion: 0.14
Nodes (20): Pickup/Ranked Stats and ELO Approach, Roadmap Phase 1: Ingestion Workflow, Player Role Feature (Farmer/Flex/Support), ROLE_IMPLEMENTATION_GUIDE.md, Manual Integration Option, Direct File Replacement Option, calculate_expected_outcome(), calculate_new_rating() (+12 more)

### Community 16 - "Match Data Cleaning CLI"
Cohesion: 0.14
Nodes (20): clean_data(), create_new_player(), edit_match_data(), edit_player(), edit_player_data(), main(), pretty_print_match(), print_player_table() (+12 more)

### Community 17 - "Claude Vision Score Extraction"
Cohesion: 0.11
Nodes (20): anthropic, azure_functions, base64, Multiple Images with System Prompt Example, Stale Model ID claude-3-7-sonnet-20250219, HttpRequest, HttpResponse, io (+12 more)

### Community 18 - "Stats Reader Module Init"
Cohesion: 0.15
Nodes (18): pathlib, re, get_or_create_season(), get_or_create_team(), Get a team ID from the database or create it if it doesn't exist. If reference…, Get a season ID from the database or create it if it doesn't exist, Star Wars Squadrons Stats Reader - Modules package Contains modular components…, process_match_data() (+10 more)

### Community 19 - "Pending Battle Ambiguity Handling"
Cohesion: 0.11
Nodes (17): get_latest_match(), GET /matches/latest -- the same campaign-project read route…, _already_reported(), AlreadyReportedError, AmbiguousBattleError, _fetch_pending_battles(), _get_live_battle_context(), _handle_pending() (+9 more)

### Community 20 - "Ambiguity Q&A Rendering"
Cohesion: 0.12
Nodes (16): parse_edit_command(), _parse_index(), Pure rendering/parsing for the score bot's plain-text ambiguity Q&A (ROADMAP…, Parses a reply to a candidate-numbered question: 1..count picks a candidate…, Split '<match_id> <player name> field=value ...' into (match_id, player_name,…, render_help(), _render_question_body(), render_screenshot_received() (+8 more)

### Community 21 - "ELO Ladder Test Suite"
Cohesion: 0.13
Nodes (9): Test the expected outcome calculation, Tests for the ELO ladder generator, Test the new rating calculation, Test that the ELO ladder is generated correctly, Set up a test database with sample match data, Test with a sample from the actual data format, Clean up temporary files, Create a test database with sample data (+1 more)

### Community 22 - "Match-Persisted Webhook"
Cohesion: 0.19
Nodes (11): httpx, ingestion, Outbound push to the campaign project once a Match persists (ROADMAP Phase 5,…, send_match_persisted(), logging, test_no_header_when_secret_unset(), test_no_op_when_webhook_url_unset(), test_retries_then_gives_up_without_raising() (+3 more)

### Community 23 - "Player Hash & Resolution"
Cohesion: 0.14
Nodes (14): generate_player_hash(), get_or_create_player(), player_resolution_cache, Player processing module for Star Wars Squadrons statistics. Handles player…, Generate a consistent hash for a player name, Get a player ID from the database or create it if it doesn't exist. Handles…, Test player hash generation for exact name matching, Test creating and retrieving players without reference DB (+6 more)

### Community 24 - "Player Role CRUD Functions"
Cohesion: 0.17
Nodes (11): add_player(), find_fuzzy_player_matches(), get_player(), list_players(), Updated functions for reference_manager.py to support player roles (Farmer,…, Update a player in the reference database, now with role support, List all players in the reference database, Get a player from the reference database (now with role) (+3 more)

### Community 25 - "Team ELO Recompute"
Cohesion: 0.40
Nodes (8): GET /elo/teams Endpoint, Team ELO ladder, recomputed from scratch on each 'team' Match persist, scoped…, recompute_team_elo(), _make_match(), _make_team(), test_elo_is_isolated_per_campaign(), test_recompute_team_elo_replays_matches_chronologically(), test_recompute_team_elo_starts_teams_with_no_matches_at_starting_elo()

### Community 26 - "Match Persistence Helpers"
Cohesion: 0.22
Nodes (10): _compute_stats_hash(), _get_or_create_player(), _get_or_create_team(), _get_or_create_team_by_name(), _normalize_winner(), _persist(), _player_hash(), Returns (player_id, canonical_name). The players row always uses the reference… (+2 more)

### Community 27 - "Player ELO Recompute"
Cohesion: 0.53
Nodes (9): recompute_player_elo(), _update(), _make_match(), _make_player(), _make_player_stat(), _rating(), test_player_elo_is_isolated_per_campaign_and_match_type(), test_recompute_player_elo_computes_general_and_role_ladders() (+1 more)

### Community 28 - "Player Subbing System"
Cohesion: 0.24
Nodes (10): is_subbing Flag, player_performance.json, player_performance_no_subs.json, player_stats Table, Player Subbing System, player_teams.json, season_summary.json, subbing_report.json (+2 more)

### Community 29 - "Match Cancel & Rejection"
Cohesion: 0.22
Nodes (9): cancel_match(), submit_answer(), Message shown after the user replies '0' to a player_match/ team_assignment…, render_cancelled(), render_rejection(), _handle_pending_answer(), test_render_cancelled_mentions_re_posting(), test_render_rejection_player_match() (+1 more)

### Community 30 - "Role Review Dead-End Check"
Cohesion: 0.22
Nodes (9): is_dead_end(), True if this question has no candidate to reply with (e.g. an unrecognized…, _handle_result(), Right after a match persists: walk every player one at a time, offering to set…, _start_role_review(), test_is_dead_end_false_for_roster_size_and_missing_field(), test_is_dead_end_false_when_candidates_present(), test_is_dead_end_true_for_player_match_with_no_candidates() (+1 more)

### Community 31 - "Postgres Migration Runner"
Cohesion: 0.33
Nodes (7): main(), CLI entry point for Phase 0: apply the Postgres schema and, optionally, import…, _copy_table(), migrate(), One-time import of the existing SQLite reference/stats databases into Postgres.…, Copy ref_teams/ref_players and seasons/teams/matches/players/player_stats from…, _reset_sequences()

### Community 32 - "SQLite Database Utilities"
Cohesion: 0.31
Nodes (7): create_database(), Database utilities for the Star Wars Squadrons statistics database. Contains…, Create the SQLite database with the required schema including role column, Update match types for existing matches in the database using a batch approach…, update_match_types_batch(), _build_fixture_databases(), test_migrate_copies_reference_and_stats_data_into_postgres()

### Community 33 - "Screenshot Folder Scanner"
Cohesion: 0.33
Nodes (8): check_database_match(), check_for_seasons(), list_screenshot_files(), main(), Find all screenshot files in the Screenshots directory, Utility script to scan for screenshots in the new folder structure and help…, Check for season subdirectories in the Screenshots folder, Check if filenames in the database match the available screenshots

### Community 34 - "Interactive Role Assignment"
Cohesion: 0.25
Nodes (8): assign_role(), assign_roles_interactive(), list_players(), _mirror_role_to_postgres(), Interactive mode to assign roles to players, Best-effort mirror of a role assignment into the live Postgres DB that the…, List players from the reference database, Assign a role to a player

### Community 35 - "Match Summary Rendering"
Cohesion: 0.25
Nodes (8): Formats a backend error response's `detail` for display - either a plain string…, Post-persist confirmation table, re-rendered after !edit too., render_error_detail(), render_match_summary(), test_render_error_detail_duplicate_match_shape_renders_summary(), test_render_error_detail_plain_string_passthrough(), test_render_match_summary_includes_winner_and_both_factions(), test_render_match_summary_skips_empty_faction()

### Community 36 - "Role-Based Report Generation"
Cohesion: 0.25
Nodes (8): generate_player_team_roles_report(), generate_role_based_reports(), generate_role_distribution_report(), main(), Generate player performance reports filtered by role, Generate a report showing players' teams and roles, Generate all role-based reports, Generate a report showing the distribution of roles

### Community 37 - "Role Report Generator (Draft)"
Cohesion: 0.32
Nodes (7): generate_role_based_reports(), generate_role_distribution_report(), generate_stats_reports(), Updates to the report generator to add role-based filtering and reports, Generate various statistics reports from the database, Generate player performance reports filtered by role, Generate a report showing the distribution of roles

### Community 38 - "Sample Match Role Processing"
Cohesion: 0.33
Nodes (6): hashlib, get_player_role(), process_sample_match(), Script to process a sample of match data with role support., Get a player's primary role from the reference database, Process a sample match with role support

### Community 39 - "Read API & ELO Endpoints"
Cohesion: 0.33
Nodes (5): GET /elo/players Endpoint, GET /matches/latest Endpoint, Match-Persisted Webhook, Roadmap Phase 5: Read API and Push Notification, Player ELO ladders for pickup/ranked matches: a "general" (base) ladder plus…

### Community 40 - "Postgres Test Fixtures"
Cohesion: 0.40
Nodes (5): psycopg2, _drop_all_tables(), pg_conn(), fixture, A connection to a Postgres test database, wiped clean before each test.

### Community 41 - "Role Distribution Reports (Draft)"
Cohesion: 0.33
Nodes (6): generate_role_based_reports(), generate_role_distribution_report(), generate_stats_reports(), Generate player performance reports filtered by role, Generate various statistics reports from the database, Generate a report showing the distribution of roles

### Community 42 - "Discord Admin Role Check"
Cohesion: 0.40
Nodes (5): is_admin_reactor(), role_names: a Discord member's role names (any iterable of str) - the member…, test_is_admin_reactor_false_for_no_roles(), test_is_admin_reactor_false_when_role_absent(), test_is_admin_reactor_true_when_role_present()

### Community 43 - "Frontend Deploy Workflow"
Cohesion: 0.50
Nodes (5): GitHub Pages Static Deploy Workflow, Frontend Viz Phase 1 (MVP), Frontend Viz Phase 2 (Enhancements), web_visualizations Directory Structure Decision, Development and Deployment Workflow (GitHub Pages)

### Community 44 - "Chart.js Leaderboard Charts"
Cohesion: 0.40
Nodes (5): Chart.js Library, FRF102: Basic Team ELO Ladder Chart, FRF103: Basic Pickup Player ELO Ladder Chart, FRF104: Simple Leaderboard Display, FRF205: Leaderboard-Chart Interaction (Filtering)

### Community 45 - "Pending-Match Pause States"
Cohesion: 0.40
Nodes (5): awaiting_missing_field pause state, awaiting_player_match pause state, awaiting_roster_size pause state, awaiting_team_assignment pause state, pending_matches State Machine

### Community 46 - "Reference DB Fuzzy Matching"
Cohesion: 0.50
Nodes (5): Alias Matching, Interactive Fuzzy Matching, Reference Database, Database Recreation Steps, squadrons_reference.db

### Community 47 - "Leaderboard Role Filtering"
Cohesion: 0.40
Nodes (3): leaderboardsContainer, setupRoleFiltering(), waitForTables()

### Community 48 - "ELO Rating Formulas"
Cohesion: 0.50
Nodes (4): Base ELO Rating (1000), Expected Outcome Formula, K-factor, Rating Update Formula

### Community 49 - "Interactive Player Management (Draft)"
Cohesion: 0.50
Nodes (3): interactive_player_management(), Updated interactive_player_management function for reference_manager.py to…, Interactive console interface for player management

### Community 50 - "SQLite Schema Update (Draft)"
Cohesion: 0.50
Nodes (3): create_database(), Updated create_database function to include the role column for player_stats, Create the SQLite database with the required schema including role column

### Community 51 - "Player Stats Role Update (Draft)"
Cohesion: 0.50
Nodes (3): process_player_stats(), Updated process_player_stats function to handle player roles, Process stats for a single player including role handling

### Community 52 - "Frontend Data Fetch (CORS)"
Cohesion: 0.50
Nodes (4): ../elo_reports_pickup/ directory, Local Web Server Requirement (CORS), ../stats_reports/ directory, fetchData()

### Community 53 - "Frontend PRD Phases"
Cohesion: 0.50
Nodes (4): Phase 1 (MVP), Phase 2 (Enhancements), Phase 3 (Future), PRD_frontend.md

### Community 55 - "Cavern Angels Squadron Emblem"
Cohesion: 1.00
Nodes (3): Cavern Angels - Blue Squadron Emblem, Cavern Angels (Blue Squadron), X-wing Starfighter Silhouette Motif

## Ambiguous Edges - Review These
- `score_extractor/__init__.py` → `Multiple Images with System Prompt Example`  [AMBIGUOUS]
  example multiple image prompt.txt · relation: semantically_similar_to

## Knowledge Gaps
- **64 isolated node(s):** `leaderboardsContainer`, `Faction (domain term)`, `Frontend Viz Phase 2 (Enhancements)`, `FRF103: Basic Pickup Player ELO Ladder Chart`, `FRF104: Simple Leaderboard Display` (+59 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 357 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **26 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `score_extractor/__init__.py` and `Multiple Images with System Prompt Example`?**
  _Edge tagged AMBIGUOUS (relation: semantically_similar_to) - confidence is low._
- **Why does `apply_schema()` connect `Migration & Duplicate-Check Runner` to `SQLite Database Utilities`, `Score-Bot API & Auth`, `Claude Image Extraction Adapter`, `Team ELO Recompute`, `Player ELO Recompute`, `Postgres Migration Runner`?**
  _High betweenness centrality (0.113) - this node is a cross-community bridge._
- **Why does `Pilot Stats Page (pickup.html)` connect `Landing Page Floating Logos` to `Web Viz Chart Interactivity`, `Legacy CLI Requirements Doc`?**
  _High betweenness centrality (0.113) - this node is a cross-community bridge._
- **Why does `Pickup Player ELO Ladder` connect `Legacy CLI Requirements Doc` to `Landing Page Floating Logos`?**
  _High betweenness centrality (0.112) - this node is a cross-community bridge._
- **What connects `leaderboardsContainer`, `Faction (domain term)`, `Frontend Viz Phase 2 (Enhancements)` to the rest of the system?**
  _64 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Migration & Duplicate-Check Runner` be split into smaller, more focused modules?**
  _Cohesion score 0.07082748948106592 - nodes in this community are weakly interconnected._
- **Should `Score-Bot API & Auth` be split into smaller, more focused modules?**
  _Cohesion score 0.051131354687040845 - nodes in this community are weakly interconnected._