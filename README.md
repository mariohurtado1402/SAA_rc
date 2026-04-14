# SAA_rc — Raspberry Pi ESC control

Control a Hobbywing XR10 ESC (17.5T motor, slowest profile) from a Raspberry Pi 4
using only the **signal** and **ground** wires of the ESC receiver lead.

## Wiring

| ESC wire                    | Pi connection            |
| --------------------------- | ------------------------ |
| Signal (white / yellow)     | GPIO18 — physical pin 12 |
| Ground (black / brown)      | GND    — physical pin 6  |
| Red / BEC (5 V)             | **Leave disconnected**   |

Do not connect the ESC's red BEC wire to the Pi 5 V rail — it can back-feed the
Pi and cause ground-loop or brown-out issues. The Pi must be powered from its
own supply; the ESC is powered from the car battery.

Common ground between the ESC and the Pi is mandatory, which is why the black
wire still goes to a Pi GND pin.

## Why `pigpio`

The XR10 expects a standard RC servo signal: 50 Hz pulses between 1000 µs
(full reverse) and 2000 µs (full forward), with 1500 µs = neutral.

`pigpio` generates those pulses with hardware-timed DMA, so there is no jitter.
Software PWM from `RPi.GPIO` jitters enough to make the ESC twitch or disarm —
do not use it for ESCs.

## Install

On the Raspberry Pi (Raspberry Pi OS):

```bash
sudo apt update
sudo apt install pigpio python3-pigpio
sudo systemctl enable --now pigpiod
```

Then, from the project directory:

```bash
python3 main.py
```

## Arming

When `main.py` starts it sends 1500 µs (neutral) for 3 seconds. The ESC will
beep through its startup sequence and then arm. Keep the wheels off the ground
the first time you run it.

## Controls

| Key     | Action                          |
| ------- | ------------------------------- |
| `w`     | Throttle +5 %                   |
| `s`     | Throttle −5 %                   |
| space   | Stop (return to neutral)        |
| `q`     | Quit (sends neutral, then stops)|

Throttle is clamped to ±100 %. Because the ESC is in its slowest profile, full
stick (±100 %) is already throttle-limited at the ESC — the Pi still sends the
full 1000–2000 µs range.

## Pulse mapping

| Throttle | Pulse width |
| -------- | ----------- |
| −100 %   | 1000 µs     |
|    0 %   | 1500 µs     |
| +100 %   | 2000 µs     |

## First test

1. Car on a stand, wheels off the ground.
2. Run `python3 main.py`, wait for "ESC armed."
3. Press `w` once (+5 %). Wheels should spin forward slowly.
4. Press space to stop, `q` to quit.

If the wheels spin the wrong direction, swap any two of the three motor phase
wires between the ESC and the motor, or change the direction setting in the
ESC's programming card / LCD program box.

## Troubleshooting

- **"Cannot connect to pigpiod"** — run `sudo systemctl start pigpiod`.
- **Motor never spins, ESC keeps beeping** — the ESC did not arm. Confirm
  signal is on GPIO18 and grounds are common, then restart the script so it
  re-sends the 3 s neutral arming pulse.
- **Motor twitches at rest** — usually a ground issue or software PWM; make
  sure you are using `pigpio` (this project does) and that the ESC ground is
  connected to a Pi GND pin.
- **Runs backwards** — swap two motor phase wires, or invert direction in the
  ESC profile.
