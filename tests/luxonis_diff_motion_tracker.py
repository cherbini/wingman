import cv2
import depthai as dai

# Initialize pipeline
pipeline = dai.Pipeline()

# Define sources and outputs
camRgb = pipeline.create(dai.node.ColorCamera)
xoutRgb = pipeline.create(dai.node.XLinkOut)
xoutRgb.setStreamName("rgb")
camRgb.video.link(xoutRgb.input)

# Properties
camRgb.setPreviewSize(416, 416)
camRgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_4_K)
camRgb.setInterleaved(False)
camRgb.setIspScale(1, 3)
camRgb.setPreviewKeepAspectRatio(False)
camRgb.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
camRgb.setFps(15)

# Create the device and start the pipeline
device = dai.Device(pipeline)

# Get the video queue
queue = device.getOutputQueue(name="rgb", maxSize=8, blocking=False)

# Initialize frame difference variables
prev_frame = None
frame_diff = None

# Desired display size for the difference frame
display_width = 320
display_height = 240

while True:
    frame_data = queue.get()
    frame = frame_data.getCvFrame()

    if prev_frame is not None:
        # Compute the absolute difference between the current frame and the previous frame
        frame_diff = cv2.absdiff(prev_frame, frame)

        # Resize the difference frame
        frame_diff_resized = cv2.resize(frame_diff, (display_width, display_height))

        # Flip the resized difference frame (horizontal flip)
        frame_diff_flipped = cv2.flip(frame_diff_resized, 1)

        # Display the frame difference
        cv2.imshow("Frame Difference", frame_diff_flipped)

    # Update the previous frame
    prev_frame = frame.copy()

    # Break the loop if 'q' key is pressed
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cv2.destroyAllWindows()

