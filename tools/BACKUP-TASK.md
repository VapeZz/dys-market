# DYS data backup — task prompt (version 2)

Proposed prompt for the scheduled task **DYS data backup (Sundays)**. It goes with `tools/backup_pack.py`
version 2 (pack → verify → confirm). The two must go live together: the new script refuses the old prompt's
command line and does nothing, so a mismatch fails safely instead of recording a backup that wasn't checked.

---

You are running the weekly Drive Your Style (DYS) data backup. It copies the market site's data from GitHub (public repo VapeZz/dys-market) into the folder C:\Users\chris\Documents\DYS Backup on Keo's computer "Skibidi", checks every copied file as it is on the computer, and only then records the backup. Nobody is watching, so work alone. Do exactly the steps below and nothing else.

RULES
- GitHub is read-only for this task: never push, never start a workflow, never change the repo.
- On the computer, write only inside C:\Users\chris\Documents\DYS Backup, and only the files the script lists. Never delete, rename or move anything there. Never touch any other folder.
- Don't post, send or publish anything anywhere (sending files to yourself with SendUserFile as a step of the copy is fine). Don't open or print the contents of data files.
- Never pass --recover-month unless Keo's own message in this run asks for it by month.
- Never edit plan.json, verify.json, commit.json or any state file. Never write backup-state.json yourself except as step 8 says.
- If a step fails twice, stop and report (step 9). Do not invent another way to copy the files.

Below, ROOT = C:\Users\chris\Documents\DYS Backup and WORK = a new empty folder of your own under /tmp.

STEPS
1. Tools. You need mcp__remote-devices__device_list_dir, mcp__remote-devices__device_stage_files and mcp__remote-devices__device_commit_files. If they aren't loaded, load them with ToolSearch ("select:mcp__remote-devices__device_list_dir,mcp__remote-devices__device_stage_files,mcp__remote-devices__device_commit_files"). If they don't exist, or can't reach the computer after one retry: step 9 with "FAILED: Skibidi not reachable".

2. List ROOT with device_list_dir (recursive true). Save the tool's JSON result exactly as returned to WORK/before.json. It must contain backup-state.json; if the folder or that file is missing: step 9 with "FAILED: backup folder or backup-state.json missing". Do not create a state file.

3. Stage ROOT\backup-state.json plus the three files in ROOT\state-history with the highest names (if there are any), in one device_stage_files call. Wait until each exists at its stagedPath (check up to 6 times, 10 seconds apart). Copy backup-state.json to WORK/backup-state.json and the history files into WORK/hist/ (create it even if empty).

4. In WORK run:
   git clone -q --depth 1 https://github.com/VapeZz/dys-market.git
   python3 -I dys-market/tools/backup_pack.py pack --out WORK/out --state WORK/backup-state.json --state-history WORK/hist --dest-listing WORK/before.json
   (20 minute timeout.) Exit 0 = go on. Exit 3 (BLOCKED) = step 9 with "FAILED: blocked:" and the BLOCKED line; copy nothing. Any other exit: run it once more; if it fails again, step 9 with "FAILED: the packing script failed" and its last line.
   Read WORK/out/plan.json.

5. Copy the data files: plan.json "transfer", in order. For each: SendUserFile with its "local" (display "attach", status "normal", caption "Weekly DYS backup pieces on their way to Skibidi") → it returns a file_uuid; then device_commit_files with devicePath = its "device_path" and fileUuid = that file_uuid. Keep each commit call at or under 900 MB. If a commit call returns an error (for example disk full or a dropped connection), note it and carry on: step 7 decides. If "transfer" is empty (a HOLD), skip to step 6.

6. Read it all back. List ROOT again (recursive) and save the result exactly to WORK/after.json. Then for each list in plan.json "stage_paths", call device_stage_files with those paths (one call per list), wait for the files as in step 3, and save all the results, in order, as one JSON list to WORK/staged.json.

7. Verify:
   python3 -I dys-market/tools/backup_pack.py verify --out WORK/out --dest-listing WORK/after.json --staged WORK/staged.json
   - Exit 0 ("READY"): go to step 8.
   - Otherwise read WORK/out/verify.json. If "verdict" is "retry": copy again only the files in "resend" (as in step 5), list ROOT again into WORK/after.json, stage those files again and add the new results to the end of WORK/staged.json, then run verify again with --attempt 2. Exit 0: step 8. Anything else: step 9 with "DYS backup " followed by verify's first output line (it starts with "FAILED:"). Do NOT do step 8.
   - "verdict" "failed": step 9 with "DYS backup " followed by verify's first output line (it starts with "FAILED:"). Do NOT do step 8.

8. Record the backup. WORK/out/commit.json "files" lists the record files in order: write each one exactly as in step 5 (SendUserFile, then device_commit_files with devicePath = ROOT\ + its "dest"), one at a time, in that order, backup-state.json last. Then list ROOT again into WORK/final.json, stage those same files (devicePath ROOT\ + "dest") into WORK/staged-commit.json, and run:
   python3 -I dys-market/tools/backup_pack.py confirm --out WORK/out --dest-listing WORK/final.json --staged WORK/staged-commit.json
   Its last output line is your report line (it starts with "DYS backup OK:", "DYS backup HELD:" or "DYS backup FAILED:").

9. Report. Your final reply is one or two lines and starts with exactly one of:
   "DYS backup OK:" (confirm's line), "DYS backup HELD:" (confirm's line), or "DYS backup FAILED:" then what failed.
   For HELD or FAILED, or an OK line that contains "WARNINGS", also tell Keo: send the same line with PushNotification if you have that tool, and with SendUserMessage. For a plain OK with no warnings, send no notification.

---

## What each outcome means
- **OK**: every copied file was read back from Skibidi and matched its SHA-256; zips, tars and git bundles opened and held what they should; then the record was saved (in `state-history\` and `backup-state.json`).
- **OK with a warning about a state copy**: one of the two record copies didn't land; the other did, so the run counts.
- **HELD**: GitHub's data looks wiped or much smaller; nothing copied, both weekly copies untouched.
- **FAILED**: something didn't copy or didn't match. Nothing is recorded. The newest good weekly copy was never touched (each run only writes the other slot), and the next run redoes the work.
- **FAILED: blocked**: a case the script won't decide alone (unreadable or unknown record, incomplete folder listing, a file that would be overwritten). Nothing copied.
- **"monthly copy YYYY-MM is listed … NOT rebuilt"**: an old record lists that month but its file is missing or damaged. It is reported each run. Making a replacement needs Keo's OK and only works during that month (`--recover-month`); the replacement is named `...-recovered-DATE.zip`.

## Restoring
Use the slot named in `backup-state.json` → `newest_slot` (or the newest intact file in `state-history\`). That slot's `FILE-LIST.txt` lists every file with its SHA-256. Pieces named `.part01`, `.part02`… are joined in order. Files in a slot that are not in its FILE-LIST.txt are left over from an earlier run and can be ignored.
