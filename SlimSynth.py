import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
from collections import deque
import sounddevice as sd
from scipy import signal as scipy_signal

# Auto-detect Arduino port
def find_arduino_port():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if 'Arduino' in port.description or 'CH340' in port.description or 'USB' in port.description:
            print(f"Found Arduino on: {port.device}")
            return port.device
    
    print("Available ports:")
    for port in ports:
        print(f"  {port.device}: {port.description}")
    return None

arduino_port = find_arduino_port()

if arduino_port is None:
    print("\nCouldn't auto-detect Arduino. Please enter port manually:")
    arduino_port = input("Port: ").strip()

try:
    arduino = serial.Serial(arduino_port, 115200, timeout=0.1)
    print(f"Successfully connected to {arduino_port}")
    import time
    time.sleep(1)
    arduino.reset_input_buffer()
except Exception as e:
    print(f"Error connecting to {arduino_port}: {e}")
    exit()

# Vintage CRT styling
plt.style.use('dark_background')
fig = plt.figure(figsize=(16, 10), facecolor='black')
fig.canvas.manager.set_window_title('OSCILLOSCOPE-9000 /// SYNTH WORKSTATION')

# Disable only the Q quit binding, keep F for fullscreen
plt.rcParams['keymap.quit'] = []

# Create grid layout
from matplotlib.gridspec import GridSpec
gs = GridSpec(3, 2, figure=fig, hspace=0.3, wspace=0.3)

ax1 = fig.add_subplot(gs[0:2, :])  # Main spectrogram
ax2 = fig.add_subplot(gs[2, 0])     # Waveform
ax3 = fig.add_subplot(gs[2, 1])     # Effects display

spectrogram_data = deque(maxlen=800)
min_freq, max_freq = 100, 2000

# Vintage colors
PHOSPHOR_GREEN = '#00FF00'
DIM_GREEN = '#003300'
GRID_GREEN = '#004400'
AMBER = '#FFBF00'
CYAN = '#00FFFF'
MAGENTA = '#FF00FF'
RED = '#FF3333'

# Audio settings
SAMPLE_RATE = 44100
current_freq = 440
current_waveform = 0
target_freq = 440

# Extended waveform list
waveform_names = [
    'SAWTOOTH', 'SINE', 'SQUARE', 'TRIANGLE',
    'PULSE', 'NOISE', 'PWM', 'RAMP'
]

# EFFECTS PARAMETERS
harmonics_level = 0.3      # H/h
distortion_level = 0.0     # D/d
chorus_depth = 0.0         # C/c
chorus_rate = 2.0          # R/r
bit_depth = 12             # B/b
filter_cutoff = 1.0        # L/l (also controlled by joystick Y)
reverb_level = 0.0         # E/e
delay_mix = 0.0            # Y/y
delay_time = 0.3           # T/t
ring_mod_freq = 0.0        # M/m
tremolo_depth = 0.0        # O/o
tremolo_rate = 4.0         # P/p
phaser_depth = 0.0         # A/a
volume = 0.35              # V/v

# Joystick state
joy_x_value = 512
joy_y_value = 512
target_filter_cutoff = 1.0

# Effect buffers
chorus_phase = 0.0
chorus_delay_buffer = np.zeros(int(SAMPLE_RATE * 0.05))
chorus_buffer_index = 0

reverb_buffer = np.zeros(int(SAMPLE_RATE * 0.5))
reverb_buffer_index = 0

delay_buffer = np.zeros(int(SAMPLE_RATE * 1.0))
delay_buffer_index = 0

tremolo_phase = 0.0
phaser_phase = 0.0
pwm_phase = 0.0

