"""
Hardware communication module for LED Matrix.

This module provides low-level functions for communicating with LED matrix hardware.
It includes functions for sending commands, controlling brightness, and other basic operations.
"""

from enum import IntEnum
import serial

from .constants import FWK_MAGIC, DISCONNECTED_DEVS, RESPONSE_SIZE

# Import the necessary functions from the controller module
from led_matrix_battery.led_matrix.helpers.status_handler import get_status, set_status


class CommandVals(IntEnum):
    Brightness = 0x00
    Pattern = 0x01
    BootloaderReset = 0x02
    Sleep = 0x03
    Animate = 0x04
    Panic = 0x05
    Draw = 0x06
    StageGreyCol = 0x07
    DrawGreyColBuffer = 0x08
    SetText = 0x09
    StartGame = 0x10
    GameControl = 0x11
    GameStatus = 0x12
    SetColor = 0x13
    DisplayOn = 0x14
    InvertScreen = 0x15
    SetPixelColumn = 0x16
    FlushFramebuffer = 0x17
    ClearRam = 0x18
    ScreenSaver = 0x19
    SetFps = 0x1A
    SetPowerMode = 0x1B
    PwmFreq = 0x1E
    DebugMode = 0x1F
    Version = 0x20


class PatternVals(IntEnum):
    Percentage = 0x00
    Gradient = 0x01
    DoubleGradient = 0x02
    DisplayLotus = 0x03
    ZigZag = 0x04
    FullBrightness = 0x05
    DisplayPanic = 0x06
    DisplayLotus2 = 0x07


class Game(IntEnum):
    Snake = 0x00
    Pong = 0x01
    Tetris = 0x02
    GameOfLife = 0x03


class GameOfLifeStartParam(IntEnum):
    Currentmatrix = 0x00
    Pattern1 = 0x01
    Blinker = 0x02
    Toad = 0x03
    Beacon = 0x04
    Glider = 0x05

    def __str__(self):
        return self.name.lower()

    def __repr__(self):
        return str(self)

    @staticmethod
    def argparse(s):
        try:
            return GameOfLifeStartParam[s.lower().capitalize()]
        except KeyError:
            return s


class GameControlVal(IntEnum):
    Up = 0
    Down = 1
    Left = 2
    Right = 3
    Quit = 4


def disconnect_dev(dev):
    """
    Disconnect the device from the system.

    Parameters:
        dev (str):
            The device to disconnect.
    """
    global DISCONNECTED_DEVS
    if dev in DISCONNECTED_DEVS:
        return
    DISCONNECTED_DEVS.append(dev)


def bootloader_jump(dev):
    """Reboot into the bootloader to flash new firmware"""
    send_command(dev, CommandVals.BootloaderReset, [0x00])


def brightness(dev, b: int):
    """Adjust the brightness scaling of the entire screen."""
    send_command(dev, CommandVals.Brightness, [b])


def get_brightness(dev):
    """Adjust the brightness scaling of the entire screen."""
    res = send_command(dev, CommandVals.Brightness, with_response=True)
    return int(res[0])


def get_version(dev):
    """Get the device's firmware version"""
    res = send_command(dev, CommandVals.Version, with_response=True)
    if not res:
        return 'Unknown'
    major = res[0]
    minor = (res[1] & 0xF0) >> 4
    patch = res[1] & 0xF
    pre_release = res[2]

    version = f"{major}.{minor}.{patch}"
    if pre_release:
        version += " (Pre-release)"
    return version


def send_command(dev, command, parameters=[], with_response=False):
    return send_command_raw(dev, FWK_MAGIC + [command] + parameters, with_response)


def send_command_raw(dev, command, with_response=False):
    """Send a command to the device.
    Opens new serial connection every time"""
    # print(f"Sending command: {command}")
    try:
        with serial.Serial(dev.device, 115200) as s:
            s.write(command)

            if with_response:
                res = s.read(RESPONSE_SIZE)
                # print(f"Received: {res}")
                return res
    except (IOError, OSError) as _ex:
        disconnect_dev(dev.device)
        # print("Error: ", ex)


def send_serial(dev, s, command):
    """Send serial command by using existing serial connection"""
    try:
        s.write(command)
    except (IOError, OSError) as _ex:
        disconnect_dev(dev.device)
        # print("Error: ", ex)


def animate(dev, b: bool):
    """Enable/disable animation"""
    send_command(dev, CommandVals.Animate, [0x01 if b else 0x00])


def get_animate(dev):
    """Check if animation is enabled"""
    res = send_command(dev, CommandVals.Animate, with_response=True)
    return bool(res[0])


def get_pwm_freq(dev):
    """Adjust the brightness scaling of the entire screen."""
    res = send_command(dev, CommandVals.PwmFreq, with_response=True)
    freq = int(res[0])
    if freq == 0:
        return 29000
    elif freq == 1:
        return 3600
    elif freq == 2:
        return 1800
    elif freq == 3:
        return 900
    else:
        return None


def pwm_freq(dev, freq):
    """Set the PWM frequency"""
    if freq == "29kHz":
        send_command(dev, CommandVals.PwmFreq, [0])
    elif freq == "3.6kHz":
        send_command(dev, CommandVals.PwmFreq, [1])
    elif freq == "1.8kHz":
        send_command(dev, CommandVals.PwmFreq, [2])
    elif freq == "900Hz":
        send_command(dev, CommandVals.PwmFreq, [3])


def percentage(dev, p):
    """Fill a percentage of the screen. Bottom to top"""
    send_command(dev, CommandVals.Pattern, [PatternVals.Percentage, p])