# Star Wars Squadrons Score Reader

This project uses AI vision capabilities to extract and analyze scores from Star Wars Squadrons game screenshots, building a comprehensive database of match results and player statistics. It includes ELO rating systems to track both team and individual player skill levels.

## 🚀 Live Demo

- **Main site**: [https://harry84.github.io/score-reader/](https://harry84.github.io/score-reader/)
- **Mirror site**: [https://gmt-erisi.github.io/score-reader/](https://gmt-erisi.github.io/score-reader/)

---

## Project Structure

```
Star Wars Squadrons Score Reader
│
├── ../Screenshots/             - Raw screenshots organized by season (outside project folder)
│   ├── SCL13/                  - Season 13 screenshots
│   ├── SCL14/                  - Season 14 screenshots
│   ├── SCL15/                  - Season 15 screenshots
│   ├── TEST/                   - Test screenshots
│   └── ...
│
├── Extracted Results/          - JSON files containing extracted match data
│   ├── SCL13/                  - Extracted data for Season 13
│   ├── SCL14/                  - Extracted data for Season 14
│   ├── ...
│   └── all_seasons_data.json   - Combined data from all seasons
│
├── score_extractor/            - Module for extracting data from screenshots
│   ├── __init__.py             - Main extraction logic using Claude API
│   ├── season_processor.py     - Process screenshots by season
│   └── test_extraction.py      - Test utilities for extraction
│
├── stats_reader/               - Module for processing data and managing the database
│   ├── elo_ladder.py           - ELO rating system for teams
│   ├── player_elo_ladder.py    - ELO rating system for individual players (pickup/ranked)
│   ├── role_elo_calculator.py  - Role-specific ELO rating system for players
│   ├── reference_manager.py    - Manages the reference database
│   ├── stats_db_processor_direct.py - Processes extracted data into the database (using modules)
│   ├── stats_db_processor.py   - (Legacy/Alternative processor)
│   ├── modules/                - Submodules for processing logic (database, match, player, report)
│   ├── ELO_LADDER_README.md    - Documentation for the ELO ladder
│   ├── README.md               - Documentation for stats processing
│   └── ...
│
├── elo_reports_pickup/         - Generated pickup ELO reports
│   ├── pickup_player_elo_ladder.json - ELO ratings for players in pickup matches
│   ├── pickup_player_elo_history.json - History of ELO changes for pickup players
│   ├── pickup_flex_elo_ladder.json - ELO ratings for Flex role players
│   ├── pickup_support_elo_ladder.json - ELO ratings for Support role players
│   ├── pickup_farmer_elo_ladder.json - ELO ratings for Farmer role players
│   └── ...
│
├── stats_reports/              - Generated team statistical reports
│   ├── elo_ladder_team.json    - Current ELO ratings for teams
│   ├── elo_history_team.json   - History of ELO changes for teams
│   └── ...
│
├── tests/                      - Unit tests for the project
│   ├── test_data/              - Test data fixtures
│   ├── test_score_extractor.py - Tests for score extraction
│   ├── test_stats_reader.py    - Tests for stats processing
│   └── test_reference_data.json- Test reference data
│
├── utilities/                  - Maintenance and diagnostic tools
│   ├── scan_screenshots.py     - Scan and organize screenshots
│   ├── update_paths.py         - Update file paths
│   └── README.md               - Documentation for utilities
│
├── env-setup.ps1               - PowerShell script for environment setup
├── squadrons_reference.db      - SQLite database with canonical player/team names
├── squadrons_stats.db          - SQLite database with all processed match data
└── README.md                   - This file
```

## Setup

1.  Clone the repository:
    ```
    git clone https://github.com/Harry84/score-reader
    cd score-reader
    ```

2.  Set up Python environment:
    ```powershell
    # Run the provided setup script to configure environment
    .\env-setup.ps1

    # Or manually set up the environment:
    # Note: These instructions assume pyenv-win is installed. If not, you can install it or use
    # a regular Python installation instead of 3.10.9 (if not already installed)
    pyenv install 3.10.9

    # Set local Python version
    pyenv local 3.10.9

    # Create and activate virtual environment
    python -m venv venv
    .\venv\Scripts\Activate.ps1

    # Install dependencies
    pip install -r requirements.txt
    ```

3.  Edit the .env file to add your Claude API key

4.  Place your screenshots in the `../Screenshots` folder (at the same level as the project folder) in the appropriately named folder

## Standard Workflow for Team Matches

1.  **Add new screenshots** to the appropriate folder in the `../Screenshots` folder

2.  **Process screenshots**:
    ```bash
    python -m score_extractor.season_processor --base-dir ../Screenshots --output-dir "Extracted Results"
    ```
    This generates `Extracted Results/all_seasons_data.json`.

### Date Handling during Extraction

The extraction process (`score_extractor/season_processor.py`) attempts to determine the match date automatically from the screenshot filename. It looks for specific patterns:

1.  `Star Wars Squadrons Screenshot YYYY.MM.DD - HH.MM.SS[.ms].png`
2.  `YYYY[.-]MM[.-]DD[_HH.MM.SS].png` (Time defaults to 12:00:00 if missing)

The extracted date is always converted to the standard `"YYYY-MM-DD HH:MM:SS"` format.

**Important Fallback:** If a valid date cannot be extracted from the filename using these patterns, the script will **prompt the user** during the extraction run:

Could not extract a valid date from filename. Please enter date (YYYY-MM-DD) or press Enter to use the current date:

-   If you enter a date in `YYYY-MM-DD` format, it will be used with the time set to `00:00:00`.
-   If you press Enter without typing anything, or if your input is invalid, the script will default to using the **current date and time** when the script is run (time set to `00:00:00`).

This ensures that every match record processed has a `match_date` field added to the raw JSON output. Note that the subsequent database processing step (`stats_reader.stats_db_processor_direct.py`) will also display this date and prompt for confirmation or override before saving to the database.

3.  **Clean the extracted data** (Recommended):
    ```bash
    python -m stats_reader clean --input "Extracted Results/all_seasons_data.json" --output "Extracted Results/all_seasons_data_cleaned.json"
    ```
    This launches an interactive tool to review and correct potential AI extraction errors (scores, team names, results) by comparing against the original screenshots. Don't worry about slightly different player names for the same person here; that's handled in the next step.

4.  **Populate and manage the reference database**:
    ```bash
    # Start fresh by deleting any existing reference database if needed
    # del squadrons_reference.db

    # Populate the reference database with player names from the CLEANED data
    python -m stats_reader.reference_manager --db squadrons_reference.db --populate-from-json "Extracted Results/all_seasons_data_cleaned.json"

    # Then manage teams and players using the interactive tool
    python -m stats_reader.reference_manager --db squadrons_reference.db --manage
    ```

    When using the management interface:
    1.  Choose "Team Management" to first create any teams you need.
    2.  Then select "Player Management" to assign players to their primary teams and use "Resolve Duplicate Player IDs" to merge different names for the same player (e.g., "PlayerA" and "Player A") into a single canonical entry. This also updates the `_cleaned.json` file for consistency.

    Setting primary teams is important for tracking substitute appearances.

5.  **Process data into database**:
    ```bash
    # Use the CLEANED data as input
    python -m stats_reader.stats_db_processor_direct --input "Extracted Results/all_seasons_data_cleaned.json" --reference-db squadrons_reference.db
    ```
    
    When prompted during processing, choose the match type. The processor will now prompt you to select the match type (team, pickup, ranked) at the beginning, which eliminates the need for further special steps to remove team IDs for pickup and ranked games. It will also prompt for player roles based on the reference database.

5b. **Generate Player Roles File** (Required for Web Visualizations):
    ```bash
    python generate_player_roles_json.py squadrons_stats.db stats_reports
    ```
    This creates `stats_reports/player_roles.json`, consolidating player roles based on the database and reference info.

6.  **Generate ELO ladder**:
    ```bash
    python -m stats_reader.elo_ladder --match-type team
    ```

    This will create team ELO reports in the `stats_reports` directory.

## Workflow for Pickup/Ranked Matches

For processing pickup or ranked matches:

1.  **Process screenshots** as in the standard workflow.

2.  **Clean the extracted data** as in the standard workflow.

3.  **Process the data as pickup/ranked matches**:
    ```bash
    # Generic command:
    python -m stats_reader.stats_db_processor_direct --input "Extracted Results/[FOLDER]/[FOLDER]_results_cleaned.json" --reference-db squadrons_reference.db
    # Example if we pretend SCL15 folder has pickup matches in it (just to show the command):
    python -m stats_reader.stats_db_processor_direct --input "Extracted Results/SCL15/SCL15_results_cleaned.json" --reference-db squadrons_reference.db
    # The default db for the --db argument is squadrons_stats.db (i.e. if you don't specify a db name via the arg)
    # To process towards a db of your choice (for example to have a separate database for pickup vs SPBL vs SCL vs ranked):
    python -m stats_reader.stats_db_processor_direct --input "Extracted Results/SCL15/SCL15_results_cleaned.json" --reference-db squadrons_reference.db --db squadrons_pickup.db
    ```

    When prompted during processing:
    -   Choose "pickup" or "ranked" as the match type
    -   The processor will automatically:
        -   Assign generic team names ("Imp_pickup_team"/"NR_pickup_team" or "Imperial_ranked_team"/"NR_ranked_team")
        -   Set player team_ids to NULL for proper pickup/ranked tracking
    -   You will be prompted to confirm/enter player roles for each match.

4. **Generate Player Roles File** (Required for Web Visualizations):
    ```bash
    # Use the appropriate DB and output directory if you used a custom one in step 3
    # Example for custom pickup DB:
    python generate_player_roles_json.py squadrons_pickup.db elo_reports_pickup
    ```
    This creates `player_roles.json` in the specified output directory.

5.  **Generate player-based ELO ladder**:
    ```bash
    # For pickup matches (preferred method) with custom DB:
    python -m stats_reader.player_elo_ladder --db squadrons_pickup.db --output "elo_reports_pickup" --match-type pickup
    ```

    This will create the following reports in the `elo_reports_pickup` directory:
    -   `pickup_player_elo_ladder.json`: Current ELO ratings for individual players
    -   `pickup_player_elo_history.json`: Full history of player ELO changes (including roles)

5a. **Generate role-specific ELO ladders**:
    ```bash
    # Generate role-specific ELO ladders for pickup matches:
    python -m stats_reader.role_elo_calculator --db squadrons_pickup.db --output "elo_reports_pickup" --match-type pickup
    ```

    This will create the following additional reports in the `elo_reports_pickup` directory:
    -   `pickup_flex_elo_ladder.json`: ELO ratings for players in the Flex role
    -   `pickup_support_elo_ladder.json`: ELO ratings for players in the Support role
    -   `pickup_farmer_elo_ladder.json`: ELO ratings for players in the Farmer role
    -   `pickup_flex_elo_history.json`: History of ELO changes for Flex role players
    -   `pickup_support_elo_history.json`: History of ELO changes for Support role players
    -   `pickup_farmer_elo_history.json`: History of ELO changes for Farmer role players

6.  **Generate Role-Specific Performance Reports** (Required for Additional Leaderboards):
    ```bash
    # This step is critical for the web visualization's additional leaderboards to work
    python generate_role_reports.py squadrons_pickup.db elo_reports_pickup
    ```

    This will generate several important files in the `elo_reports_pickup` directory:
    -   `player_performance_pickup_role_flex.json`
    -   `player_performance_pickup_role_farmer.json`
    -   `player_performance_pickup_role_support.json`
    -   `role_distribution.json`
    -   `role_distribution_by_match_type.json`
    -   `player_teams_roles.json`

    These files are needed for the web visualization to display the additional leaderboards (AI Kills, Damage, Net Kills, and Least Deaths).

7.  **View generated reports** in the web visualization:
    ```bash
    # Navigate to the web_visualizations directory and open pickup.html in a browser
    ```

## Key Differences between Team and Pickup/Ranked Processing

-   **Team Assignment**: In team matches, players represent specific teams. In pickup/ranked matches, players play for themselves regardless of their primary team affiliation.
-   **ELO Calculation**: Team matches use team-based ELO. Pickup/ranked matches use player-based ELO.
-   **Database Handling**: For pickup/ranked matches, player team_ids are automatically set to NULL in the database when you select the appropriate match type during processing.
-   **Reports**: Pickup/ranked matches generate player-centric reports rather than team-centric ones.
-   **Report Location**: Team ELO reports go to `stats_reports` directory, while pickup ELO reports should go to `elo_reports_pickup` directory.

## Processing a Single Folder

If you want to process only a specific folder of screenshots (e.g., for a season of team games or a batch of pickup games or just for testing):

1.  **Process screenshots from a specific folder**:
    ```bash
    # Example using TEST folder
    python -m score_extractor.season_processor --base-dir ../Screenshots --season TEST --output-dir "Extracted Results"
    ```
    This processes only the `TEST` folder and saves results to `Extracted Results/TEST/TEST_results.json`.

2.  **Clean the extracted data** (Recommended):
    ```bash
    # Example using TEST folder output
    python -m stats_reader clean --input "Extracted Results/TEST/TEST_results.json" --output "Extracted Results/TEST/TEST_results_cleaned.json"
    ```
    Review and correct potential AI extraction errors (scores, team names, results) against the screenshots for this specific folder. Don't worry about slightly different player names for the same person here.

3.  **Populate and manage the reference database**:
    ```bash
    # Start fresh if necessary by deleting any existing reference database
    # del squadrons_reference.db

    # Populate the reference database with player names from the CLEANED data
    python -m stats_reader.reference_manager --db squadrons_reference.db --populate-from-json "Extracted Results/TEST/TEST_results_cleaned.json"

    # Then manage teams and players using the interactive tool
    python -m stats_reader.reference_manager --db squadrons_reference.db --manage
    ```

    When using the management interface:
    1.  Create teams if needed.
    2.  Assign primary teams and roles, and use "Resolve Duplicate Player IDs" to merge different names for the same player. This also updates the `_cleaned.json` file.

4.  **Process the extracted data into the stats database**:
    ```bash
    python -m stats_reader.stats_db_processor_direct --input "Extracted Results/TEST/TEST_results_cleaned.json" --reference-db squadrons_reference.db
    ```

    When prompted, select the appropriate match type (team, pickup, ranked) and confirm/enter player roles.

4b. **Generate Player Roles File** (Required for Web Visualizations):
    ```bash
    # Use the appropriate DB and output directory
    python generate_player_roles_json.py squadrons_stats.db stats_reports
    ```
    This creates `player_roles.json` in the specified output directory.

5.  **Generate appropriate ELO ladder**:
    ```bash
    # For team matches
    python -m stats_reader.elo_ladder --match-type team

    # For pickup matches
    python -m stats_reader.player_elo_ladder --db squadrons_stats.db --output "elo_reports_pickup" --match-type pickup
    
    # Generate role-specific ELO ladders (for pickup matches)
    python -m stats_reader.role_elo_calculator --db squadrons_stats.db --output "elo_reports_pickup" --match-type pickup
    ```

## Workflow Components

Each step in the workflow corresponds to specific components in the project:

| Step                       | Component                                  | Description                                                                              |
| -------------------------- | ------------------------------------------ | ---------------------------------------------------------------------------------------- |
| 1. Process Screenshots     | `score_extractor/season_processor.py`      | Extracts match data from screenshots using Claude API                                    |
| 2. Clean Extracted Data    | `stats_reader clean`                       | Interactive tool to correct AI extraction errors                                         |
| 3a. Populate Reference DB  | `stats_reader/reference_manager.py`        | Creates the reference database with player names from cleaned data                       |
| 3b. Manage Reference DB    | `stats_reader/reference_manager.py --manage` | Interactive tool for setting player primary teams/roles and resolving duplicate names    |
| 4. Process Match Data      | `stats_reader/stats_db_processor_direct.py`  | Adds cleaned match data to the stats database (with match type & role selection)         |
| 5a. Generate Team ELO      | `stats_reader/elo_ladder.py`               | Calculates team ELO ratings and generates ladders                                        |
| 5b. Generate Player ELO    | `stats_reader/player_elo_ladder.py`        | Calculates individual player ELO ratings for pickup/ranked matches (includes role history) |
| 5c. Generate Role ELO      | `stats_reader/role_elo_calculator.py`      | Calculates role-specific ELO ratings for pickup/ranked matches                           |

## Reference Database

The reference database (`squadrons_reference.db`) maintains consistent team and player names across matches. For advanced management:

```bash
python -m stats_reader.reference_manager --manage
```

This opens an interactive tool for managing canonical team and player names, including primary roles.

## Player Subbing System

The project tracks whether players are 'subbing' (playing for a team that is not their primary team) to differentiate between regular team appearances and substitute appearances. Here's how it works:

### How Subbing is Determined

1.  **During Import**: The subbing status (is_subbing = 0 or 1) is determined and stored when match data is imported via `stats_db_processor_direct.py`.

2.  **Reference-Based Suggestion**: When importing match data, the system compares:
    -   The player's primary team in the reference database
    -   The team they're playing for in the current match

3.  **User Confirmation**: The system suggests a subbing status (Yes/No) based on team name comparison, but you can override this suggestion during import by answering Yes/No to the prompt.

4.  **Permanent Storage**: Once confirmed, the subbing status is permanently stored in the database with that player's stats for that match. It is not recalculated later.

### Important Note About Player Transfers

If a player changes teams between seasons:

-   **Option 1**: Update their primary team in the reference database using `reference_manager`.
    ```bash
    python -m stats_reader.reference_manager --db squadrons_reference.db --manage
    ```
    Then select Player Management → Edit Player → Update Primary Team.

-   **Option 2**: During import, simply reject the suggested subbing status if it doesn't reflect the historical reality of whether they were subbing at that time.

The crucial detail is that **subbing status is determined and fixed at import time**, not dynamically recalculated based on the current reference database. The reference database only provides default suggestions during import.

### How Subbing Affects Reports

The system generates several reports that use the subbing status differently:

-   `player_performance.json`: Includes ALL games, regardless of subbing status
-   `player_performance_no_subs.json`: Only includes games where is_subbing = 0 (regular team appearances)
-   `subbing_report.json`: Only shows games where is_subbing = 1 (substitute appearances)

## Pickup/Ranked Stats and ELO

For pickup and ranked matches, the system takes a different approach:

-   **No Team Assignment**: Players are not associated with teams (team_id is NULL)
-   **Faction-Based Stats**: Players are still tracked based on their faction (Imperial/Rebel)
-   **Player-Centric ELO**: The ELO system rates individual players instead of teams
-   **Specialized Reports**: Dedicated reports track player performance in pickup/ranked matches
-   **Role-Specific ELO**: The system can also track separate ELO ratings for each role (Flex, Support, Farmer)

The player ELO system works by:
1.  Calculating the average ELO of all players on each faction in a match
2.  Updating individual player ratings based on match outcomes
3.  Ranking players based on their personal skill level

For role-specific ELO, the system uses the general ELO for team average calculation, but updates role-specific ratings only for players in that role.

### Important Note for Pickup ELO

For the pickup player ELO ladder, it is preferred to use the `player_elo_ladder.py` command and store the output in the `elo_reports_pickup` folder:

```bash
python -m stats_reader.player_elo_ladder --db squadrons_stats.db --output "elo_reports_pickup" --match-type pickup
```

This ensures the pickup player ladder is kept separate from the team ladder.

## Match Type Selection

The `stats_db_processor_direct.py` script prompts you to choose the match type (team, pickup, ranked) at the beginning of processing each match. This improvement eliminates the need for a separate step to remove team IDs for pickup and ranked games.

When you choose "pickup" or "ranked" as the match type:
-   Generic team names are automatically assigned
-   Player team_ids are automatically set to NULL in the database
-   No further steps are needed before generating player ELO ladders

This streamlined approach makes it easier to maintain separate ladders for different match types.

# Optional: If you need to fix team IDs for existing pickup/ranked matches in the database
# This command finds pickup/ranked matches where player_stats.team_id is not NULL and sets them to NULL
python -m stats_reader.fix_pickup_team_ids --db squadrons_stats.db

-   You accidentally processed pickup/ranked matches using the team workflow
-   You changed a match's type from "team" to "pickup" or "ranked" after initial processing
-   You're migrating data from an older version of the database structure
-   You want to regenerate pickup/ranked player ELO ladders but get errors about team IDs not being NULL

## Additional Tools

-   **Stats Processing**: More details in `stats_reader/README.md`
-   **ELO Ladder System**: Configuration and details in `stats_reader/ELO_LADDER_README.md`
-   **Utilities**: Maintenance scripts documented in `utilities/README.md`

## Processing Ranked Matches

For ranked matches, follow a similar workflow but with these commands:

```bash
# Process ranked match data
python -m stats_reader.stats_db_processor_direct --input "Extracted Results/[FOLDER]/[FOLDER]_results_cleaned.json" --reference-db squadrons_reference.db --db squadrons_ranked.db

# Generate roles file
python generate_player_roles_json.py squadrons_ranked.db stats_reports

# Generate ELO ladder
python -m stats_reader.player_elo_ladder --db squadrons_ranked.db --output "stats_reports" --match-type ranked

# Generate role-specific ELO ladders
python -m stats_reader.role_elo_calculator --db squadrons_ranked.db --output "stats_reports" --match-type ranked

# Generate role-specific performance reports
python generate_role_reports.py squadrons_ranked.db stats_reports
```

This will create the ranked player reports in the `stats_reports` directory:
- `ranked_player_elo_ladder.json`: Current ELO ratings for ranked players
- `ranked_player_elo_history.json`: Full history of ranked player ELO changes (including roles)
- Role-specific ladder files (e.g., `ranked_flex_elo_ladder.json`)
- Role-specific performance files for the web visualization

## Development and Deployment Workflow

This section outlines the recommended workflow for making changes, testing, and deploying updates to the GitHub Pages site hosted on the `upstream` remote (secondary GitHub account).

1.  **Make Changes**: Perform all development work on your local `dev` branch.
2.  **Test Locally**:
    *   Ensure all necessary report files (`stats_reports/*.json`, `elo_reports_pickup/*.json`) are generated using the appropriate commands.
    *   Start a local HTTP server from the project root directory:
        ```bash
        python -m http.server 8000
        ```
    *   Open your browser to `http://localhost:8000/web_visualizations/` and verify that the site functions correctly and loads all data.
    *   Stop the server with Ctrl+C when finished.
3.  **Push to `origin/dev`**: Commit your changes and push the `dev` branch to your primary GitHub repository (`origin`):
    ```bash
    git add .
    git commit -m "Your descriptive commit message"
    git push origin dev
    ```
4.  **Create Pull Request**: Go to your `origin` repository on GitHub and create a Pull Request from the `dev` branch to the `main` branch.
5.  **Review and Merge**: Review the changes in the Pull Request and merge it into the `main` branch on `origin`.
6.  **Update Local `main`**: Switch to your local `main` branch and pull the latest changes from `origin`:
    ```bash
    git checkout main
    git pull origin main
    ```
7.  **Deploy to GitHub Pages (`upstream`)**: Push the updated local `main` branch to the `upstream` remote (secondary GitHub account) to trigger the GitHub Pages deployment workflow:
    ```bash
    git push upstream main
    ```

### GitHub Pages Deployment Note

The GitHub Actions workflow (`.github/workflows/static.yml`) is configured to deploy only the contents of the `web_visualizations` directory. To ensure the JavaScript code can find the necessary JSON data files (e.g., `stats_reports/elo_ladder_team.json`, `elo_reports_pickup/pickup_player_elo_ladder.json`) both locally and on the deployed site:

*   **Workflow Copy Step**: The workflow includes a step that copies all `.json` files from the root `stats_reports` and `elo_reports_pickup` directories into corresponding subdirectories *within* the `web_visualizations` directory on the Actions runner *before* deployment.
*   **JavaScript Paths**: The `fetch` paths in `web_visualizations/js/realdata_fixed.js` are set relative to the HTML files (e.g., `stats_reports/file.json`, `elo_reports_pickup/file.json`), not relative to the script file itself.

This setup allows the same JavaScript code to work correctly in both the local development environment (served from the project root) and the deployed GitHub Pages environment.
## Notes

-   The project is configured to work with PNG and JPG files
-   Extracted data is saved to the Extracted Results directory
-   The SQLite database `squadrons_stats.db` contains all processed match data
-   Reports are generated in the `stats_reports` directory (team reports) and `elo_reports_pickup` directory (pickup player reports)