print("\n" + "="*70)
print("KEYBOARD CONTROLS - SYNTH WORKSTATION")
print("="*70)
print("HARDWARE CONTROLS:")
print("  Joystick X-axis: Frequency sweep speed")
print("  Joystick Y-axis: Real-time filter cutoff")
print("  Joystick Button: Cycle waveforms")
print("  Button (D3):     Cycle waveforms (alternate)")
print("\nWAVEFORMS:")
print("  1-8: Select waveform (Saw/Sine/Square/Tri/Pulse/Noise/PWM/Ramp)")
print("\nEFFECTS:")
print("  H/h - Harmonics        | D/d - Distortion     | C/c - Chorus Depth")
print("  R/r - Chorus Rate      | B/b - Bit Depth      | L/l - Filter Cutoff")
print("  E/e - Reverb           | Y/y - Delay Mix      | T/t - Delay Time")
print("  M/m - Ring Modulator   | O/o - Tremolo Depth  | P/p - Tremolo Rate")
print("  A/a - Phaser Depth     | V/v - Volume")
print("\nUTILITY:")
print("  F     - Toggle fullscreen")
print("  SPACE - Reset all effects to default")
print("  ESC   - Quit")
print("="*70 + "\n")

def generate_base_waveform(t, freq, waveform_type):
    """Generate various waveform types"""
    
    if waveform_type == 0:  # Sawtooth
        return 2 * (t * freq - np.floor(0.5 + t * freq))
    
    elif waveform_type == 1:  # Sine
        return np.sin(2 * np.pi * freq * t)
    
    elif waveform_type == 2:  # Square
        return np.sign(np.sin(2 * np.pi * freq * t))
    
    elif waveform_type == 3:  # Triangle
        return 2 * np.abs(2 * (t * freq - np.floor(t * freq + 0.5))) - 1
    
    elif waveform_type == 4:  # Pulse (25% duty cycle)
        phase = (t * freq) % 1.0
        return np.where(phase < 0.25, 1.0, -1.0)
    
    elif waveform_type == 5:  # White Noise
        return np.random.uniform(-1, 1, len(t))
    
    elif waveform_type == 6:  # PWM (Pulse Width Modulation)
        global pwm_phase
        lfo = 0.5 + 0.4 * np.sin(2 * np.pi * 0.5 * pwm_phase)
        phase = (t * freq) % 1.0
        pwm_phase += len(t) / SAMPLE_RATE
        return np.where(phase < lfo, 1.0, -1.0)
    
    elif waveform_type == 7:  # Ramp (reverse sawtooth)
        return -2 * (t * freq - np.floor(0.5 + t * freq))
    
    return np.zeros_like(t)

def apply_harmonics(wave, freq, level):
    """Add harmonic overtones"""
    if level <= 0:
        return wave
    
    t = np.arange(len(wave)) / SAMPLE_RATE
    harmonics = np.zeros_like(wave)
    
    harmonics += level * 0.5 * np.sin(2 * np.pi * freq * 2 * t)
    harmonics += level * 0.33 * np.sin(2 * np.pi * freq * 3 * t)
    harmonics += level * 0.25 * np.sin(2 * np.pi * freq * 4 * t)
    harmonics += level * 0.2 * np.sin(2 * np.pi * freq * 5 * t)
    harmonics += level * 0.17 * np.sin(2 * np.pi * freq * 6 * t)
    
    return wave + harmonics

def apply_distortion(wave, amount):
    """Balanced wub-wub distortion using waveshaping"""
    if amount <= 0:
        return wave
    
    # Moderate gain for musical distortion
    gain = 1 + amount * 8
    driven = wave * gain
    
    # Smooth waveshaping using multiple tanh stages for warmth
    stage1 = np.tanh(driven * 0.8)
    stage2 = np.tanh(stage1 * 1.2) * 0.9
    
    # Wub-wub effect: smooth wavefolder
    if amount > 0.3:
        fold_intensity = (amount - 0.3) * 1.4
        folded = np.sin(stage2 * np.pi * (1 + fold_intensity))
        output = stage2 * (1 - fold_intensity * 0.6) + folded * (fold_intensity * 0.6)
    else:
        output = stage2
    
    # Add subtle harmonic enhancement
    if amount > 0.5:
        enhanced = np.sign(output) * np.sqrt(np.abs(output))
        harmonic_mix = (amount - 0.5) * 0.3
        output = output * (1 - harmonic_mix) + enhanced * harmonic_mix
    
    # Final gentle saturation
    output = np.tanh(output * 1.1) * 0.95
    
    # Blend with dry signal
    dry_mix = 0.15 * (1 - amount)
    output = output * (1 - dry_mix) + wave * dry_mix
    
    return output

