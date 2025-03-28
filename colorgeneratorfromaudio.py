import os
import pyaudio
import time
from google.cloud import speech_v1p1beta1 as speech
import cohere
import numpy as np

# Retrieve credentials from environment variables
google_credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if not google_credentials_path:
    raise EnvironmentError("Please set the GOOGLE_APPLICATION_CREDENTIALS environment variable with the path to your Google Cloud service account JSON file.")

cohere_api_key = os.getenv("COHERE_API_KEY")
if not cohere_api_key:
    raise EnvironmentError("Please set the COHERE_API_KEY environment variable with your Cohere API key.")

# Set up the Speech Client using credentials from environment variables
client = speech.SpeechClient.from_service_account_json(google_credentials_path)

# Set up the Cohere Client using the API key from environment variables
co = cohere.Client(cohere_api_key)

# Define 10 common colors with HSV bounds
COLOR_RANGES = {
    "red": [
        np.array([0, 120, 70]),
        np.array([10, 255, 255]),
        np.array([170, 120, 70]),
        np.array([180, 255, 255])
    ],
    "blue": [
        np.array([100, 150, 0]),
        np.array([140, 255, 255]),
        np.array([100, 100, 0]),
        np.array([130, 255, 200])
    ],
    "green": [
        np.array([35, 100, 50]),
        np.array([85, 255, 255]),
        np.array([35, 50, 20]),
        np.array([85, 255, 200])
    ],
    "yellow": [
        np.array([20, 100, 100]),
        np.array([35, 255, 255]),
        np.array([20, 100, 100]),
        np.array([30, 255, 200])
    ],
    "purple": [
        np.array([130, 50, 50]),
        np.array([160, 255, 255]),
        np.array([125, 50, 50]),
        np.array([155, 255, 200])
    ],
    "orange": [
        np.array([10, 100, 20]),
        np.array([25, 255, 255]),
        np.array([10, 100, 20]),
        np.array([20, 255, 200])
    ],
    "pink": [
        np.array([160, 50, 100]),
        np.array([170, 255, 255]),
        np.array([150, 50, 80]),
        np.array([170, 255, 180])
    ],
    "brown": [
        np.array([10, 100, 20]),
        np.array([20, 255, 200]),
        np.array([10, 150, 10]),
        np.array([20, 255, 150])
    ],
    "white": [
        np.array([0, 0, 200]),
        np.array([180, 30, 255]),
        np.array([0, 0, 180]),
        np.array([180, 50, 255])
    ],
    "black": [
        np.array([0, 0, 0]),
        np.array([180, 255, 50]),
        np.array([0, 0, 0]),
        np.array([180, 255, 30])
    ]
}

# Configure streaming recognition
streaming_config = speech.StreamingRecognitionConfig(
    config=speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="en-US"
    ),
    interim_results=False
)

# Set up PyAudio for microphone input
p = pyaudio.PyAudio()
stream = p.open(
    format=pyaudio.paInt16,
    channels=1,
    rate=16000,
    input=True,
    frames_per_buffer=1024
)

# Define a generator to stream audio data
def audio_stream_generator():
    start_time = time.time()
    duration = 5  # 5 seconds for speed
    while time.time() - start_time < duration:
        data = stream.read(1024)
        yield speech.StreamingRecognizeRequest(audio_content=data)

# Extract color using Cohere
def extract_color(text):
    prompt = (
        f"Extract the color from this sentence: '{text}'. "
        f"Return only the color name (e.g., 'red', 'blue') or 'none' if no color is found. "
        f"Do not include any extra text."
    )
    response = co.generate(
        model='command',
        prompt=prompt,
        max_tokens=10,  # Small output, just the color
        temperature=0.1  # Precise output
    )
    color = response.generations[0].text.strip().lower()
    return color if color in COLOR_RANGES else "none"

# Process streaming recognition and extract color
def run():
    try:
        print("Listening to microphone... Speak now!")
        responses = client.streaming_recognize(
            config=streaming_config,
            requests=audio_stream_generator()
        )
        final_transcript = None
        for response in responses:
            for result in response.results:
                if result.is_final:
                    if final_transcript is None:  # Take first final transcript
                        print("Final transcript: {}".format(result.alternatives[0].transcript))
                        final_transcript = result.alternatives[0].transcript

        # Extract color and get bounds
        if final_transcript:
            color = extract_color(final_transcript)
            color_bounds = COLOR_RANGES.get(color, [np.array([0, 0, 0]), np.array([0, 0, 0]), np.array([0, 0, 0]), np.array([0, 0, 0])])
            print(f"Extracted color: {color}")
            print("Color bounds:", [bound.tolist() for bound in color_bounds])
            return [bound.tolist() for bound in color_bounds]
        else:
            print("No final transcript captured.")

    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
        print("Stopped listening.")

if __name__ == "__main__":
    run()
