import sqlite3


def connect_db(db_path):
    """Otvara konekciju ka Weimar SQLite bazi."""
    return sqlite3.connect(db_path)


def find_melid_by_title(conn, title_substring):
    """
    Pronalazi melid (ID sola) na osnovu dela naziva pesme.
    Korisno kad ne znas tacan melid, samo naziv pesme (npr. 'Just Friends').
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT melid, title, performer, instrument
        FROM solo_info
        WHERE title LIKE ?
    """, (f"%{title_substring}%",))
    return cursor.fetchall()


def get_melody_events(conn, melid):
    """
    Vraca sve note (melody events) za dati melid, sortirane po eventid
    (koji je vec inkrementalan po vremenu nastanka note).
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT eventid, onset, pitch, duration
        FROM melody
        WHERE melid = ?
        ORDER BY eventid
    """, (melid,))
    return cursor.fetchall()


def get_phrase_sections(conn, melid):
    """
    Vraca zvanicne PHRASE granice za dati solo (melid) iz sections tabele.
    start/end su indeksi NOTA relativno u okviru sola (0-indeksirano po
    redosledu), NE apsolutni eventid iz melody tabele - treba se mapirati.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT start, end, value
        FROM sections
        WHERE melid = ? AND type = 'PHRASE'
        ORDER BY start
    """, (melid,))
    return cursor.fetchall()


def print_phrases_with_pitches(conn, melid):
    """
    Ispisuje zvanicne fraze sa njihovim pitch nizovima - da mozes vizuelno
    da uporedis sa onim sto je nas rest_threshold kod pronalazio.
    """
    events = get_melody_events(conn, melid)
    pitches = [round(e[2]) for e in events]  # pitch je REAL (frakciono), zaokruzujemo

    phrases = get_phrase_sections(conn, melid)

    print(f"Melid {melid}: {len(events)} nota ukupno, {len(phrases)} zvanicnih fraza\n")

    for i, (start, end, value) in enumerate(phrases):
        # start/end su indeksi note unutar sola (0-indeksirano), NE eventid
        phrase_pitches = pitches[start:end+1]  # end je inkluzivan
        print(f"Fraza {value} (note {start}-{end}, {len(phrase_pitches)} nota): {phrase_pitches}")


if __name__ == "__main__":
    db_path = r"C:\Users\nikol\Desktop\jazzdialog\data_midi\wjazzd.db"  # prilagodi putanju gde si sacuvala .db fajl
    conn = connect_db(db_path)

    # prvo pronadji tacan melid za pesmu koja te zanima
    matches = find_melid_by_title(conn, "Just Friends")
    print("Pronadjeni solo-i sa 'Just Friends' u naslovu:")
    for melid, title, performer, instrument in matches:
        print(f"  melid={melid}: {title} - {performer} ({instrument})")
    print()

    # kad znas tacan melid (npr. iz gornje liste), ispisi njegove fraze:
    print_phrases_with_pitches(conn, melid=71)

    conn.close()