def apply_chorus(wave, depth, rate):
    """Chorus with delay modulation"""
    global chorus_phase, chorus_delay_buffer, chorus_buffer_index
    
    if depth <= 0:
        return wave
    
    output = np.zeros_like(wave)
    
    for i in range(len(wave)):
        lfo = np.sin(2 * np.pi * rate * chorus_phase)
        delay_samples = int(0.002 * SAMPLE_RATE + depth * 0.01 * SAMPLE_RATE * (lfo + 1) / 2)
        delay_samples = max(1, min(delay_samples, len(chorus_delay_buffer) - 1))
        
        read_index = (chorus_buffer_index - delay_samples) % len(chorus_delay_buffer)
        delayed = chorus_delay_buffer[read_index]
        
        output[i] = wave[i] * 0.6 + delayed * 0.4
        
        chorus_delay_buffer[chorus_buffer_index] = wave[i]
        chorus_buffer_index = (chorus_buffer_index + 1) % len(chorus_delay_buffer)
        
        chorus_phase += rate / SAMPLE_RATE
        if chorus_phase > 1.0:
            chorus_phase -= 1.0
    
    return output

def apply_reverb(wave, level):
    """Simple reverb using comb filters"""
    global reverb_buffer, reverb_buffer_index
    
    if level <= 0:
        return wave
    
    output = np.zeros_like(wave)
    delays = [0.029, 0.037, 0.041, 0.043]
    
    for i in range(len(wave)):
        reverb_sum = 0
        for delay in delays:
            delay_samples = int(delay * SAMPLE_RATE)
            read_index = (reverb_buffer_index - delay_samples) % len(reverb_buffer)
            reverb_sum += reverb_buffer[read_index] * 0.25
        
        output[i] = wave[i] + reverb_sum * level
        reverb_buffer[reverb_buffer_index] = wave[i] + reverb_sum * 0.5
        reverb_buffer_index = (reverb_buffer_index + 1) % len(reverb_buffer)
    
    return output

def apply_delay(wave, mix, delay_time):
    """Tape-style delay effect"""
    global delay_buffer, delay_buffer_index
    
    if mix <= 0:
        return wave
    
    output = np.zeros_like(wave)
    delay_samples = int(delay_time * SAMPLE_RATE)
    delay_samples = min(delay_samples, len(delay_buffer) - 1)
    
    for i in range(len(wave)):
        read_index = (delay_buffer_index - delay_samples) % len(delay_buffer)
        delayed = delay_buffer[read_index]
        
        output[i] = wave[i] * (1 - mix) + delayed * mix
        delay_buffer[delay_buffer_index] = wave[i] + delayed * 0.4
        delay_buffer_index = (delay_buffer_index + 1) % len(delay_buffer)
    
    return output

def apply_ring_modulator(wave, freq, mod_freq):
    """Ring modulation for metallic/bell tones"""
    if mod_freq <= 0:
        return wave
    
    t = np.arange(len(wave)) / SAMPLE_RATE
    modulator = np.sin(2 * np.pi * (freq + mod_freq * 100) * t)
    return wave * modulator

def apply_tremolo(wave, depth, rate):
    """Amplitude modulation tremolo"""
    global tremolo_phase
    
    if depth <= 0:
        return wave
    
    output = np.zeros_like(wave)
    
    for i in range(len(wave)):
        lfo = 1 - depth * (0.5 + 0.5 * np.sin(2 * np.pi * rate * tremolo_phase))
        output[i] = wave[i] * lfo
        tremolo_phase += 1.0 / SAMPLE_RATE
        if tremolo_phase > 1.0:
            tremolo_phase -= 1.0
    
    return output

