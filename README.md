# SlimSynth
Small form Arduino/python controlled waveform generator and synthesizer.
# OSCILLOSCOPE-9000 Synth Workstation

## Overview

This project combines an Arduino-based hardware controller with a Python-based software synthesizer to create a vintage-styled frequency visualization and sound generation system. The interface mimics the aesthetic of 1980s CRT oscilloscopes with phosphor green displays, while providing modern synthesis capabilities including multiple waveforms and real-time audio effects processing.

## How It Works

### Hardware Component (Arduino)

The Arduino acts as a simple serial data transmitter that reads two physical inputs:

1. **Potentiometer**: Connected to analog pin A0, this controls the frequency sweep speed. The analog value (0-1023) is mapped to determine how quickly the synthesizer sweeps through its frequency range from 100Hz to 2000Hz.

2. **Button**: Connected to digital pin 2 with internal pull-up resistor, this cycles through eight available waveforms each time it's pressed. The Arduino implements basic debouncing with a 200ms delay.

The Arduino continuously performs a frequency sweep, incrementing the current frequency by an amount determined by the potentiometer reading. When the frequency reaches 2000Hz, it resets to 100Hz and begins again. Data is transmitted over serial at 115200 baud every 20 milliseconds, formatted as comma-separated values: frequency, potentiometer value, and current waveform type.

### Software Component (Python)

The Python application consists of three main subsystems: serial communication, audio synthesis, and visual display.

#### Serial Communication

The application auto-detects Arduino ports by scanning for devices with common Arduino identifiers in their descriptions. Once connected, it continuously reads incoming serial data, parsing the comma-separated values to update the synthesizer's state. The high baud rate of 115200 ensures minimal latency between hardware input and audio/visual output.

#### Audio Synthesis Engine

Audio generation happens in real-time through a callback function that runs in a separate thread managed by the sounddevice library. This callback is invoked continuously to fill audio buffers with samples.

**Waveform Generation**: The synthesizer supports eight base waveforms, each generated mathematically:
- Sawtooth and ramp waves use modulo arithmetic to create linear rise/fall patterns
- Sine waves use standard trigonometric functions
- Square and pulse waves use sign functions and phase comparisons
- Triangle waves use absolute value transformations
- PWM (Pulse Width Modulation) uses an LFO to modulate duty cycle
- White noise uses random number generation

**Frequency Smoothing**: Rather than jumping instantly to new frequencies, the system uses exponential smoothing where the current frequency gradually approaches the target frequency. This prevents audio clicks and creates smooth pitch transitions.

**Effects Chain**: Audio passes through a series of effects processors in a specific order designed to maximize sound quality:

1. **Harmonics**: Adds overtones at integer multiples of the fundamental frequency, creating richer timbres
2. **Ring Modulator**: Multiplies the signal with a modulating oscillator for metallic, bell-like tones
3. **Distortion**: Uses multi-stage waveshaping with smooth saturation curves and sine-based wavefolding to create warm, musical distortion with a characteristic "wub-wub" quality at higher settings
4. **Tremolo**: Applies amplitude modulation using an LFO to create rhythmic volume variations
5. **Phaser**: Implements comb filtering with time-varying delay for sweeping notch effects
6. **Chorus**: Uses modulated delay lines to create the illusion of multiple voices
7. **Delay**: Tape-style echo with feedback for rhythmic repetitions
8. **Reverb**: Implements multiple comb filters at prime-number delays to simulate room acoustics
9. **Bit Crushing**: Reduces bit depth to create lo-fi digital artifacts
10. **Low-Pass Filter**: Simple one-pole filter for smoothing high frequencies

Each effect can be controlled independently via keyboard, with uppercase letters increasing effect intensity and lowercase decreasing it.

#### Visual Display System

The matplotlib-based interface provides three synchronized panels:

**Spectrogram Panel**: The main display shows frequency over time as the sweep progresses. The visualization uses multiple overlaid traces with decreasing opacity to create a phosphor-glow effect characteristic of CRT displays. Horizontal scanlines are drawn at regular frequency intervals to enhance the vintage aesthetic. The display uses a deque (double-ended queue) with a maximum length of 800 samples, automatically discarding old data to maintain smooth scrolling.

**Waveform Panel**: Shows three cycles of the current waveform in the time domain. This panel generates a fresh waveform snapshot on each frame based on the current frequency and waveform type, providing real-time visualization of the selected waveform shape.

**Effects Rack Panel**: Displays all effect parameters in a two-column layout with color-coded categories. Parameters are shown as horizontal bar graphs using filled and unfilled block characters, with numeric values displayed alongside. The color scheme uses amber for modulation effects, cyan for time-based effects, magenta for pitch and amplitude effects, red for tone shaping, and green for output volume.

#### Technical Implementation Details

**Buffer Management**: Effects that require history (chorus, delay, reverb) use circular buffers to store past samples efficiently. Buffer indices wrap around using modulo arithmetic, eliminating the need for array shifting.

**Phase Continuity**: To prevent audio clicks, the main oscillator maintains phase continuity across buffer boundaries. The phase accumulator increments with each sample and wraps at the sample rate, ensuring smooth waveform generation even when buffers are refilled.

**Animation Loop**: The matplotlib animation system calls an update function approximately every 30 milliseconds. This function reads all available serial data, updates internal state, clears all three display panels, and redraws them with current data. This refresh rate provides smooth visual updates without excessive CPU usage.

**Keyboard Event Handling**: matplotlib's event system captures key presses and routes them to effect parameter updates. The system disables default matplotlib keybindings that would conflict with effect controls, allowing keys like 'q' and 'f' to be repurposed while still maintaining fullscreen toggle functionality.

## Design Philosophy

The project balances vintage aesthetics with modern functionality. The visual design deliberately mimics the constraints and appearance of 1980s test equipment, using monospaced fonts, limited color palettes, and CRT-style glow effects. However, the audio synthesis uses contemporary DSP techniques to achieve professional-quality sound.

The effects chain ordering follows standard audio engineering practices, placing harmonic generation and modulation effects before saturation, and time-based effects after distortion. This ensures natural-sounding results and prevents unwanted artifacts.

The distortion algorithm specifically uses multi-stage soft saturation rather than hard clipping to maintain musicality even at extreme settings. The wavefolding technique creates complex harmonics through smooth waveshaping rather than harsh limiting, producing the characteristic "wub" sound of bass synthesis without the harshness of simple clipping distortion.
