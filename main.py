# File: main.py

import time
import threading
import cv2
import users
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
        self.device_port = "/dev/ttyUSB0"
        self.baudrate = 1000000 
        self.pan_servo_id = 1
        self.tilt_servo_id = 2
        self.tilt_offset = 10
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
        self.process_noise_cov = 6
        self.measurement_noise_cov = 4
        self.kalman.processNoiseCov = np.eye(4, dtype=np.float32) * self.process_noise_cov
        self.kalman.measurementNoiseCov = np.eye(2, dtype=np.float32) * self.measurement_noise_cov
        self.kalman.statePost = np.zeros((4,1), np.float32)
        self.kalman.statePre = np.zeros((4,1), np.float32)
        self.kalman.errorCovPost = np.eye(4, dtype=np.float32)
        self.kalman.errorCovPre = np.eye(4, dtype=np.float32)


        # Set home and detection timer
        self.home_position = (self.dynamixel_controller.PAN_CENTER_POSITION, self.dynamixel_controller.TILT_CENTER_POSITION)
        print(f"Home Position: {self.home_position}", flush=True)
        self.last_positions = []
        self.start_time = None
        self.last_centroid = None
        self.THRESHOLD_DISTANCE = 5
        self.TIME_LIMIT = 3.0

        self.april_detector = apriltag.Detector()
        self.april_tag_visible = False
        self.flip_horizontal = 1
        self.flip_vertical = 1
        self.tag_confidence_threshold = .7
        self.servo_scale = 1
        self.show_frame = 1
        self.servo_speed = 200
        self.reverse_pan = 0
        self.reverse_tilt = 0
        self.prev_x_pixels = None
        self.prev_y_pixels = None
        self.prev_vx_pixels = None
        self.prev_vy_pixels = None

    def update_kalman_filter(self):
        self.kalman.processNoiseCov = np.eye(4, dtype=np.float32) * self.process_noise_cov
        self.kalman.measurementNoiseCov = np.eye(2, dtype=np.float32) * self.measurement_noise_cov

    def activate_relay(self, duration=2):
            GPIO.output(self.relay_pin, GPIO.HIGH)
            time.sleep(duration)
            GPIO.output(self.relay_pin, GPIO.LOW)

    def set_servo_speed(self, servo_id, speed):
        try:
            self.dynamixel_controller.set_speed(servo_id, speed)
        except Exception as e:
            print(f"Failed to set servo speed for servo ID {servo_id}: {e}", flush=True)

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

    def draw_blue_circle(self, frame, centroid):
        center = (int(centroid[0] * frame.shape[1]), int(centroid[1] * frame.shape[0]))
        radius = 10  # Example radius; adjust as necessary
        color = (255, 165, 0)  # RGB for blue
        thickness = 2  # Thickness of the circle outline
        cv2.circle(frame, center, radius, color, thickness)

    def calculate_velocity(self, centroid):
        if self.prev_x_pixels is not None and self.prev_y_pixels is not None:
            velocity = self.coordinate_system.calculate_velocity(centroid[0], centroid[1], self.prev_x_pixels, self.prev_y_pixels, dt=2)
            print(f"Calculated Velocity: {velocity}", flush=True)
            return velocity
        print("Returning None for velocity", flush=True)
        return None, None

    def calculate_centroid(self, detection):
        return tuple(np.float32(val) for val in [(detection.xmax + detection.xmin) / 2, (detection.ymax + detection.ymin) / 2])

    def is_authorized(self, frame, badge_id):
        # Check if badge ID exists in the database
        if badge_id in users.database:
            font = cv2.FONT_HERSHEY_SIMPLEX
            frame_height, frame_width, _ = frame.shape
    
            # Draw the name
            name = users.database[badge_id]["last_name"] + ", " + users.database[badge_id]["first_name"]
            name_font_scale = 1.5  # Adjust this value to change the size of the name text
            name_text_size = cv2.getTextSize(name, font, name_font_scale, 2)[0]
            name_text_x = (frame_width - name_text_size[0]) // 2
            name_text_y = ((frame_height - name_text_size[1]) // 2)
            cv2.putText(frame, name, (name_text_x, name_text_y), font, name_font_scale, (0, 255, 0), 2, cv2.LINE_AA)
    
            # Draw "AUTHORIZED" below the name
            auth_text_size = cv2.getTextSize("AUTHORIZED", font, 2, 2)[0]
            auth_text_x = (frame_width - auth_text_size[0]) // 2
            auth_text_y = ((frame_height - auth_text_size[1]) // 2) + auth_text_size[1] + 40  # added 40 for spacing
            cv2.putText(frame, "AUTHORIZED", (auth_text_x, auth_text_y), font, 2, (0, 255, 0), 2, cv2.LINE_AA)
    
        return frame

    def run(self):
        pan_goal = None
        tilt_goal = None
        last_centroid = None
        last_prediction = None
        last_detection_time = None

        if self.home_position is None:
            print("Error: Home Position is not set", flush=True)
            return

        self.dynamixel_controller.home_servos()

        while True:

            try:
                for frame, detections in self.motion_tracker.run():
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    tags = self.april_detector.detect(gray)

                    # Filter detections based on confidence
                    detections = [d for d in detections if d.confidence >= self.tag_confidence_threshold]
        
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

                        self.is_authorized(frame, tag.tag_id)

                        print(f"Badge Detected: {tag.tag_id}", flush=True)
                        print(f"Type of centroid matrix: {centroid.dtype}", flush=True)
                        print(f"Type of measurementMatrix: {self.kalman.measurementMatrix.dtype}", flush=True)
                        print(f"Dimensions of measurementMatrix: {self.kalman.measurementMatrix.shape}", flush=True)
                        print(f"Dimensions of centroid: {centroid.shape}", flush=True)
                    
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
                        last_detection_timestamp = None
                        last_still_timestamp = None
                    
                        # Predict using Kalman
                        prediction = self.kalman.predict()
                    
                        # If no detections, use the prediction
                        if not detections:
                            centroid = (prediction[0][0], prediction[1][0])
                            self.draw_blue_circle(frame, centroid)
                    
                        # If detections are present
                        elif detections:
                            most_confident_detection = max(detections, key=lambda detection: detection.confidence)
                            print(most_confident_detection)
                    
                            # Update timestamp and correct Kalman filter
                            last_detection_timestamp = time.time()
                            print(f"Last Detection Timestamp: {last_detection_timestamp}")
                            centroid = self.calculate_centroid(most_confident_detection)
                            print(f"centroid: {centroid}")
                            centroid_measurement = np.array([[np.float32(centroid[0])], [np.float32(centroid[1])]])
                            print(f"centroid measurement: {centroid_measurement}")
                            self.kalman.correct(centroid_measurement)
                            print(f"Kalman filter corrected with centroid measurement")

                            pan_goal = self.coordinate_system.image_position_to_servo_goal(
                             1 - centroid[0] if self.reverse_pan else centroid[0], 1,
                             self.dynamixel_controller.PAN_MIN_POSITION,
                             self.dynamixel_controller.PAN_MAX_POSITION
                            ) * self.servo_scale
                            print(f"First Pan Goal: {pan_goal}")
                        
                            tilt_goal = self.coordinate_system.image_position_to_servo_goal(
                             1 - centroid[1] if self.reverse_tilt else centroid[1], 1,
                             self.dynamixel_controller.TILT_MIN_POSITION,
                             self.dynamixel_controller.TILT_MAX_POSITION
                            ) * self.servo_scale
                            print(f"First Tilt Goal: {tilt_goal}")
#                        
#                            self.process_centroid(frame, centroid)
#
                            if pan_goal and tilt_goal:
                                pan_goal = self.clamp_servo_position(pan_goal, self.dynamixel_controller.PAN_MIN_POSITION, self.dynamixel_controller.PAN_MAX_POSITION)
                                tilt_goal = self.clamp_servo_position(tilt_goal, self.dynamixel_controller.TILT_MIN_POSITION, self.dynamixel_controller.TILT_MAX_POSITION)
                                
                                try:
                                    self.dynamixel_controller.set_goal_position_with_pid(pan_goal, tilt_goal + self.tilt_offset)

                                except Exception as e:
                                    print(f"Error: The data value exceeds the limit value. {e}", flush=True)
#
#                            elapsed_time_since_detection = time.time() - last_detection_timestamp if last_detection_timestamp else float('inf')
#                            elapsed_time_still = time.time() - last_still_timestamp if last_still_timestamp else float('inf')
#                            if elapsed_time_still >= 4:
#                                self.draw_red_circle(frame, centroid)
#                            else:
#                                self.draw_centroid(frame, centroid)  # Green dot

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
                print(f"A cv2.error occurred: {e}", flush=True)
                # Decide what to do in case of a cv2 error. For example, you might want to break the loop:
                break
    
            except KeyboardInterrupt:
                print("Interrupted by user", flush=True)
                break
    
            except Exception as e:
                print(f"An unexpected error occurred: {e}", flush=True)
                # Decide what to do in case of a general error. You might want to continue, or you might want to break the loop:
                continue
    
        # Close Dynamixel controller
        self.dynamixel_controller.close()
    
        # Destroy all OpenCV windows
        cv2.destroyAllWindows()
    
if __name__ == "__main__":
    app = Application()
    app.run()
