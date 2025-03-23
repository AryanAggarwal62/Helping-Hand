import cv2
import time
import numpy as np
import requests
import colorgeneratorfromaudio
from colorgeneratorfromaudio import run

# color bounds from colorgeneratorfromaudio file
colours = run()

# ESP32 URLs
camera_url = "http://172.20.10.2/stream"
control_url = "http://172.20.10.2/move"

# open the video stream and retry if it fails
max_attempts = 3
cap = None  # Initialize cap
for attempt in range(max_attempts):
    cap = cv2.VideoCapture(camera_url)
    if cap.isOpened():
        print(f"✅ Connected to ESP32 camera stream on attempt {attempt + 1}")
        break
    else:
        print(f"❌ Connection failed on attempt {attempt + 1}/{max_attempts}. Retrying in 5 seconds...")
        time.sleep(5)
else:
    print("❌ All connection attempts failed. Exiting.")
    exit()

time.sleep(1)

# AprilTag detector
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
parameters = cv2.aruco.DetectorParameters()
parameters.minMarkerPerimeterRate = 0.03  # Allow smaller markers
parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX  # Improve accuracy
detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)

# Color ranges for object, using color given by audio
lower_red1 = np.array(colours[0])    # Bright reds: lower bound
upper_red1 = np.array(colours[1])    # Bright reds: upper bound
lower_red2 = np.array(colours[2])    # Dark reds: lower bound
upper_red2 = np.array(colours[3])    # Dark reds: upper bound

# Table grid settings
table_width_cm = 50  # Table width in cm (sideways)
table_height_cm = 23  # Table height in cm (forwards)
camera_width_px = 320  # Camera resolution width
camera_height_px = 240  # Camera resolution height
px_to_cm_x = table_width_cm / camera_width_px  # 50cm / 320px ≈ 0.15625cm/px
px_to_cm_y = table_height_cm / camera_height_px  # 23cm / 240px ≈ 0.09583cm/px

# Detection threshold for red object
min_red_area = 500  # Minimum contour area (pixels)

# Timing settings
process_interval = 0.5  # Process frames every 0.5 seconds
command_cooldown = 2.0  # Send commands every 2 seconds
tolerance_cm = 1.0  # Only send if distance > 1cm
last_process_time = 0
last_command_time = 0

while True:
    # Grab the latest frame
    for _ in range(5):  # Read a few frames
        cap.grab()
    ret, frame = cap.read()
    if not ret:
        print("❌ Failed to grab frame from stream.")
        break

    current_time = time.time()

    # processing loop
    if current_time - last_process_time >= process_interval:
        # Detect AprilTags
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, rejected = detector.detectMarkers(gray)
        april_x_px, april_y_px, april_x_cm, april_y_cm = 0, 0, 0.0, 0.0
        april_detected = False

        if ids is not None and len(ids) > 0:
            corner = corners[0][0]
            x_min, y_min = corner.min(axis=0)
            x_max, y_max = corner.max(axis=0)
            april_x_px = int((x_min + x_max) / 2)
            april_y_px = int((y_min + y_max) / 2)
            april_x_cm = april_x_px * px_to_cm_x
            april_y_cm = april_y_px * px_to_cm_y
            april_detected = True
            cv2.aruco.drawDetectedMarkers(frame, corners, ids, (0, 255, 0))
            cv2.putText(frame, f"Tag {ids[0][0]}: ({april_x_cm:.1f}, {april_y_cm:.1f}) cm",
                        (april_x_px - 20, april_y_px - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Detect object
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
        mask = cv2.bitwise_or(mask1, mask2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        red_x_px, red_y_px, red_x_cm, red_y_cm = 160, 120, 25.0, 11.5
        red_detected = False

        if contours:
            largest_contour = max(contours, key=cv2.contourArea)
            contour_area = cv2.contourArea(largest_contour)
            if contour_area >= min_red_area:
                x, y, w, h = cv2.boundingRect(largest_contour)
                red_x_px = x + w // 2
                red_y_px = y + h // 2
                red_x_cm = red_x_px * px_to_cm_x
                red_y_cm = red_y_px * px_to_cm_y
                red_detected = True
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
                cv2.putText(frame, f"Red: ({red_x_cm:.1f}, {red_y_cm:.1f}) cm",
                            (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

        # Calculate distance if april tag and object are detected
        delta_x_cm, delta_y_cm = 0.0, 0.0
        move_commands = {"delta_x_cm": 0.0, "delta_y_cm": 0.0}
        if april_detected and red_detected:
            delta_x_px = red_x_px - april_x_px
            delta_y_px = red_y_px - april_y_px
            delta_x_cm = delta_x_px * px_to_cm_x
            delta_y_cm = delta_y_px * px_to_cm_y
            move_commands = {
                "delta_x_cm": round(delta_x_cm, 1),
                "delta_y_cm": round(delta_y_cm, 1)
            }

        # Log detection status
        if april_detected:
            print(f"AprilTag: ({april_x_cm:.1f}, {april_y_cm:.1f}) cm")
        else:
            print("No AprilTags detected.")
        if red_detected:
            print(f"Red: ({red_x_cm:.1f}, {red_y_cm:.1f}) cm")
        else:
            print("No red object detected.")
        if april_detected and red_detected:
            print(f"Move: ({delta_x_cm:.1f}, {delta_y_cm:.1f}) cm, Commands: {move_commands}")
        else:
            print("Move: Waiting for both AprilTag and red object to be detected.")

        # Send commands only if both are detected
        if (april_detected and red_detected and
            current_time - last_command_time >= command_cooldown and
            (abs(delta_x_cm) > tolerance_cm or abs(delta_y_cm) > tolerance_cm)):
            try:
                response = requests.post(
                    control_url,
                    json=move_commands,
                    headers={"Content-Type": "application/json"},
                    timeout=5
                )
                if response.status_code == 200:
                    print(f"✅ Sent to ESP32: {move_commands} -> {response.text}")
                    last_command_time = current_time
                else:
                    print(f"❌ Failed to send. Status: {response.status_code}")
            except requests.RequestException as e:
                print(f"❌ Request error: {e}")

        last_process_time = current_time

    # Display status
    cv2.putText(frame, f"AprilTag: {'Detected' if april_detected else 'Not Detected'}", (10, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    cv2.putText(frame, f"Red: {'Detected' if red_detected else 'Not Detected'}", (10, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    cv2.putText(frame, f"Move: ({delta_x_cm:.1f}, {delta_y_cm:.1f}) cm", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

    # Display frame
    cv2.imshow('Video Stream', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Cleanup
cap.release()
cv2.destroyAllWindows()
