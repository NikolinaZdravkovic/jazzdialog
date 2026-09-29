import pretty_midi
from dtaidistance import dtw
from pathlib import Path


def _dtw_norm(a, b):
    distance, paths = dtw.warping_paths(a, b)
    best_path = dtw.best_path(paths)
    return distance / len(best_path)


def incipit_similarity(call_pitches, response_pitches, k=4):
    call_start = call_pitches[:k]
    response_start = response_pitches[:k]
    if len(call_start) < 2 or len(response_start) < 2:
        return 0.0
    absolute_score = _dtw_norm(call_start, response_start)
    call_shape = [p - call_start[0] for p in call_start]
    response_shape = [p - response_start[0] for p in response_start]
    shape_score = _dtw_norm(call_shape, response_shape)
    return min(absolute_score, shape_score)


def load_solo_pitches(midi_path):
    """Ucitava ceo solo kao prostu listu (pitch, start_time, end_time) - jedan niz, bez segmentacije."""
    pm = pretty_midi.PrettyMIDI(midi_path)
    notes = sorted(pm.instruments[0].notes, key=lambda n: n.start)
    return notes


def search_call_response_pairs(notes, min_len=4, max_len=16, max_gap=3,
                                 alpha=0.5, incipit_k=4, top_n=10):
    """
    Klizi kroz ceo solo trazeci najbolje call-response parove.

    min_len, max_len: dozvoljena duzina (u notama) i za call i za response
    max_gap: maksimalan broj nota izmedju kraja call-a i pocetka response-a
             (0 = response pocinje odmah posle call-a, bez ijedne note izmedju)
    top_n: koliko najboljih (ne-preklapajucih) parova da vrati

    Vraca listu (call_start, call_end, response_start, response_end, skor),
    sortiranu od najboljeg ka najgorem.
    """
    pitches = [n.pitch for n in notes]
    n = len(pitches)
    candidates = []

    for call_start in range(n):
        for call_len in range(min_len, max_len + 1):
            call_end = call_start + call_len
            if call_end > n:
                break
            call_seq = pitches[call_start:call_end]

            for gap in range(0, max_gap + 1):
                resp_start = call_end + gap
                for resp_len in range(min_len, max_len + 1):
                    resp_end = resp_start + resp_len
                    if resp_end > n:
                        break
                    resp_seq = pitches[resp_start:resp_end]

                    global_score = _dtw_norm(call_seq, resp_seq)
                    inc_score = incipit_similarity(call_seq, resp_seq, k=incipit_k)
                    combined = alpha * global_score + (1 - alpha) * inc_score

                    candidates.append((call_start, call_end, resp_start, resp_end, combined))

    # sortiraj od najboljeg (najmanjeg skora) ka najgorem
    candidates.sort(key=lambda c: c[4])

    # ukloni preklapajuce kandidate (non-max suppression) - zadrzi samo najbolje
    # ne-preklapajuce parove, redom
    selected = []
    used_ranges = []

    def overlaps(a_start, a_end, b_start, b_end):
        return not (a_end <= b_start or b_end <= a_start)

    for cand in candidates:
        call_start, call_end, resp_start, resp_end, score = cand
        conflict = False
        for (used_start, used_end) in used_ranges:
            if overlaps(call_start, resp_end, used_start, used_end):
                conflict = True
                break
        if not conflict:
            selected.append(cand)
            used_ranges.append((call_start, resp_end))
        if len(selected) >= top_n:
            break

    return selected


def sliding_fixed_window_search(notes, window_size=8, gap=0, alpha=0.5, incipit_k=4, top_n=10):
    """
    Efikasnija pretraga: FIKSNA duzina prozora (call i response iste duzine)
    i FIKSAN razmak izmedju njih. Klizi pozicijom kroz ceo solo - O(n) umesto
    O(n^2 * duzina^2) kao kod pune pretrage svih kombinacija.

    window_size: broj nota u call-u (isti broj se koristi i za response)
    gap: broj nota izmedju kraja call-a i pocetka response-a (0 = odmah posle)
    top_n: koliko najboljih ne-preklapajucih parova da vrati
    """
    pitches = [n.pitch for n in notes]
    n = len(pitches)
    candidates = []

    last_call_start = n - (2 * window_size + gap)

    for call_start in range(last_call_start + 1):
        call_end = call_start + window_size
        resp_start = call_end + gap
        resp_end = resp_start + window_size

        call_seq = pitches[call_start:call_end]
        resp_seq = pitches[resp_start:resp_end]

        global_score = _dtw_norm(call_seq, resp_seq)
        inc_score = incipit_similarity(call_seq, resp_seq, k=incipit_k)
        combined = alpha * global_score + (1 - alpha) * inc_score

        candidates.append((call_start, call_end, resp_start, resp_end, combined))

    candidates.sort(key=lambda c: c[4])

    selected = []
    used_ranges = []

    def overlaps(a_start, a_end, b_start, b_end):
        return not (a_end <= b_start or b_end <= a_start)

    for cand in candidates:
        call_start, call_end, resp_start, resp_end, score = cand
        conflict = any(overlaps(call_start, resp_end, us, ue) for (us, ue) in used_ranges)
        if not conflict:
            selected.append(cand)
            used_ranges.append((call_start, resp_end))
        if len(selected) >= top_n:
            break

    return selected


if __name__ == "__main__":
    midi_path = Path(__file__).resolve().parents[1] / "data_midi" / "solo72.mid"
    notes = load_solo_pitches(midi_path)
    pitches = [n.pitch for n in notes]

    print(f"Ukupno nota u solu: {len(pitches)}\n")

    # brza verzija: fiksna duzina prozora (~2 takta = probaj 8 nota za pocetak,
    # prilagodi na osnovu tvog tempa/ritma) i fiksan razmak (0 = odmah posle)
    results = sliding_fixed_window_search(
        notes, window_size=8, gap=0, alpha=0.5, incipit_k=4, top_n=10
    )

    print(f"Top {len(results)} kandidata za call-response parove:\n")
    for i, (cs, ce, rs, re, score) in enumerate(results):
        call_seq = pitches[cs:ce]
        resp_seq = pitches[rs:re]
        print(f"#{i+1} skor={score:.4f}")
        print(f"  CALL     (note {cs}-{ce}):  {call_seq}")
        print(f"  RESPONSE (note {rs}-{re}):  {resp_seq}")
        print()
