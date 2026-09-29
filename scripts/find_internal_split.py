from dtaidistance import dtw
from pathlib import Path
try:
    import numpy as np
except ImportError:  # Zadrzi rad u minimalnom okruzenju bez NumPy-ja.
    np = None
try:
    from .segment_phrases import segment_by_rests, phrase_to_pitch_sequence, phrase_to_interval_sequence
except ImportError:
    from segment_phrases import segment_by_rests, phrase_to_pitch_sequence, phrase_to_interval_sequence


def _dtw_norm(a, b):
    """DTW distanca podeljena stvarnom duzinom najbolje warping putanje."""
    # C implementacija iz dtaidistance vraca isti put kao referentna verzija,
    # ali je bitno brza kada se pregleda cela WJD baza. Fallback cuva staro
    # ponasanje ako C/NumPy varijanta nije dostupna.
    if np is not None and hasattr(dtw, "warping_paths_fast"):
        distance, paths = dtw.warping_paths_fast(
            np.asarray(a, dtype=np.double), np.asarray(b, dtype=np.double)
        )
    else:
        distance, paths = dtw.warping_paths(a, b)
    best_path = dtw.best_path(paths)
    return distance / len(best_path)


def incipit_similarity(call_pitches, response_pitches, k=3):
    """
    Meri koliko su slicni POCECI call-a i response-a (prvih k nota).
    Uzima bolji rezultat apsolutnog i transponovanog poredjenja.
    """
    call_start = call_pitches[:k]
    response_start = response_pitches[:k]

    if len(call_start) < 2 or len(response_start) < 2:
        return 0.0

    absolute_score = _dtw_norm(call_start, response_start)

    call_shape = [pitch - call_start[0] for pitch in call_start]
    response_shape = [pitch - response_start[0] for pitch in response_start]
    shape_score = _dtw_norm(call_shape, response_shape)

    return min(absolute_score, shape_score)


def _find_best_pitch_split(pitches, min_segment_len=3, incipit_k=3, alpha=0.5):
    """Osnovna logika za WJD frazu predstavljenu listom pitch vrednosti."""
    n = len(pitches)
    best_split = None
    best_score = float("inf")
    results = []

    for split_point in range(min_segment_len, n - min_segment_len + 1):
        call_pitches = pitches[:split_point]
        response_pitches = pitches[split_point:]

        global_score = _dtw_norm(call_pitches, response_pitches)
        incipit_score = incipit_similarity(call_pitches, response_pitches, k=incipit_k)
        combined = alpha * global_score + (1 - alpha) * incipit_score

        results.append((split_point, combined))
        if combined < best_score:
            best_score = combined
            best_split = split_point

    return best_split, best_score, results


def find_best_internal_split(phrase, use_intervals=False, min_segment_len=3,
                               incipit_k=3, alpha=0.5):
    """
    Proba sve moguce podele fraze na dva dela (call, response) i
    vraca tacku podele sa najmanjim kombinovanim skorom.
    """
    # WJD fraze su proste liste int/float pitch vrednosti. Za njih koristimo
    # tacno osnovnu logiku iznad: jedna podela, CALL + RESPONSE = cela fraza.
    if not phrase or isinstance(phrase[0], (int, float)):
        return _find_best_pitch_split(
            list(phrase), min_segment_len=min_segment_len,
            incipit_k=incipit_k, alpha=alpha
        )

    # Zadrzana je kompatibilnost sa starim pretty_midi note objektima.
    if use_intervals:
        full_sequence = phrase_to_interval_sequence(phrase)
    else:
        full_sequence = phrase_to_pitch_sequence(phrase)

    full_pitches = phrase_to_pitch_sequence(phrase)

    n = len(full_sequence)
    best_split = None
    best_score = float("inf")
    results = []

    for split_point in range(min_segment_len, n - min_segment_len + 1):
        left = full_sequence[:split_point]
        right = full_sequence[split_point:]

        distance, paths = dtw.warping_paths(left, right)
        best_path = dtw.best_path(paths)
        global_score = distance / len(best_path)

        pitch_split = split_point + 1 if use_intervals else split_point
        call_pitches = full_pitches[:pitch_split]
        response_pitches = full_pitches[pitch_split:]

        incipit_score = incipit_similarity(call_pitches, response_pitches, k=incipit_k)

        combined = alpha * global_score + (1 - alpha) * incipit_score

        results.append((split_point, global_score, incipit_score, combined))

        if combined < best_score:
            best_score = combined
            best_split = split_point

    return best_split, best_score, results


def analyze_phrase(phrase, phrase_number=None, use_intervals=False, incipit_k=3, alpha=0.5, show_all=False):
    """
    Analizira jednu frazu i ispisuje najbolju call-response podelu.
    show_all=True prikazuje skorove za sve tacke podele (za detaljniju proveru).
    """
    pitches = phrase_to_pitch_sequence(phrase)
    label = f"Fraza {phrase_number}" if phrase_number is not None else "Fraza"

    print(f"{label} ({len(pitches)} nota): {pitches}")

    best_split, best_score, all_results = find_best_internal_split(
        phrase, use_intervals=use_intervals, incipit_k=incipit_k, alpha=alpha
    )

    call_part = phrase[:best_split]
    response_part = phrase[best_split:]

    print(f"  -> Podela nakon note {best_split} (skor: {best_score:.4f})")
    print(f"  CALL:     {phrase_to_pitch_sequence(call_part)}")
    print(f"  RESPONSE: {phrase_to_pitch_sequence(response_part)}")

    if show_all:
        print("  Svi skorovi po tacki podele:")
        for split_point, g, inc, combined in all_results:
            marker = " <-- najbolja" if split_point == best_split else ""
            print(f"    posle note {split_point}: {combined:.4f}{marker}")

    print()
    return best_split, best_score


if __name__ == "__main__":
    midi_path = Path(__file__).resolve().parents[1] / "data_midi" / "solo72.mid"
    phrases = segment_by_rests(midi_path, rest_threshold=0.3)

    # promeni broj ovde da testiras drugu frazu, ili napravi petlju za sve odjednom
    analyze_phrase(phrases[5], phrase_number=5,show_all=True)
