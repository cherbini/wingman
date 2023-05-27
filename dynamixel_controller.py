import dynamixel_sdk as sdk
import time

class DynamixelController:

    # Define valid ranges for PAN and TILT servos
    PAN_MIN_POSITION = 648  # Adjust as needed
    PAN_MAX_POSITION = 2448  # Adjust as needed
    TILT_MIN_POSITION = 648  # Adjust as needed
    TILT_MAX_POSITION = 2548  # Adjust as needed

    def __init__(self, device_port, baudrate, pan_servo_id, tilt_servo_id):
        # Protocol version
        self.PROTOCOL_VERSION = 2.0

        # Default setting
        self.DEVICE_PORT = device_port
        self.BAUDRATE = baudrate
        self.PAN_SERVO_ID = pan_servo_id
        self.TILT_SERVO_ID = tilt_servo_id

        # Control table address for Protocol 2.0 (MX series)
        self.ADDR_MX_TORQUE_ENABLE = 64
        self.ADDR_MX_GOAL_POSITION = 116
        self.LEN_GOAL_POSITION = 4  # Data Byte Length
        self.ADDR_MX_PRESENT_POSITION = 132
        self.LEN_PRESENT_POSITION = 4  # Data Byte Length

        # Communication result
        self.COMM_SUCCESS = sdk.COMM_SUCCESS
        self.COMM_TX_FAIL = sdk.COMM_TX_FAIL

        # Initialize PortHandler instance
        self.portHandler = sdk.PortHandler(self.DEVICE_PORT)

        # Initialize PacketHandler instance
        self.packetHandler = sdk.PacketHandler(self.PROTOCOL_VERSION)

        # Open port
        if not self.portHandler.openPort():
            raise Exception("Failed to open the Dynamixel port")

        # Set port baudrate
        if not self.portHandler.setBaudRate(self.BAUDRATE):
            raise Exception("Failed to set the Dynamixel baudrate")

        # Enable Dynamixel torque
        self.set_torque(self.PAN_SERVO_ID, True)
        self.set_torque(self.TILT_SERVO_ID, True)

        # Initialize GroupSyncWrite instance
        self.groupSyncWrite = sdk.GroupSyncWrite(self.portHandler, self.packetHandler, self.ADDR_MX_GOAL_POSITION, self.LEN_GOAL_POSITION)

        # Initialize GroupSyncRead instance
        self.groupSyncRead = sdk.GroupSyncRead(self.portHandler, self.packetHandler, self.ADDR_MX_PRESENT_POSITION, self.LEN_PRESENT_POSITION)
        self.groupSyncRead.addParam(self.PAN_SERVO_ID)
        self.groupSyncRead.addParam(self.TILT_SERVO_ID)

    def set_torque(self, servo_id, enable):
        dxl_comm_result, dxl_error = self.packetHandler.write1ByteTxRx(
            self.portHandler, servo_id, self.ADDR_MX_TORQUE_ENABLE, int(enable)
        )
        if dxl_comm_result != self.COMM_SUCCESS:
            raise Exception("Error occurred while enabling/disabling torque")
    # Clamp servo position to the valid range
    @staticmethod
    def clamp_servo_position(position, min_position, max_position):
        return max(min(position, max_position), min_position)



    def set_goal_position(self, servo_id, goal_position):
        # Check if servo_id is PAN or TILT and clamp goal_position accordingly
        if servo_id == self.PAN_SERVO_ID:
            goal_position = self.clamp_servo_position(goal_position, self.PAN_MIN_POSITION, self.PAN_MAX_POSITION)
        elif servo_id == self.TILT_SERVO_ID:
            goal_position = self.clamp_servo_position(goal_position, self.TILT_MIN_POSITION, self.TILT_MAX_POSITION)

        # Ensure goal_position is within valid range [0, 4095]
        goal_position = min(max(goal_position, 0), 4095)

        # Allocate goal position values into byte array for servo
        param_goal_position = [
            goal_position & 0xFF,
            (goal_position >> 8) & 0xFF,
            (goal_position >> 16) & 0xFF,
            (goal_position >> 24) & 0xFF
        ]

        # Add goal position value for servo
        self.groupSyncWrite.addParam(servo_id, param_goal_position)

        # Execute SyncWrite
        dxl_comm_result = self.groupSyncWrite.txPacket()
        if dxl_comm_result != self.COMM_SUCCESS:
            raise Exception("Error occurred while setting goal position")

        # Clear syncwrite parameter storage
        self.groupSyncWrite.clearParam()

    def get_present_position(self):
        # Syncread present position
        dxl_comm_result = self.groupSyncRead.txRxPacket()
        if dxl_comm_result != self.COMM_SUCCESS:
            raise Exception("Error occurred while reading present position")
    
        # Get pan servo present position value
        pan_present_position = self.groupSyncRead.getData(self.PAN_SERVO_ID, self.ADDR_MX_PRESENT_POSITION, self.LEN_PRESENT_POSITION)
    
        # Get tilt servo present position value
        tilt_present_position = self.groupSyncRead.getData(self.TILT_SERVO_ID, self.ADDR_MX_PRESENT_POSITION, self.LEN_PRESENT_POSITION)
    
        return pan_present_position, tilt_present_position


    def close(self):
        # Disable Dynamixel torque
        self.set_torque(self.PAN_SERVO_ID, False)
        self.set_torque(self.TILT_SERVO_ID, False)

        # Close port
        self.portHandler.closePort()


    def servo_test(self):
        # Define the square path for the servos
        pan_offset = 1000
        tilt_offset = 1000
        pan_positions = [2048, 2048 + pan_offset, 2048 + pan_offset, 2048 - pan_offset, 2048 - pan_offset, 2048]
        tilt_positions = [2048, 2048, 2048 + tilt_offset, 2048 + tilt_offset, 2048 - tilt_offset, 2048]

        # Move the servos in the square path
        for pan_pos, tilt_pos in zip(pan_positions, tilt_positions):
            self.set_goal_position(self.PAN_SERVO_ID, pan_pos)
            self.set_goal_position(self.TILT_SERVO_ID, tilt_pos)
            time.sleep(1)  # Wait for 1 second for each move

# Usage example
if __name__ == "__main__":
    # Parameters: device port, baud rate, pan servo ID, tilt servo ID
    dynamixel_controller = DynamixelController("/dev/ttyDXL", 1000000, 1, 2)

    # Perform servo test
    dynamixel_controller.servo_test()

    # Close and release resources
    dynamixel_controller.close()