def apply_phaser(wave, depth):
    """Phaser effect using all-pass filters"""
    global phaser_phase
    
    if depth <= 0:
        return wave
    
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.5 * phaser_phase)
    delay_samples = int((2 + lfo * 8) * 0.001 * SAMPLE_RATE)
    
    output = np.zeros_like(wave)
    for i in range(len(wave)):
        if i >= delay_samples:
            output[i] = wave[i] + depth * wave[i - delay_samples]
        else:
            output[i] = wave[i]
    
    phaser_phase += len(wave) / SAMPLE_RATE
    
    return output

def apply_bit_crushing(wave, bits):
    """Reduce bit depth for lo-fi digital sound"""
    if bits >= 16:
        return wave
    
    levels = 2 ** bits
    crushed = np.round(wave * levels) / levels
    return crushed

def apply_filter(wave, cutoff):
    """Low-pass filter"""
    if cutoff >= 1.0:
        return wave
    
    alpha = cutoff
    filtered = np.zeros_like(wave)
    filtered[0] = wave[0]
    
    for i in range(1, len(wave)):
        filtered[i] = alpha * wave[i] + (1 - alpha) * filtered[i-1]
    
    return filtered

# Audio callback
phase = 0.0

def audio_callback(outdata, frames, time_info, status):
    global current_freq, current_waveform, phase, target_freq
    global harmonics_level, distortion_level, chorus_depth, chorus_rate
    global bit_depth, filter_cutoff, volume, reverb_level, delay_mix
    global delay_time, ring_mod_freq, tremolo_depth, tremolo_rate, phaser_depth
    global target_filter_cutoff
    
    # Smooth frequency transition
    current_freq = current_freq * 0.95 + target_freq * 0.05
    
    # Smooth filter cutoff transition (from joystick Y-axis)
    filter_cutoff = filter_cutoff * 0.9 + target_filter_cutoff * 0.1
    
    t = (np.arange(frames) + phase) / SAMPLE_RATE
    
    # Generate base waveform
    wave = generate_base_waveform(t, current_freq, current_waveform)
    
    # Apply effects chain
    wave = apply_harmonics(wave, current_freq, harmonics_level)
    wave = apply_ring_modulator(wave, current_freq, ring_mod_freq)
    wave = apply_distortion(wave, distortion_level)
    wave = apply_tremolo(wave, tremolo_depth, tremolo_rate)
    wave = apply_phaser(wave, phaser_depth)
    wave = apply_chorus(wave, chorus_depth, chorus_rate)
    wave = apply_delay(wave, delay_mix, delay_time)
    wave = apply_reverb(wave, reverb_level)
    wave = apply_bit_crushing(wave, int(bit_depth))
    wave = apply_filter(wave, filter_cutoff)
    
    # Update phase
    phase = (phase + frames) % SAMPLE_RATE
    
    # Normalize and apply volume
    if np.max(np.abs(wave)) > 0:
        wave = wave / np.max(np.abs(wave))
    
    outdata[:, 0] = wave * volume

# Start audio stream
stream = sd.OutputStream(
    samplerate=SAMPLE_RATE,
    channels=1,
    callback=audio_callback,
    blocksize=1024
)
stream.start()

last_x_value = 512
last_y_value = 512

