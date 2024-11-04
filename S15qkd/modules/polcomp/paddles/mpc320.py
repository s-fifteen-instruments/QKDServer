#!/usr/bin/env python3
"""Controls the Thorlabs MPC320 motorized polarization controller.

Communicates with Thorlabs MPC320 motorized polarization controller directly,
without use of Windows-dependent 'APT.dll' required in 'thorlabs-apt' library.
This allows Linux platforms to interact with the motor.

Uses 'thorlabs_apt_protocol' for generating and reading messages.
Documentation for APT protocol can be found in:
https://www.thorlabs.com/Software/Motion%20Control/APT_Communications_Protocol.pdf

Changelog:
    2022-07-19 Justin: Initialize base Thorlabs APT class
    2023-02-15 Syed: Modify code for Thorlabs MPC320 controller
    2024-10-17 Justin: Standardize conventions
"""

import time
import warnings

import numpy as np
import serial
import thorlabs_apt_protocol as _apt


class ThorlabsMPC320:
    """Wrapper for APT commands relevant to MPC320."""

    CHANNELS = [1, 2, 4]  # index to actual channel number
    MIN_RANGE = 1.5
    MAX_RANGE = 159
    FULL_REV = 170
    STEPS_PER_REVOLUTION = 1370
    MIN_STEP = FULL_REV / STEPS_PER_REVOLUTION

    def __init__(self, port, blocking=True, homed=False, suppress_errors=False):
        """Creates the motor instance.

        If blocking is set to 'True', both homing and moving
        commands will block until completion.

        Important: Ensure that the homing parameter 'offset_position'
        is correct for your stage.

        Usage:
            >>> motor = ThorlabsMPC320("/dev/serial/by-id/...")
            >>> motor.angles
            (83.94, 83.94, 83.94)
            >>> motor.channel = 0
            >>> motor.angle = 0
            >>> motor.channel = 1
            >>> motor.angle = 45
            >>> motor.channel = 2
            >>> motor.angle = 90
            >>> motor.angles
            (4.59, 48.15, 93.07)
        """
        self.suppress_errors = suppress_errors
        self._com = serial.Serial(
            port=port,
            baudrate=115200,
            rtscts=True,
            timeout=0.1,
        )

        # Enable RTS control flow (technically not needed)
        # and reset input/output buffers
        self._com.rts = True
        self._com.reset_input_buffer()
        self._com.reset_output_buffer()
        self._com.rts = False

        # Enable channels
        self.enabled = True

        # Reader for device output - unpacks messages
        self.reader = apt.Unpacker(self._com)

        # Device constants
        self.steps_per_revolution = 1370
        self.min_range = self.MIN_RANGE
        self.max_range = self.MAX_RANGE
        self.min_step = self.FULL_REV / self.steps_per_revolution
        self.blocking = blocking
        self.offset = [989, 989, 989]

        # Required initialization as per APT protocol
        # self.w(_apt.hw_no_flash_programming(dest=0x50,source=0x01))

        # Initialize device defaults, defined below in 'Parameters'
        self.params_velocity = {}
        self.params_jog = {}
        self.params_homing = {}  # important: check homing offset

        if not homed:
            time.sleep(0.5)  # give the controller some time to initialize itself
            for ch in range(len(self.CHANNELS)):
                self.channel = ch
                self.home()

        # Set default channel
        self.channel = 0

    ################
    #   COMMANDS   #
    ################

    # Most usage will only require interfacing via these commands.
    #   For customizing operating parameters, see 'Parameters' section.
    #   For direct interfacing with motor, see 'Helper' section.

    @property
    def identity(self) -> int:
        """Returns serial number of motor.

        Note that Thorlabs software typically distinguish devices
        by serial number.
        """
        return self.rw(apt.hw_req_info()).serial_number

    def home(self):
        """Requests motor to go to home based on homing parameters."""
        self.w(apt.mot_move_home(chan_ident=self._channel))
        if self.blocking:
            while self.is_moving():
                time.sleep(0.1)
                pass

    def stop(self, abrupt=False):
        """Stops motor movement."""
        stop_mode = 0x1 if abrupt else 0x2
        self.w(apt.mot_move_stop(chan_ident=self._channel, stop_mode=stop_mode))

    @property
    def channel(self):
        return self.CHANNELS.index(self._channel)

    @channel.setter
    def channel(self, v):
        if not isinstance(v, int):
            raise TypeError(f"Channel supplied is not an integer: '{v}'")
        num_channels = len(self.CHANNELS)
        if not 0 <= v < num_channels:
            raise ValueError(
                f"Channel supplied is not one of {set(range(num_channels))}"
            )
        self._channel = self.CHANNELS[v]

    @property
    def angle(self) -> float:
        """Returns angular position in degrees."""
        return round(self.position * self.min_step, 2)

    @angle.setter
    def angle(self, angle: float):
        """Sets angular position of current channel, in degrees."""
        angle = self.validate_angle(angle)
        self.goto(self._channel, self.deg2pos(angle))
        if self.blocking:
            while self.is_moving():
                time.sleep(0.1)
                pass

    @property
    def angles(self) -> list:
        """Returns angular positions of all channels in degrees."""
        _channel = self.channel
        angles = []
        for channel in range(len(self.CHANNELS)):
            self.channel = channel
            angles.append(self.angle)
        self.channel = _channel
        return tuple(angles)

    @angles.setter
    def angles(self, angles):
        """Sets angular positions of all channels in degrees.

        If None is passed, then the channel is ignored.

        Note:
            There is no need to specially disable blocking mode, since
            the motor controller processes the angle rotations in a
            sequential manner anyway.
        """
        _channel = self.channel
        angles = self.validate_3tuple(angles)
        for channel, angle in enumerate(angles):
            if angle is None:
                continue
            self.channel = channel
            self.angle = angle
        self.channel = _channel

    def scan(self, start=10, end=90, scan_step=1, channel=None):
        """Performs an angle scan on the current channel.

        Usage:
            >>> for angle in motor.scan(45, 135, 0.5):
            ...     result = get_result(angle)
        """
        start = self.validate_angle(start)
        end = self.validate_angle(end)
        scan_step = max(scan_step, self.min_step)
        scan_angles = np.arange(
            start, end, scan_step
        )  # TODO: Floating point errors will occur

        # Mainloop
        for angle in scan_angles:
            if channel is not None:
                _channel = self.channel
                self.channel = channel
            self.angle = angle
            if channel is not None:
                self.channel = _channel
            yield angle

    ########################
    #   HELPER FUNCTIONS   #
    ########################

    # Note: Forward corresponds to counter-clockwise rotation, so
    #       reverse corresponds to clockwise rotation.
    #
    # There are 1370 microsteps per 160 degree.
    #
    # Initial settings via Kinesis sets:
    # - Homing: Reverse direction with hardware reverse limit switch
    #           Zero offset = 4.0deg, velocity = 10.0deg/s
    # - Hardware limit switch: CCW makes (home), CW ignore.
    # - Software limit switch policy: Complete moves only
    # - Motor: Steps/revolution 200, gearbox ratio 120:1
    # - Backlash: 1deg

    def w(self, command: bytes):
        """Writes byte command to motor."""
        self._com.write(command)

    def r(self):
        """Reads from motor.

        As far as possible, we want to keep only a single message in buffer,
        for ease of debugging, and since use cases for multiple REQs before
        a single GET is rare, e.g. high resolution motor positioning.

        If multiple messages exist, a warning is raised and only the latest
        message is returned.

        Note that the status update messages pushed by the motor is generally
        ignored, since similar functionality is achieved by actually
        querying the motor directly.
        """
        resp = list(self.reader)

        # Filter status update responses
        status = [
            "mot_move_completed",
            "mot_move_stopped",
            "mot_move_homed",
        ]
        responses = [m for m in resp if m.msg not in status]
        if not responses:
            if self.suppress_errors:
                warnings.warn("No reply from motor.")
                return
            raise ValueError("No reply from motor.")

        if len(responses) > 1 and not self.suppress_errors:
            warning = [
                "Multiple messages received:",
                *responses,
            ]
            warnings.warn("\n  * ".join(map(str, warning)))
        return responses[-1]  # ignore all but the last message

    def rw(self, command: bytes) -> list:
        """Writes and reads motor controller."""
        self.w(command)
        return self.r()

    def pos2deg(self, position: int) -> float:
        return position * self.min_step

    def deg2pos(self, degree: float) -> int:
        return round(degree / self.min_step)

    def posdiff(self, target_position, curr_position):
        """Returns relative move distance based on absolute position."""

        # Normalize
        target = target_position % self.steps_per_revolution
        curr = curr_position % self.steps_per_revolution

        # Get smallest rotation
        diff = target - curr
        if abs(diff) > self.steps_per_revolution / 2:
            if diff > 0:
                return diff - self.steps_per_revolution
            else:
                return diff + self.steps_per_revolution
        return diff

    @property
    def position(self):
        """Returns absolute position based on encoder value.

        Accurate only after homing. Does not normalize within
        revolution steps.

        Equivalent representation using encoder_count:
        `self.rw(apt.mot_req_enccounter()).encoder_count`
        """
        offset = self.offset[self.channel]
        return self.rw(apt.mot_req_poscounter(self._channel)).position - offset

    def is_moving(self) -> bool:
        """Queries if motor is still rotating."""
        message = self.rw(apt.mot_req_dcstatusupdate(chan_ident=self._channel))
        data = self.extract(message, "moving_forward", "moving_reverse")
        return data.get("moving_forward", False) or data.get("moving_reverse", False)

    def goto(self, ch, position: int = 0):
        """Move motor to 'position' in units of microsteps."""

        self.w(apt.mot_move_absolute(ch, position))

    def jog(self, ch, direction: int):
        """Performs a jog based on jog parameters.

        Currently not used, similar functionality to spin.

        Args:
            direction: 0x01 (forward) or 0x02 (backward)
        """
        self.w(apt.mot_move_jog(ch, direction))

    def identify(self):
        """Blinks LED."""
        self.w(apt.mod_identify(chan_ident=1))

    @property
    def enabled(self) -> tuple:
        """Returns ENABLE state on each individual channel."""
        states = []
        for ch in self.CHANNELS:
            msg = apt.mod_req_chanenablestate(ch)
            state = self.rw(msg).enabled
            states.append(state)
        return tuple(states)

    @enabled.setter
    def enabled(self, states: tuple):
        """Sets ENABLE state on each individual channel.

        Disabling of the motor channels is strongly not recommended:
        setting an angle A when the channel is disabled, and then an
        angle B when the channel is enabled, results in a fast transition
        to angle A before the usual gradual transition from A to B.
        At this point, it is not clear if this is expected, or if this
        causes unintentional stress to the motor gears.

        Args:
            states: One of boolean 3-tuple, or a single boolean.
        """
        states = self.validate_3tuple(states, bool)
        ch_ids = sum([(1 << i) for i, state in enumerate(states) if state])
        self.w(apt.mod_set_chanenablestate(chan_ident=ch_ids, enable_state=0x1))

    @staticmethod
    def validate_angle(angle):
        return np.clip(angle, ThorlabsMPC320.MIN_RANGE, ThorlabsMPC320.MAX_RANGE)

    @staticmethod
    def validate_3tuple(obj, t=None):
        if hasattr(obj, "__len__"):  # object is already a tuple
            if len(obj) != 3:
                raise ValueError("Tuple needs to be of length 3.")
            if t is not None and not all(isinstance(v, t) for v in obj):
                raise ValueError(f"Tuple is not of type '{t}': '{obj}'")
            obj = tuple(obj)
        else:
            if t is not None and not isinstance(obj, t):
                raise ValueError(f"Input is not of type '{t}': '{obj}'")
            obj = (obj, obj, obj)
        return obj

    @staticmethod
    def extract(message, *fields):
        return {key: getattr(message, key) for key in fields}

    ##################
    #   PARAMETERS   #
    ##################

    # Units are in microsteps, see 'position()' for details.

    @property
    def params(self):
        """Returns parameters used for device

        Usage:
            >>> motor.params = {"velocity": 15}
            >>> motor.params
            {
                "velocity": 15, # newly set
                "home_position": 685,
                "jog_step1": 25,
                "jog_step2": 25,
                "jog_step3": 25,  # see setter defaults
            }
        """
        data = self.rw(apt.pol_req_params())
        return self.extract(
            data,
            "velocity",
            "home_position",
            "jog_step1",
            "jog_step2",
            "jog_step3",
        )

    @params.setter
    def params(self, value):
        settings = {
            "velocity": 10,
            "home_position": 685,
            "jog_step1": 25,
            "jog_step2": 25,
            "jog_step3": 25,
            **value,  # override by value
        }
        return self.w(apt.pol_set_params(**settings))

    @property
    def params_limswitch(self):
        """Returns limit switch parameters.

        Unknown whether software limit switch is used.

        For the hardware limit switches:
          - '0x01': ignore switch
          - '0x02': switch makes on contact
          - '0x03': switch breaks on contact
          - '0x04': switch makes on contact (only used for homing)
          - '0x05': switch breaks on contact (only used for homing)
        """
        data = self.rw(apt.mot_req_limswitchparams())
        return self.extract(
            data,
            "cw_hardlimit",
            "ccw_hardlimit",
            "cw_softlimit",
            "ccw_softlimit",
            "soft_limit_mode",
        )

    @params_limswitch.setter
    def params_limswitch(self, value):
        settings = {
            "cw_hardlimit": 2,
            "ccw_hardlimit": 2,
            "cw_softlimit": 0,
            "ccw_softlimit": 0,
            "soft_limit_mode": 1,
            **value,  # override by value
        }
        return self.w(apt.mot_set_limswitchparams(**settings))


