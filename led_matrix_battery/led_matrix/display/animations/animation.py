import threading
from typing import List, Dict, Optional, Union, Any
from time import sleep  # Potentially used by Frame.play()
import time
from pathlib import Path

from serial.tools.list_ports_common import ListPortInfo

from led_matrix_battery.led_matrix.display.animations.frame.base import Frame
from led_matrix_battery.led_matrix.helpers import get_json_from_file




class Animation:
    """
    Represents an animation for the LED matrix.

    An animation consists of a sequence of frames that are displayed
    in order, with each frame having its own duration.
    """
    def __init__(
            self,
            frame_data: Optional[List[Dict[str, Any]]] = None,
            fallback_frame_duration: float = 0.33,
            loop: bool = False,
            thread_safe: bool = False,
            breathe_on_pause: bool = False,
            devices: Optional[List[ListPortInfo]] = None
    ):
        """
        Initialize a new Animation instance.

        Parameters:
            frame_data (Optional[List[Dict[str, Any]]]):
                A list of dictionaries, each containing data for a single frame:

                    - 'grid' (required):
                      A 2D list of 0s and 1s representing the frame.

                    - 'duration' (optional):
                        A float value representing the duration of the frame in seconds.

                If a frame dictionary does not specify a duration, the animation's
                fallback_frame_duration will be used.

            fallback_frame_duration (float, optional):
                Default duration in seconds for frames that don't specify one (defaults to 0.33).

            loop (bool, optional):
                Whether the animation should loop when it reaches the end (optional, defaults to False).

            thread_safe (bool, optional):
                Whether the animation should be thread-safe (optional, defaults to False).
                If True, the animation will be played in a separate thread, and the
                `play()` method will block until the animation is finished.

            breathe_on_pause (bool, optional):
                Whether to breathe on pause (optional, defaults to False).
        """
        self.__lock = None
        self.__frames: List[Frame] = []
        self.__breathing_thread = None
        self.__breathe_on_pause: bool = False
        self.__cursor: int = 0
        self.__devices: List[ListPortInfo] = []
        self.__making_thread_safe: bool = False
        self.__playing: bool = False
        self.__thread_lock = None
        self.__pause_event = None
        self.__thread_safe: bool = False
        
        if devices:
            self.devices = devices

        if thread_safe:
            self.breathe_on_pause = breathe_on_pause
            self.make_thread_safe()

        # fallback_frame_duration property setter handles validation
        self.fallback_frame_duration: float = fallback_frame_duration
        self.loop: bool = loop  # loop property setter handles validation

        if frame_data:
            for f_dict in frame_data:
                # Frame.from_dict is expected to create a Frame instance.
                # If f_dict lacks 'duration', Frame.from_dict should set
                # the frame's duration to Frame.DEFAULT_DURATION (a sentinel).
                frame_obj = Frame.from_dict(f_dict)

                # If the frame's duration is the sentinel, apply the animation's fallback.
                if frame_obj.duration == Frame.DEFAULT_DURATION:
                    frame_obj.duration = self.__fallback_frame_duration
                self.__frames.append(frame_obj)

        # Ensure cursor is valid if frames exist, or 0 if no frames
        if not self.__frames:
            self.__cursor = 0
        elif self.__cursor >= len(self.__frames):  # Should not happen with fresh init
            self.__cursor = 0

    @property
    def breathe_on_pause(self) -> bool:
        """Get whether the animation breathes on pause."""
        return self.__breathe_on_pause

    @breathe_on_pause.setter
    def breathe_on_pause(self, new_value: bool) -> None:
        if not isinstance(new_value, bool):
            raise TypeError("Breathe on pause must be a boolean value.")
        self.__breathe_on_pause = new_value

    @property
    def cursor(self) -> int:
        """Get the current position (index) in the animation sequence."""
        return self.__cursor

    @cursor.setter
    def cursor(self, new_value: int) -> None:
        """
        Set the current position in the animation sequence.

        Parameters:
            new_value (int):
                The new cursor position.

        Raises:
            TypeError:
                If the new value is not an integer.

            ValueError:
                If trying to set `cursor` on an animation with no frames (unless new_value is 0).

            IndexError:
                If the new value is out of bounds for existing frames.
        """
        if not isinstance(new_value, int):
            raise TypeError("Cursor must be an integer.")

        if not self.__frames:
            if new_value == 0:
                self.__cursor = 0  # Allow setting to 0 if no frames
                return
            raise ValueError("Cannot set cursor on an animation with no frames.")

        if not (0 <= new_value < len(self.__frames)):
            raise IndexError(f"Cursor out of bounds. Must be between 0 and {len(self.__frames) - 1}.")

        self.__cursor = new_value

    @property
    def devices(self) -> List[Any]:
        """Get the list of devices used by the animation."""
        return self.__devices

    @devices.setter
    def devices(self, value: Union[Any, List[Any]]):
        """
        Set the devices used by the animation.

        Parameters:
            value (Union[Any, List[Any]]): A single ListPortInfo or a list of them.
        """
        self.__devices = value if isinstance(value, list) else [value]

    @property
    def fallback_frame_duration(self) -> float:
        """Get the default duration for frames that don't specify one."""
        return self.__fallback_frame_duration

    @fallback_frame_duration.setter
    def fallback_frame_duration(self, new_value: Union[float, int]) -> None:
        """
        Set the default duration for frames that don't specify one.
        This duration is applied to new frames if they don't have their own.
        It does not retroactively change durations of existing frames that
        were already assigned a duration (either specific or a previous fallback).
        Use `set_all_frame_durations()` for that purpose.
        """
        if not isinstance(new_value, (float, int)):
            raise TypeError("Fallback frame duration must be a float or integer.")
        if new_value < 0:
            raise ValueError("Fallback frame duration must be non-negative.")
        self.__fallback_frame_duration = float(new_value)

    @property
    def frames(self) -> List[Frame]:
        """Get the list of frames that make up the animation."""
        return self.__frames  # Returns a reference; could return a copy if immutability is desired

    @property
    def loop(self) -> bool:
        """Get whether the animation should loop when it reaches the end."""
        return self.__loop

    @loop.setter
    def loop(self, new_value: bool) -> None:
        """Set whether the animation should loop."""
        if not isinstance(new_value, bool):
            raise TypeError("Loop must be a boolean value.")
        self.__loop = new_value

    @property
    def is_empty(self) -> bool:
        """Check if the animation has any frames."""
        return not self.__frames

    @property
    def is_playing(self) -> bool:
        """Check if the animation is currently playing."""
        return self.__playing

    @is_playing.setter
    def is_playing(self, new: bool) -> None:
        """
        Set the playing state of the animation.

        Parameters:
            new (bool):
                The new playing state.
        """
        if not isinstance(new, bool):
            raise TypeError("Playing state must be a boolean value.")
        self.__playing = new

    @property
    def is_thread_safe(self) -> bool:
        """Check if the animation is thread-safe."""
        return self.__thread_safe

    @is_thread_safe.setter
    def is_thread_safe(self, new: bool) -> None:
        """
        Set the thread safety of the animation.

        Parameters:
            new (bool):
                The new thread safety state.
        """
        if not isinstance(new, bool):
            raise TypeError("Thread safety must be a boolean value.")

        if new and not self.__thread_safe and not self.__making_thread_safe:
            self.make_thread_safe()

        self.__thread_safe = new

    @property
    def thread_lock(self):
        if not self.is_thread_safe:
            raise RuntimeError("Thread lock is not available in non-thread-safe mode.")

        return self.__thread_lock



    def __len__(self) -> int:
        """Return the number of frames in the animation."""
        return len(self.__frames)

    def make_thread_safe(self, breathe_on_pause: bool = False) -> None:
        if not self.is_thread_safe:
            self.__making_thread_safe = True
            self.__thread_lock = threading.Lock()
            self.__pause_event = threading.Event()
            self.__breathe_on_pause = breathe_on_pause
            self.is_thread_safe = True

    def pause(self, keep_frame_displayed: bool = True) -> None:
        """Pauses animation playback and keeps the current frame displayed."""
        if not self.is_thread_safe:
            raise RuntimeError("pause() requires thread-safe mode to be enabled.")

        with self.thread_lock:
            self.__playing = False
            self.__pause_event.clear()

            if keep_frame_displayed and not self.__breathing_thread:
                self.__breathing_thread = threading.Thread(
                    target=self._paused_display_loop,
                    daemon=True
                )
                self.__breathing_thread.start()

    def play(self, devices: Optional[List[ListPortInfo]] = None) -> None:
        """
        Play the animation on the LED matrix.

        Plays all frames, starting from the current cursor position.
        If `loop` is True, this animation repeats indefinitely.

        Parameters:
            devices (Optional[List[ListPortInfo]]):
                Device to play on (passed to `Frame.play()`).

        Raises:
            ValueError:
                If the animation has no frames.
        """
        if self.is_empty:
            raise ValueError("Cannot play an animation with no frames.")

        if not devices and not self.devices:
            raise ValueError("No devices specified for playback.")


        # Store initial value for `cursor` to handle non-looping play
        # from mid-animation and to correctly play just once if not
        # looping.

        # The loop below will handle cursor advancement.

        self.is_playing = True
        while self.is_playing:
            # Iterate from current cursor to the end of frames
            for i in range(self.__cursor, len(self.__frames)):
                self.__cursor = i
                current_frame = self.__frames[self.__cursor]
                for device in devices:
                    current_frame.play(device)  # Frame.play() is responsible for its own duration (e.g., sleep)

            if self.__loop:
                self.__cursor = 0  # Reset for next loop iteration
                # Continue with active_play = True
            else:
                # If not looping, we've played to the end from the initial cursor.
                active_play = False  # Stop the while loop

    def play_frame(self, frame_index: Optional[int] = None, device: Any = None) -> None:
        """
        Play a single frame of the animation.

        Parameters:
            frame_index (Optional[int]): 
                Index of the frame to play.
                If None, play the current frame.
            
            device (Any, optional):
                Device to play on.

        Raises:
            ValueError:
                If the animation has no frames.
            
            IndexError:
                If frame_index is out of bounds.
        """
        if self.is_empty:
            raise ValueError("Cannot play a frame from an animation with no frames.")

        if frame_index is not None:
            if not (0 <= frame_index < len(self.__frames)):
                raise IndexError(f"Frame index {frame_index} out of bounds (0-{len(self.__frames) - 1}).")
            self.__cursor = frame_index

        # If frame_index was None, self.cursor is already the current frame.
        # If frame_index was valid, self.cursor is now updated.
        self.__frames[self.__cursor].play(device)

    def resume(self) -> None:
        """Resumes playback from paused state."""
        if not self.is_thread_safe:
            raise RuntimeError("resume() requires thread-safe mode to be enabled.")

        with self.thread_lock:
            self.__playing = True
            self.__pause_event.set()

        if self.__breathing_thread and self.__breathing_thread.is_alive():
            self.__breathing_thread.join(timeout=0.1)
            self.__breathing_thread = None

    def _advance_cursor(self, step: int) -> bool:
        """
        Internal helper to advance or rewind the cursor.
        
        Returns:
             - :bool:`True` if `Animation.cursor` changed and is valid, False otherwise (e.g., at the end and not looping).
        """
        if self.is_empty:
            return False

        new_cursor = self.__cursor + step

        if 0 <= new_cursor < len(self.__frames):
            self.__cursor = new_cursor
            return True
        elif self.__loop:
            if new_cursor >= len(self.__frames):
                self.__cursor = 0  # Wrap to beginning
            else:
                self.__cursor = len(self.__frames) - 1  # Wrap to end
            return True
        else:
            # Not looping and new_cursor is out of bounds
            return False

    def _paused_display_loop(self):
        """Keeps redrawing the current frame while paused. Adds breathing effect if enabled."""
        breath_phase = 0.0
        while not self.__pause_event.is_set():
            current_frame = self.__frames[self.cursor]
            for device in self.devices:
                current_frame.play(device)
                if self.breathe_on_pause:
                    # Placeholder: replace with real brightness method for your device
                    brightness = 0.5 + 0.5 * abs((time.time() % 2) - 1)  # triangle wave
                    # device.set_brightness(brightness)
            sleep(1)  # re-draw interval

    def next_frame(self, device: Any = None) -> None:
        """
        Advance to and play the next frame. Wraps if looping.

        Parameters:
            device (Any, optional): Device to play on.
        Raises:
            ValueError: If the animation is empty.
        """
        if self.is_empty:
            raise ValueError("Cannot play next frame: animation is empty.")
        if self._advance_cursor(1):
            self.__frames[self.__cursor].play(device)

    def previous_frame(self, device: Any = None) -> None:
        """
        Move to and play the previous frame. Wraps if looping.

        Parameters:
            device (Any, optional): Device to play on.
        Raises:
            ValueError: If the animation is empty.
        """
        if self.is_empty:
            raise ValueError("Cannot play previous frame: animation is empty.")
        if self._advance_cursor(-1):
            self.__frames[self.__cursor].play(device)

    def set_all_frame_durations(self, duration: Union[float, int]) -> None:
        """
        Set the duration for all frames in the animation.

        Parameters:
            duration (Union[float, int]):
                New duration for all frames in seconds.

        Raises:
            TypeError:
                If duration is not float or int.

            ValueError:
                If duration is negative, or if animation is empty.
        """
        if not isinstance(duration, (float, int)):
            raise TypeError("Duration must be a float or integer.")
        if duration < 0:
            raise ValueError("Duration must be non-negative.")

        if self.is_empty:
            # Or just do nothing, depends on desired behavior
            raise ValueError("Cannot set frame durations: animation is empty.")

        for frame in self.__frames:
            frame.duration = float(duration)

    @classmethod
    def from_file(
            cls,
            filename: Union[str, Path],
            fallback_frame_duration: float = 0.33,
            loop: bool = False
    ) -> 'Animation':
        """
        Create an Animation instance from a JSON file.

        The file should contain a JSON array. Each element can be:
        1. A 2D grid (list of lists of 0s and 1s) - duration will be this method's
           `fallback_frame_duration`.
        2. A dictionary with a 'grid' key and an optional 'duration' key.

        Parameters:
            filename: Path to the JSON file.
            fallback_frame_duration: Default duration for the Animation instance,
                                     and also used for raw grids from the file.
            loop: Whether the created animation should loop.

        Returns:
            Animation: A new Animation instance.

        Raises:
            FileNotFoundError, IsADirectoryError: If file issues.
            ValueError: If file content is not a valid JSON array or frame data is invalid.
        """
        raw_data = get_json_from_file(filename)  # Expected to raise FileNotFoundError etc.

        if not isinstance(raw_data, list):
            raise ValueError(f"File '{filename}' does not contain a valid JSON array of frames.")

        processed_frame_data: List[Dict[str, Any]] = []
        for i, item in enumerate(raw_data):
            if isinstance(item, dict) and 'grid' in item:
                # Item is already a frame dictionary (may or may not have 'duration')
                processed_frame_data.append(item)
            elif isinstance(item, list):  # Assuming it's a raw grid
                # Validate if it looks like a grid (list of lists)
                # A more thorough validation would be inside Frame.from_dict or Grid class
                if not all(isinstance(row, list) for row in item):
                    raise ValueError(
                        f"Invalid raw grid data at index {i} in file '{filename}'. Expected list of lists.")

                # Convert raw grid to a frame dictionary.
                # The 'duration' here will be used by Frame.from_dict if present.
                # If Frame.from_dict finds 'duration', it uses it. If not, it uses Frame.DEFAULT_DURATION.
                # Then Animation.__init__ applies its own fallback if it sees Frame.DEFAULT_DURATION.
                # To ensure this fallback_frame_duration is used for raw grids:
                processed_frame_data.append({
                    'grid': item,
                    'duration': fallback_frame_duration  # Explicitly set duration for raw grids
                })
            else:
                raise ValueError(
                    f"Invalid frame data type at index {i} in file '{filename}'. Expected dict or list (grid).")

        # Pass the processed list of frame dictionaries and other parameters to __init__
        return cls(
            frame_data=processed_frame_data,
            fallback_frame_duration=fallback_frame_duration,
            loop=loop
        )

