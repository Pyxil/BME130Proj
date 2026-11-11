# Validation of the pronunciation scoring

This document records **what was measured, on what data, and what it does not
show**. Re-run everything with the commands at the end; numbers below come
from `docs/validation_results.json`.

## Signal analysis (default engine)

The default engine compares the recording with standard recordings (see
[architecture.md](architecture.md#signal-analysis-speech_analysissignal_analysis)). There are no
recordings of real learners in this repository yet, so it was calibrated and validated on **generated
voices that are never used as standards**: Piper speakers other than the standards and the fixtures,
with random speaking rate (0.85-1.25x) and voice variation, 0.3 s of room noise around each word.
Every practice word was generated correctly (675 recordings: 3 US and 2 British
voices x 135 words) and with mistakes (948 recordings) of two kinds:

* **covered** - mistakes that have a minimal-pair standard: a common consonant substitution
  (/w/ for /r/, /th/ for /s/ ...), a common confusion of the stressed vowel, a dropped cluster
  consonant or final consonant;
* **uncovered** - mistakes without one (/k/ for /t/ and similar, a dropped weak syllable).

The 0-100 mappings are anchored on the correct recordings (median -> 95, worst 10% -> 85); the
minimal-pair threshold is set so that 5% of correct recordings raise a false alarm. Everything else
below is measured, not fitted. Rerun: `python scripts/calibrate_signal.py` (about 30 minutes).

| Question | Answer (unseen generated voices) |
|---|---|
| Is a recording closest to its own word, out of all 135? | **78%** first choice, 90% in the top 3 |
| Do correct recordings score higher than covered mistakes? | **AUC 0.74** |
| ... than uncovered mistakes? | AUC 0.59 |
| How often is a covered mistake named at the right sound? | 43% of mistaken recordings |
| How often is a mistake wrongly named on a correct recording? | 5% (by design) |
| Ratings of correct recordings | mastered 68%, satisfactory 27%, needs practice 5% |
| Ratings of mistaken recordings | mastered 38%, satisfactory 40%, needs practice 22% |

| Mistake type | n | median score | AUC vs. correct | named | worst part = mistake's part |
|---|---|---|---|---|---|
| cluster reduction (covered) | 52 | 76.5 | 0.79 | 60% | 40% |
| consonant substitution (covered) | 232 | 87 | 0.71 | 38% | 25% |
| final consonant deletion (covered) | 150 | 69 | 0.89 | 67% | 35% |
| other consonant substitution (uncovered) | 208 | 91 | 0.56 | 4% | 24% |
| vowel change (covered) | 270 | 89 | 0.66 | 30% | 5% |
| weak syllable deletion (uncovered) | 36 | 85 | 0.78 | 8% | 75% |

What this shows and does not show:

* Template matching tells words apart well from the waveform alone, and catches dropped sounds and
  common substitutions, especially with minimal-pair standards (vowel changes: AUC 0.52 before vowel
  minimal pairs were added, 0.66 after).
* It is **lenient**: 38% of mistaken recordings are still rated "mastered", because
  two different voices saying the same word differ more, as waveforms, than one voice saying it right and
  wrong. Mistakes outside the minimal-pair list are mostly missed.
* Generated voices are cleaner and more alike than real people, microphones and rooms: expect lower
  numbers on real speech. A per-syllable penalty in word identification made no meaningful difference
  (78% with it, 79% without).
* Not clinically validated; no children with speech-sound disorders.

## Optional phoneme model (Allosaurus)

The results below are for the optional neural phoneme engine (`dev.py setup --ml`, `SA_ENGINE=allosaurus`).

### Summary

| Question | Answer (held-out data) |
|---|---|
| Does a low sound score mean experts heard an error? | Mispronunciation detection **AUC 0.913** (2,149 clearly wrong phones vs. phones all experts accepted) |
| How well do sound scores track expert ratings? | Pearson **r = 0.473** (47,369 phones), mean absolute error 8.7 points on 0-100 |
| How well do word scores track expert ratings? | Pearson **r = 0.476** (15,967 words), MAE 8.4 points; word-level AUC 0.863 |
| How precise is a "poor" sound (< 70)? | Experts judged **35%** of them wrong; this band catches 40% of all expert-flagged errors |
| How precise is a "not good" sound (< 85)? | 20% judged wrong; catches **75%** of expert-flagged errors |
| Is it clinically validated? | **No.** No clinical population, no speech-language pathologist ratings, no children with speech-sound disorders. |

For context: published systems trained specifically on speechocean762 reach
phone-level correlations of roughly 0.45-0.65 (e.g. GOPT, 2022). Our engine is
not trained on this corpus; only a monotone calibration is fitted.

## Data

**speechocean762** (Zhang et al., Interspeech 2021; CC BY 4.0): 5,000 English
sentences read by 250 non-native speakers (Mandarin L1; adults and children),
each phone rated 0-2 by five experts and averaged (2 = correct, 1 = heavy
accent, 0 = wrong or missing). We use the official split: calibration is fitted
on 1,500 train utterances (28,277 phones), and every number above is from the
2,500 **test** utterances, which were never used for fitting.

Limitations of this data for our use case:
- Read sentences, not isolated words (the app scores isolated words).
- Non-native adult/child speakers with one L1; no clinical speech-sound disorders.
- Experts are lenient: 86% of phones are rated fully correct, so only a minority
  of low-scoring phones are expert-judged errors (see precision above).

## Method

1. The Allosaurus English model (`eng2102`) produces CTC phone posteriors.
2. For each canonical phone we compute the substitution/deletion-aware GOP
   posterior (see [architecture.md](architecture.md#phoneme-level-gop)).
3. **Phone calibration:** per-phone isotonic curves (log posterior -> mean expert
   score x 50), shrunk toward a global curve by the number of expert-flagged
   errors for that phone (`speech_analysis/calibration/fit.py`).
4. **Word calibration:** isotonic curve from `mean - sum(max(0, 85 - phone score))`
   to the expert word accuracy (0-10 x 10). The 85 threshold and unit penalty
   were chosen on the train split (train r = 0.543; robust across settings 0.53-0.54).

| Variant (test split) | Phone r | Word r | AUC |
|---|---|---|---|
| Raw posterior | 0.355 | 0.325 (mean) | 0.908 |
| Log posterior | 0.444 | 0.409 (mean log) | 0.908 |
| Global calibration | 0.446 | - | - |
| **Per-phone + word calibration (deployed)** | **0.473** | **0.476** | **0.913** |

### Experiments that did not help (kept for the record)

- **PocketSphinx GOP** (HMM-GMM, bundled with the `pocketsphinx` wheel): forced-alignment
  scores alone did not separate correct from wrong productions, and the free-choice
  likelihood ratio picked wrong phones even for correct TTS speech (e.g. /k/ heard as /p/).
  Rejected as the phoneme judge; see [ADR 0001](adr/0001-phoneme-engine.md).
- **"Confident competitor" feature:** we expected errors with a single strong alternative
  (e.g. /w/ for /r/) to be more precise. On real speech the opposite held: with
  posterior < 0.05, P(expert error) was 24% overall but 18% when the competitor
  probability was >= 0.95. Adding competitor and deletion probabilities to a linear
  model improved phone r only from 0.477 to 0.482 (2-fold CV on train). Not deployed.
- **Energy-based syllable counting** (de Jong & Wempe style, vowel band): exact on
  only 6/13 synthetic fixtures; fluent unstressed syllables merge. Kept as weak
  supporting evidence (30% of the syllable component, +/-1 tolerance).

### Per-phone reliability (train split, AUC wrong vs. correct)

Strong (AUC >= 0.95): CH, EY, SH, W, Y, V, NG, M, F, G, IY, DH.
Weaker: L 0.86, TH 0.85, AA 0.81, unstressed/stressed AH 0.73. The per-phone
calibration makes scores for unreliable phones more lenient automatically.
Known model limitation: Allosaurus works on 8 kHz features, so cues above 4 kHz
(important for /s/ vs. /θ/) are weakened.

## Pipeline behaviour on controlled recordings

`speech_analysis/tests/test_pipeline_fixtures.py` runs the full pipeline on
committed synthetic recordings (Piper TTS with controlled phoneme errors):

| Recording | Result |
|---|---|
| rabbit / "wabbit" (r->w) | 100 / 80; /r/ flagged "may have sounded more like /w/" |
| leaf / "weaf" (l->w) | 93 / 89 (capped: not every sound good); /l/ flagged as /w/ |
| butterfly / "batterfly" (vowel) | 97 / 89 (capped); /ʌ/ flagged as /ɛ/ |
| spoon / "poon" (cluster reduction) | 96 / 86; /s/ flagged |
| banana / "nana" (syllable dropped) | 95 / 77; /b/ and syllable flagged |
| British "butterfly", British "tomato" | matched the RP / alternate variant, 88 / 90 |
| silence, too quiet, clipped, noisy, cut off | all rejected with a specific re-record message |

End-to-end in a real browser (Playwright, fake microphone feeding the real recorder, `e2e/practice-flow.cjs`),
two runs with different planned words: "road" 99 (mastered) and "mirror" with r->w 69 (needs practice);
"orange" 97 (mastered) and "giraffe" with r->w 78 (satisfactory). The /r/ -> /w/ substitution was flagged
in both error cases.

**Caveat:** synthetic speech tests behaviour, not accuracy on real people.

## Acoustic similarity (DTW)

Calibrated on synthetic held-out TTS speakers (`scripts/calibrate_dtw.py`):
same-word cost 0.498 vs. different-word 0.644, 92.6% pair classification. The
fitted logistic slope was widened (scale 0.020 -> 0.05) because real voices
compared with TTS references are expected to cost more. This component is not
validated on real speech; it carries 20% weight by design.

## What would make this stronger

1. Ratings of real users' isolated words by speech-language pathologists (with consent).
2. Children with speech-sound disorders and other L1 backgrounds.
3. Evaluate the experimental wav2vec2 engine (16 kHz, larger model) with the same script.
4. A learned regressor on GOP features (GOPT-style) trained on the train split.

## Reproduce

```bash
git clone --depth 1 https://github.com/jimbozhang/speechocean762 /data/so762
python scripts/evaluate_speechocean762.py --data /data/so762 --split train --limit 1500 --save-raw train.npz
python scripts/evaluate_speechocean762.py --data /data/so762 --split test --save-raw test.npz --report docs/validation_results.json
python scripts/fit_calibration.py --train train.npz --test test.npz \
    --out speech_analysis/calibration/allosaurus-eng2102.json --report docs/validation_results.json
pytest -m model   # fixture behaviour
```