# Keyboard event handler
def on_key_press(event):
    global harmonics_level, distortion_level, chorus_depth, chorus_rate
    global bit_depth, filter_cutoff, volume, current_waveform
    global reverb_level, delay_mix, delay_time, ring_mod_freq
    global tremolo_depth, tremolo_rate, phaser_depth, target_filter_cutoff
    
    key = event.key
    
    # Waveform selection (1-8)
    if key in ['1', '2', '3', '4', '5', '6', '7', '8']:
        current_waveform = int(key) - 1
        print(f"Waveform: {waveform_names[current_waveform]}")
    
    # Harmonics
    elif key.lower() == 'h':
        if key == 'H':
            harmonics_level = min(1.0, harmonics_level + 0.1)
        else:
            harmonics_level = max(0.0, harmonics_level - 0.1)
        print(f"Harmonics: {harmonics_level:.2f}")
    
    # Distortion
    elif key.lower() == 'd':
        if key == 'D':
            distortion_level = min(1.0, distortion_level + 0.1)
        else:
            distortion_level = max(0.0, distortion_level - 0.1)
        print(f"Distortion: {distortion_level:.2f}")
    
    # Chorus depth
    elif key.lower() == 'c':
        if key == 'C':
            chorus_depth = min(1.0, chorus_depth + 0.1)
        else:
            chorus_depth = max(0.0, chorus_depth - 0.1)
        print(f"Chorus Depth: {chorus_depth:.2f}")
    
    # Chorus rate
    elif key.lower() == 'r':
        if key == 'R':
            chorus_rate = min(10.0, chorus_rate + 0.5)
        else:
            chorus_rate = max(0.1, chorus_rate - 0.5)
        print(f"Chorus Rate: {chorus_rate:.2f} Hz")
    
    # Bit depth
    elif key.lower() == 'b':
        if key == 'B':
            bit_depth = max(4, bit_depth - 1)
        else:
            bit_depth = min(16, bit_depth + 1)
        print(f"Bit Depth: {int(bit_depth)}-bit")
    
    # Filter (L/l - manual keyboard override)
    elif key.lower() == 'l':
        if key == 'L':
            target_filter_cutoff = min(1.0, target_filter_cutoff + 0.1)
        else:
            target_filter_cutoff = max(0.1, target_filter_cutoff - 0.1)
        print(f"Filter Cutoff (Manual): {target_filter_cutoff:.2f}")
    
    # Reverb
    elif key.lower() == 'e':
        if key == 'E':
            reverb_level = min(1.0, reverb_level + 0.1)
        else:
            reverb_level = max(0.0, reverb_level - 0.1)
        print(f"Reverb: {reverb_level:.2f}")
    
    # Delay mix
    elif key.lower() == 'y':
        if key == 'Y':
            delay_mix = min(0.8, delay_mix + 0.1)
        else:
            delay_mix = max(0.0, delay_mix - 0.1)
        print(f"Delay Mix: {delay_mix:.2f}")
    
    # Delay time
    elif key.lower() == 't':
        if key == 'T':
            delay_time = min(1.0, delay_time + 0.05)
        else:
            delay_time = max(0.05, delay_time - 0.05)
        print(f"Delay Time: {delay_time:.2f}s")
    
    # Ring modulator
    elif key.lower() == 'm':
        if key == 'M':
            ring_mod_freq = min(10.0, ring_mod_freq + 0.5)
        else:
            ring_mod_freq = max(0.0, ring_mod_freq - 0.5)
        print(f"Ring Mod: {ring_mod_freq:.2f}")
    
    # Tremolo depth
    elif key.lower() == 'o':
        if key == 'O':
            tremolo_depth = min(1.0, tremolo_depth + 0.1)
        else:
            tremolo_depth = max(0.0, tremolo_depth - 0.1)
        print(f"Tremolo Depth: {tremolo_depth:.2f}")
    
    # Tremolo rate
    elif key.lower() == 'p':
        if key == 'P':
            tremolo_rate = min(20.0, tremolo_rate + 1.0)
        else:
            tremolo_rate = max(0.5, tremolo_rate - 1.0)
        print(f"Tremolo Rate: {tremolo_rate:.1f} Hz")
    
    # Phaser
    elif key.lower() == 'a':
        if key == 'A':
            phaser_depth = min(1.0, phaser_depth + 0.1)
        else:
            phaser_depth = max(0.0, phaser_depth - 0.1)
        print(f"Phaser: {phaser_depth:.2f}")
    
    # Volume
    elif key.lower() == 'v':
        if key == 'V':
            volume = min(0.8, volume + 0.05)
        else:
            volume = max(0.05, volume - 0.05)
        print(f"Volume: {volume:.2f}")
    
    # Reset all effects
    elif key == ' ':
        harmonics_level = 0.3
        distortion_level = 0.0
        chorus_depth = 0.0
        chorus_rate = 2.0
        bit_depth = 12
        target_filter_cutoff = 1.0
        reverb_level = 0.0
        delay_mix = 0.0
        delay_time = 0.3
        ring_mod_freq = 0.0
        tremolo_depth = 0.0
        tremolo_rate = 4.0
        phaser_depth = 0.0
        volume = 0.35
        print("\n>>> ALL EFFECTS RESET <<<\n")
    
    # Quit
    elif key == 'escape':
        print("Quitting...")
        stream.stop()
        stream.close()
        arduino.close()
        plt.close('all')

