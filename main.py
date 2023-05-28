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
        cv2.createTrackbar("Confidence", "Settings", 50, 100, nothing)  # Let's say default confidence is 50%, and maximum is 100%
        cv2.createTrackbar("Servo Scale", "Settings", 90 , 100, nothing)

        # Initialize Kalman filter

        self.kalman = cv2.KalmanFilter(4, 2)
        self.kalman.measurementMatrix = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], np.float32)
        self.kalman.transitionMatrix = np.array([[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]], np.float32)
        self.kalman.processNoiseCov = np.eye(4, dtype=np.float32) * 1e-4

    def run(self):
        pan_goal = None
        tilt_goal = None
        self.dynamixel_controller.servo_test()
        prev_x_pixels, prev_y_pixels = None, None
        prev_vx_pixels, prev_vy_pixels = None, None
        while True:
            try:
                for frame, detections in self.motion_tracker.run():
                    try:
                        lead_time = cv2.getTrackbarPos("Lead Time", "Settings")
                        flip_horizontal = cv2.getTrackbarPos("Flip Horizontal", "Settings")
                        flip_vertical = cv2.getTrackbarPos("Flip Vertical", "Settings")
                        confidence_threshold = cv2.getTrackbarPos("Confidence", "Settings") / 100.0  # Convert to a value between 0 and 1
                        servo_scale = cv2.getTrackbarPos("Servo Scale", "Settings") / 100.0  # Convert to a value between 0 and 1
                    except Exception as e:
                        print(f"An error occurred while adjusting the sliders: {e}")
                        # You may want to set default values here
                        lead_time = 1
                        flip_horizontal = 1
                        flip_vertical = 1
                        confidence_threshold = 0.5
                        servo_scale = .9


                    # Filter detections based on confidence
                    detections = [d for d in detections if d.confidence >= confidence_threshold]
        
                    if flip_horizontal:
                        frame = cv2.flip(frame, 1)
                        for detection in detections:
                            detection.xmin, detection.xmax = 1 - detection.xmin, 1 - detection.xmax
        
                    if flip_vertical:
                        frame = cv2.flip(frame, 0)
                        for detection in detections:
                            detection.ymin, detection.ymax = 1 - detection.ymin, 1 - detection.ymax
        
        
                    if detections:
                        # Sort detections by confidence
                        detections.sort(key=lambda detection: detection.confidence, reverse=True)


                        # Take the most confident detection
                        most_confident_detection = detections[0]
                        # Now, handle only the most_confident_detection
                        if most_confident_detection.label == 0:
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
                                    # Update Kalman filter
                                    centroid = np.array([[np.float32(centroid_px[0])], [np.float32(centroid_px[1])]])  # Convert to column vector
                                    self.kalman.correct(centroid)
                                    prediction = self.kalman.predict()

                                    # Draw prediction
                                    prediction_px = (int(prediction[0]), int(prediction[1]))
                                    cv2.circle(frame, prediction_px, 5, (255, 0, 0), -1)  # Draw a blue dot at the predicted position
                                
                                    if bbox is not None:
                                        # Calculate centroid
                                        centroid = ((detection.xmax + detection.xmin) / 2, (detection.ymax + detection.ymin) / 2)

                                        # Calculate velocity
                                        if prev_x_pixels is not None and prev_y_pixels is not None:
                                            prev_vx_pixels, prev_vy_pixels = self.coordinate_system.calculate_velocity(
                                                centroid[0], centroid[1], prev_x_pixels, prev_y_pixels, dt=1  # Assuming dt=1 for this example
                                            )
                                
                                        # Update previous position
                                        prev_x_pixels, prev_y_pixels = centroid[0], centroid[1]
                                
                                    else:
                                        # Detection lost
                                        if prev_x_pixels is not None and prev_y_pixels is not None and prev_vx_pixels is not None and prev_vy_pixels is not None:
                                            # Predict new position based on last known velocity
                                            predicted_x_pixels = prev_x_pixels + prev_vx_pixels
                                            predicted_y_pixels = prev_y_pixels + prev_vy_pixels
                                
                                            # Use predicted position as if it was a real detection
                                            centroid = (predicted_x_pixels, predicted_y_pixels)
                                
                                    # Set goal position for servos
                                    pan_goal = self.coordinate_system.image_position_to_servo_goal(
                                        centroid[0],
                                        1, #image_max for x coord
                                        self.dynamixel_controller.PAN_MIN_POSITION,
                                        self.dynamixel_controller.PAN_MAX_POSITION
                                    ) * servo_scale
                                
                                    tilt_goal = self.coordinate_system.image_position_to_servo_goal(
                                        centroid[1],
                                        1, #image_max for Y coord
                                        self.dynamixel_controller.TILT_MIN_POSITION,
                                        self.dynamixel_controller.TILT_MAX_POSITION
                                    ) * servo_scale
                                
                                    # Set servo goal positions
                                    if pan_goal is not None and tilt_goal is not None:
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

