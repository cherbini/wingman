# File: main.py

import time
import threading
import cv2
import numpy as np
import apriltag
from dynamixel_controller import DynamixelController
from motion_tracker import MotionTracker
from coordinate_system import CoordinateSystem
from pyPS4Controller.controller import Controller


def nothing(x):
    pass

class MyController(Controller):

    def __init__(self, **kwargs):
        Controller.__init__(self, **kwargs)
        self.pan_goal = None
        self.tilt_goal = None
    def on_left_joystick_y(self, value):
        # Handle tilt here
        self.tilt_goal = self.map_range(value, -1.0, 1.0, self.dynamixel_controller.TILT_MIN_POSITION, self.dynamixel_controller.TILT_MAX_POSITION)
        print(f"Left joystick Y: {value}, Tilt goal: {self.tilt_goal}")
            
    def on_left_joystick_x(self, value):
        # Handle pan here
        self.pan_goal = self.map_range(value, -1.0, 1.0, self.dynamixel_controller.PAN_MIN_POSITION, self.dynamixel_controller.PAN_MAX_POSITION)
        print(f"Left joystick X: {value}, Pan goal: {self.pan_goal}")


    def map_range(self, input_value, input_min, input_max, output_min, output_max):
        return ((input_value - input_min) * (output_max - output_min) / (input_max - input_min)) + output_min

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
        cv2.createTrackbar("Flip Horizontal Image", "Settings", 1, 1, nothing)
        cv2.createTrackbar("Flip Vertical Image", "Settings", 1, 1, nothing)
        cv2.createTrackbar("Servo Speed", "Settings", 500, 1023, nothing)  # Default speed is 512, maximum is 1023
        cv2.createTrackbar("Lead Time", "Settings", 1, 5, nothing)
        cv2.createTrackbar("Confidence", "Settings", 65, 100, nothing)  # Let's say default confidence is 50%, and maximum is 100%
        cv2.createTrackbar("Servo Scale", "Settings", 100 , 100, nothing)
        cv2.createTrackbar("Process Noise Cov", "Settings", 1, 10, nothing)
        cv2.createTrackbar("Measurement Noise Cov", "Settings", 3, 10, nothing)
        cv2.createTrackbar("Show Frame", "Settings", 1, 1, nothing)
        cv2.createTrackbar("Reverse Pan", "Settings", 0, 1, nothing)
        cv2.createTrackbar("Reverse Tilt", "Settings", 0, 1, nothing)
        cv2.createTrackbar("Joystick Control", "Settings", 0, 1, self.toggle_joystick_control)
        # Add trackbars (acting as buttons)
        cv2.createTrackbar("Save Settings", "Settings", 0, 1, self.save_settings)
        cv2.createTrackbar("Load Settings", "Settings", 0, 1, self.load_settings)


        # Initialize Kalman filter
        self.kalman = cv2.KalmanFilter(4, 2)
        self.kalman.measurementMatrix = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], np.float32)
        self.kalman.transitionMatrix = np.array([[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]], np.float32)
        process_noise_cov = 1e-5
        measurement_noise_cov = 1e-4
        self.kalman.processNoiseCov = np.eye(4, dtype=np.float32) * process_noise_cov
        self.kalman.measurementNoiseCov = np.eye(2, dtype=np.float32) * measurement_noise_cov

        self.MAX_VALID_PREDICTION = 1000
        self.MIN_VALID_PREDICTION = 0

        # Set home and detection timer
        self.home_position = (self.dynamixel_controller.PAN_CENTER_POSITION, self.dynamixel_controller.TILT_CENTER_POSITION)
        print("Home Position: {self.home_position}")
        self.last_detection_time = time.time()
        self.last_positions = []

        self.april_detector = apriltag.Detector()
        self.april_tag_visible = False
        self.controller = MyController(interface="/dev/input/js0", connecting_using_ds4drv=False)


    def toggle_joystick_control(self, value):
        self.joystick_control = bool(value)

    def get_trackbar_position(self, name, window="Settings", default_value=0):
        try:
            return cv2.getTrackbarPos(name, window)
        except Exception as e:
            print(f"An error occurred while adjusting the {name} slider: {e}")
            return default_value


    def save_settings(self, value):
        if value == 1:  # Only save when the trackbar is set to 1
            settings = {}
            for setting in ["Flip Horizontal Image", "Flip Vertical Image", "Lead Time", "Confidence", "Servo Scale", "Process Noise Cov", "Measurement Noise Cov", "Show Frame", "Reverse Pan", "Reverse Tilt"]:
                settings[setting] = cv2.getTrackbarPos(setting, "Settings")
            with open("settings.json", "w") as f:
                json.dump(settings, f)
    
    def load_settings(self, value):
        if value == 1:  # Only load when the trackbar is set to 1
            with open("settings.json", "r") as f:
                settings = json.load(f)
            for setting, value in settings.items():
                cv2.setTrackbarPos(setting, "Settings", value)
            # Optionally reset the "Load Settings" trackbar to 0 here

    def run(self):
        pan_goal = None
        tilt_goal = None
        last_centroid = None
        last_prediction = None
        last_detection_time = None

        try:
            thread = threading.Thread(target=self.controller.listen)
            thread.start()

            self.home_position = (self.dynamixel_controller.PAN_CENTER_POSITION, self.dynamixel_controller.TILT_CENTER_POSITION)
        except AttributeError as e:
            print(f"Failed to get home position: {e}")
            self.home_position = None

        if self.home_position is None:
            print("Error: Home Position is not set")
            return


            self.home_position = (self.dynamixel_controller.PAN_CENTER_POSITION, self.dynamixel_controller.TILT_CENTER_POSITION)

        self.dynamixel_controller.servo_test()
        prev_x_pixels, prev_y_pixels = None, None
        prev_vx_pixels, prev_vy_pixels = None, None
        while True:
            if self.controller.pan_goal is not None and self.controller.tilt_goal is not None:
                pan_goal = self.controller.pan_goal
                tilt_goal = self.controller.tilt_goal

            try:

                for frame, detections in self.motion_tracker.run():
                    lead_time = self.get_trackbar_position("Lead Time", window="Settings", default_value=0) / 10.0
                    flip_horizontal = self.get_trackbar_position("Flip Horizontal Image", window="Settings", default_value=0)
                    flip_vertical = self.get_trackbar_position("Flip Vertical Image", window="Settings", default_value=0)
                    confidence_threshold = self.get_trackbar_position("Confidence", window="Settings", default_value=70) / 100.0
                    servo_scale = self.get_trackbar_position("Servo Scale", window="Settings", default_value=0) / 100.0
                    #process_noise_cov = self.get_trackbar_position("Process Noise Cov", window="Settings", default_value=0) * 1e-2
                    #measurement_noise_cov = self.get_trackbar_position("Measurement Noise Cov", window="Settings", default_value=0) * 1e-2
                    process_noise_cov = self.get_trackbar_position("Process Noise Cov", window="Settings", default_value=0)
                    measurement_noise_cov = self.get_trackbar_position("Measurement Noise Cov", window="Settings", default_value=0)
                    show_frame = self.get_trackbar_position("Show Frame", window="Settings", default_value=1)
                    servo_speed = self.get_trackbar_position("Servo Speed", window="Settings", default_value=512)
                    reverse_pan = self.get_trackbar_position("Reverse Pan", window="Settings", default_value=0)
                    reverse_tilt = self.get_trackbar_position("Reverse Tilt", window="Settings", default_value=0)



                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    tags = self.april_detector.detect(gray)

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
        
                    if tags:
                        # There are AprilTags detected, so give them priority
                        self.april_tag_visible = True
                    
                        # Track the first detected AprilTag
                        tag = tags[0]
                        corners = tag.corners
                    
                        # Flip the corners horizontally if the image is flipped horizontally
                        if flip_horizontal:
                            corners[:, 0] = frame.shape[1] - corners[:, 0]
                    
                        # Flip the corners vertically if the image is flipped vertically
                        if flip_vertical:
                            corners[:, 1] = frame.shape[0] - corners[:, 1]
                    
                        # Draw the bounding box
                        cv2.polylines(frame, [np.int32(corners)], isClosed=True, color=(0, 255, 0))
                    
                        # Calculate centroid
                        centroid = np.mean(corners, axis=0)
                        centroid = centroid.astype(np.float32)  # Convert centroid matrix to float32
                        print(f"Type of centroid matrix: {centroid.dtype}")
                        print(f"Type of measurementMatrix: {self.kalman.measurementMatrix.dtype}")
                        print(f"Dimensions of measurementMatrix: {self.kalman.measurementMatrix.shape}")
                        print(f"Dimensions of centroid: {centroid.shape}")
                    
                        # Convert centroid to pixel coordinates
                        centroid_px = (int(centroid[0]), int(centroid[1]))
                    
                        # Ensure centroid is within frame boundaries
                        centroid_px = (max(0, min(frame.shape[1]-1, centroid_px[0])),
                                       max(0, min(frame.shape[0]-1, centroid_px[1])))
                    
                        # Draw a green dot on the centroid
                        cv2.circle(frame, centroid_px, 5, (0, 255, 0), -1)
                    
                        # Update Kalman filter
                    #    self.kalman.processNoiseCov = np.eye(4, dtype=np.float32) * process_noise_cov
                    #    self.kalman.measurementNoiseCov = np.eye(2, dtype=np.float32) * measurement_noise_cov
                    
                        self.kalman.correct(centroid)
                    
                        prediction = self.kalman.predict()
                    
                        # Draw prediction
                        prediction_px = (int(prediction[0]), int(prediction[1]))
                        cv2.circle(frame, prediction_px, 5, (255, 0, 0), -1)
                    
                        # Calculate velocity
                        if prev_x_pixels is not None and prev_y_pixels is not None:
                            prev_vx_pixels, prev_vy_pixels = self.coordinate_system.calculate_velocity(
                                centroid[0], centroid[1], prev_x_pixels, prev_y_pixels, dt=2
                            )
                        
                        # Update previous position
                        prev_x_pixels, prev_y_pixels = centroid[0], centroid[1]
                        
                    else:
                        self.april_tag_visible = False
                        # No AprilTags detected, handle accordingly
    
                        if detections:

                            last_detection_time = time.time()
                            centroid = (0.5, 0.5)
                            # Sort detections by confidence
                            detections.sort(key=lambda detection: detection.confidence, reverse=True)
    
                            # Take the most confident detection
                            most_confident_detection = detections[0]
                            # Now, handle only the most_confident_detection
                            if most_confident_detection.label == 0:
                                # Print class label
                                print(f"Label: {detection.label}")
    
                                # Get bounding box coordinates
                                bbox = [detection.xmin, detection.ymin, detection.xmax, detection.ymax]
                                print(f"Bounding Box: {bbox}")
    
                                # Calculate centroid
                                centroid = ((detection.xmax + detection.xmin) / 2, (detection.ymax + detection.ymin) / 2)
                                last_centroid = centroid
    
                                print(f"Centroid: {centroid}")
                                # Draw a green dot on the centroid
                                centroid_px = (int(centroid[0] * frame.shape[1]), int(centroid[1] * frame.shape[0]))  # Convert normalized coordinates to pixel coordinates
                                cv2.circle(frame, centroid_px, 5, (0, 255, 0), -1)  # Draw a green dot with radius 5
                                # Update Kalman filter
                                self.kalman.processNoiseCov = np.eye(4, dtype=np.float32) * process_noise_cov
                                self.kalman.measurementNoiseCov = np.eye(2, dtype=np.float32) * measurement_noise_cov
    
                                centroid = np.array([[np.float32(centroid_px[0])], [np.float32(centroid_px[1])]])  # Convert to column vector
                                self.kalman.correct(centroid)
    
                                prediction = self.kalman.predict()
    
                                print(f"Kalman prediction: {prediction}")
    
    
                                if np.all(self.MIN_VALID_PREDICTION <= prediction) and np.all(prediction <= self.MAX_VALID_PREDICTION):
    
                                    # Draw prediction
                                    prediction_px = (int(prediction[0]), int(prediction[1]))
                                    last_prediction = prediction_px
    
                                    cv2.circle(frame, prediction_px, 5, (255, 0, 0), -1)  # Draw a blue dot at the predicted position
                                
                                    if bbox is not None:
                                        # Calculate centroid
                                        centroid = ((detection.xmax + detection.xmin) / 2, (detection.ymax + detection.ymin) / 2)
        
                                        # Calculate velocity
                                        if prev_x_pixels is not None and prev_y_pixels is not None:
                                            prev_vx_pixels, prev_vy_pixels = self.coordinate_system.calculate_velocity(
                                                centroid[0], centroid[1], prev_x_pixels, prev_y_pixels, dt=2  # Assuming dt=1 for this example
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
                                else:
                                    # If we have a last known centroid, draw it
                                    if last_centroid is not None:
                                        last_centroid_px = (int(last_centroid[0] * frame.shape[1]), int(last_centroid[1] * frame.shape[0]))
                                        cv2.circle(frame, last_centroid_px, 5, (0, 255, 0), -1)  # Draw a green dot with radius 5
                     
                                    # If we have a last known prediction, draw it
                                    if last_prediction is not None:
                                         cv2.circle(frame, last_prediction, 5, (255, 0, 0), -1)  # Draw a blue dot at the predicted position
    
    
                            # Set goal position for servos, even if no new detections have been made
                            if centroid is not None:
                                pan_goal = self.coordinate_system.image_position_to_servo_goal(
                                    1 - centroid[0] if reverse_pan else centroid[0],
                                    1,  # image_max for x coord
                                    self.dynamixel_controller.PAN_MIN_POSITION,
                                    self.dynamixel_controller.PAN_MAX_POSITION
                                ) * servo_scale
                    
                                tilt_goal = self.coordinate_system.image_position_to_servo_goal(
                                    1 - centroid[1] if reverse_tilt else centroid[1],
                                    1,  # image_max for Y coord
                                    self.dynamixel_controller.TILT_MIN_POSITION,
                                    self.dynamixel_controller.TILT_MAX_POSITION
                                ) * servo_scale

                                # Print pan_goal and tilt_goal for debugging
                                print(f"Setting PAN goal position to: {pan_goal}")
                                print(f"Setting TILT goal position to: {tilt_goal}")
    
                            # Set the servo speed
                            try:
                                self.dynamixel_controller.set_speed(self.dynamixel_controller.PAN_SERVO_ID, servo_speed)
                            except Exception as e:
                                print(f"Failed to set PAN servo speed: {e}")
                            
                            try:
                                self.dynamixel_controller.set_speed(self.dynamixel_controller.TILT_SERVO_ID, servo_speed)
                            except Exception as e:
                                print(f"Failed to set TILT servo speed: {e}")
    
                            # Set servo goal positions
                            if pan_goal is not None and tilt_goal is not None:
                                pan_goal = self.dynamixel_controller.clamp_servo_position(
                                    pan_goal, self.dynamixel_controller.PAN_MIN_POSITION, self.dynamixel_controller.PAN_MAX_POSITION
                                )
                                tilt_goal = self.dynamixel_controller.clamp_servo_position(
                                    tilt_goal, self.dynamixel_controller.TILT_MIN_POSITION, self.dynamixel_controller.TILT_MAX_POSITION
                                )
                                # Print pan_goal and tilt_goal after clamping
                                print(f"Clamped PAN goal position to: {pan_goal}")
                                print(f"Clamped TILT goal position to: {tilt_goal}")
    
                                try:
                                    self.dynamixel_controller.set_goal_position(self.dynamixel_controller.PAN_SERVO_ID, pan_goal)
                                    self.dynamixel_controller.set_goal_position(self.dynamixel_controller.TILT_SERVO_ID, tilt_goal)
                                except RxPacketError:
                                    print("Error: The data value exceeds the limit value.")
                                    continue
    
                    
                            # If no detection for the last 3 seconds, move servos back to home position
                            #if last_detection_time and time.time() - last_detection_time > 3.0:
                            #    if self.home_position is not None:
                            #        pan_home, tilt_home = self.home_position
                            #        self.dynamixel_controller.set_goal_position(self.dynamixel_controller.PAN_SERVO_ID, pan_home)
                            #        self.dynamixel_controller.set_goal_position(self.dynamixel_controller.TILT_SERVO_ID, tilt_home)
                            #    else:
                            #        print("Home position not set. Unable to return to home position.") 
    
                    # Display the frame
                    if show_frame:
                        cv2.imshow("Frame", frame)
                    else:
                        cv2.destroyWindow("Frame")
                    
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