fig.canvas.mpl_connect('key_press_event', on_key_press)

def animate(frame):
    global current_freq, current_waveform, target_freq
    global joy_x_value, joy_y_value, last_x_value, last_y_value
    global target_filter_cutoff
    
    # Read serial data
    while arduino.in_waiting > 0:
        try:
            line = arduino.readline().decode().strip()
            if not line:
                continue
                
            parts = line.split(',')
            
            if len(parts) >= 4:
                freq = int(parts[0])
                x_value = int(parts[1])
                y_value = int(parts[2])
                waveform_type = int(parts[3])
                
                # Update state
                waveform_type = waveform_type % 8
                target_freq = freq
                current_waveform = waveform_type
                joy_x_value = x_value
                joy_y_value = y_value
                
                # Map Y-axis to filter cutoff (inverted: up = brighter, down = darker)
                target_filter_cutoff = np.interp(y_value, [0, 1023], [0.1, 1.0])
                
                spectrogram_data.append((freq, x_value, y_value))
        except Exception as e:
            pass
    
    # Clear axes
    ax1.clear()
    ax2.clear()
    ax3.clear()
    
    # SPECTROGRAM (ax1)
    ax1.set_facecolor('#000000')
    ax1.set_xlim(0, 800)
    ax1.set_ylim(min_freq - 100, max_freq + 100)
    ax1.grid(True, color=GRID_GREEN, linestyle='-', linewidth=0.5, alpha=0.3)
    ax1.set_ylabel('FREQUENCY [Hz]', color=PHOSPHOR_GREEN, fontsize=12, family='monospace')
    ax1.set_title('◢◤ FREQUENCY SPECTROGRAM ◥◣', color=PHOSPHOR_GREEN, 
                  fontsize=18, family='monospace', weight='bold', pad=20)
    
    if spectrogram_data:
        x_vals = list(range(len(spectrogram_data)))
        y_vals = [d[0] for d in spectrogram_data]
        
        ax1.plot(x_vals, y_vals, color=PHOSPHOR_GREEN, linewidth=2, alpha=0.8)
        ax1.plot(x_vals, y_vals, color=PHOSPHOR_GREEN, linewidth=4, alpha=0.3)
        ax1.plot(x_vals, y_vals, color=PHOSPHOR_GREEN, linewidth=6, alpha=0.1)
        
        for i in range(min_freq, max_freq, 50):
            ax1.axhline(y=i, color=DIM_GREEN, linewidth=0.3, alpha=0.2)
    
    ax1.tick_params(colors=PHOSPHOR_GREEN, labelsize=10)
    for spine in ax1.spines.values():
        spine.set_edgecolor(GRID_GREEN)
        spine.set_linewidth(2)
    
    # WAVEFORM (ax2)
    ax2.set_facecolor('#000000')
    
    display_freq = int(current_freq)
    if display_freq > 0:
        cycles = 3
        t = np.linspace(0, cycles/display_freq, 2000)
        
        wave = generate_base_waveform(t, display_freq, current_waveform)
        
        t_ms = t * 1000
        
        ax2.plot(t_ms, wave, color=PHOSPHOR_GREEN, linewidth=2, alpha=0.9)
        ax2.plot(t_ms, wave, color=PHOSPHOR_GREEN, linewidth=4, alpha=0.3)
        
        for i in np.linspace(-1, 1, 20):
            ax2.axhline(y=i, color=DIM_GREEN, linewidth=0.3, alpha=0.15)
        
        ax2.set_ylim(-1.3, 1.3)
        ax2.set_xlim(0, max(t_ms))
        ax2.grid(True, color=GRID_GREEN, linestyle='-', linewidth=0.5, alpha=0.3)
        ax2.set_xlabel('TIME [ms]', color=PHOSPHOR_GREEN, fontsize=10, family='monospace')
        ax2.set_ylabel('AMP', color=PHOSPHOR_GREEN, fontsize=10, family='monospace')
        
        joy_x_percent = int(joy_x_value / 1023.0 * 100)
        joy_y_percent = int(joy_y_value / 1023.0 * 100)
        title_text = f'{waveform_names[current_waveform]} | {display_freq} Hz | X:{joy_x_percent}% Y:{joy_y_percent}%'
        ax2.set_title(title_text, color=PHOSPHOR_GREEN, 
                     fontsize=12, family='monospace', weight='bold')
    
    ax2.tick_params(colors=PHOSPHOR_GREEN, labelsize=9)
    for spine in ax2.spines.values():
        spine.set_edgecolor(GRID_GREEN)
        spine.set_linewidth(2)
    
    # EFFECTS DISPLAY (ax3)
    ax3.set_facecolor('#000000')
    ax3.set_xlim(0, 10)
    ax3.set_ylim(0, 15)
    ax3.axis('off')
    
    # Organized effects in columns
    effects_left = [
        ("HARMONICS", harmonics_level, 1.0, AMBER),
        ("DISTORTION", distortion_level, 1.0, AMBER),
        ("CHORUS", chorus_depth, 1.0, AMBER),
        ("CHR RATE", chorus_rate, 10.0, AMBER),
        ("", 0, 0, AMBER),  # Spacer
        ("REVERB", reverb_level, 1.0, CYAN),
        ("DELAY MIX", delay_mix, 0.8, CYAN),
        ("DELAY TIME", delay_time, 1.0, CYAN),
    ]
    
    effects_right = [
        ("RING MOD", ring_mod_freq, 10.0, MAGENTA),
        ("TREMOLO", tremolo_depth, 1.0, MAGENTA),
        ("TREM RATE", tremolo_rate, 20.0, MAGENTA),
        ("PHASER", phaser_depth, 1.0, MAGENTA),
        ("", 0, 0, MAGENTA),  # Spacer
        ("BIT DEPTH", bit_depth, 16, RED),
        ("FILTER", filter_cutoff, 1.0, RED),
        ("VOLUME", volume, 0.8, PHOSPHOR_GREEN),
    ]
    
    # Draw left column
    y_pos = 14
    for name, value, max_val, color in effects_left:
        if name == "":  # Spacer
            y_pos -= 0.8
            continue
        
        if name in ["CHR RATE", "DELAY TIME", "TREM RATE", "BIT DEPTH"]:
            text = f"{name:12s} {value:.1f}" if name != "BIT DEPTH" else f"{name:12s} {int(value)}"
        else:
            bar_length = int((value / max_val) * 10)
            bar = '█' * bar_length + '░' * (10 - bar_length)
            text = f"{name:10s} {bar} {value:.1f}"
        
        ax3.text(0.2, y_pos, text, color=color, fontsize=9.5, 
                family='monospace', weight='bold', verticalalignment='top')
        y_pos -= 1.7
    
    # Draw right column
    y_pos = 14
    for name, value, max_val, color in effects_right:
        if name == "":  # Spacer
            y_pos -= 0.8
            continue
        
        if name in ["TREM RATE", "BIT DEPTH"]:
            text = f"{name:10s} {value:.1f}" if name != "BIT DEPTH" else f"{name:10s} {int(value)}"
        else:
            bar_length = int((value / max_val) * 10)
            bar = '█' * bar_length + '░' * (10 - bar_length)
            text = f"{name:8s} {bar} {value:.1f}"
        
        ax3.text(5.5, y_pos, text, color=color, fontsize=9.5, 
                family='monospace', weight='bold', verticalalignment='top')
        y_pos -= 1.7
    
    ax3.set_title('◢◤ EFFECTS RACK ◥◣', color=PHOSPHOR_GREEN, 
                 fontsize=14, family='monospace', weight='bold', pad=10)

# Animation
ani = animation.FuncAnimation(fig, animate, interval=30, blit=False)

plt.tight_layout()
plt.show()

# Cleanup
stream.stop()
stream.close()
arduino.close()