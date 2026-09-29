import pretty_midi
from pathlib import Path

def segment_by_rests(midi_path, rest_threshold=0.3):
    """
    Deli solo na fraze na osnovu pauza duzih od rest_threshold sekundi.
    Vraca listu fraza, gde je svaka fraza lista nota (pitch, start, end, velocity).
    """
    pm = pretty_midi.PrettyMIDI(midi_path)
    notes = pm.instruments[0].notes  # pretpostavka: jedan instrument (kao kod solo71)
    notes = sorted(notes, key=lambda n: n.start)

    phrases = []
    current_phrase = [notes[0]]

    for i in range(1, len(notes)):
        gap = notes[i].start - notes[i-1].end
        if gap > rest_threshold:
            # nova fraza pocinje
            phrases.append(current_phrase)
            current_phrase = [notes[i]]
        else:
            current_phrase.append(notes[i])

    phrases.append(current_phrase)  # dodaj poslednju frazu
    return phrases


def phrase_to_pitch_sequence(phrase):
    """Izvlaci niz pitch-eva iz fraze (za DTW poredjenje)."""
    return [note.pitch for note in phrase]


def phrase_to_interval_sequence(phrase):
    """Izvlaci niz intervala (razlika izmedju uzastopnih pitch-eva)."""
    pitches = phrase_to_pitch_sequence(phrase)
    return [pitches[i+1] - pitches[i] for i in range(len(pitches)-1)]


if __name__ == "__main__":
    midi_path = Path(__file__).resolve().parents[1] / "data_midi" / "solo72.mid"
    phrases = segment_by_rests(midi_path, rest_threshold=0.3)

    print(f"Broj pronadjenih fraza: {len(phrases)}\n")

    for i, phrase in enumerate(phrases):
        pitches = phrase_to_pitch_sequence(phrase)
        start_time = phrase[0].start
        end_time = phrase[-1].end
        print(f"Fraza {i}: {len(phrase)} nota, {start_time:.2f}s - {end_time:.2f}s")
        print(f"  Pitch niz: {pitches}")
