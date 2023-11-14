# Importing required libraries
import depthai as dai
import numpy as np
import time
import cv2
import zmq
import argparse

# Argument parser for FPS
parser = argparse.ArgumentParser()
parser.add_argument('--fps', type=int, default=60, help="FPS to set for the server's camera feed")
args = parser.parse_args()

# ZeroMQ setup
context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind("tcp://*:5555")
responder = context.socket(zmq.REP)
responder.bind("tcp://*:5556")

class MotionTracker:
    def __init__(self, nnPath):
        self.SYNC_NN = True
        self.NN_LABELS = ["person"]
        self.pipeline = dai.Pipeline()

        # Setup camera and neural network
        self.camRgb = self.pipeline.create(dai.node.ColorCamera)
        self.detectionNetwork = self.pipeline.create(dai.node.YoloDetectionNetwork)
        self.xoutRgb = self.pipeline.create(dai.node.XLinkOut)
        self.nnOut = self.pipeline.create(dai.node.XLinkOut)

        self.xoutRgb.setStreamName("rgb")
        self.nnOut.setStreamName("nn")

        # Camera properties
        self.camRgb.setPreviewSize(416, 416)
        self.camRgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
        self.camRgb.setInterleaved(False)
        self.camRgb.setIspScale(1, 3)
        self.camRgb.setPreviewKeepAspectRatio(False)
        self.camRgb.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)

        # Neural network properties
        self.detectionNetwork.setConfidenceThreshold(0.8)
        self.detectionNetwork.setBlobPath(nnPath)
        self.detectionNetwork.input.setBlocking(False)

        # Linking
        self.camRgb.preview.link(self.detectionNetwork.input)
        self.detectionNetwork.passthrough.link(self.xoutRgb.input)
        self.detectionNetwork.out.link(self.nnOut.input)

    def frameNorm(self, frame, bbox):
        normVals = np.full(len(bbox), frame.shape[0])
        normVals[::2] = frame.shape[1]
        return (np.clip(np.array(bbox), 0, 1) * normVals).astype(int)

    def run(self):
        with dai.Device(self.pipeline) as device:
            qRgb = device.getOutputQueue(name="rgb", maxSize=4, blocking=False)
            qDet = device.getOutputQueue(name="nn", maxSize=4, blocking=False)

            frame = None
            detections = []

            while True:
                inRgb = qRgb.get()
                inDet = qDet.get()

                if inRgb is not None:
                    frame = inRgb.getCvFrame()
                
                if inDet is not None:
                    detections = inDet.detections

                if frame is not None:
                    for detection in detections:
                        bbox = self.frameNorm(frame, [detection.xmin, detection.ymin, detection.xmax, detection.ymax])
                        cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)

                    ret, compressed_frame = cv2.imencode('.jpg', frame)
                    socket.send_pyobj({
                        "type": "frame_data",
                        "frame": compressed_frame.tobytes(),
                        "detections": detections,
                        "send_timestamp": time.time()
                    })

                    # Listen for a time sync request from the client
                    try:
                        message = responder.recv_pyobj(flags=zmq.NOBLOCK)  # Non-blocking receive
                        if message and message["type"] == "client_time_sync":
                            responder.send_pyobj({
                                "type": "server_time_sync",
                                "client_timestamp": message["client_timestamp"],
                                "server_timestamp": time.time()
                            })
                    except zmq.Again:
                        pass  # No message received, continue

if __name__ == "__main__":
    motion_tracker = MotionTracker('yolo-v4-tiny-tf_openvino_2021.4_6shave.blob')
    motion_tracker.run()


