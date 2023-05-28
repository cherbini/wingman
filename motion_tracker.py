# File: motion_tracker.py

import depthai as dai
import numpy as np
import time
import cv2

class MotionTracker:
    def __init__(self, nnPath):
        # Define class constants
        self.SYNC_NN = True
        self.NN_LABELS = [
            "person" 
            ]
        # Initialize pipeline
        self.pipeline = dai.Pipeline()

        # Define sources and outputs
        self.camRgb = self.pipeline.create(dai.node.ColorCamera)
        self.detectionNetwork = self.pipeline.create(dai.node.YoloDetectionNetwork)
        self.xoutRgb = self.pipeline.create(dai.node.XLinkOut)
        self.nnOut = self.pipeline.create(dai.node.XLinkOut)

        self.xoutRgb.setStreamName("rgb")
        self.nnOut.setStreamName("nn")

        # Properties
        self.camRgb.setPreviewSize(416, 416)
        self.camRgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
        self.camRgb.setInterleaved(False)
        self.camRgb.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
        self.camRgb.setFps(40)

        # Network specific settings
        self.detectionNetwork.setConfidenceThreshold(0.5)
        self.detectionNetwork.setNumClasses(80)
        self.detectionNetwork.setCoordinateSize(4)
        self.detectionNetwork.setAnchors([10, 14, 23, 27, 37, 58, 81, 82, 135, 169, 344, 319])
        self.detectionNetwork.setAnchorMasks({"side26": [1, 2, 3], "side13": [3, 4, 5]})
        self.detectionNetwork.setIouThreshold(0.5)
        self.detectionNetwork.setBlobPath(nnPath)
        self.detectionNetwork.setNumInferenceThreads(2)
        self.detectionNetwork.input.setBlocking(False)

        # Linking
        self.camRgb.preview.link(self.detectionNetwork.input)
        if self.SYNC_NN:
            self.detectionNetwork.passthrough.link(self.xoutRgb.input)
        else:
            self.camRgb.preview.link(self.xoutRgb.input)

        self.detectionNetwork.out.link(self.nnOut.input)


    def run(self):
        # Connect to device and start pipeline
        with dai.Device(self.pipeline) as device:
            # Output queues will be used to get the rgb frames and nn data from the outputs defined above
            qRgb = device.getOutputQueue(name="rgb", maxSize=4, blocking=False)
            qDet = device.getOutputQueue(name="nn", maxSize=4, blocking=False)

            frame = None
            detections = []
            startTime = time.monotonic()
            counter = 0
            color2 = (255, 255, 255)

            # nn data, being the bounding box locations, are in <0..1> range - they need to be normalized with frame width/height
            def frameNorm(frame, bbox):
                normVals = np.full(len(bbox), frame.shape[0])
                normVals[::2] = frame.shape[1]
                return (np.clip(np.array(bbox), 0, 1) * normVals).astype(int)

            while True:
                if self.SYNC_NN:
                    inRgb = qRgb.get()
                    inDet = qDet.get()
                else:
                    inRgb = qRgb.tryGet()
                    inDet = qDet.tryGet()

                if inRgb is not None:
                    frame = inRgb.getCvFrame()
                    cv2.putText(frame, "NN fps: {:.2f}".format(counter / (time.monotonic() - startTime)),
                                (2, frame.shape[0] - 1), cv2.FONT_HERSHEY_TRIPLEX, 0.4, color2)

                if inDet is not None:
                    detections = inDet.detections
                    counter += 1

                if frame is not None:
                    yield frame, detections

if __name__ == "__main__":
    motion_tracker = MotionTracker('yolo-v4-tiny-tf_openvino_2021.4_6shave.blob')
    for frame, detections in motion_tracker.run():
        # Do something with frame and detections
        pass
