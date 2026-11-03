# SimCoach – iRacing training with Garage 61

SimCoach is a local app for the PC that runs iRacing. It:

- **Reads live iRacing telemetry** at 60 Hz and shows a **live delta** against a reference lap. It also shows whether you're losing or gaining time right now, your predicted lap time, and speed and pedal inputs compared with the reference.
- **Coaches you corner by corner while you drive.** After each corner you get feedback such as *"C3 +0.21s – braking 17 m too early, apex speed 8 km/h slower"*.
- **Connects to Garage 61** and lists laps from **you, your teammates and drivers you follow** for the car and track you're on. Any of them can be your live reference or used in an analysis.
- **Analyses laps after the session.** It shows delta, speed, throttle and brake traces, a track map coloured red where you lose time and green where you gain it, and a corner table. The table compares brake point, apex speed, exit speed, full-throttle point and coasting, and gives ranked coaching tips.
- **Records every clean lap** you drive to `%APPDATA%\SimCoach\laps`, so you can compare against your own past laps too.

Everything runs on your PC. The dashboard is a local web page at `http://127.0.0.1:8061`.

## Install (Windows)

1. Install **Python 3.10 or newer** from python.org and tick **"Add python.exe to PATH"**.
2. Download or clone this repository.
3. Double-click **`install.bat`** (one time only).
4. Double-click **`run.bat`**. The dashboard opens in your browser.

To try it without iRacing, run `run.bat --demo`. A simulated driver laps a demo track against a reference lap.

Optional: `build_exe.bat` builds a standalone `dist\SimCoach\SimCoach.exe` that doesn't need Python installed.

**Tip:** run `run.bat --host 0.0.0.0` to open the dashboard on a tablet or phone next to your rig at `http://<your-pc-ip>:8061`.

## Connect Garage 61

1. On garage61.net, go to **Settings → Developer** and create a **personal access token** with the `driving_data` permission.
2. In SimCoach, open **Settings**, paste the token, click **Save**, then **Test connection**.

The token is stored only on your PC in `%APPDATA%\SimCoach\config.json`. You can also set the `GARAGE61_TOKEN` environment variable instead.

**Garage 61 limitations**

- The Garage 61 API only returns laps from yourself, your teammates and drivers you follow. There is no global lap search. To compare with someone fast, join a team with them or follow them on Garage 61. You can also add their Garage 61 slug under *Extra drivers*.
- Viewing other drivers' telemetry needs a **Garage 61 Pro** plan.

## How to train with it

1. Start iRacing and SimCoach, and go out on track.
2. Open **Garage 61 laps** and click **Match current session**. This selects your car and track. Click **Search**.
3. On the lap you want to chase, click **Set as live reference**. Faster laps are usually a better target than the very fastest alien.
4. Drive. Watch the delta and the *"Losing time here"* indicator, and read the corner feedback in the pits.
5. After a run, open **Analyse** and compare *Last lap* or a saved lap with the reference. Work on the **Focus on** corners first. These are the three corners where you lose the most time.

If no reference is selected, SimCoach uses your session best as the reference.

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
python -m simcoach --demo        # run with the simulated driver
python -m pytest tests           # run tests
```

| File | Purpose |
| --- | --- |
| `simcoach/garage61.py` | Garage 61 API client (`https://garage61.net/api/v1`, Bearer token) |
| `simcoach/lap.py` | Lap model, resampling, CSV import/export |
| `simcoach/analysis.py` | Corner detection, delta, coaching tips |
| `simcoach/live.py` | iRacing telemetry (pyirsdk), live lap builder, live delta and callouts |
| `simcoach/server.py` | FastAPI REST API + WebSocket stream |
| `simcoach/static/` | Dashboard UI (no external dependencies, works offline) |
