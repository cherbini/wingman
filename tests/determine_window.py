import dynamixel_sdk as sdk
import time
from dynamixel_controller import DynamixelController 

def manual_position_check():
    # Parameters: device port, baud rate, pan servo ID, tilt servo ID
    dynamixel_controller = DynamixelController("/dev/ttyDXL", 1000000, 1, 2)
    
    # Disable torque so servos can be moved manually
    dynamixel_controller.set_torque(dynamixel_controller.PAN_SERVO_ID, False)
    dynamixel_controller.set_torque(dynamixel_controller.TILT_SERVO_ID, False)

    print("Move the PAN and TILT servos to desired position manually...")
    input("Press ENTER once you've set the position...")

    # Read the present position after manually adjusting
    pan_position, tilt_position = dynamixel_controller.get_present_position()
    print(f"PAN servo position: {pan_position}")
    print(f"TILT servo position: {tilt_position}")

    # Close and release resources
    dynamixel_controller.close()

if __name__ == "__main__":
    manual_position_check()






