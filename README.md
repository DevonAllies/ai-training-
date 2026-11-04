# SimCoach – iRacing training with Garage 61

> **Also in this repository:** [DataLab Trainer](datalab_trainer/README.md), a hands-on training app for data analysis and data science in SQL, Python and R (import → clean → EDA → modelling → SHAP → report writing) that runs natively on Windows and Ubuntu.

SimCoach is a local app for the PC that runs iRacing. It:

- **Reads live iRacing telemetry** at 60 Hz and shows a **live delta** against a reference lap. It also shows whether you're losing or gaining time right now, your predicted lap time, and speed and pedal inputs compared with the reference.
- **Coaches you corner by corner while you drive.** After each corner you get feedback such as *"C3 +0.21s – braking 17 m too early, apex speed 8 km/h slower"*.
- **Connects to Garage 61** and lists laps from **you, your teammates and drivers you follow** for the car and track you're on. Any of them can be your live reference or used in an analysis.
- **Analyses laps after the session.** It shows delta, speed, throttle and brake traces, a track map coloured red where you lose time and green where you gain it, and a corner table. The table compares brake point, apex speed, exit speed, full-throttle point and coasting, and gives ranked coaching tips.
- **Shows an in-game overlay while you practise.** A small always-on-top window over iRacing tells you, corner by corner, whether you **braked too early**, **carried too little minimum speed**, **turned in too late** or **got on the throttle late**. It also shows a *brake in 120 m → BRAKE* cue at the reference braking point, your live delta, and sector deltas.
- **Imports Garage 61 session exports (.xlsx).** It shows best and theoretical-best laps, consistency, and how much time each sector costs you. Your best sectors become live sector targets for the same car and track.
- **Voice coach that doesn't nag.** Before each corner it speaks *one* short reminder based on what you did there last lap (*"C3, brake later"*), and tells you when you've fixed it. There's an optional detailed mode that also says the time lost or gained.
- **Technique grades (0–100)** for braking, turn-in, trail braking, minimum speed and throttle, plus overall pace, for every lap.
- **Corner drill mode.** The coach picks the corner where you lose the most time and focuses all feedback on it. It moves on once you're within the target for 3 laps in a row.
- **Session report.** Covers every lap you've driven: average and best time lost per corner, consistency, the mistake you repeat most in each corner, technique trends, and how much time is available by repeating your *own* best corners.
- **Records every clean lap** you drive to `%APPDATA%\SimCoach\laps`, so you can compare against your own past laps too.

Everything runs on your PC. The dashboard is a local web page at `http://127.0.0.1:8061`.

## Install (Windows)

**SimCoach is a single, self-contained app.** The installer contains everything: the Python runtime, every library, the dashboard, the overlay and the voice coach. You don't install Python or anything else, and an internet connection is only needed for Garage 61 and updates.

1. Open the repository's **Releases** page on GitHub and download **`SimCoach-Setup-x.y.z.exe`**.
2. Run it. No admin rights are needed. You can choose a desktop shortcut and *Start with Windows*.
3. SimCoach starts in the **system tray** (next to the clock), opens the dashboard in your browser, and shows the overlay over iRacing in practice sessions.
   - Right-click the tray icon to open the dashboard, change overlay or voice mode, check for updates, or quit.
   - Clicking the shortcut again while it's running just reopens the dashboard.
4. To uninstall, go to Windows **Settings → Apps → SimCoach**. Your laps, settings and imports in `%APPDATA%\SimCoach` are kept.

Windows SmartScreen may warn you because the installer isn't code-signed. Click **More info → Run anyway**.

Also available:
- **Portable zip** (`SimCoach-portable-x.y.z.zip`): unzip anywhere and run `SimCoach.exe`.
- **Start Menu → SimCoach demo**: try everything without iRacing. To leave the demo, click **Exit demo & use iRacing** in the yellow banner, or just start the normal **SimCoach** shortcut, which closes the demo and starts live mode.

### Automatic updates

