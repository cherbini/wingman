#!/usr/bin/env python
# -*- coding: utf-8 -*-

from pyPS4Controller.controller import Controller
from dynamixel_sdk import *
import Jetson.GPIO as GPIO  # New Import

# Definitions from your previous code...
ADDR_PRESENT_POSITION = 132
LEN_PRESENT_POSITION = 4
MY_DXL = 'MX_SERIES'
ADDR_TORQUE_ENABLE = 64
ADDR_GOAL_POSITION = 116
LEN_GOAL_POSITION = 4
BAUDRATE = 1000000
PROTOCOL_VERSION = 2.0
DXL1_ID = 1
DXL2_ID = 2
DEVICENAME = '/dev/ttyDXL'
TORQUE_ENABLE = 1
TORQUE_DISABLE = 0
DXL_MOVING_STATUS_THRESHOLD = 20
RELAY_PIN = 7

# Initialize the GPIO pin for the relay
GPIO.setmode(GPIO.BOARD)
GPIO.setup(RELAY_PIN, GPIO.OUT, initial=GPIO.LOW)

# Dynamixel controller setup
portHandler = PortHandler(DEVICENAME)

if portHandler.openPort():
    print("Port opened successfully!")
else:
    print("Failed to open the port!")

packetHandler = PacketHandler(PROTOCOL_VERSION)
groupSyncWrite = GroupSyncWrite(portHandler, packetHandler, ADDR_GOAL_POSITION, LEN_GOAL_POSITION)

# A conversion function for mapping joystick inputs to servo positions
def joystick_to_servo_position(dxl_id, joystick_value):
    # Get current position
    dxl_present_position, dxl_comm_result, dxl_error = packetHandler.read4ByteTxRx(portHandler, dxl_id, ADDR_PRESENT_POSITION)
    if dxl_comm_result != COMM_SUCCESS:
        print("%s" % packetHandler.getTxRxResult(dxl_comm_result))
    elif dxl_error != 0:
        print("%s" % packetHandler.getRxPacketError(dxl_error))

    # Calculate new position proportional to joystick movement
    dxl_goal_position = dxl_present_position + int(joystick_value / 32767 * 500)  # Adjust 500 for sensitivity
    return dxl_goal_position

# Enable Torque for both servos and setup groupSyncRead
for dxl_id in [DXL1_ID, DXL2_ID]:
    dxl_comm_result, dxl_error = packetHandler.write1ByteTxRx(portHandler, dxl_id, ADDR_TORQUE_ENABLE, TORQUE_ENABLE)
    if dxl_comm_result != COMM_SUCCESS or dxl_error != 0:
        print(f"Failed to enable torque on Dynamixel#{dxl_id}")

class MyController(Controller):
    def __init__(self, **kwargs):
        Controller.__init__(self, **kwargs)

    # Override the R3 stick methods (you may need to adjust depending on your controller layout)
    def on_R3_up(self, value):
        self.handle_joystick(2, value)
    def on_R3_down(self, value):
        self.handle_joystick(2, value)
    def on_R3_left(self, value):
        self.handle_joystick(1, value)
    def on_R3_right(self, value):
        self.handle_joystick(1, value)
    def on_R2_press(self, value):
        GPIO.output(RELAY_PIN, GPIO.HIGH)
    def on_R2_release(self, *args):
        GPIO.output(RELAY_PIN, GPIO.LOW)


    # Method to handle joystick events
    def handle_joystick(self, dxl_id, joystick_value):
        dxl_goal_position = joystick_to_servo_position(dxl_id, joystick_value)

        # Create goal position byte array
        param_goal_position = [DXL_LOBYTE(DXL_LOWORD(dxl_goal_position)), DXL_HIBYTE(DXL_LOWORD(dxl_goal_position)), DXL_LOBYTE(DXL_HIWORD(dxl_goal_position)), DXL_HIBYTE(DXL_HIWORD(dxl_goal_position))]

        # Add goal position value to the Syncwrite storage
        dxl_addparam_result = groupSyncWrite.addParam(dxl_id, param_goal_position)
        if dxl_addparam_result != True:
            print(f"[ID:{dxl_id}] groupSyncWrite addparam failed")
            return

        # Syncwrite goal position
        dxl_comm_result = groupSyncWrite.txPacket()
        if dxl_comm_result != COMM_SUCCESS:
            print(packetHandler.getTxRxResult(dxl_comm_result))

        # Clear Syncwrite parameter storage
        groupSyncWrite.clearParam()

try:
    # Start listening for controller events
    controller = MyController(interface="/dev/input/js0", connecting_using_ds4drv=False)
    controller.listen()
finally:
    GPIO.cleanup()


