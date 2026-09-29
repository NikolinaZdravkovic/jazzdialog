import pretty_midi
from pathlib import Path

midi_path = Path(__file__).resolve().parents[1] / "data_midi" / "solo71.mid"

pm = pretty_midi.PrettyMIDI(midi_path)

print(f"Broj instrumenata: {len(pm.instruments)}")
print(f"Ukupno trajanje: {pm.get_end_time():.2f} sekundi")
print(f"Tempo (estimated): {pm.estimate_tempo():.1f} bpm")

for i, instrument in enumerate(pm.instruments):
    print(f"\n--- Instrument {i}: {instrument.name} ---")
    for note in instrument.notes[:15]:  # prvih 15 nota za pregled
        print(f"Pitch: {note.pitch}, Start: {note.start:.3f}s, End: {note.end:.3f}s, Velocity: {note.velocity}")