SimCoach keeps itself up to date from this repository's GitHub Releases:

1. It checks shortly after starting and then every 6 hours. You can also use **Settings → Updates → Check now** or the tray menu.
2. It downloads the new installer in the background and **verifies its SHA-256 checksum** against the one published with the release. If there's no checksum or it doesn't match, it won't install.
3. It **installs silently and restarts itself**, but never while you're on track. It waits until you're back in the garage or iRacing is closed.

Modes in **Settings → Updates**:

| Mode | What it does |
| --- | --- |
| *Install automatically when I'm not driving* | Default |
| *Download, then ask me* | Shows an "Install & restart" banner in the dashboard |
| *Off* | Never checks for updates |

Your laps and settings are kept across updates.

**From source (developers)**

Install Python 3.10+ (tick "Add python.exe to PATH"), then run `install.bat` once and `run.bat` to start. `build_exe.bat` builds `SimCoach.exe`, and the installer too if [Inno Setup 6](https://jrsoftware.org/isinfo.php) is installed.

**Second screen:** drag the dashboard to another monitor and press **F11** for full screen. To use a **tablet or phone** next to your rig:

1. Switch on **Settings → Tablet / phone → Allow my tablet/phone on my home network** and click **Restart now**.
2. Scan the **QR code** with the tablet's camera, or type the address shown.

Devices on your network can use the coaching screens, but only this PC can change settings, quit or delete anything. Windows may ask once whether to allow SimCoach on networks; allow **private** networks only.

### Releases (maintainers)

Every push runs **tests on Linux and Windows**, builds `SimCoach.exe` with PyInstaller, smoke-tests it, and builds the installer with Inno Setup.

To publish a release, which every installed copy then auto-updates to:

1. Bump `__version__` in `simcoach/__init__.py` and `pyproject.toml`, then merge to `main`.
2. On GitHub, go to **Actions → Build → Run workflow**, choose branch `main`, tick **Publish a GitHub Release**, and click **Run**.

Alternatively, push a tag `vX.Y.Z`. Either way, the workflow creates the release with the installer, portable zip and `SHA256SUMS.txt` attached.

## Connect Garage 61

1. On garage61.net, go to **Settings → Developer** and create a **personal access token** with the `driving_data` permission.
2. In SimCoach, open **Settings**, paste the token, click **Save**, then **Test connection**.

The token is stored only on your PC in `%APPDATA%\SimCoach\config.json`. You can also set the `GARAGE61_TOKEN` environment variable instead.

**Garage 61 limitations**

- The Garage 61 API only returns laps from yourself, your teammates and drivers you follow. There is no global lap search. To compare with someone fast, join a team with them or follow them on Garage 61. You can also add their Garage 61 slug under *Extra drivers*.
- Viewing other drivers' telemetry needs a **Garage 61 Pro** plan.

## In-game overlay

The overlay starts with SimCoach. By default it only appears when you are **on track in a practice, testing or warm-up session**. You can change this in Settings to *Always* or *Off*.

- Run iRacing in **borderless windowed** mode (Options → Graphics → untick *Fullscreen*). Windows can't draw any overlay on top of exclusive fullscreen.
- **Drag** the overlay to move it, use the **mouse wheel** to resize it, and **right-click** for options (practice only / always / hide, bigger or smaller, quit). Position and size are remembered.
- What it shows:
  - **Delta** to your reference lap, and *LOSING / GAINING x.xx s here*
  - **Brake cue**: a bar that fills as you approach the reference braking point, then turns red with *BRAKE*
  - **Corner feedback** as it happens. Brake *x m too early* or *later*, Turn-in *x m too late* or *early*, Min speed *x km/h too slow*, and Throttle *x m late*. Red means fix it, amber is worth a look, green is on target.
  - **Sector chips**: each sector against your target (imported Garage 61 best sectors, or your session best)
- **Browser version:** `http://127.0.0.1:8061/overlay`. Use it as an OBS *Browser source*, on a second monitor, or on a tablet (start with `--host 0.0.0.0`). Add `?always=1` to show it outside practice too.

All feedback is measured against your reference lap, which must have telemetry: a Garage 61 lap, one of your recorded laps, or your session best. Turn-in is detected from steering angle, at 30% of the reference driver's peak steering in that corner.

## Optimal lap

**Laps → Build my optimal lap** takes your best version of every corner from all your clean laps on the track, plus imported teammate laps if you want, and stitches them into one reference lap with full telemetry.

- The lap is cut on the straights between corners, where you're flat out, so the joins are smooth.
- It shows how much faster this composite is than your best single lap. That's time you've already driven, just not all in one lap.
- **Build & use as reference** chases it straight away.

## Racing line and car control

iRacing doesn't send GPS (Lat/Lon) in live telemetry; it only writes it into `.ibt` files. So SimCoach rebuilds the line of every lap you drive from heading, speed and slip angle, closes it into a loop and fits it onto the reference line. In tests this is accurate to about half a metre. Laps recorded before 0.8 have no line. Teammate `.ibt` files have real GPS.

On **Analyse**, the **racing line** card compares your line with the reference using the GPS position iRacing records:

- **Offset chart:** how far left or right of the reference line you are all round the lap.
- **Line map:** both lines drawn together. Click a corner in the table to zoom in, with a 20 m scale bar.
- **Per corner:** wide or tight at turn-in, apex and exit, for example *"2.4 m wide at the apex – get closer to the inside kerb"*.

The **car-control** analysis compares you with the reference at the same place on track, so it needs no car settings:

| Check | How it's detected |
| --- | --- |
| **Oversteer** | Opposite lock where the reference had none |
| **Understeer** | More steering lock than the reference for the same or less rotation (yaw rate) |
| **Wheelspin on exit** | RPM above the gear's normal RPM-to-speed ratio |
| **ABS** | Metres with ABS working in the braking zone, against the reference |
| **Busy steering** | Extra steering corrections |
| **Gears** | Gear at the apex, and short-shifting (upshift RPM against the reference) |

Results appear as badges in the corner table and as tips. *Racing line* and *Car control* are also added to the technique grades.

## Progress and practice plans

Every session is saved, per car and track. The **Progress** tab shows:

- your best lap per session, against your personal best so far
- technique grades over time
- problems that keep coming back, such as *"T5: Braking too early (3 sessions)"*
- corners that have improved

**Make my practice plan** builds a plan for your next session that fits the time you have (30–90 min): warm-up, drills on your two costliest corners with a target and a focus cue, your weakest technique, a consistency run, and push laps against your optimal lap.

## Voice coach

The default **Full coach** mode calls what happens as you drive, in a few words, at about 5–8 short calls per lap:

- **Braking:** *"Brake later, 15 metres"* and *"Brake harder"* (peak brake pressure)
- **Turn-in:** *"Turn in earlier"* or *"Turn in later"*
- **Trail braking:** *"Trail the brake deeper"* when you come off the brake before turning in
- **Apex speed and throttle:** *"Carry more speed"*, *"Throttle earlier"*

It also gives a reminder before each corner based on last lap (*"T5, brake later"*) and praises a fixed mistake (*"Good trail"*). During a drill it only talks about the drill corner.

Prefer it quieter? **Settings → Voice** offers *Braking, turn-in & trail braking* only, *Quiet* (one reminder per corner) or *Off*.

## Drills

Drills (Live tab) work on one corner. The coach picks the right drill for your most common mistake there, or you choose one:

| Drill | For | Goal |
| --- | --- | --- |
| **Brake-point ladder** | braking too early | Brake 5 m later each lap until you reach the reference; if you overshoot, the last good point is locked in and you hit it twice |
| **Trail braking** | coming off the brake before turning in | Stay on the brake into the turn like the reference |
| **Turn-in point** | turning in early or late, line | Turn in within 5 m of the reference |
| **Minimum speed** | over-slowing, understeer | Apex speed within 2 km/h |
| **Throttle pick-up** | late throttle, wheelspin, slow exits | Full throttle as early as the reference, no wheelspin |
| **Consistency** | slides, busy steering | 3 laps in a row within 0.08 s of each other |
| **Match the reference** | everything else | Within the target of the reference, 3 laps in a row |

Every attempt is judged on that drill's own measure, logged on the drill card, shown on the overlay (including the brake-point target during the ladder) and called by voice.

## Consistency trainer

The Live tab's **Consistency trainer** is for race pace: the same lap, every lap.

1. **Set it up.** Choose a window (for example ±0.3 s) and a goal (for example 10 laps in a row). Enter a target lap, or leave it empty and the trainer sets it from your pace after 3 laps.
2. **Every lap** lands **inside** or **outside** the window. The overlay shows the streak, and the voice calls *"In the window, 7 in a row"* or *"Outside, plus 0.6. T3 cost 0.4"*.
3. **When a lap falls out**, the trainer compares it with *your own usual lap*, not the reference, and names the corner and the habit that changed. For example: *"T3 cost 0.55 s – braked 13 m earlier than usual"*.
4. **Results:** a consistency **score** (0–100), your best streak and lap-time spread. They're saved per session, so they appear in Progress.
5. **The track map** shows where you're inconsistent: red is a corner that varies more than your typical corner, green is steadier.
6. **From the plan:** the practice plan's *Consistency run* starts the trainer with one click and ticks itself off when you reach the goal.


**Faster laps count** (race pace; on by default):
- A lap quicker than the window keeps the streak going; the voice says "faster, still counts".
- With fuel saving on, a faster lap counts only if it also hit the fuel target. If you burned extra fuel to go faster, the streak breaks and the trainer says how much you were over.
- Three faster laps in a row move the target down to your new pace.
- Untick **Faster laps count** for the strict two-sided window.

## Weekly training goal and streak

At the top of the **Progress** tab you can set a weekly goal: **minutes on track** (default 3 hours), **sessions** or **laps** per week.

- **This week:** shows your progress so far, what's left and the days remaining. The voice calls *"Weekly goal reached. 4 week streak"* when you hit it.
- **Streak:** the number of weeks in a row with the goal met, plus your best streak. The week you're in never breaks it until it's over.
- **Last 8 weeks:** a chart against the goal line, and a small *"Week 1h 20m / 3h · streak 3"* chip on the Live tab.

Time on track is measured live (pit lane and pauses don't count).

## Training hub on your phone

Open **`/train`** on your phone (Settings → Tablet / phone; the QR code opens the training hub by default). From the phone you can:

- **Pick what you train:** practice plan, corner drill (choose the corner and drill, or let the coach pick), consistency run (window and laps in a row), fuel saving (+1 lap or 0.1 L per lap), or free driving. Starting one stops the others.
- **See what's running:** the active quest, drill streak, consistency streak or fuel laps on target.
- **Switch training features on or off.** Other settings, quit, restart and delete stay limited to the PC.

## Widgets

Small single-purpose pages for a phone, tablet, second monitor or OBS browser source:

| Widget | Shows |
|---|---|
| `/widget/plan` | The practice plan as a quest path, with XP, combo, daily challenge and badges |
| `/widget/consistency` | Streak ring, target ± window, a dot per lap, score and spread |
| `/widget/endurance` | Fuel, laps of fuel, laps to go, fuel to finish, stops, pit window, stint pace |
| `/widget/fuel` | Fuel-save target per lap and which laps hit it |
| `/widget/racecraft` | Cars around you, faster-car warning, clean passes / let-bys / defending, incidents |

Add `?transparent=1` for OBS, or `?readonly=1` to hide the buttons.

## Teammate race prep (multi-lap .ibt)

When a teammate sends you the `.ibt` of a stint or a whole race, upload it on the **Race tab → Teammate race prep**. You can also choose **Build race prep** after uploading it on the Laps tab. SimCoach analyses every lap in the file:

- **Race pace:** typical lap (median of clean laps within 3 % of the best), best lap, and consistency.
- **Stints:** split at pit stops, with laps, average and pace drop-off (tyres) for each.
- **Fuel:** fuel per lap (median of clean laps), its range, and fuel per stint.
- **Fuel-saving lap:** their most fuel-efficient clean lap, what it saved, and what it cost against their race pace. It also shows *where* they lift and coast: per corner, how many metres earlier they come off the throttle than on their fastest lap, and how far they coast to the brakes. Each braking zone is the one nearest that corner's apex (never the previous corner's), and corners use the track's corner names.

Then you can:

- **Use in endurance planner:** fills in their race pace and fuel per lap. "Fill from teammate prep" in the planner does the same.
- **Fuel training: match their fuel-save lap:** **LIFT** is cued at the points where your teammate actually lifted on that lap (track positions from their file), before your own braking point for each corner. The target is their fuel per lap on that lap.
- **Fuel training: match their typical fuel per lap:** same target idea, but the lift points are estimated from your own lap.
- **Fuel-save lap as my reference:** your live delta runs against their fuel-saving lap, so you learn to save fuel without losing more time than they did.
- **Their fastest lap as my reference.**

The fuel figures need the file's `FuelLevel` channel, which iRacing records by default. The newest 20 preps are kept in the `preps` folder.

## Race mode and race report

In race sessions SimCoach switches the training off: no corner calls, brake cues, drills, consistency trainer or game pop-ups. You keep the delta, fuel, fuel-save lift cues and faster-car warnings. Race mode is on by default; switch it off in Settings to keep training on in races. In races the overlay only shows if the overlay is set to **Always** (the default is practice only), and then as the stripped race version.

It also records a **race report**. Open it from the Race tab or the phone training page (`/race-report`). It updates live during the race and can be printed or saved as PDF. It covers:

- **Result:** start and finish position, overall and in class, plus your position on every lap.
- **Pace and consistency:** best and typical lap, spread, the share of laps within 0.5 s of your typical lap, and the laps more than 1 s off.
- **Stints:** laps, average and best, pace drop-off per lap (tyre wear; mistakes are left out of the trend) and fuel per lap.
- **Tyres:** wear and carcass temperatures for each corner of the car, and wear per lap per stint. iRacing only sends tyre data while you're stopped in your pit stall, so this needs a pit stop; without one, the pace drop-off stands in for tyre wear.
- **Fuel:** per lap, total, fuel left (spare-fuel advice only once the chequered flag is out), and fuel-save laps on target.
- **Racecraft:** score, clean passes and let-bys, defending, incidents, traffic cost, and every move.
- **Key takeaways** written from all of the above.

The newest 50 race reports are kept in the `races` folder.

## Racecraft: clean passes and good racing

This works with real traffic: races, iRacing AI races (great for practising traffic) and open practice. SimCoach reads every car's position on track, its class, the spotter's left/right flag and your incident count.

- **Clean pass:**
  - A car close to you goes from ahead to behind and stays there for 3 s.
  - It's clean if you got no new incident points and didn't go off track in the 5 s before or 3 s after.
  - It also shows what the pass cost you, compared with *your usual time over that stretch* (median of your recent clean laps).
- **Lapping a slower class:** counts as clean if it cost you less than 0.3 s.
- **Clean let-by:** a faster class goes past you with no incident and costs you under 0.5 s. If it costs more, the tip is: hold your line and lift a little on the straight.
- **Defending:** a same-class car stays within 0.6 s behind you for 20 s and doesn't get by.
- **Battles:** swapping places with the same car again and again within 30 s counts as one battle, not many passes.
- **Faster-car warning:** a faster class closing within 3 s. It gives the gap and the corner where it will catch you ("FASTER GTP 2.9s · AT C3"), so you can plan where to let it by. It appears in the in-game window and the browser overlay, and is spoken.
- **Contact:** incident points during a battle count as contact, and contact breaks your game combo.
- **Racecraft score (0–100):** the share of clean moves, minus 4 points per incident point.
- **Traffic time:** what laps in traffic cost you compared with your clean laps.
- **Widget:** `/widget/racecraft` shows the gap bar around you (purple = faster class), the nearby cars, your counts and the last moves.

XP: clean pass 30, clean let-by 15, defended 20 (all with the combo multiplier). Badges: Clean racer, Good neighbour, Iron wall. Spoken calls follow the voice coach's "practice only" setting, so switch that off to hear them in races.

Ghost cars aren't used: SimCoach can't put cars on the iRacing track, so it only coaches real traffic.

## Training game

Training is repetitive on purpose, so SimCoach keeps score:

- **XP:**
  - clean lap: 10
  - new session best: 25
  - beating your reference: 60
  - drill attempt on target: 6
  - finished drill: 50
  - finished practice-plan step ("quest"): 40
  - finished whole plan ("boss"): +150
  - lap inside the consistency window: 8
  - fuel-save lap on target: 15
  - weekly goal: 200
- **Combo:** hits in a row multiply XP: x2 from 3, x3 from 6, x4 from 10. A miss resets it.
- **Levels:** Rookie → Club Racer → … → Alien.
- **Daily challenge:** one task a day, worth +75 XP.
- **14 badges:** for example Late braker (finish a brake ladder), Robot (10 consistent laps in a row), Fuel whisperer.
- **Where it shows:** the in-game browser overlay shows your level, combo and XP pops. The voice announces level-ups, badges and the daily challenge.
- **Storage:** progress is kept in `game.json` in the SimCoach folder.

## Training features on/off

**Settings → Training features** (or the phone's training hub) switches each part on or off: live corner feedback, the overlay brake cue, sector times, corner drills, the consistency trainer, race/endurance/fuel saving, progress/practice plan, weekly goal and the training game. A switched-off feature disappears from the dashboard, overlay and voice. The voice coach has its own setting.

## Session report and practice plan

- **Printable report** (Live tab → Session report, or Progress tab). One page with:
  - laps, best lap, gap and grades
  - a summary
  - the **top three problem corners**, each with speed, pedal and line traces and the tips
  - recurring problems
  - the practice plan, with tick boxes
- **Print / Save as PDF** prints it or saves a PDF. **Download** saves a self-contained HTML file to share with a coach or teammate.
- **Practice plan** (Progress tab). Every corner step has a **Start drill** button that starts the right drill on that corner. The step is **ticked off automatically** when you complete the drill on track, and the voice announces the next step. *Push laps* builds your optimal lap and sets it as the reference in one click.

## Race, endurance and fuel saving

The **Race** tab is for longer races.

**Live stint**
- fuel left, fuel per lap and laps of fuel in the tank
- laps to go (lap or timed races), fuel needed to finish, stops needed and the **pit window**
- stint pace, the lap-time trend within the stint (s/lap), and consistency

**Endurance planner**
- Fill it in one click from:
  - **Live session:** time left (or laps left), fuel in the tank, tank size, your current pace and fuel per lap.
  - **Garage 61:** race pace and fuel per lap from *your* laps, or your team's, in this car at this track. Race pace is the median of clean laps within 3 % of the best, not your single fastest lap, because that's what you'll actually average over a stint.
  - **Imported session:** the same figures from a Garage 61 Excel export, which includes fuel used per lap.
- With **Fuel in tank now** filled, it plans **from now**: the first stint is what's in the tank, then full stints to the flag. It also shows the fuel needed and the margin at the flag.
- You get the number of stops, laps per stint and fuel per stop.
- It also shows what saving fuel buys you: one stop fewer, or an extra lap per tank, with the **time cost against the time saved in the pits**.

**Fuel saving – an extra lap without losing time**
- **Save for one extra lap**, or enter litres per lap to save. SimCoach plans **lift-and-coast** points: the braking zones where lifting early saves the most fuel for the least time.
- It's worked out from your own lap: your brake points, your fuel flow at full throttle, and your car's coast-down, fitted to the parts of the lap where you were off both pedals.
- While it's on, the overlay shows **LIFT** instead of the brake cue, and the voice coach calls *"T1, lift 50 metres early"*.

All fuel-saving figures are estimates and are labelled as such.

## Teammate lap files

You can use a teammate's lap as your reference without Garage 61. They send you a file, and you upload it on the **Laps** tab:

1. Your teammate turns on telemetry logging in iRacing (**Alt+L** in the car, or permanently in the options) and drives.
2. They send you the session's **`.ibt`** file from `Documents\iRacing\telemetry\`.
3. Drop it on **Laps → Teammate lap files**. SimCoach finds every lap in it, fastest clean lap first, and reads the driver, car and track.
4. Click **Use as my reference**. The lap is also saved under *Saved laps*, so you can pick it again later.

Also accepted: a **Garage 61 lap CSV export** (enter the lap time if the file has no time column) or a **SimCoach lap file**.

iRacing's **`.blap` / `.olap`** ghost files can't be used. They're a private format that isn't publicly documented, and guessing it could give you a wrong reference. The `.ibt` file contains the same lap plus full telemetry (speed, pedals, steering, gear, GPS).

## Corner numbers and names

iRacing and Garage 61 telemetry contain no turn numbers or names, so SimCoach finds corners itself, as **C1, C2…** in the order of the lap's slow points. To use the real names:

1. Open the **Corners** tab and pick a lap on that track. The live reference is the default.
2. For each detected corner, type the official **turn number** and **name**. The track map and speed trace highlight the corner you're editing.
   - For a chicane, enter a combined number like `4-5`.
   - Leave a corner blank to keep its C-number.
3. Click **Save names**.

From then on that track shows **T5 · Tertre Rouge** everywhere: overlay, live feedback, corner summaries, session report and drill mode. The voice coach says *"Tertre Rouge, brake later"*.

Some details:
- The map is saved per track in `%APPDATA%\SimCoach\corners\` and works for every car and reference lap.
- Garage 61 and iRacing spellings of a track name are matched automatically.
- Use **Export** / **Import** to share corner maps, for example with teammates.

## Garage 61 session exports

In Garage 61, open a session or event and choose **Export → Excel**. Then open SimCoach's **Sessions** tab and import the `.xlsx`. Exports in `sample_data/` are imported automatically on first start. That folder includes your IMSA race at Le Mans in the Dallara P217.

The export contains lap and sector times, not per-meter telemetry. From it SimCoach calculates:

- your best lap and theoretical best (your best sectors added together)
- your average lap and how consistent you were
- per sector: your best, your average, the average time lost against your best, and how much your laps varied there
- which sectors to focus on

Slow outliers are left out using the 107% rule, along with in-laps, out-laps and unclean laps. The best sectors become live targets in the overlay automatically when you drive the same car and track.

Example from the included export (race, 9 laps used): the best lap is 3:38.637 and the theoretical best is 3:37.833. **Sector 7** (0.37 s per lap on average) and **sector 1** (0.32 s) are where most time is left.

## How to train with it

1. Start iRacing and SimCoach, and go out on track.
2. Open **Garage 61 laps** and click **Match current session**. This selects your car and track. Click **Search**.
3. On the lap you want to chase, click **Set as live reference**. Faster laps are usually a better target than the very fastest alien.
4. Drive. Watch the delta and the *"Losing time here"* indicator, and read the corner feedback in the pits.
5. After a run, open **Analyse** and compare *Last lap* or a saved lap with the reference. Work on the **Focus on** corners first. These are the three corners where you lose the most time.

If no reference is selected, SimCoach uses your session best as the reference.

## Design notes

- **Local and private.** Telemetry, laps and settings stay on your PC. No account, no subscription, no upload. Garage 61 is only contacted to fetch laps you ask for.
- **Your data and your team's.** References can be your own laps, your session best, or laps from Garage 61 teammates and drivers you follow, not only stock "pro" laps.
- **Explains why, not only where.** Each corner is broken down into brake point, brake pressure, turn-in, trail braking, minimum speed, coasting, throttle pick-up and exit speed. The tips are ranked by time lost.
- **Coaches the next attempt, not the last one.** Feedback is timed for when you can act on it: a cue before the corner and a summary after it.
- **Light on your rig.** The live engine uses about 2% of one CPU core at 60 Hz. All session history is held in fixed-size buffers, so memory stays flat over long stints. An automated soak test checks this.

SimCoach is an independent project. All code is original and it isn't affiliated with any other coaching product.

## How the comparison works

- Each lap is resampled onto 1000 points over lap distance, so laps line up exactly by track position.
- The time delta at each point is your elapsed time minus the reference's elapsed time at the same track position.
- Garage 61 CSV exports may not include a time column. In that case the time comes from integrating the speed trace, and it is scaled to the official lap time.
- Corners are found from speed minima on the reference lap and are named C1, C2… in order. These may not match official turn numbers. Each corner runs from the top speed before it to the top speed after it, and time on the start/finish straight is credited to the last corner's exit.
- For each corner, SimCoach compares:
  - brake point (first brake application)
  - peak brake pressure
  - minimum speed
  - full-throttle point
  - coasting distance
  - exit speed

  It then turns the differences into tips, ranked by time lost.

## Development

```bash
pip install -r requirements.txt pytest httpx
python -m simcoach --demo        # run with the simulated driver (practice session)
python -m simcoach --import export.xlsx   # import a Garage 61 export from the command line
python -m pytest tests           # run tests
```

| File | Purpose |
| --- | --- |
| `simcoach/garage61.py` | Garage 61 API client (`https://garage61.net/api/v1`, Bearer token) |
| `simcoach/lap.py` | Lap model, resampling, CSV import/export |
| `simcoach/analysis.py` | Corner detection, delta, coaching tips |
| `simcoach/live.py` | iRacing telemetry (pyirsdk), live lap builder, live delta, corner phase events, sectors |
| `simcoach/coach.py` | Session report, corner drill, voice cue logic |
| `simcoach/voice.py` | Text-to-speech output (Windows SAPI via pyttsx3) + browser voice log |
| `simcoach/overlay.py` | Native always-on-top overlay window (tkinter) |
| `simcoach/sessions.py` | Garage 61 Excel export import and sector analysis |
| `simcoach/server.py` | FastAPI REST API + WebSocket stream |
| `simcoach/ibt.py` | iRacing .ibt telemetry reader (teammate lap files) |
| `simcoach/control.py` | Racing line (GPS) and car-control analysis |
| `simcoach/optimal.py` | Optimal lap from your best corners |
| `simcoach/history.py` | Session history, progress, practice plans |
| `simcoach/race.py` | Stints, fuel, endurance planner, lift-and-coast planner |
| `simcoach/corners.py` | Per-track corner numbers/names (corner maps) |
| `simcoach/lan.py` | Tablet/phone access on the home network (QR code, settings guard) |
| `simcoach/consistency.py` | Consistency trainer (window, streak, why a lap fell out, score) |
| `simcoach/goals.py` | Weekly training goal and streak |
| `simcoach/drills.py` | Drill library (brake ladder, trail braking, turn-in, apex speed, throttle, consistency) |
| `simcoach/static/report.html` | Printable post-session report |
| `simcoach/updater.py` | Auto-update from GitHub Releases (checksum-verified, silent install) |
| `simcoach/tray.py` / `autostart.py` | System-tray icon, *Start with Windows* |
| `packaging/` | PyInstaller spec, Inno Setup installer script, icon |
| `.github/workflows/build.yml` | CI: tests, Windows build, installer, releases |
| `simcoach/static/` | Dashboard UI (no external dependencies, works offline) |
