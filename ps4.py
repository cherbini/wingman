#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
import cv2
import sys
import depthai as dai
from pyPS4Controller.controller import Controller
from dynamixel_sdk import *
import Jetson.GPIO as GPIO
import numpy as np
import threading

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
DEVICENAME = '/dev/ttyUSB0'
TORQUE_ENABLE = 1
TORQUE_DISABLE = 0
DXL_MOVING_STATUS_THRESHOLD = 40
RELAY_PIN = 7
ADDR_GOAL_TORQUE = 102
LEN_GOAL_TORQUE = 2

# Be careful with this value. High torques may lead to overheating and damage to the servo.
DXL_GOAL_TORQUE = 500  # This value depends on your servo model.

draw_red_dots = True

try:
    # Initialize the GPIO pin for the relay
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(RELAY_PIN, GPIO.OUT, initial=GPIO.LOW)

    # Dynamixel controller setup
    portHandler = PortHandler(DEVICENAME)

    if portHandler.openPort():
        print("Port opened successfully!", flush=True)
    else:
        print("Failed to open the port!", flush=True)

    packetHandler = PacketHandler(PROTOCOL_VERSION)

    # Dynamixel Torque setup
    dxl_comm_result, dxl_error = packetHandler.write2ByteTxRx(portHandler, DXL2_ID, ADDR_GOAL_TORQUE, DXL_GOAL_TORQUE)
    if dxl_comm_result != COMM_SUCCESS:
        print("%s" % packetHandler.getTxRxResult(dxl_comm_result), flush=True)
    elif dxl_error != 0:
        print("%s" % packetHandler.getRxPacketError(dxl_error), flush=True)

    groupSyncWrite = GroupSyncWrite(portHandler, packetHandler, ADDR_GOAL_POSITION, LEN_GOAL_POSITION)

    def checkbox_handler(pos):
        global draw_red_dots
        draw_red_dots = bool(pos)

    # A conversion function for mapping joystick inputs to servo positions
    def joystick_to_servo_position(dxl_id, joystick_value):
        # Define separate sensitivities for pan (DXL1_ID) and tilt (DXL2_ID)
        sensitivity_pan =600 
        sensitivity_tilt = 200  # Adjust this value for the desired tilt sensitivity
        dead_zone = 6000  # Define the range of joystick values to be considered as the "dead zone"
    
        # Get current position
        dxl_present_position, dxl_comm_result, dxl_error = packetHandler.read4ByteTxRx(portHandler, dxl_id, ADDR_PRESENT_POSITION)
        if dxl_comm_result != COMM_SUCCESS:
            print("%s" % packetHandler.getTxRxResult(dxl_comm_result), flush=True)
        elif dxl_error != 0:
            print("%s" % packetHandler.getRxPacketError(dxl_error), flush=True)
    
        # Calculate new position proportional to joystick movement
        sensitivity = sensitivity_pan if dxl_id == DXL1_ID else sensitivity_tilt
    
        # If joystick is within the dead zone, do not change the servo position
        if -dead_zone < joystick_value < dead_zone:
            return dxl_present_position
    
        dxl_goal_position = dxl_present_position + int(joystick_value / 32767 * sensitivity)
        return dxl_goal_position


    # Enable Torque for both servos and setup groupSyncRead
    for dxl_id in [DXL1_ID, DXL2_ID]:
        dxl_comm_result, dxl_error = packetHandler.write1ByteTxRx(portHandler, dxl_id, ADDR_TORQUE_ENABLE, TORQUE_ENABLE)
        if dxl_comm_result != COMM_SUCCESS or dxl_error != 0:
            print(f"Failed to enable torque on Dynamixel#{dxl_id}", flush=True)

    class MyController(Controller):
        def __init__(self, **kwargs):
            Controller.__init__(self, **kwargs)
            self.joystick_values = {DXL1_ID: 0, DXL2_ID: 0}  # Initialize joystick values
            self.stop_event = threading.Event()
            self.update_thread = threading.Thread(target=self.update_servos)
            self.update_thread.start()

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
            if dxl_id == DXL2_ID:
                joystick_value = -joystick_value
            # Save latest joystick value
            self.joystick_values[dxl_id] = joystick_value


        # Method to continuously update servos
        def update_servos(self):
            while not self.stop_event.is_set():
                for dxl_id in [DXL1_ID, DXL2_ID]:
                    dxl_goal_position = joystick_to_servo_position(dxl_id, self.joystick_values[dxl_id])

                    # Create goal position byte array
                    param_goal_position = [DXL_LOBYTE(DXL_LOWORD(dxl_goal_position)), DXL_HIBYTE(DXL_LOWORD(dxl_goal_position)), DXL_LOBYTE(DXL_HIWORD(dxl_goal_position)), DXL_HIBYTE(DXL_HIWORD(dxl_goal_position))]

                    # Add goal position value to the Syncwrite storage
                    dxl_addparam_result = groupSyncWrite.addParam(dxl_id, param_goal_position)
                    if dxl_addparam_result != True:
                        print(f"[ID:{dxl_id}] groupSyncWrite addparam failed", flush=True)
                        continue

                    # Syncwrite goal position
                    dxl_comm_result = groupSyncWrite.txPacket()
                    if dxl_comm_result != COMM_SUCCESS:
                        print(packetHandler.getTxRxResult(dxl_comm_result), flush=True)

                    # Clear Syncwrite parameter storage
                    groupSyncWrite.clearParam()

                time.sleep(0.01)  # Delay between updates

    def mouse_callback(event, x, y, flags, param):
        # Check if left mouse button is clicked within the bounding box of the "X"
        if event == cv2.EVENT_LBUTTONDOWN and 0 <= x <= 40 and 0 <= y <= 40:
            cv2.destroyAllWindows()
            sys.exit()  # Exit the program

    # Video capture function that runs on a separate thread
    def video_capture():
        pipeline = dai.Pipeline()
    
        cam_rgb = pipeline.createColorCamera()
        cam_rgb.initialControl.setManualFocus(128) #0 is infinity, 255 is macro
        cam_rgb.setBoardSocket(dai.CameraBoardSocket.RGB)
        cam_rgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
        #cam_rgb.setPreviewSize(400, 400)
        #cam_rgb.setIspScale(2,3) #1080P -> 720P
        cam_rgb.setIspScale(3,4) #1080P -> 720P
        #cam_rgb.setVideoSize(640,360)
        cam_rgb.setInterleaved(False)
    
        xout_rgb = pipeline.createXLinkOut()
        xout_rgb.setStreamName("rgb")
        cam_rgb.video.link(xout_rgb.input)

        #cv2.namedWindow("Control Panel")
        #cv2.createTrackbar("Draw Red Dots", "Control Panel", int(draw_red_dots), 1, checkbox_handler)

    
        with dai.Device(pipeline) as device:
            q_rgb = device.getOutputQueue(name="rgb", maxSize=4, blocking=False)

            while True:
                try:
                    in_rgb = q_rgb.get()
                    frame = in_rgb.getCvFrame()

                    #Flip the frame
                    frame = cv2.flip(frame, -1)

                    # Resize the frame
                    #frame = cv2.resize(frame, (640, 480))

                    # Add a red dot in the center
                    center_coordinates = (frame.shape[1] // 2 - 144, frame.shape[0] // 2 - 280)
                    if draw_red_dots:
                        cv2.circle(frame, center_coordinates, 5, (0, 0, 255), -1)

                        # Add a red circle around the dot
                        cv2.circle(frame, center_coordinates, 25, (0, 0, 255), 1)

                    # Draw "X" for exit in top-left corner
                    cv2.putText(frame, "X", (10,30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)

                    cv2.namedWindow("OAK-1", cv2.WND_PROP_FULLSCREEN)
                    cv2.setMouseCallback("OAK-1", mouse_callback)
                    cv2.setWindowProperty("OAK-1", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                    cv2.imshow("OAK-1", frame)

                    if cv2.waitKey(1) == ord('q'):
                        break
                except Exception as e:
                    print("Error in video_capture thread:", str(e), flush=True)
                    break

    # Start video capture on a separate thread
    video_thread = threading.Thread(target=video_capture)
    video_thread.start()

    # Start listening for controller events
    controller = MyController(interface="/dev/input/js0", connecting_using_ds4drv=False)
    controller.listen()
except Exception as e:
    print("Error:", str(e), flush=True)
finally:
    controller.stop_event.set()  # Stop the servo update thread
    GPIO.cleanup()
    portHandler.closePort()

