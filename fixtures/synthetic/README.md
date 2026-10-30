# Synthetic fixtures

Everything in this folder is synthetic test data made with ffmpeg's built-in test
sources (a colour test pattern and a sine tone). None of it is a real shop, product or
person, and it is never presented as real.

| File | What it is | Used by |
| --- | --- | --- |
| `synthetic-test-pattern.mp4` | 2 s, 180 × 320 test pattern with a 660 Hz tone | Web end-to-end upload test |
| `synthetic-sprite.png` | 320 × 220 transparent shoe-like shape drawn with OpenCV | Engine tests and the builder tests |
| `synthetic-photo.jpg` | 480 × 480 square picture with that shape, for the puzzle | Engine tests and the builder tests |
| `synthetic-strip.png` | 960 × 160 strip of six frames: a blue box with a white band turning, drawn with OpenCV | Engine tests of the moving product (feature 7) |
