/**
 * Reel2Play's own sound effects (feature 21), synthesized at play time with Web Audio.
 * There are no audio files and nothing licensed from anyone else; the shop's own music is
 * never reused. Sound starts only after the player's first tap, as browsers require.
 */

export type SfxName = "tap" | "catch" | "miss" | "jump" | "coin" | "swap" | "bump" | "win" | "end";

interface Tone {
  wave: OscillatorType;
  from: number;
  to: number;
  seconds: number;
  gain: number;
  delay?: number;
}

const RECIPES: Record<SfxName, Tone[]> = {
  tap: [{ wave: "triangle", from: 660, to: 880, seconds: 0.06, gain: 0.18 }],
  catch: [
    { wave: "sine", from: 740, to: 1180, seconds: 0.09, gain: 0.22 },
    { wave: "triangle", from: 1180, to: 1480, seconds: 0.08, gain: 0.12, delay: 0.05 },
  ],
  miss: [{ wave: "sawtooth", from: 220, to: 120, seconds: 0.18, gain: 0.12 }],
  jump: [{ wave: "square", from: 300, to: 620, seconds: 0.14, gain: 0.08 }],
  coin: [
    { wave: "square", from: 990, to: 990, seconds: 0.05, gain: 0.07 },
    { wave: "square", from: 1320, to: 1320, seconds: 0.12, gain: 0.07, delay: 0.05 },
  ],
  swap: [{ wave: "triangle", from: 520, to: 400, seconds: 0.08, gain: 0.16 }],
  bump: [{ wave: "sawtooth", from: 160, to: 70, seconds: 0.16, gain: 0.16 }],
  win: [
    { wave: "triangle", from: 523, to: 523, seconds: 0.12, gain: 0.2 },
    { wave: "triangle", from: 659, to: 659, seconds: 0.12, gain: 0.2, delay: 0.12 },
    { wave: "triangle", from: 784, to: 784, seconds: 0.12, gain: 0.2, delay: 0.24 },
    { wave: "triangle", from: 1047, to: 1047, seconds: 0.3, gain: 0.22, delay: 0.36 },
  ],
  end: [
    { wave: "sine", from: 440, to: 440, seconds: 0.14, gain: 0.16 },
    { wave: "sine", from: 349, to: 349, seconds: 0.26, gain: 0.16, delay: 0.14 },
  ],
};

export function recipe(name: SfxName): readonly Tone[] {
  return RECIPES[name];
}

export class Sfx {
  private context: AudioContext | null = null;
  muted = false;
  /** Called for every sound, heard or not, so the page can caption it (feature 23). */
  onSound: ((name: SfxName) => void) | null = null;

  /** Call from a pointer handler: browsers only allow audio after a user gesture. */
  unlock(): void {
    if (this.context || typeof AudioContext === "undefined") return;
    try {
      this.context = new AudioContext();
    } catch {
      this.context = null;
    }
  }

  play(name: SfxName): void {
    this.onSound?.(name);
    const context = this.context;
    if (!context || this.muted) return;
    const start = context.currentTime;
    for (const tone of RECIPES[name]) {
      const at = start + (tone.delay ?? 0);
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.type = tone.wave;
      oscillator.frequency.setValueAtTime(tone.from, at);
      oscillator.frequency.exponentialRampToValueAtTime(tone.to, at + tone.seconds);
      gain.gain.setValueAtTime(0.0001, at);
      gain.gain.exponentialRampToValueAtTime(tone.gain, at + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + tone.seconds);
      oscillator.connect(gain).connect(context.destination);
      oscillator.start(at);
      oscillator.stop(at + tone.seconds + 0.02);
    }
  }
}
