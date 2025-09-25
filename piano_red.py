import curses
import threading
import time
import numpy as np
import simpleaudio as sa


NIVEL_DE_SONIDO = 44100

DURACION = 2.0

TECLAS = list("qwertyuiop")

FRECUENCIAS = {
    'q' : 261.63,
    'w' : 293.66,
    'e' : 329.63,
    'r' : 349.23,
    't' : 392.00,
    'y' : 440.00,
    'u' : 466.16,
    'i' : 493.88,
    'o' : 261.63,
    'p' : 293.66,
}

NOTAS_ACTIVAS = {}

def adsr_envolvente(length, sr, attack=0.01, decay=0.1, sustain=0.7, release=0.3):
    ejemplos_totales = int(length * sr)
    env = np.zeros(ejemplos_totales, dtype=np.float32)
    ejemplo_a = int(sr * attack)
    ejemplo_d = int(sr * decay)
    ejemplo_r = int(sr * release)
    sostener_ejemplos = max(0, ejemplos_totales - (ejemplo_a + ejemplo_d + ejemplo_r))

    if ejemplo_a > 0:
        env[:ejemplo_a] = np.linspace(0, 1.0, ejemplo_a, endpoint=False)
        idx = ejemplo_a
    if ejemplo_d > 0:
        env[idx:idx + ejemplo_d] = np.linspace(1.0, sustain, ejemplo_d, endpoint=False)
        idx += ejemplo_d
    if sostener_ejemplos > 0:
        env[idx:idx + sostener_ejemplos] = sustain
        idx += sostener_ejemplos
    if ejemplo_r > 0:
        env[idx:idx + ejemplo_r] = np.linspace(sustain, 0.0, ejemplo_r, endpoint=True)
    return env

def generar_tono(frecuencia, duracion, sr=NIVEL_DE_SONIDO, amplitud=0.6):
    t = np.linspace(0, duracion, int(sr * duracion), False)
    wave = np.sin(2 * np.pi * frecuencia * t)
    wave += 0.25 * np.sin(2 * np.pi * (2*frecuencia) * t)
    wave += 0.12 * np.sin(2 * np.pi * (3*frecuencia) * t)
    wave = wave / np.max(np.abs(wave))
    env = adsr_envolvente(duracion, sr, attack=0.01, decay=0.12, sustain=0.7, release=0.2)
    wave = wave * env * amplitud
    audio = (wave * 32767).astype(np.int16)
    return audio, env

def play_note_thread(key, velocity=1.0):
    if key not in FRECUENCIAS:
        return
    frecuencia = FRECUENCIAS[key]
    duracion = DURACION
    audio, env = generar_tono(frecuencia, duracion, amplitud=0.6 * velocity)
    frame_size = 1024
    n_frames = len(audio) // frame_size
    note_lock = threading.Lock()
    NOTAS_ACTIVAS[key] = {'rms': 0.0, 't': 0.0, 'lock': note_lock}
    play_obj = sa.play_buffer(audio, 1, 2, NIVEL_DE_SONIDO)

    for i in range(n_frames):
        start = i * frame_size
        end = start + frame_size
        frame = audio[start:end].astype(np.float32) / 32767.0
        rms = np.sqrt(np.mean(frame**2))
        note = NOTAS_ACTIVAS.get(key)
        if note:
            with note['lock']:
                note['rms'] = rms
                note['t'] = i * (frame_size / NIVEL_DE_SONIDO)
        time.sleep(frame_size / NIVEL_DE_SONIDO)

    rem = len(audio) % frame_size
    if rem > 0:
        frame = audio[-rem:].astype(np.float32) / 32767.0
        rms = np.sqrt(np.mean(frame**2))
        if note:
            with note['lock']:
                note['rms'] = rms
                note['t'] = duracion

    play_obj.wait_done()
    note = NOTAS_ACTIVAS.get(key)
    if note:
        with note['lock']:
            NOTAS_ACTIVAS.pop(key, None)

def run_curses(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(50)

    if curses.has_colors():
        curses.start_color()
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)

    h, w = stdscr.getmaxyx()
    instructions = "[ Piano de Terminal RED — Teclas para tocar sonidos: " + " ".join(TECLAS) + "  |  ( s para salir ) ]"
    stdscr.addstr(0, 0, instructions[:w-1], curses.color_pair(4))
    last_resize = (h, w)

    try:
        while True:
            ch = stdscr.getch()
            if ch != -1:
                try:
                    key = chr(ch)
                except ValueError:
                    key = None
                if key == 's':
                    break
                if key in TECLAS:
                    t = threading.Thread(target=play_note_thread, args=(key,))
                    t.daemon = True
                    t.start()

            h, w = stdscr.getmaxyx()
            if (h, w) != last_resize:
                stdscr.clear()
                stdscr.addstr(0, 0, instructions[:w-1], curses.color_pair(4))
                last_resize = (h, w)
            base_row = 2
            max_bar_width = max(10, w - 20)
            for idx, k in enumerate(TECLAS):
                row = base_row + idx
                label = f"[{k}]"
                rms = 0.0
                note = NOTAS_ACTIVAS.get(k)
                if note:
                    with note['lock']:
                        rms = note['rms']
                width = int(min(1.0, rms * 6.0) * max_bar_width)
                bar = "█" * width
                spaces = " " * (max_bar_width - width)
                if curses.has_colors():
                    if rms < 0.08:
                        col = curses.color_pair(1)
                    elif rms < 0.18:
                        col = curses.color_pair(2)
                    else:
                        col = curses.color_pair(3)
                else:
                    col = 0

                stdscr.addstr(row, 0, f"{label:3} ", curses.A_BOLD)
                stdscr.addstr(row, 4, bar + spaces, col)
                stdscr.addstr(row, 4 + max_bar_width + 1, f"{rms:.3f}")

            stdscr.refresh()
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass

def main():
    curses.wrapper(run_curses)

if __name__ == "__main__":
    main()