class Apt:
    """
    See Thorlabs APT protocol specification, page 12, for description of
    dest and source. Used when messages are broadcasted to sub-modules.
    In modern systems, typically connect one-to-one COM port connection,
    so can simply replace all source reference to 0x01 (host) and
    destination reference to 0x50 (generic USB).

    Source:
        https://www.thorlabs.com/software/apt/APT_Communications_Protocol_Rev_15.pdf
    """

    def __getattr__(self, name):
        """Intercepts calls to and injects apt.functions.

        Calls to every other function in apt is transparently passed
        through, unless they are defined in apt.functions.

        This monkey patch curries '0x50' as destination byte and
        '0x01' as source byte, since all apt.functions.[^_]* have them
        as first and second positional arguments.
        """
        target = getattr(_apt, name)  # could have been imported downstream
        if not hasattr(_apt.functions, name):
            return target

        # Patch APT function
        curry = [0x50, 0x01]

        def f(*args, **kwargs):
            target = getattr(_apt, name)
            return target(*curry, *args, **kwargs)

        return f


apt = Apt()  # required

if __name__ == "__main__":
    port = "/dev/serial/by-id/usb-Thorlabs_Polarization_Controller_38418404-if00-port0"
    motor = ThorlabsMPC320(port, homed=True)
    motor.identify()  # blinks LED
    print("Serial:", motor.identity)  # prints identity information
