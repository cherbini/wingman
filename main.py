# File: main.py

import time
import threading
import cv2
import numpy as np
import apriltag
import Jetson.GPIO as GPIO
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
        self.relay_pin = 7
        self.nnPath = "models/yolo-v3-tiny-tf_openvino_2021.4_6shave.blob"  # Set the correct path to the YOLO model blob file

        # Initialize components
        self.dynamixel_controller = DynamixelController(self.device_port, self.baudrate, self.pan_servo_id, self.tilt_servo_id)
        self.motion_tracker = MotionTracker(self.nnPath)
        self.coordinate_system = CoordinateSystem()

        # Initialize Kalman filter
        self.kalman = cv2.KalmanFilter(4, 2)
        self.kalman.measurementMatrix = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], np.float32)
        self.kalman.transitionMatrix = np.array([[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]], np.float32)
        self.process_noise_cov = 2
        self.measurement_noise_cov = 0
        self.kalman.processNoiseCov = np.eye(4, dtype=np.float32) * self.process_noise_cov
        self.kalman.measurementNoiseCov = np.eye(2, dtype=np.float32) * self.measurement_noise_cov
        self.kalman.statePost = np.zeros((4,1), np.float32)
        self.kalman.statePre = np.zeros((4,1), np.float32)
        self.kalman.errorCovPost = np.eye(4, dtype=np.float32)
        self.kalman.errorCovPre = np.eye(4, dtype=np.float32)


        self.MAX_VALID_PREDICTION = 1000
        self.MIN_VALID_PREDICTION = 0


        # Set home and detection timer
        self.home_position = (self.dynamixel_controller.PAN_CENTER_POSITION, self.dynamixel_controller.TILT_CENTER_POSITION)
        print(f"Home Position: {self.home_position}")
        self.last_positions = []
        self.start_time = None
        self.last_centroid = None
        self.THRESHOLD_DISTANCE = 5
        self.TIME_LIMIT = 3.0

        self.april_detector = apriltag.Detector()
        self.april_tag_visible = False
        self.flip_horizontal = 1
        self.flip_vertical = 1
        self.confidence_threshold = .8
        self.servo_scale = 1
        self.show_frame = 1
        self.servo_speed = 500
        self.reverse_pan = 1
        self.reverse_tilt = 1
        self.prev_x_pixels = None
        self.prev_y_pixels = None
        self.prev_vx_pixels = None
        self.prev_vy_pixels = None

    def activate_relay(duration=2):
            GPIO.output(RELAY_PIN, GPIO.HIGH)
            time.sleep(duration)
            GPIO.output(RELAY_PIN, GPIO.LOW)

    def set_servo_speed(self, servo_id, speed):
        try:
            self.dynamixel_controller.set_speed(servo_id, speed)
        except Exception as e:
            print(f"Failed to set servo speed for servo ID {servo_id}: {e}")

    def clamp_servo_position(self, goal, min_position, max_position):
        return self.dynamixel_controller.clamp_servo_position(goal, min_position, max_position)

    def get_bbox_coordinates(self, detection):
        return [detection.xmin, detection.ymin, detection.xmax, detection.ymax]

    def update_kalman_filter(self, centroid):
        self.kalman.processNoiseCov = np.eye(4, dtype=np.float32) * self.process_noise_cov
        self.kalman.measurementNoiseCov = np.eye(2, dtype=np.float32) * self.measurement_noise_cov
        centroid_array = np.array(centroid).astype(np.float32)
        self.kalman.correct(centroid_array)
        return self.kalman.predict()

    def draw_centroid(self, frame, centroid):
        centroid_px = (int(centroid[0] * frame.shape[1]), int(centroid[1] * frame.shape[0]))
        cv2.circle(frame, centroid_px, 5, (0, 255, 0), -1)

    def draw_prediction(self, frame, prediction):
        prediction_px = (int(prediction[0]), int(prediction[1]))
        cv2.circle(frame, prediction_px, 5, (255, 0, 0), -1)

    def is_close(self, centroid1, centroid2):
        """Check if two centroids are close to each other."""
        distance = np.linalg.norm(np.array(centroid1) - np.array(centroid2))
        return distance < self.THRESHOLD_DISTANCE

    def process_centroid(self, frame, centroid):
        # If it's the first time processing, or if the centroid has moved significantly
        if self.last_centroid is None or not self.is_close(centroid, self.last_centroid):
            self.start_time = time.time()
            self.last_centroid = centroid
        else:
            elapsed_time = time.time() - self.start_time
            if elapsed_time >= self.TIME_LIMIT:
                # Draw a red circle on the centroid
                self.draw_red_circle(frame, centroid)

    def draw_red_circle(self, frame, centroid):
        center = (int(centroid[0] * frame.shape[1]), int(centroid[1] * frame.shape[0]))
        radius = 10  # Example radius; adjust as necessary
        color = (0, 0, 255)  # RGB for red
        thickness = 2  # Thickness of the circle outline
        cv2.circle(frame, center, radius, color, thickness)

    def calculate_velocity(self, centroid):
        if self.prev_x_pixels is not None and self.prev_y_pixels is not None:
            velocity = self.coordinate_system.calculate_velocity(centroid[0], centroid[1], self.prev_x_pixels, self.prev_y_pixels, dt=2)
            print(f"Calculated Velocity: {velocity}")
            return velocity
        print("Returning None for velocity")
        return None, None

    def calculate_centroid(self, detection):
        return tuple(np.float32(val) for val in [(detection.xmax + detection.xmin) / 2, (detection.ymax + detection.ymin) / 2])

    def is_authorized(self, frame):
        font = cv2.FONT_HERSHEY_SIMPLEX
        frame_height, frame_width, _ = frame.shape
        text_size = cv2.getTextSize("AUTHORIZED", font, 2, 2)[0]
        text_x = (frame_width - text_size[0]) // 2
        text_y = ((frame_height - text_size[1]) // 2) + text_size[1]
        cv2.putText(frame, "AUTHORIZED", (text_x, text_y), font, 2, (0, 255, 0), 2, cv2.LINE_AA)
        return frame

    def run(self):
        pan_goal = None
        tilt_goal = None
        last_centroid = None
        last_prediction = None
        last_detection_time = None

        if self.home_position is None:
            print("Error: Home Position is not set")
            return

        self.dynamixel_controller.home_servos()

        while True:

            try:
                for frame, detections in self.motion_tracker.run():
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    tags = self.april_detector.detect(gray)

                    # Filter detections based on confidence
                    detections = [d for d in detections if d.confidence >= self.confidence_threshold]
        
                    if self.flip_horizontal:
                        frame = cv2.flip(frame, 1)
                        for detection in detections:
                            detection.xmin, detection.xmax = 1 - detection.xmin, 1 - detection.xmax
        
                    if self.flip_vertical:
                        frame = cv2.flip(frame, 0)
                        for detection in detections:
                            detection.ymin, detection.ymax = 1 - detection.ymin, 1 - detection.ymax
        
                    if tags:
                        # There are AprilTags detected, so give them priority
                        self.april_tag_visible = True
                        self.is_authorized(frame)
                    
                        # Track the first detected AprilTag
                        tag = tags[0]
                        corners = tag.corners
                    
                        # Flip the corners horizontally if the image is flipped horizontally
                        if self.flip_horizontal:
                            corners[:, 0] = frame.shape[1] - corners[:, 0]
                    
                        # Flip the corners vertically if the image is flipped vertically
                        if self.flip_vertical:
                            corners[:, 1] = frame.shape[0] - corners[:, 1]
                    
                        # Draw the bounding box
                        cv2.polylines(frame, [np.int32(corners)], isClosed=True, color=(0, 255, 0))
                    
                        # Calculate centroid
                        centroid = np.mean(corners, axis=0)
                        centroid = centroid.astype(np.float32)  # Convert centroid matrix to float32
                        print(f"Badge Detected: {tag.tag_id}")
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
                        self.kalman.processNoiseCov = np.eye(4, dtype=np.float32) * self.process_noise_cov
                        self.kalman.measurementNoiseCov = np.eye(2, dtype=np.float32) * self.measurement_noise_cov
                    
                        centroid = np.array([[np.float32(centroid_px[0])], [np.float32(centroid_px[1])]])

                        self.kalman.correct(centroid)
                    
                        prediction = self.kalman.predict()
                    
                        # Draw prediction
                        prediction_px = (int(prediction[0]), int(prediction[1]))
                        cv2.circle(frame, prediction_px, 5, (255, 0, 0), -1)
                    
                        # Calculate velocity
                        vx, vy = self.calculate_velocity(centroid)
                        if vx is not None and vy is not None:
                            self.prev_vx_pixels, self.prev_vy_pixels = vx, vy
                        
                        # Update previous position
                        self.prev_x_pixels, self.prev_y_pixels = centroid[0], centroid[1]
                        
                    else:
                        self.april_tag_visible = False
                        # No AprilTags detected, handle accordingly

                        last_detection_timestamp = None
                        last_still_timestamp = None

                        if detections:
                            centroid = (0.5, 0.5)
                            most_confident_detection = max(detections, key=lambda detection: detection.confidence)
                    
                            # Update the timestamp for the last detection
                            last_detection_timestamp = time.time()
                    
                            if most_confident_detection.label == 0:
                                bbox = self.get_bbox_coordinates(most_confident_detection)
                                centroid = self.calculate_centroid(most_confident_detection)
                                last_centroid = centroid 
                    
                                try: 
                                    self.draw_centroid(frame, centroid)
                                    prediction = self.update_kalman_filter(centroid)

                                    if np.all(self.MIN_VALID_PREDICTION <= prediction) and np.all(prediction <= self.MAX_VALID_PREDICTION):
                                        self.draw_prediction(frame, prediction)
                                        vx, vy = self.calculate_velocity(centroid)
                                        if vx == 0 and vy == 0:  # Detected object is still
                                            if not last_still_timestamp:
                                                last_still_timestamp = time.time()
                                        else:
                                            last_still_timestamp = None
                                        
                                        if vx and vy:
                                            self.prev_vx_pixels, self.prev_vy_pixels = vx, vy
                                    else:
                                        if last_centroid:
                                            self.draw_centroid(frame, last_centroid)
                                        if last_prediction:
                                            self.draw_prediction(frame, last_prediction)
                        
                                    pan_goal = self.coordinate_system.image_position_to_servo_goal(
                                        1 - centroid[0] if self.reverse_pan else centroid[0], 1,
                                        self.dynamixel_controller.PAN_MIN_POSITION,
                                        self.dynamixel_controller.PAN_MAX_POSITION
                                    ) * self.servo_scale
                        
                                    tilt_goal = self.coordinate_system.image_position_to_servo_goal(
                                        1 - centroid[1] if self.reverse_tilt else centroid[1], 1,
                                        self.dynamixel_controller.TILT_MIN_POSITION,
                                        self.dynamixel_controller.TILT_MAX_POSITION
                                    ) * self.servo_scale
                        
                                    self.process_centroid(frame, centroid)

                                except Exception as e:
                                    print(f"Error processing detections: {e}")

                            if pan_goal and tilt_goal:
                                pan_goal = self.clamp_servo_position(pan_goal, self.dynamixel_controller.PAN_MIN_POSITION, self.dynamixel_controller.PAN_MAX_POSITION)
                                tilt_goal = self.clamp_servo_position(tilt_goal, self.dynamixel_controller.TILT_MIN_POSITION, self.dynamixel_controller.TILT_MAX_POSITION)
                                
                                try:
                                    self.dynamixel_controller.set_goal_position(pan_goal, tilt_goal)

                                except RxPacketError:
                                    print("Error: The data value exceeds the limit value.")

                            # Check elapsed time since last detection
                            elapsed_time_since_detection = time.time() - last_detection_timestamp if last_detection_timestamp else float('inf')
                            elapsed_time_still = time.time() - last_still_timestamp if last_still_timestamp else float('inf')
                        
                            # Display green dot if within three seconds of detection
                            if elapsed_time_since_detection <= 3:
                                self.draw_centroid(frame, centroid)  # Assuming you have this method
                        
                            # Display red and green dots if the detection has been still for three seconds
                            if elapsed_time_still <= 3 and elapsed_time_since_detection <= 3:
                                self.draw_red_circle(frame, centroid)  # Assuming you have this method

                            # Go Home after 5 seconds no detections
                            if elapsed_time_since_detection <= 7:
                                self.dynamixel_controller.home_servos()

                    # Display the frame
                    if self.show_frame:
                        cv2.imshow("Frame", frame)
                    else:
                        cv2.destroyWindow("Frame")
                        pass
                  
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
