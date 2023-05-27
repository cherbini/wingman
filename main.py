# File: main.py

import cv2
import numpy as np
import tkinter as tk
from tkinter import simpledialog
from dynamixel_controller import DynamixelController
from motion_tracker import MotionTracker
from coordinate_system import CoordinateSystem

def nothing(x):
    pass

class Application:
    def __init__(self):
        # Create settings window
        self.device_port = "/dev/ttyDXL"
        self.baudrate = 1000000
        self.pan_servo_id = 1
        self.tilt_servo_id = 2
        self.nnPath = "models/yolo-v3-tiny-tf_openvino_2021.4_6shave.blob"  # Set the correct path to the YOLO model blob file

        # Initialize components
        self.dynamixel_controller = DynamixelController(self.device_port, self.baudrate, self.pan_servo_id, self.tilt_servo_id)
        self.motion_tracker = MotionTracker(self.nnPath)
        self.coordinate_system = CoordinateSystem()

        cv2.namedWindow("Settings")
        cv2.createTrackbar("Flip Horizontal", "Settings", 1, 1, nothing)
        cv2.createTrackbar("Flip Vertical", "Settings", 1, 1, nothing)
        cv2.createTrackbar("Lead Time", "Settings", 0, 5, nothing)


    def run(self):
        while True:
            try:
                prev_x_pixels, prev_y_pixels = None, None

                for frame, detections in self.motion_tracker.run():

                    lead_time = cv2.getTrackbarPos("Lead Time", "Settings")
                    flip_horizontal = cv2.getTrackbarPos("Flip Horizontal", "Settings")
                    flip_vertical = cv2.getTrackbarPos("Flip Vertical", "Settings")
        
                    if flip_horizontal:
                        frame = cv2.flip(frame, 1)
                        for detection in detections:
                            detection.xmin, detection.xmax = 1 - detection.xmin, 1 - detection.xmax
        
                    if flip_vertical:
                        frame = cv2.flip(frame, 0)
                        for detection in detections:
                            detection.ymin, detection.ymax = 1 - detection.ymin, 1 - detection.ymax
        
        
                    for detection in detections:
                        if detection.label == 0:
                            # Print class label
                            print(f"Label: {detection.label}")
                        
                            # Get bounding box coordinates
                            bbox = [detection.xmin, detection.ymin, detection.xmax, detection.ymax]
                            print(f"Bounding Box: {bbox}")
                        
                            # Calculate centroid
                            centroid = ((detection.xmax + detection.xmin) / 2, (detection.ymax + detection.ymin) / 2)
                            print(f"Centroid: {centroid}")
                            # Draw a green dot on the centroid
                            centroid_px = (int(centroid[0] * frame.shape[1]), int(centroid[1] * frame.shape[0]))  # Convert normalized coordinates to pixel coordinates
                            cv2.circle(frame, centroid_px, 5, (0, 255, 0), -1)  # Draw a green dot with radius 5
                            # Calculate velocity
                            if prev_x_pixels is not None and prev_y_pixels is not None:
                                vx_pixels, vy_pixels = self.coordinate_system.calculate_velocity(
                                    centroid[0], centroid[1], prev_x_pixels, prev_y_pixels, dt=1  # Assuming dt=1 for this example
                                )
                
                                # Calculate interception point
                                lead_time = 1  # Set this to the appropriate value
                                interception_x, interception_y = self.coordinate_system.calculate_interception_point(
                                    centroid[0], centroid[1], vx_pixels, vy_pixels, lead_time
                                )
                
                                # Draw a yellow dot at the interception point
                                interception_point_px = (int(interception_x * frame.shape[1]), int(interception_y * frame.shape[0]))  # Convert normalized coordinates to pixel coordinates
                                cv2.circle(frame, interception_point_px, 5, (0, 255, 255), -1)  # Draw a yellow dot with radius 5
                
                            prev_x_pixels, prev_y_pixels = centroid[0], centroid[1]
            
                            # Set goal position for servos
                            pan_goal = self.coordinate_system.image_position_to_servo_goal(
                                centroid[0],
                                0, #image_min for x coord
                                1, #image_max for x coord
                                self.dynamixel_controller.PAN_MIN_POSITION,
                                self.dynamixel_controller.PAN_MAX_POSITION
                            )
                            tilt_goal = self.coordinate_system.image_position_to_servo_goal(
                                centroid[1],
                                0, #image_min for y coord
                                1, #image_max for Y coord
                                self.dynamixel_controller.TILT_MIN_POSITION,
                                self.dynamixel_controller.TILT_MAX_POSITION
                            )
                        
                            # Set servo goal positions
                            self.dynamixel_controller.set_goal_position(self.dynamixel_controller.PAN_SERVO_ID, pan_goal)
                            self.dynamixel_controller.set_goal_position(self.dynamixel_controller.TILT_SERVO_ID, tilt_goal)
            
                        # Display the frame
                        cv2.imshow("Frame", frame)
            
                        # Break if 'q' is pressed
                        if cv2.waitKey(1) == ord('q'):
                            break
            except cv2.error as e:
                print(f"A cv2.error occurred: {e}")
                # Decide what to do in case of a cv2 error. For example, you might want to break the loop:
                break
    
            except KeyboardInterrupt:
                print("Interrupted by user")
                break
    
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
                # Decide what to do in case of a general error. You might want to continue, or you might want to break the loop:
                continue
    
        # Close Dynamixel controller
        self.dynamixel_controller.close()
    
        # Destroy all OpenCV windows
        cv2.destroyAllWindows()
    
if __name__ == "__main__":
    app = Application()
    app.run()

