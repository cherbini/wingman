import depthai as dai
import cv2
import apriltag

# Initialize AprilTag detector
detector = apriltag.Detector()

# Initialize Luxonis OAK-1-MAX pipeline
pipeline = dai.Pipeline()
cam = pipeline.createColorCamera()
cam.setPreviewSize(640, 480)
cam.setInterleaved(False)
cam.setFps(30)

# Define output stream
xout = pipeline.createXLinkOut()
xout.setStreamName("preview")
cam.preview.link(xout.input)

# Create device and start the pipeline
device = dai.Device(pipeline)
preview_queue = device.getOutputQueue(name="preview", maxSize=1, blocking=False)

while True:
    # Get the current frame from the camera
    frame = preview_queue.get().getCvFrame()

    # Convert frame to grayscale
    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Detect AprilTags in the grayscale frame
    detections = detector.detect(gray_frame)

    # Print detected AprilTags information
    for detection in detections:
        print(f"Detected AprilTag: ID {detection.tag_id}, Center ({detection.center[0]}, {detection.center[1]})")

    # Display the frame with AprilTag detections (optional)
    for detection in detections:
        cv2.circle(frame, tuple(detection.center.astype(int)), 4, (0, 255, 0), 2)
        cv2.putText(frame, str(detection.tag_id), tuple(detection.center.astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    cv2.imshow('Preview', frame)

    # Exit the loop if 'q' key is pressed
    if cv2.waitKey(1) == ord('q'):
        break

# Clean up
cv2.destroyAllWindows()
device.close()
device = None

