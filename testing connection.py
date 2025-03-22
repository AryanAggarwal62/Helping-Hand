import cv2
import time
import google.generativeai as genai
import os

# Configure the Gemini API key (load from environment variable for security)
api_key = 'AIzaSyBPbmFaYqeWaioRtk3if_47BH0tgujRjmM'
if not api_key:
    raise ValueError("Please set the GEMINI_API_KEY environment variable.")
genai.configure(api_key=api_key)

# Initialize the Gemini vision model
model = genai.GenerativeModel('gemini-1.5-flash')

# Open the video stream from the ESP32 camera
cap = cv2.VideoCapture('http://172.20.10.2/stream')
if not cap.isOpened():
    print("Error: Could not open video stream.")
    exit()

# Variables for frame processing
frame_count = 0
process_every = 30  # Assuming 30 fps, this processes one frame per second
current_identification = "Waiting for identification..."

# Main loop to process the video stream
while True:
    # Read a frame from the stream
    ret, frame = cap.read()
    if not ret:
        print("Error: Could not read frame.")
        break

    frame_count += 1

    # Process every nth frame (e.g., once per second)
    if frame_count % process_every == 0:
        # Encode the frame to JPEG format
        success, encoded_image = cv2.imencode('.jpg', frame)
        if success:
            image_data = encoded_image.tobytes()

            # Prepare the image part for the Gemini API
            image_part = {
                "mime_type": "image/jpeg",
                "data": image_data
            }

            # Define the prompt for identification
            prompt = "Identify the objects in this image."

            # Send the request to the Gemini API
            try:
                response = model.generate_content([prompt, image_part])
                if response and response.candidates:
                    candidate = response.candidates[0]
                    if candidate.content and candidate.content.parts:
                        current_identification = candidate.content.parts[0].text
            except Exception as e:
                print(f"Error in API call: {e}")

    # Overlay the current identification on the frame
    lines = current_identification.split('\n')
    for i, line in enumerate(lines):
        cv2.putText(
            frame,
            line,
            (10, 30 + i * 30),  # Position: 10 pixels from left, 30 pixels per line
            cv2.FONT_HERSHEY_SIMPLEX,
            1,  # Font scale
            (0, 255, 0),  # Green color in BGR
            2  # Thickness
        )

    # Display the frame with identification
    cv2.imshow('Video Stream', frame)

    # Exit on 'q' key press
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Cleanup: release the capture and close windows
cap.release()
cv2.destroyAllWindows()
