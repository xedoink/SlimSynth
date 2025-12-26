# SlimSynth Workstation

## Technical Overview

SlimSynth is a real-time software synthesizer with hardware control surface, combining an Arduino-based HID (Human Interface Device) controller with a Python DSP (Digital Signal Processing) engine. The system achieves sub-10ms latency through optimized serial communication protocols and lock-free audio buffer management, while presenting data through a vintage CRT-styled matplotlib visualization interface running at 33fps.

![SlimSynth Screenshot](https://github.com/xedoink/SlimSynth/blob/main/SlimSynth%20Screenshot.png)

## Architecture

### Hardware Layer: Arduino Microcontroller

The Arduino firmware operates as a polled I/O interface, sampling analog inputs and transmitting state vectors over UART at 115200 baud (11520 bytes/sec theoretical throughput). The system employs a 20ms polling interval to balance responsiveness with serial bandwidth constraints.

**Joystick Interface**: The analog joystick module provides two independent 10-bit ADC channels (X and Y axes) and one digital input (button with hardware pull-up). The ADC operates at Arduino's native resolution, yielding values in the range [0, 1023]. These are transmitted raw to preserve maximum resolution for subsequent processing on the host.

- **X-Axis (A0)**: Controls frequency sweep velocity. The full ADC range is mapped to sweep rates between 2-100 Hz per iteration cycle.
- **Y-Axis (A1)**: Controls filter cutoff frequency. Mapped non-linearly to the range [0.1, 1.0] representing normalized cutoff values, where 1.0 represents no filtering and lower values progressively attenuate high-frequency content.
- **Button (D2)**: Cycles through eight waveform types using a finite state machine with modulo arithmetic. Implements software debouncing via temporal filtering (200ms lockout period).

**Serial Protocol**: Data is transmitted as ASCII-encoded comma-separated values (CSV format) with newline delimiters: `freq,x_axis,y_axis,waveform\n`. This human-readable format sacrifices bandwidth efficiency for debugging transparency and cross-platform compatibility. Each packet consumes approximately 20-25 bytes including delimiters.

**Timing Characteristics**: The main loop executes with a target period of 5ms, limited by the serial transmission overhead and ADC settling time. Non-blocking serial writes prevent buffer overflow under high-frequency updates.

### Software Layer: Python DSP Engine

The Python application employs a multi-threaded architecture separating I/O, audio synthesis, and visualization into independent execution contexts.

#### Real-Time Audio Thread

Audio generation occurs in an isolated callback thread managed by the PortAudio backend (via sounddevice). This thread operates at elevated priority with minimal latency configurations:

- **Sample Rate**: 44100 Hz (CD quality)
- **Buffer Size**: 1024 samples (23.2ms at 44.1kHz)
- **Bit Depth**: 16-bit signed integer PCM
- **Channels**: Mono (1 channel)

**Phase-Coherent Oscillator**: The primary oscillator maintains phase accumulation across buffer boundaries to ensure continuity. Phase is stored as a floating-point accumulator incremented by `(buffer_size) / sample_rate` per callback, with modulo wrapping to prevent numerical overflow.

**Frequency Smoothing**: Target frequency updates from serial input are smoothed using a first-order IIR (Infinite Impulse Response) low-pass filter:
```
current_freq = current_freq * 0.95 + target_freq * 0.05
```
This exponential smoothing prevents zipper noise and implements a time constant of approximately 20 samples for a 63% rise time.

#### Waveform Synthesis Algorithms

All waveforms are generated through direct mathematical computation in the time domain:

**Sawtooth**: `y(t) = 2 * (t * f - floor(0.5 + t * f))`
- Implements bandlimited synthesis through phase wrapping
- Fundamental plus infinite harmonic series at -6dB/octave

**Triangle**: `y(t) = 2 * |2 * (t * f - floor(t * f + 0.5))| - 1`
- Absolute value transformation of sawtooth
- Odd harmonics only at -12dB/octave

**Square**: `y(t) = sign(sin(2πft))`
- Binary quantization of sine wave
- Odd harmonics at -6dB/octave with Gibbs phenomenon

**PWM**: Variable duty cycle pulse wave with LFO modulation at 0.5 Hz
- Duty cycle: `D(t) = 0.5 + 0.4 * sin(2π * 0.5 * t)`
- Creates spectral movement through time-varying harmonic content

**White Noise**: Uniformly distributed random samples in [-1, 1]
- Flat power spectral density across entire Nyquist bandwidth

#### Digital Signal Processing Chain

Effects are applied sequentially in a fixed-order chain optimized for minimal artifacts:

**1. Harmonic Generator**
Adds phase-locked harmonics at integer multiples of fundamental frequency with amplitude weighting:
```
harmonics = Σ (level * amplitude_n * sin(2π * n * f * t))
where n ∈ {2,3,4,5,6} and amplitude_n = 1/n
```

**2. Ring Modulator**
Implements four-quadrant multiplication with carrier offset:
```
y(t) = x(t) * sin(2π * (f + mod_freq * 100) * t)
```
Creates sum and difference frequencies (f ± fm) for inharmonic timbres.

**3. Waveshaping Distortion**
Multi-stage soft saturation using hyperbolic tangent transfer functions:
- Stage 1: `tanh(x * gain * 0.8)` - Gentle compression
- Stage 2: `tanh(stage1 * 1.2) * 0.9` - Character addition
- Wavefolder (amount > 0.3): `sin(x * π * (1 + fold_intensity))` - Generates subharmonics through wavefolding
- Final stage blends 15% dry signal for transient preservation

**4. Tremolo**
Amplitude modulation via LFO: `y(t) = x(t) * [1 - depth * (0.5 + 0.5 * sin(2π * rate * t))]`

**5. Phaser**
All-pass filter with swept notch implemented via feedforward comb filtering:
```
y[n] = x[n] + depth * x[n - D(t)]
where D(t) varies sinusoidally between 2-10ms
```

**6. Chorus**
Modulated delay line creating pseudo-stereo effect through phase decorrelation. Uses circular buffer with sinusoidal LFO controlling read position offset (2-12ms range).

**7. Delay**
Digital delay line with feedback:
```
y[n] = x[n] * (1 - mix) + buffer[n - delay_samples] * mix
buffer[n] = x[n] + buffer[n - delay_samples] * 0.4
```

**8. Reverb**
Schroeder reverberator using parallel comb filters with prime-number delays (29ms, 37ms, 41ms, 43ms) to minimize modal resonances.

**9. Bit Depth Reduction**
Quantization noise generation: `y = round(x * 2^bits) / 2^bits`
Effective SNR reduction: `SNR_dB ≈ 6.02 * bits + 1.76`

**10. Low-Pass Filter**
First-order recursive filter: `y[n] = α * x[n] + (1-α) * y[n-1]`
Cutoff frequency controlled by coefficient α, modulated in real-time by joystick Y-axis.

#### Serial Communication Protocol

The application implements non-blocking serial I/O with automatic port detection via device descriptor parsing. Connection parameters:
- Baud rate: 115200 bps
- Data bits: 8
- Stop bits: 1
- Parity: None
- Flow control: None
- Timeout: 100ms

Input buffer is read completely each frame to minimize latency, processing all available packets in FIFO order.

#### Visualization Subsystem

The matplotlib-based GUI renders at approximately 30fps (33ms frame period) using FuncAnimation with blit disabled for full redraw capability.

**Spectrogram Algorithm**:
- Maintains 800-sample circular buffer of (frequency, x_axis, y_axis) tuples
- Renders using parametric plotting with time-varying alpha for phosphor decay simulation
- Implements three overlaid traces at linewidths [2, 4, 6] pixels with alpha values [0.8, 0.3, 0.1] to create bloom effect
- Horizontal grid lines rendered at 50Hz intervals using axhline primitives

**Waveform Display**:
- Generates 2000-point waveform snapshot per frame showing 3 complete cycles
- Time axis displayed in milliseconds for readability
- Dual-trace rendering (solid + glow) identical to spectrogram technique

**Effects Rack**:
- Real-time parameter visualization using Unicode block characters (█ = filled, ░ = empty)
- Color-coded by effect category using ANSI-approximate RGB values
- Two-column layout for spatial efficiency
- Updates synchronized to animation frame rate

## Performance Characteristics

**Latency Budget**:
- Arduino sampling + transmission: ~5ms
- Serial transmission @ 115200 baud: ~2ms
- Python parsing + state update: <1ms  
- Audio callback buffering: 23.2ms
- **Total system latency**: ~31ms (acceptable for real-time interaction)

**CPU Utilization**:
- Audio thread: ~5-8% single core (varies with effect complexity)
- Animation thread: ~2-4% single core
- Serial I/O: <1% single core

**Memory Footprint**:
- Circular audio buffers: ~220KB (multiple effect buffers @ 44100 samples each)
- Visualization buffer: ~25KB (800 tuples × 3 elements × 8 bytes)
- Total working set: <10MB

## Signal Flow Diagram

```
Hardware Input → Serial UART → Parser → State Vector
                                            ↓
                                    Frequency Smoother
                                            ↓
                                    Oscillator (Phase-coherent)
                                            ↓
                                    Effects Chain (10 stages)
                                            ↓
                                    Normalize & Volume
                                            ↓
                                    PortAudio Output Buffer
                                            ↓
                                    System Audio Driver
```

## Control Mapping

| Input | Parameter | Range | Transfer Function |
|-------|-----------|-------|-------------------|
| Joystick X | Sweep Rate | 2-100 Hz/step | Linear map from ADC |
| Joystick Y | Filter Cutoff | 0.1-1.0 | Linear map from ADC |
| Joystick Button | Waveform | 0-7 | Modulo increment |

## Keyboard Effect Matrix

Effects utilize ASCII keycodes with case sensitivity for bidirectional control (uppercase = increase, lowercase = decrease):

| Key | Effect | Range | Step Size |
|-----|--------|-------|-----------|
| H/h | Harmonics | 0.0-1.0 | 0.1 |
| D/d | Distortion | 0.0-1.0 | 0.1 |
| C/c | Chorus Depth | 0.0-1.0 | 0.1 |
| R/r | Chorus Rate | 0.1-10.0 Hz | 0.5 Hz |
| B/b | Bit Depth | 4-16 bits | 1 bit |
| L/l | Filter Cutoff | 0.1-1.0 | 0.1 |
| E/e | Reverb | 0.0-1.0 | 0.1 |
| Y/y | Delay Mix | 0.0-0.8 | 0.1 |
| T/t | Delay Time | 0.05-1.0 s | 0.05 s |
| M/m | Ring Mod Freq | 0.0-10.0 | 0.5 |
| O/o | Tremolo Depth | 0.0-1.0 | 0.1 |
| P/p | Tremolo Rate | 0.5-20.0 Hz | 1.0 Hz |
| A/a | Phaser Depth | 0.0-1.0 | 0.1 |
| V/v | Volume | 0.05-0.8 | 0.05 |
| SPACE | Reset All | - | - |
| F | Fullscreen | - | Toggle |
| ESC | Quit | - | - |

## Dependencies

**Hardware**:
- Arduino Uno/Nano/compatible (ATmega328P minimum)
- Analog joystick module (2-axis + button)
- USB cable (Type-B or Mini-B depending on board)

**Software**:
- Python 3.7-3.11 (3.12+ untested)
- pyserial >= 3.5
- numpy >= 1.20
- matplotlib >= 3.3
- sounddevice >= 0.4
- scipy >= 1.7

## Build Instructions

1. Flash Arduino with provided firmware
2. Wire joystick: VCC→5V, GND→GND, VRx→A0, VRy→A1, SW→D2
3. Install Python dependencies: `pip install pyserial numpy matplotlib sounddevice scipy`
4. Execute: `python slimsynth.py`
5. Application will auto-detect Arduino serial port

## Technical Notes

**Anti-Aliasing**: Waveforms are generated with inherent aliasing above Nyquist frequency. For production use, consider implementing bandlimited synthesis using BLIT (Band-Limited Impulse Train) or polyBLEP algorithms.

**Fixed-Point Optimization**: Current implementation uses floating-point throughout. For embedded DSP, convert to Q15 or Q31 fixed-point representation for performance gains.

**Buffer Underrun Prevention**: Audio callback uses numpy's vectorized operations to ensure sub-buffer-period execution time. If underruns occur, increase buffer size at cost of latency.

**Serial Overflow**: At maximum update rate, serial buffer may overflow. Current implementation discards old data; consider implementing flow control for critical applications.

**Joystick Calibration**: The Y-axis filter control assumes full 0-1023 ADC range. If your joystick has restricted range or dead zones, modify the `np.interp()` mapping in the Python code to compensate.

**Filter Response**: The low-pass filter implements a simple one-pole design with cutoff frequency directly proportional to the coefficient α. For more sophisticated filtering (resonance, multiple poles, different topologies), consider implementing state-variable or Moog ladder filter designs.
