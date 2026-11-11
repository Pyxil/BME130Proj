"""Signals-and-systems pronunciation analysis: compare a recording's waveform features with standards.

No speech-recognition model is involved: the recording and each standard pass
through the same signal-processing front end (:mod:`.dsp`, :mod:`.features`),
are aligned with dynamic time warping, and compared measure by measure
(:mod:`.compare`). :mod:`.standards` holds the standard recordings and ranks
all practice words for a recording (word identification).
"""
